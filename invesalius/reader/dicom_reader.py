# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------
import os
import sys
import wx
import time

import gdcm

# Not showing GDCM warning and debug messages
try:
    gdcm.Trace_DebugOff()
    gdcm.Trace_WarningOff()
except AttributeError:
    pass


from vtkmodules.vtkCommonCore import vtkFileOutputWindow, vtkOutputWindow

import invesalius.constants as const
import invesalius.reader.dicom as dicom
import invesalius.reader.dicom_grouper as dicom_grouper
import invesalius.utils as utils
import invesalius.data.imagedata_utils as iu
from invesalius import inv_paths
from invesalius.data import imagedata_utils
from invesalius.pubsub import pub as Publisher

# Import enhanced logging and error handling
from invesalius.enhanced_logging import get_logger
from invesalius.error_handling import handle_errors, DicomError, ErrorCategory, ErrorSeverity

# Initialize logger
logger = get_logger("reader.dicom_reader")

# Try to import vtkGDCMImageReader, but provide a fallback if it fails
try:
    from vtkmodules.vtkIOImage import vtkGDCMImageReader
    HAS_VTK_GDCM = True
    logger.info("Successfully imported vtkGDCMImageReader")
except ImportError:
    HAS_VTK_GDCM = False
    logger.warning("vtkGDCMImageReader not available, using fallback mechanisms for DICOM reading")

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
        logger.warning("win32api module not found, using regular paths")
else:
    _has_win32api = False


@handle_errors(
    error_message="Error selecting larger DICOM group",
    category=ErrorCategory.DICOM,
    severity=ErrorSeverity.ERROR,
    reraise=False
)
def SelectLargerDicomGroup(patient_groups):
    """
    Select the larger DICOM group from a list of patient groups.
    Returns the group with the most files.
    """
    try:
        if not patient_groups:
            logger.error("No patient groups to select from")
            return None
            
        # Find the largest group (the one with most files)
        largest_group = None
        max_files = 0
        
        for patient in patient_groups:
            for study in patient.GetStudies():
                for series in study.GetSeries():
                    series_files = len(series.GetDicomSeries().GetList())
                    if series_files > max_files:
                        max_files = series_files
                        largest_group = series
        
        if largest_group:
            logger.info(f"Selected largest DICOM group with {max_files} files")
            return largest_group
        else:
            logger.warning("No valid DICOM groups found")
            return None
            
    except Exception as e:
        logger.error(f"Error selecting larger DICOM group: {str(e)}")
        return None


@handle_errors(
    error_message="Error sorting DICOM files",
    category=ErrorCategory.GENERAL, 
    severity=ErrorSeverity.ERROR,
    reraise=False
)
def SortFiles(filelist, dicom):
    # Sort slices
    # FIXME: Coronal Crash. necessary verify
    # if (dicom.image.orientation_label != "CORONAL"):
    ##Organize reversed image
    sorter = gdcm.IPPSorter()
    sorter.SetComputeZSpacing(True)
    sorter.SetZSpacingTolerance(1e-10)
    sorter.Sort(filelist)

    # Getting organized image
    filelist = sorter.GetFilenames()
    logger.debug(f"Sorted {len(filelist)} DICOM files")

    return filelist


tag_labels = {}
main_dict = {}
dict_file = {}


