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
from invesalius import inv_paths
from invesalius.data import imagedata_utils
from invesalius.pubsub import pub as Publisher

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False


def SelectLargerDicomGroup(patient_group):
    maxslices = 0
    for patient in patient_group:
        group_list = patient.GetGroups()
        for group in group_list:
            if group.nslices > maxslices:
                maxslices = group.nslices
                larger_group = group

    return larger_group


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

    return filelist


tag_labels = {}
main_dict = {}
dict_file = {}


def _is_valid_dicom(filepath):
    """
    Check if a file is a valid DICOM file.
    Handles filenames with spaces and parentheses.
    
    Parameters:
    -----------
    filepath (str): Path to the file to check.
    
    Returns:
    --------
    bool: True if the file is likely a DICOM file, False otherwise.
    """
    try:
        # Check if file exists
        if not os.path.isfile(filepath):
            print(f"File does not exist: {filepath}")
            return False
            
        # Check file extension - be very permissive
        file_extension = os.path.splitext(filepath)[1].lower()
        valid_extensions = ('.dcm', '.dicom', '.dic', '.acr', '', '.ima', '.img')
        
        # For files with parentheses or special characters, be more permissive
        if file_extension not in valid_extensions:
            if ".dcm" in filepath.lower() or "dicom" in filepath.lower():
                print(f"Accepting file with DCM in name: {filepath}")
                # Continue processing
            else:
                # Try to open file to check basic binary signature
                with open(filepath, "rb") as f:
                    # Read first few bytes to check for DICOM-like patterns
                    header = f.read(132)
                    # Check for common DICOM patterns
                    if b"DICM" in header or b"UI" in header or b"SQ" in header:
                        print(f"File has DICOM patterns in header: {filepath}")
                        # Continue processing
                    else:
                        print(f"Skipping file with invalid extension: {filepath} (extension: {file_extension})")
                        return False
                
        # Try to read the file using GDCM, handling all possible encoding issues
        reader = gdcm.ImageReader()
        try:
            # For Windows paths with spaces and special characters
            if _has_win32api:
                try:
                    reader.SetFileName(utils.encode(win32api.GetShortPathName(filepath), const.FS_ENCODE))
                except Exception as e:
                    print(f"Win32 path error, trying alternative: {str(e)}")
                    try:
                        # Try direct path setting
                        reader.SetFileName(filepath)
                    except:
                        # Last resort, try raw bytes
                        if isinstance(filepath, str):
                            reader.SetFileName(filepath.encode('utf-8'))
                        else:
                            reader.SetFileName(filepath)
            else:
                # For non-Windows systems
                try:
                    reader.SetFileName(utils.encode(filepath, const.FS_ENCODE) if isinstance(filepath, str) else filepath)
                except Exception as e:
                    print(f"Path encoding error, trying alternative: {str(e)}")
                    # Direct path setting
                    reader.SetFileName(filepath if isinstance(filepath, str) else filepath.decode('utf-8'))
            
            if reader.Read():
                print(f"GDCM successfully read DICOM file: {filepath}")
                return True
            else:
                print(f"GDCM cannot read file as DICOM: {filepath}")
        except Exception as e:
            print(f"GDCM error: {str(e)} - trying manual checks")
            
        # Manual method as fallback
        try:
            with open(filepath, "rb") as f:
                # Standard DICOM files have DICM at offset 128
                f.seek(128)
                if f.read(4) == b"DICM":
                    print(f"Found DICM magic bytes: {filepath}")
                    return True
                
                # Some DICOMs don't have the magic bytes, check for common group numbers
                f.seek(0)
                header = f.read(16)
                # Check group numbers (both endianness)
                groups = [b"\x02\x00", b"\x00\x02", b"\x08\x00", b"\x00\x08", 
                          b"\x10\x00", b"\x00\x10", b"\x20\x00", b"\x00\x20"]
                if any(header.startswith(g) for g in groups):
                    print(f"Found DICOM group at start: {filepath}")
                    return True
                
                # Last try - assume it's DICOM if filename looks like it
                filename = os.path.basename(filepath).lower()
                if any(pattern in filename for pattern in ["dicom", "dcm", "ct", "mri", "xray", "scan"]):
                    print(f"Assuming DICOM from filename: {filepath}")
                    return True
        except Exception as e:
            print(f"Manual check error: {str(e)} for {filepath}")
            
        print(f"Not a recognized DICOM file: {filepath}")
        return False
    except Exception as e:
        print(f"Exception in DICOM validation: {str(e)} for {filepath}")
        return False


