#!/usr/bin/env python3
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
import logging
import os
import sys
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
from invesalius import inv_paths
from invesalius.data import imagedata_utils
from invesalius.error_handling import ErrorCategory, ErrorSeverity, handle_errors
from invesalius.pubsub import pub as Publisher

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

# Initialize logger
logger = logging.getLogger("invesalius.reader.dicom_reader")


@handle_errors(
    error_message="Error selecting larger DICOM group",
    category=ErrorCategory.DICOM,
    severity=ErrorSeverity.ERROR,
)
def SelectLargerDicomGroup(patient_group):
    maxslices = 0
    for patient in patient_group:
        group_list = patient.GetGroups()
        for group in group_list:
            if group.nslices > maxslices:
                maxslices = group.nslices
                larger_group = group

    return larger_group


@handle_errors(
    error_message="Error sorting DICOM files",
    category=ErrorCategory.DICOM,
    severity=ErrorSeverity.ERROR,
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

    return filelist


tag_labels = {}
main_dict = {}
dict_file = {}


class LoadDicom:
    def __init__(self, grouper, filepath):
        self.grouper = grouper
        self.filepath = utils.decode(filepath, const.FS_ENCODE)
        self.run()

    @handle_errors(
        error_message="Error loading DICOM file",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def run(self):
        grouper = self.grouper
        reader = gdcm.ImageReader()

        # Verify filepath is a valid string
        if not isinstance(self.filepath, str):
            logger.error(f"Invalid filepath type: {type(self.filepath)}, expected string")
            return

        logger.info(f"Reading DICOM file: {self.filepath}")

        try:
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
                            logger.warning(
                                f"Unknown DICOM encoding value: {encoding_value}, defaulting to ISO_IR 100"
                            )
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
                except (KeyError, ValueError) as e:
                    logger.warning(f"Could not get window/level for thumbnail: {e}")
                    level = None
                    window = None

                try:
                    img = reader.GetImage()
                    thumbnail_path = imagedata_utils.create_dicom_thumbnails(img, window, level)
                except Exception as e:
                    logger.error(f"Failed to create DICOM thumbnail: {e}")
                    thumbnail_path = None

                # ------ Verify the orientation --------------------------------
                try:
                    direc_cosines = img.GetDirectionCosines()
                    orientation = gdcm.Orientation()
                    try:
                        _type = orientation.GetType(tuple(direc_cosines))
                    except TypeError:
                        _type = orientation.GetType(direc_cosines)
                    label = orientation.GetLabel(_type)
                except Exception as e:
                    logger.warning(f"Error determining image orientation: {e}")
                    label = "AXIAL"

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
                        # self.l.release()
                    except Exception as e:
                        logger.error(f"Failed to process DICOM file data: {e}")
                        raise
            else:
                logger.warning(f"Failed to read DICOM file: {self.filepath}")
        except Exception as e:
            logger.error(f"Exception during DICOM file loading: {e}")
            raise


@handle_errors(
    error_message="Error getting DICOM groups",
    category=ErrorCategory.DICOM,
    severity=ErrorSeverity.ERROR,
)
def GetDicomGroups(directory, recursive=True):
    """
    Return all DICOM groups from a directory.
    """
    if not os.path.isdir(directory):
        logger.error(f"Directory does not exist: {directory}")
        return []

    # Create a new DICOM Patient Grouper to collect the files
    reader = dicom_grouper.DicomPatientGrouper()
    file_list = []

    # First scan directory and collect all valid DICOM files
    try:
        # Iterate through directory and collect files
        if recursive:
            for dirpath, dirnames, filenames in os.walk(directory):
                for name in filenames:
                    file_list.append(os.path.join(dirpath, name))
        else:
            try:
                dirpath, dirnames, filenames = next(os.walk(directory))
                for name in filenames:
                    file_list.append(os.path.join(dirpath, name))
            except StopIteration:
                logger.error(f"Failed to read directory: {directory}")
    except Exception as e:
        logger.error(f"Error scanning directory: {e}")
        return []

    if not file_list:
        logger.warning(f"No files found in directory: {directory}")
        return []

    # Process files
    valid_count = 0

    for filepath in file_list:
        # Try to load as DICOM
        try:
            LoadDicom(reader, filepath)
            valid_count += 1
        except Exception as e:
            # Just skip invalid files
            pass

    # If no valid DICOM files were found
    if valid_count == 0:
        logger.warning(f"No valid DICOM files found in directory: {directory}")
        return []

    logger.info(f"Found {valid_count} valid DICOM files in directory: {directory}")

    # Process patients and group them
    try:
        update_success = reader.Update()
        if not update_success:
            logger.warning("Failed to update DICOM groups - no valid data found")
            return []

        patients_groups = reader.GetPatientsGroups()
        if not patients_groups:
            logger.warning("No patient groups found")
            return []

        logger.info(
            f"Successfully processed {len(patients_groups)} patient groups from {directory}"
        )
        return patients_groups
    except Exception as e:
        logger.error(f"Failed to process DICOM groups: {e}")
        return []


class ProgressDicomReader:
    """
    Update dicom reader progress
    """

    def __init__(self):
        self.running = True
        self.progress_window = None

    def CancelLoad(self):
        self.running = False
        # Send message to close the progress dialog
        Publisher.sendMessage("Update dicom load", data=None)

        if self.progress_window:
            self.progress_window = None

        self.file_list = []

    def SetWindowEvent(self, frame):
        self.progress_window = frame

    def SetDirectoryPath(self, path, recursive=True):
        self.running = True
        self.GetDicomGroups(path, recursive)

    @handle_errors(
        error_message="Error updating DICOM file loading progress",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def UpdateLoadFileProgress(self, cont_progress):
        # Send a message to Publisher to update the progress
        # The Publisher will forward this to the Progress method in control.py
        total_files = len(getattr(self, "file_list", []))
        if total_files > 0:
            # Convert progress value (0.0 to 1.0) to count (1 to total_files)
            current_file = int(cont_progress * total_files)
            if current_file < 1:
                current_file = 1

            # Send message with current file number and total files
            Publisher.sendMessage("Update dicom load", data=(current_file, total_files))

        # Also update the direct progress window if it exists
        if self.progress_window and hasattr(self.progress_window, "UpdateLoadFileProgress"):
            self.progress_window.UpdateLoadFileProgress(cont_progress)

    @handle_errors(
        error_message="Error completing DICOM file loading",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def EndLoadFile(self, patient_list):
        # Log completion
        total_patients = len(patient_list) if patient_list else 0
        total_groups = (
            sum(len(patient.GetGroups()) for patient in patient_list) if patient_list else 0
        )
        logger.info(
            f"DICOM loading complete: {total_patients} patients, {total_groups} study groups"
        )

        try:
            # Send message to close the progress dialog
            logger.debug("Closing DICOM loading progress dialog")
            Publisher.sendMessage("Update dicom load", data=None)

            # If progress window exists, call its EndLoadFile method
            if self.progress_window and hasattr(self.progress_window, "EndLoadFile"):
                logger.debug("Calling progress window EndLoadFile method")
                self.progress_window.EndLoadFile()

            # This sends the patient groups to the controller to show the DICOM grouper window
            logger.info("Sending DICOM groups to interface for user selection")
            Publisher.sendMessage("End dicom load", patient_series=patient_list)

            # Clean up
            logger.debug("Cleaning up progress window and file list")
            self.progress_window = None
            self.file_list = []
        except Exception as e:
            logger.error(f"Error in EndLoadFile: {e}")
            # Try to clean up even if there was an error
            self.progress_window = None
            self.file_list = []

    @handle_errors(
        error_message="Error getting DICOM groups",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.WARNING,
    )
    def GetDicomGroups(self, path, recursive):
        # Verify directory exists
        if not os.path.isdir(path):
            logger.error(f"Directory does not exist: {path}")
            Publisher.sendMessage("Load group reader", group_reader=None)
            self.progress_window = None
            return

        # Retrieve directory path to DICOM files
        directory = path
        logger.info(f"Starting DICOM import from directory: {directory} (recursive={recursive})")

        # Create a new DICOM Patient Grouper to collect the files
        reader = dicom_grouper.DicomPatientGrouper()
        self.file_list = []

        # First scan directory and collect all valid DICOM files
        try:
            logger.info("Scanning directory for files...")
            start_time = time.time()

            # Iterate through directory and collect files
            if recursive:
                for dirpath, dirnames, filenames in os.walk(directory):
                    for name in filenames:
                        self.file_list.append(os.path.join(dirpath, name))
            else:
                try:
                    dirpath, dirnames, filenames = next(os.walk(directory))
                    for name in filenames:
                        self.file_list.append(os.path.join(dirpath, name))
                except StopIteration:
                    logger.error(f"Failed to read directory: {directory}")

            scan_time = time.time() - start_time
            logger.info(
                f"Directory scan completed in {scan_time:.2f}s, found {len(self.file_list)} files to analyze"
            )
        except Exception as e:
            logger.error(f"Error scanning directory: {e}")
            Publisher.sendMessage("Load group reader", group_reader=None)
            self.progress_window = None
            return

        if not self.file_list:
            logger.warning(f"No files found in directory: {directory}")
            Publisher.sendMessage("Load group reader", group_reader=None)
            self.progress_window = None
            return

        # Process files and update progress
        total_files = len(self.file_list)
        logger.info(f"Starting to process {total_files} files")
        valid_count = 0
        start_time = time.time()

        # Send initial progress message
        Publisher.sendMessage("Update dicom load", data=(0, total_files))

        for i, filepath in enumerate(self.file_list):
            if not self.running:
                logger.info("DICOM loading process was cancelled by user")
                Publisher.sendMessage("Load group reader", group_reader=None)
                self.progress_window = None
                return

            # Update progress every 10 files or for the last file
            if i % 10 == 0 or i == total_files - 1:
                progress = (i + 1) / float(total_files)
                self.UpdateLoadFileProgress(progress)
                if i > 0 and i % 50 == 0:
                    current_time = time.time()
                    elapsed = current_time - start_time
                    files_per_sec = i / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"Processed {i}/{total_files} files ({files_per_sec:.1f} files/sec)"
                    )

            # Try to load as DICOM
            try:
                LoadDicom(reader, filepath)
                valid_count += 1
            except Exception as e:
                # Just skip invalid files
                pass

        process_time = time.time() - start_time
        logger.info(f"File processing completed in {process_time:.2f}s")

        # If no valid DICOM files were found
        if valid_count == 0:
            logger.warning(f"No valid DICOM files found in directory: {directory}")
            Publisher.sendMessage("Load group reader", group_reader=None)
            self.progress_window = None
            return

        logger.info(f"Found {valid_count} valid DICOM files out of {total_files} total files")

        # Process patients and group them
        try:
            logger.info("Organizing DICOM files into patient/study/series groups...")
            start_time = time.time()

            update_success = reader.Update()
            if not update_success:
                logger.warning("Failed to update DICOM groups - no valid data found")
                Publisher.sendMessage("Load group reader", group_reader=None)
                self.progress_window = None
                return

            group_time = time.time() - start_time
            patients_groups = reader.GetPatientsGroups()
            if not patients_groups:
                logger.warning("No patient groups found")
                Publisher.sendMessage("Load group reader", group_reader=None)
                self.progress_window = None
                return

            num_patients = len(patients_groups)
            num_groups = sum(len(patient.GetGroups()) for patient in patients_groups)
            logger.info(
                f"Successfully organized data into {num_patients} patients with {num_groups} groups in {group_time:.2f}s"
            )

            self.EndLoadFile(patients_groups)
            logger.info(f"Successfully processed {len(patients_groups)} patient groups from {path}")
        except Exception as e:
            logger.error(f"Failed to process DICOM groups: {e}")
            Publisher.sendMessage("Load group reader", group_reader=None)
            self.progress_window = None