class DicomFileLoader:
    def __init__(self, grouper, filepath):
        self.grouper = grouper
        self.filepath = utils.decode(filepath, const.FS_ENCODE)
        try:
            logger.debug(f"Starting to process DICOM file: {self.filepath}")
            self.run()
        except Exception as e:
            logger.error(f"Error loading DICOM file {self.filepath}: {str(e)}")

    @handle_errors(
        error_message="Error loading DICOM file",
        category=ErrorCategory.DICOM, 
        severity=ErrorSeverity.ERROR,
        reraise=False
    )
    def run(self):
        grouper = self.grouper
        reader = gdcm.ImageReader()
        
        logger.debug(f"Loading DICOM file: {self.filepath}")
        
        if _has_win32api:
            try:
                reader.SetFileName(
                    utils.encode(win32api.GetShortPathName(self.filepath), const.FS_ENCODE)
                )
            except TypeError:
                reader.SetFileName(win32api.GetShortPathName(self.filepath))
        else:
            try:
                reader.SetFileName(utils.encode(self.filepath, const.FS_ENCODE))
            except TypeError:
                reader.SetFileName(self.filepath)
                
        if reader.Read():
            file = reader.GetFile()
            # Retrieve data set
            dataSet = file.GetDataSet()
            # Retrieve header
            header = file.GetHeader()
            stf = gdcm.StringFilter()
            stf.SetFile(file)

            data_dict = {}

            tag = gdcm.Tag(0x0008, 0x0005)
            ds = reader.GetFile().GetDataSet()
            image_helper = gdcm.ImageHelper()
            data_dict["spacing"] = image_helper.GetSpacingValue(reader.GetFile())
            if ds.FindDataElement(tag):
                data_element = ds.GetDataElement(tag)
                if data_element.IsEmpty():
                    encoding_value = "ISO_IR 100"
                else:
                    encoding_value = str(ds.GetDataElement(tag).GetValue()).split("\\")[0]

                if encoding_value.startswith("Loaded"):
                    encoding = "ISO_IR 100"
                else:
                    try:
                        encoding = const.DICOM_ENCODING_TO_PYTHON[encoding_value]
                    except KeyError:
                        encoding = "ISO_IR 100"
                        logger.warning(f"Unknown DICOM encoding: {encoding_value}, using default")
            else:
                encoding = "ISO_IR 100"

            # Iterate through the Header
            iterator = header.GetDES().begin()
            while not iterator.equal(header.GetDES().end()):
                dataElement = iterator.next()
                if not dataElement.IsUndefinedLength():
                    tag = dataElement.GetTag()
                    data = stf.ToStringPair(tag)
                    stag = tag.PrintAsPipeSeparatedString()

                    group = str(tag.GetGroup())
                    field = str(tag.GetElement())

                    tag_labels[stag] = data[0]

                    if group not in data_dict.keys():
                        data_dict[group] = {}

                    if not (utils.VerifyInvalidPListCharacter(data[1])):
                        data_dict[group][field] = utils.decode(data[1], encoding)
                    else:
                        data_dict[group][field] = "Invalid Character"

            # Iterate through the Data set
            iterator = dataSet.GetDES().begin()
            while not iterator.equal(dataSet.GetDES().end()):
                dataElement = iterator.next()
                if not dataElement.IsUndefinedLength():
                    tag = dataElement.GetTag()
                    #  if (tag.GetGroup() == 0x0009 and tag.GetElement() == 0x10e3) \
                    #  or (tag.GetGroup() == 0x0043 and tag.GetElement() == 0x1027):
                    #  continue
                    data = stf.ToStringPair(tag)
                    stag = tag.PrintAsPipeSeparatedString()

                    group = str(tag.GetGroup())
                    field = str(tag.GetElement())

                    tag_labels[stag] = data[0]

                    if group not in data_dict.keys():
                        data_dict[group] = {}

                    if not (utils.VerifyInvalidPListCharacter(data[1])):
                        data_dict[group][field] = utils.decode(data[1], encoding, "replace")
                    else:
                        data_dict[group][field] = "Invalid Character"

            # -------------- To Create DICOM Thumbnail -----------

            try:
                data = data_dict[str(0x028)][str(0x1050)]
                level = [float(value) for value in data.split("\\")][0]
                data = data_dict[str(0x028)][str(0x1051)]
                window = [float(value) for value in data.split("\\")][0]
            except (KeyError, ValueError):
                level = None
                window = None
                logger.debug("No window/level found in DICOM header")

            img = reader.GetImage()
            thumbnail_path = imagedata_utils.create_dicom_thumbnails(img, window, level)

            # ------ Verify the orientation --------------------------------

            direc_cosines = img.GetDirectionCosines()
            orientation = gdcm.Orientation()
            try:
                _type = orientation.GetType(tuple(direc_cosines))
            except TypeError:
                _type = orientation.GetType(direc_cosines)
            label = orientation.GetLabel(_type)
            logger.debug(f"DICOM orientation: {label}")

            # ----------   Refactory --------------------------------------
            data_dict["invesalius"] = {"orientation_label": label}

            # -------------------------------------------------------------
            dict_file[self.filepath] = data_dict

            # ----------  Verify is DICOMDir -------------------------------
            is_dicom_dir = 1
            try:
                if data_dict[str(0x002)][str(0x002)] != "1.2.840.10008.1.3.10":  # DICOMDIR
                    is_dicom_dir = 0
            except KeyError:
                is_dicom_dir = 0

            if not (is_dicom_dir):
                try:
                    parser = dicom.Parser()
                    parser.SetDataImage(dict_file[self.filepath], self.filepath, thumbnail_path)

                    dcm = dicom.Dicom()
                    # self.l.acquire()
                    dcm.SetParser(parser)
                    grouper.AddFile(dcm)
                    logger.info(f"Successfully added DICOM file to grouper: {self.filepath}")
                    # Try to log current count of files in grouper
                    try:
                        file_count = len(grouper.GetPatientsGroups())
                        logger.info(f"Current patient groups in grouper: {file_count}")
                    except Exception as e:
                        logger.debug(f"Could not get patient group count: {str(e)}")
                    # self.l.release()
                except Exception as e:
                    logger.error(f"Error processing DICOM file {self.filepath}: {str(e)}")
            else:
                logger.info(f"Skipping DICOMDIR file: {self.filepath}")
        else:
            logger.warning(f"Failed to read DICOM file: {self.filepath}")
            # Don't raise an exception here, just continue with the next file

        # ==========  used in test =======================================
        # print dict_file
        # main_dict = dict(
        #                data  = dict_file,
        #                labels  = tag_labels)
        # print main_dict
        # print "\n"
        # plistlib.writePlist(main_dict, ".//teste.plist")