class LoadDicom:
    def __init__(self, grouper, filepath):
        self.grouper = grouper
        self.filepath = utils.decode(filepath, const.FS_ENCODE)
        self.run()

    def run(self):
        grouper = self.grouper
        reader = gdcm.ImageReader()
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
                parser = dicom.Parser()
                parser.SetDataImage(dict_file[self.filepath], self.filepath, thumbnail_path)

                dcm = dicom.Dicom()
                # self.l.acquire()
                dcm.SetParser(parser)
                grouper.AddFile(dcm)

                # self.l.release()

        # ==========  used in test =======================================
        # print dict_file
        # main_dict = dict(
        #                data  = dict_file,
        #                labels  = tag_labels)
        # print main_dict
        # print "\n"
        # plistlib.writePlist(main_dict, ".//teste.plist")


def yGetDicomGroups(directory, recursive=True, gui=True):
    """
    Return all full paths to DICOM files inside given directory.
    """
    nfiles = 0
    # Find total number of files
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            nfiles += len(filenames)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        nfiles = len(filenames)

    counter = 0
    grouper = dicom_grouper.DicomPatientGrouper()
    # q = Queue.Queue()
    # l = threading.Lock()
    # threads = []
    # for i in xrange(cpu_count()):
    #    t = LoadDicom(grouper, q, l)
    #    t.start()
    #    threads.append(t)
    # Retrieve only DICOM files, splited into groups
    if recursive:
        for dirpath, dirnames, filenames in os.walk(directory):
            for name in filenames:
                filepath = os.path.join(dirpath, name)
                counter += 1
                if gui:
                    yield (counter, nfiles)
                LoadDicom(grouper, filepath)
    else:
        dirpath, dirnames, filenames = os.walk(directory)
        for name in filenames:
            filepath = str(os.path.join(dirpath, name))
            counter += 1
            if gui:
                yield (counter, nfiles)
            # q.put(filepath)

    # for t in threads:
    #    q.put(0)

    # for t in threads:
    #    t.join()

    # TODO: Is this commented update necessary?
    # grouper.Update()
    yield grouper.GetPatientsGroups()


def GetDicomGroups(directory, recursive=True):
    return next(yGetDicomGroups(directory, recursive, gui=False))


class ProgressDicomReader:
    def __init__(self):
        Publisher.subscribe(self.CancelLoad, "Cancel DICOM load")

    def CancelLoad(self):
        self.running = False
        self.stoped = True

    def SetWindowEvent(self, frame):
        self.frame = frame

    def SetDirectoryPath(self, path, recursive=True):
        self.running = True
        self.stoped = False
        self.GetDicomGroups(path, recursive)

    def UpdateLoadFileProgress(self, cont_progress):
        Publisher.sendMessage("Update dicom load", data=cont_progress)

    def EndLoadFile(self, patient_list):
        if patient_list and isinstance(patient_list, list) and len(patient_list) > 0:
            # Set temporary project status to prevent "Please import image first" message
            import invesalius.constants as const
            import invesalius.session as ses
            session = ses.Session()
            # Only set to new when it was previously closed
            if session.GetConfig("project_status") == const.PROJECT_STATUS_CLOSED:
                session.SetConfig("project_status", const.PROJECT_STATUS_NEW)
            # Send the message to load the import panel
            Publisher.sendMessage("End dicom load", patient_series=patient_list)
        else:
            # Don't send a message if the patient list is empty
            pass

    def GetDicomGroups(self, path, recursive):
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
            print(">>>>", value_progress)
            if not self.running:
                break
            if isinstance(value_progress, tuple):
                self.UpdateLoadFileProgress(value_progress)
            else:
                self.EndLoadFile(value_progress)
        self.UpdateLoadFileProgress(None)

        # Is necessary in the case user cancel
        # the load, ensure that dicomdialog is closed
        if self.stoped:
            self.UpdateLoadFileProgress(None)
            self.stoped = False