@handle_errors(
    error_message="Error getting DICOM groups",
    category=ErrorCategory.DICOM, 
    severity=ErrorSeverity.ERROR,
    reraise=False
)
def yGetDicomGroups(directory, recursive=True, gui=True):
    """
    Return all full paths to DICOM files inside given directory.
    """
    nfiles = 0
    # Find total number of files
    try:
        if recursive:
            for dirpath, dirnames, filenames in os.walk(directory):
                nfiles += len(filenames)
        else:
            dirpath, dirnames, filenames = next(os.walk(directory))
            nfiles = len(filenames)
    except (StopIteration, OSError) as e:
        logger.error(f"Error accessing directory {directory}: {str(e)}")
        yield (0, 0)
        return []

    logger.info(f"Found {nfiles} total files in directory, starting DICOM processing")
    
    counter = 0
    valid_dicom_counter = 0
    grouper = dicom_grouper.DicomPatientGrouper()
    
    # Try to read all files inside directory
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            for name in filenames:
                try:
                    filepath = os.path.join(dirpath, name).encode(const.FS_ENCODE)
                    counter += 1
                    
                    # Report progress
                    if gui:
                        yield (counter, nfiles)
                        # Add a SafeYield to keep the UI responsive
                        if counter % 10 == 0:  # Only yield every 10 files to improve performance
                            wx.SafeYield()
                    
                    # Load the DICOM file by creating a DicomFileLoader instance
                    DicomFileLoader(grouper, filepath)
                    
                except Exception as e:
                    logger.error(f"Error processing file {name}: {str(e)}")
                    continue
    else:
        try:
            dirpath, dirnames, filenames = next(os.walk(directory))
            for name in filenames:
                try:
                    filepath = str(os.path.join(dirpath, name)).encode(const.FS_ENCODE)
                    counter += 1
                    
                    # Report progress
                    if gui:
                        yield (counter, nfiles)
                        # Add a SafeYield to keep the UI responsive
                        if counter % 10 == 0:  # Only yield every 10 files to improve performance
                            wx.SafeYield()
                    
                    # Load the DICOM file by creating a DicomFileLoader instance
                    DicomFileLoader(grouper, filepath)
                    
                except Exception as e:
                    logger.error(f"Error processing file {name}: {str(e)}")
                    continue
        except (StopIteration, OSError) as e:
            logger.error(f"Error accessing directory {directory}: {str(e)}")

    # Return all groups (patients)
    if gui:
        yield (nfiles, nfiles)
    
    # Return patient groups
    patient_list = grouper.GetPatientsGroups()
    logger.info(f"Found {len(patient_list)} patient groups")
    if gui:
        yield patient_list
    else:
        return patient_list


@handle_errors(
    error_message="Error getting DICOM groups",
    category=ErrorCategory.DICOM, 
    severity=ErrorSeverity.ERROR,
    reraise=False
)
def GetDicomGroups(directory, recursive=True):
    return list(yGetDicomGroups(directory, recursive, gui=False))


class ProgressDicomReader():
    def __init__(self):
        self.running = True
        self.dicom_series = None
        self.directory = None
        self.recursive = True
        self.result = None
        self.stoped = False
        Publisher.subscribe(self.CancelLoad, "Cancel DICOM load")
        logger.debug("ProgressDicomReader initialized")
        
    def CancelLoad(self):
        self.running = False
        self.stoped = True
        logger.info("DICOM loading cancelled by user")
        
    def SetWindowEvent(self, frame):
        self.frame = frame
        logger.info("Window event set for DICOM reader")
    
    def SetDirectoryPath(self, path, recursive=True):
        self.directory = path
        self.recursive = recursive
        self.running = True
        self.stoped = False
        logger.info(f"Set DICOM directory path: {path}, recursive: {recursive}")
        
        # Flag this as processing and then start the DICOM groups processing
        # in the same thread to ensure proper synchronization
        Publisher.sendMessage("Begin busy cursor")
        
        # Process DICOM groups directly
        self.GetDicomGroups(path, recursive)

    def UpdateLoadFileProgress(self, cont_progress):
        # The Progress function in control.py expects a two-element list with [counter, total]
        # if we receive a tuple of two values (counter, nfiles), convert it to a list
        if isinstance(cont_progress, tuple) and len(cont_progress) == 2:
            Publisher.sendMessage("Update dicom load", data=list(cont_progress))
        # if we get a single value, assume it's a percentage
        elif isinstance(cont_progress, (int, float)):
            Publisher.sendMessage("Update dicom load", data=[int(cont_progress), 100])
        # otherwise, pass it through (assuming it's already the expected list format)
        else:
            Publisher.sendMessage("Update dicom load", data=cont_progress)

    def EndLoadFile(self, patient_series):
        Publisher.sendMessage("End dicom load", patient_series=patient_series)
            
    def SetDicomSeries(self, dicom_series):
        self.dicom_series = dicom_series
        logger.info(f"Set DICOM series with {len(dicom_series)} files")
    
    def GetDicomGroups(self, path=None, recursive=None):
        """
        Get DICOM groups from a directory.
        """
        if not const.VTK_WARNING:
            log_path = utils.encode(
                str(inv_paths.USER_LOG_DIR.joinpath("vtkoutput.txt")), const.FS_ENCODE
            )
            fow = vtkFileOutputWindow()
            fow.SetFileName(log_path)
            ow = vtkOutputWindow()
            ow.SetInstance(fow)

        y = yGetDicomGroups(path, recursive)
        for value_progress in y:
            if not self.running:
                break
            if isinstance(value_progress, tuple):
                self.UpdateLoadFileProgress(value_progress)
            else:
                self.EndLoadFile(value_progress)
        self.UpdateLoadFileProgress(None)
        
        # End busy cursor
        Publisher.sendMessage("End busy cursor")

        # Is necessary in the case user cancel
        # the load, ensure that dicomdialog is closed
        if self.stoped:
            self.UpdateLoadFileProgress(None)
            self.stoped = False

@handle_errors(
    error_message="Error reading DICOM dir",
    category=ErrorCategory.IO, 
    severity=ErrorSeverity.ERROR,
    reraise=False
)
def ReadDicomDir(directory):
    """
    Read all DICOM files in directory and return a 
    dictionary of DICOM objects.
    """
    try:
        logger.info(f"Reading DICOM directory: {directory}")
        
        dict = {}
        for dirpath, dirnames, filenames in os.walk(directory):
            for file in filenames:
                if _is_valid_dicom(os.path.join(dirpath, file)):
                    dcm_path = os.path.join(dirpath, file)
                    dicom = dicom_module.read_file(dcm_path, defer_size="512 KB", stop_before_pixels=True)
                    dict[dcm_path] = dicom
                    
        logger.info(f"Found {len(dict)} DICOM files in {directory}")
        return dict
        
    except Exception as e:
        logger.error(f"Error reading DICOM directory: {str(e)}")
        return {}

@handle_errors(
    error_message="Error getting DICOM files",
    category=ErrorCategory.IO, 
    severity=ErrorSeverity.ERROR,
    reraise=False
)
def GetDicomFiles(directory, min_slices=None):
    """
    Returns all DICOM files in directory.
    """
    try:
        logger.info(f"Getting DICOM files from: {directory}")
        
        dicom_files = []
        for dirpath, dirnames, filenames in os.walk(directory):
            for name in filenames:
                filename = os.path.join(dirpath, name)
                if _is_valid_dicom(filename):
                    dicom_files.append(filename)
        
        if min_slices and len(dicom_files) < min_slices:
            logger.warning(f"Not enough DICOM files ({len(dicom_files)}), minimum is {min_slices}")
            return False
            
        logger.info(f"Found {len(dicom_files)} DICOM files in {directory}")
        return dicom_files
        
    except Exception as e:
        logger.error(f"Error getting DICOM files: {str(e)}")
        return False

@handle_errors(
    error_message="Error sorting DICOM files",
    category=ErrorCategory.GENERAL, 
    severity=ErrorSeverity.ERROR,
    reraise=False
)
def SortDicom(dicom_list):
    """
    Sort DICOM files based on their position, direction or image numbers.
    Receives a list of DICOM objects and returns a dictionary containing ordered lists of DICOM objects.
    """
    try:
        logger.info("Sorting DICOM files")
        # Dictionary for organizing patients, studies and series.
        patients = {}
        
        for dicom in dicom_list:
            # Group by patient ID
            try:
                patient_id = dicom.PatientID
            except AttributeError:
                patient_id = "Unknown Patient"
                
            if patient_id not in patients:
                patients[patient_id] = {}
                
            # Group by study
            try:
                study_uid = dicom.StudyInstanceUID
            except AttributeError:
                study_uid = "Unknown Study"
                
            if study_uid not in patients[patient_id]:
                patients[patient_id][study_uid] = {}
                
            # Group by series
            try:
                series_uid = dicom.SeriesInstanceUID
            except AttributeError:
                series_uid = "Unknown Series"
                
            if series_uid not in patients[patient_id][study_uid]:
                patients[patient_id][study_uid][series_uid] = []
                
            # Add files to respective series
            patients[patient_id][study_uid][series_uid].append(dicom)
            
        # Sort series
        for patient_id in patients:
            for study_uid in patients[patient_id]:
                for series_uid in patients[patient_id][study_uid]:
                    # Sort each series
                    try:
                        patients[patient_id][study_uid][series_uid] = _sort_series(patients[patient_id][study_uid][series_uid])
                    except Exception as e:
                        logger.warning(f"Failed to sort series {series_uid}: {str(e)}")
                        # Try our best to sort by instance number if other methods fail
                        try:
                            patients[patient_id][study_uid][series_uid].sort(key=lambda x: getattr(x, 'InstanceNumber', 0))
                        except:
                            logger.error(f"Failed to sort series {series_uid} even by instance number")
            
        logger.info(f"DICOM files sorted for {len(patients)} patients")
        return patients
        
    except Exception as e:
        logger.error(f"Error sorting DICOM files: {str(e)}")
        return {}

@handle_errors(
    error_message="Error extracting acquisition date",
    category=ErrorCategory.GENERAL, 
    severity=ErrorSeverity.WARNING,
    reraise=False
)
def GetAcquisitionDate(dicom):
    """
    Return acquisition date in format (yyyy, mm, dd).
    """
    try:
        acquisition_date = dicom.get("AcquisitionDate")
        if acquisition_date:
            return acquisition_date[:4], acquisition_date[4:6], acquisition_date[6:8]
        
        # Try StudyDate as fallback
        study_date = dicom.get("StudyDate")
        if study_date:
            return study_date[:4], study_date[4:6], study_date[6:8]
            
        logger.warning("No acquisition or study date found in DICOM")
        return '', '', ''
        
    except Exception as e:
        logger.warning(f"Error extracting acquisition date: {str(e)}")
        return '', '', ''

@handle_errors(
    error_message="Error extracting acquisition time",
    category=ErrorCategory.GENERAL, 
    severity=ErrorSeverity.WARNING,
    reraise=False
)
def GetAcquisitionTime(dicom):
    """
    Return acquisition time in format (hh, mm, ss).
    """
    try:
        acquisition_time = dicom.get("AcquisitionTime")
        if acquisition_time:
            return acquisition_time[:2], acquisition_time[2:4], acquisition_time[4:6]
        
        # Try StudyTime as fallback
        study_time = dicom.get("StudyTime")
        if study_time:
            return study_time[:2], study_time[2:4], study_time[4:6]
            
        logger.warning("No acquisition or study time found in DICOM")
        return '', '', ''
        
    except Exception as e:
        logger.warning(f"Error extracting acquisition time: {str(e)}")
        return '', '', ''

@handle_errors(
    error_message="Error getting DICOM files by patient",
    category=ErrorCategory.GENERAL, 
    severity=ErrorSeverity.ERROR,
    reraise=False
)
def GetDicomFilesbyPatient(dicomdir):
    """
    Return dictionary of patients with their DICOM files.
    """
    try:
        logger.info(f"Getting DICOM files by patient from {dicomdir}")
        
        dict_file = ReadDicomDir(dicomdir)
        patients_dict = {}
        
        for dicom_file in dict_file:
            dicom = dict_file[dicom_file]
            
            try:
                patient_name = dicom.PatientName
                if isinstance(patient_name, dicom_module.valuerep.PersonName):
                    patient_name = patient_name.encode('UTF-8', 'replace')
                patient_name = patient_name.decode("utf-8", "ignore")
            except:
                patient_name = "Unknown"
                
            try:
                patient_id = dicom.PatientID
            except:
                patient_id = "Unknown"
                
            key = (patient_name, patient_id)
            
            if key not in patients_dict:
                patients_dict[key] = []
                
            patients_dict[key].append(dicom_file)
            
        logger.info(f"Found {len(patients_dict)} patients in DICOM directory")
        return patients_dict
        
    except Exception as e:
        logger.error(f"Error getting DICOM files by patient: {str(e)}")
        return {}

@handle_errors(
    error_message="Error loading DICOM group",
    category=ErrorCategory.IO, 
    severity=ErrorSeverity.ERROR,
    reraise=False
)
def LoadDicom(directory, slice_interval=0, mode="append"):
    """
    Load DICOM as vtkImageData and return it.
    """
    try:
        logger.info(f"Loading DICOM from {directory}")
        
        # Get dicom files
        dicom_files = GetDicomFiles(directory)
        if not dicom_files:
            logger.error("No DICOM files found")
            return False
        
        # Create a new grouper for processing these files
        grouper = dicom_grouper.DicomPatientGrouper()
        
        # Process each DICOM file
        for filepath in dicom_files:
            try:
                DicomFileLoader(grouper, filepath)
            except Exception as e:
                logger.error(f"Error loading DICOM file {filepath}: {str(e)}")
        
        # Get the patient groups
        patient_groups = grouper.GetPatientsGroups()
        if not patient_groups:
            logger.error("No valid DICOM groups found")
            return False
            
        # Select the largest group
        largest_group = SelectLargerDicomGroup(patient_groups)
        if not largest_group:
            logger.error("Could not select a valid DICOM group")
            return False
        
        if HAS_VTK_GDCM:
            # Load using vtkGDCMImageReader if available
            reader = vtkGDCMImageReader()
            reader.SetDirectoryName(directory)
            reader.Update()
            
            # Get image data
            image = reader.GetOutput()
            if not image:
                logger.error("Failed to get image data from DICOM reader")
                return False
        else:
            # Fallback using pydicom and numpy to create image data
            logger.info("Using fallback DICOM reader")
            try:
                import pydicom
                import numpy as np
                from invesalius.data.imagedata_utils import numpy_to_vtkImageData
                
                # Load the first DICOM file to get dimensions
                first_dicom = pydicom.dcmread(dicom_files[0])
                
                # Get dimensions
                rows = first_dicom.Rows
                cols = first_dicom.Columns
                slices = len(dicom_files)
                
                # Create a numpy array to hold the image data
                image_array = np.zeros((slices, rows, cols), dtype=np.int16)
                
                # Load each DICOM file
                for i, file_path in enumerate(dicom_files):
                    try:
                        ds = pydicom.dcmread(file_path)
                        image_array[i, :, :] = ds.pixel_array
                    except Exception as e:
                        logger.error(f"Error reading DICOM file {file_path}: {str(e)}")
                
                # Create vtkImageData
                image = numpy_to_vtkImageData(image_array)
                if not image:
                    logger.error("Failed to convert numpy array to vtkImageData")
                    return False
            except ImportError:
                logger.error("Required modules for fallback DICOM reading are not available")
                return False
        
        logger.info("DICOM loaded successfully")
        return image
        
    except Exception as e:
        logger.error(f"Error loading DICOM group: {str(e)}")
        return False

def _is_valid_dicom(filename):
    """
    Check if a file is a valid DICOM file.
    
    Args:
        filename (str): Path to the file to check.
        
    Returns:
        bool: True if the file is a valid DICOM file, False otherwise.
    """
    try:
        if not os.path.isfile(filename):
            logger.debug(f"Not a file: {filename}")
            return False
            
        # First, check file size - DICOM files should be at least 132 bytes
        # (128 byte preamble + 4 byte magic number)
        file_size = os.path.getsize(filename)
        if file_size < 132:
            logger.debug(f"File too small to be DICOM ({file_size} bytes): {filename}")
            return False
            
        with open(filename, 'rb') as f:
            # Check for DICOM magic bytes - standard DICOM files have 'DICM' at offset 128
            f.seek(128)  # Skip preamble
            magic = f.read(4)
            if magic == b'DICM':
                return True
                
            # Some DICOM files don't have the standard preamble+magic
            # Try to detect these by looking for a valid DICOM tag at the beginning
            f.seek(0)
            # Try to read first 16 bytes - enough for a couple of DICOM tags
            header = f.read(16)
            
            # Look for common DICOM elements that would be near the start
            # Group 0002 elements are common at the start (File Meta Information)
            # Check for a valid group number with proper endianness (0x0002 or 0x0200)
            if (header[0:2] == b'\x02\x00' or header[0:2] == b'\x00\x02'):
                return True
                
            # One more check: try to see if we can read it with GDCM
            if gdcm and hasattr(gdcm, 'ImageReader'):
                try:
                    reader = gdcm.ImageReader()
                    try:
                        reader.SetFileName(utils.encode(filename, const.FS_ENCODE))
                    except TypeError:
                        reader.SetFileName(filename)
                    if reader.Read():
                        logger.debug(f"File recognized as DICOM by GDCM ImageReader: {filename}")
                        return True
                except Exception as e:
                    logger.debug(f"GDCM ImageReader error: {str(e)}")
                    
        logger.debug(f"Not a valid DICOM file: {filename}")
        return False
    except Exception as e:
        # If any exception occurs, the file is not a valid DICOM file
        logger.debug(f"Exception checking if valid DICOM file: {filename}, error: {str(e)}")
        return False
