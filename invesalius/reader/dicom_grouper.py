#!/usr/bin/env python3
# ---------------------------------------------------------------------
# Software: InVesalius Software de Reconstrucao 3D de Imagens Medicas

# Copyright: (c) 2001  Centro de Pesquisas Renato Archer
# Homepage: http://www.softwarepublico.gov.br
# Contact:  invesalius@cenpra.gov.br
# License:  GNU - General Public License version 2 (LICENSE.txt/
#                                                         LICENCA.txt)
#
#    Este programa eh software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# ---------------------------------------------------------------------


# ---------------------------------------------------------
# PROBLEM 1
# There are times when there are lots of groups on dict, but
# each group contains only one slice (DICOM file).
#
# Equipments / manufacturer:
# TODO
#
# Cases:
# TODO 0031, 0056, 1093
#
# What occurs in these cases:
# <dicom.image.number> and <dicom.acquisition.series_number>
# were swapped


# -----------------------------------------------------------
# PROBLEM 2
# Two slices (DICOM file) inside a group have the same
# position.
#
# Equipments / manufacturer:
# TODO
#
# Cases:
# TODO 0031, 0056, 1093
#
# What occurs in these cases:
# <dicom.image.number> and <dicom.acquisition.series_number>
# were swapped

import logging
import sys

import gdcm

if sys.platform == "win32":
    try:
        import win32api

        _has_win32api = True
    except ImportError:
        _has_win32api = False
else:
    _has_win32api = False

import invesalius.constants as const
import invesalius.utils as utils
from invesalius.error_handling import ErrorCategory, ErrorSeverity, handle_errors

ORIENT_MAP = {"SAGITTAL": 0, "CORONAL": 1, "AXIAL": 2, "OBLIQUE": 2}

# Initialize logger
logger = logging.getLogger("invesalius.reader.dicom_grouper")

class DicomGroup:
    general_index = -1

    def __init__(self):
        DicomGroup.general_index += 1
        self.index = DicomGroup.general_index
        # key:
        # (dicom.patient.name, dicom.acquisition.id_study,
        #  dicom.acquisition.series_number,
        #  dicom.image.orientation_label, index)
        self.key = ()
        self.title = ""
        self.slices_dict = {}  # slice_position: Dicom.dicom
        # IDEA (13/10): Represent internally as dictionary,
        # externally as list
        self.nslices = 0
        self.zspacing = 1
        self.dicom = None

    @handle_errors(
        error_message="Error adding DICOM slice to group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.WARNING,
    )
    def AddSlice(self, dicom):
        if not self.dicom:
            self.dicom = dicom

        pos = tuple(dicom.image.position)

        # Case to test: \other\higroma
        # condition created, if any dicom with the same
        # position, but 3D, leaving the same series.
        if "DERIVED" not in dicom.image.type:
            # if any dicom with the same position
            if pos not in self.slices_dict.keys():
                self.slices_dict[pos] = dicom
                self.nslices += dicom.image.number_of_frames
                return True
            else:
                logger.info(f"Skipping DICOM slice with duplicate position: {pos}")
                return False
        else:
            self.slices_dict[dicom.image.number] = dicom
            self.nslices += dicom.image.number_of_frames
            return True

    def GetList(self):
        # Should be called when user selects this group
        # This list will be used to create the vtkImageData
        # (interpolated)
        return self.slices_dict.values()

    @handle_errors(
        error_message="Error getting DICOM filename list",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def GetFilenameList(self):
        # Should be called when user selects this group
        # This list will be used to create the vtkImageData
        # (interpolated)

        if _has_win32api:
            try:
                filelist = [
                    win32api.GetShortPathName(dicom.image.file) for dicom in self.slices_dict.values()
                ]
            except Exception as e:
                logger.error(f"Error getting short path names: {e}")
                filelist = [dicom.image.file for dicom in self.slices_dict.values()]
        else:
            filelist = [dicom.image.file for dicom in self.slices_dict.values()]

        # Sort slices using GDCM
        # if (self.dicom.image.orientation_label != "CORONAL"):
        # Organize reversed image
        sorter = gdcm.IPPSorter()
        sorter.SetComputeZSpacing(True)
        sorter.SetZSpacingTolerance(1e-10)
        try:
            logger.debug("Sorting DICOM files using IPPSorter")
            sorter.Sort([utils.encode(i, const.FS_ENCODE) for i in filelist])
        except TypeError:
            logger.debug("Sorting DICOM files using IPPSorter (without encoding)")
            sorter.Sort(filelist)
        except Exception as e:
            logger.warning(f"Error sorting DICOM files: {e}, files may not be in correct order")
            
        filelist = sorter.GetFilenames()

        # for breast-CT of koning manufacturing (KBCT)
        try:
            if list(self.slices_dict.values())[0].parser.GetManufacturerName() == "Koning":
                logger.info("Detected Koning KBCT, using filename sorting")
                filelist.sort()
        except Exception as e:
            logger.warning(f"Error checking for Koning manufacturer: {e}")

        return filelist

    def GetHandSortedList(self):
        # This will be used to fix problem 1, after merging
        # single DicomGroups of same study_id and orientation
        list_ = list(self.slices_dict.values())
        # dicom = list_[0]
        # axis = ORIENT_MAP[dicom.image.orientation_label]
        # list_ = sorted(list_, key = lambda dicom:dicom.image.position[axis])
        list_ = sorted(list_, key=lambda dicom: dicom.image.number)
        return list_

    @handle_errors(
        error_message="Error updating Z spacing",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.WARNING,
    )
    def UpdateZSpacing(self):
        list_ = self.GetHandSortedList()

        if len(list_) > 1:
            try:
                dicom = list_[0]
                axis = ORIENT_MAP[dicom.image.orientation_label]
                p1 = dicom.image.position[axis]

                dicom = list_[1]
                p2 = dicom.image.position[axis]

                self.zspacing = abs(p1 - p2)
                logger.debug(f"Updated Z spacing: {self.zspacing}")
            except Exception as e:
                logger.warning(f"Failed to calculate proper Z spacing: {e}")
                self.zspacing = 1
        else:
            self.zspacing = 1

    def GetDicomSample(self):
        size = len(self.slices_dict)
        dicom = self.GetHandSortedList()[size // 2]
        return dicom


class PatientGroup:
    def __init__(self):
        # key:
        # (dicom.patient.name, dicom.patient.id)
        self.key = ()
        self.groups_dict = {}  # group_key: DicomGroup
        self.nslices = 0
        self.ngroups = 0
        self.dicom = None

    @handle_errors(
        error_message="Error adding DICOM file to patient group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.WARNING,
    )
    def AddFile(self, dicom, index=0):
        # Given general DICOM information, we group slices according
        # to main series information (group_key)

        # WARN: This was defined after years of experience
        # (2003-2009), so THINK TWICE before changing group_key

        # Problem 2 is being fixed by the way this method is
        # implemented, dinamically during new dicom's addition
        group_key = (
            dicom.patient.name,
            dicom.acquisition.id_study,
            dicom.acquisition.serie_number,
            dicom.image.orientation_label,
            index,
        )  # This will be used to deal with Problem 2
        
        if not self.dicom:
            self.dicom = dicom

        self.nslices += 1
        # Does this group exist? Best case ;)
        if group_key not in self.groups_dict.keys():
            logger.debug(f"Creating new DICOM group with key: {group_key}")
            group = DicomGroup()
            group.key = group_key
            group.title = dicom.acquisition.series_description
            group.AddSlice(dicom)
            self.ngroups += 1
            self.groups_dict[group_key] = group
        # Group exists... Lets try to add slice
        else:
            group = self.groups_dict[group_key]
            slice_added = group.AddSlice(dicom)
            if not slice_added:
                # If we're here, then Problem 2 occured
                logger.info(f"Detected Problem 2 (duplicate position), incrementing index for DICOM file")
                # TODO: Optimize recursion
                self.AddFile(dicom, index + 1)

            # Getting the spacing in the Z axis
            group.UpdateZSpacing()

    @handle_errors(
        error_message="Error updating patient group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def Update(self):
        # Ideally, AddFile would be sufficient for splitting DICOM
        # files into groups (series). However, this does not work for
        # acquisitions / equipments and manufacturers.

        # Although DICOM is a protocol, each one uses its fields in a
        # different manner

        # Check if Problem 1 occurs (n groups with 1 slice each)
        is_there_problem_1 = False
        utils.debug("n slice %d" % self.nslices)
        utils.debug("len %d" % len(self.groups_dict))
        if (self.nslices == len(self.groups_dict)) and (self.nslices > 1):
            is_there_problem_1 = True

        # Fix Problem 1
        if is_there_problem_1:
            logger.info("Detected Problem 1 (multiple groups with single slice), fixing...")
            utils.debug("Problem1")
            self.groups_dict = self.FixProblem1(self.groups_dict)

    def GetGroups(self):
        return list(self.groups_dict.values())

    def GetDicomSample(self):
        one_group = list(self.groups_dict.items())[0][1]
        return one_group.GetDicomSample()

    @handle_errors(
        error_message="Error fixing DICOM grouping problem",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.WARNING,
    )
    def FixProblem1(self, dict):
        # Fixing Problem 1
        # In some cases there is a different interpretation for
        # group defining
        # In such cases, each DICOM file has the same
        # (series_number, orientation_label),
        # but actually each DICOM file is a different group!
        # However, it seems that in all these cases, DICOM files of
        # the same group actually have different "series_description"
        # (group_key is (name, id_study, series_number, ...)
        #
        # So we need to re-group, using also image.number or perhaps
        # position values
        #
        # We need to merge DICOM slices inside their correct group

        patient_name = self.key[0]
        patient_id = self.key[1]
        id_study = ""

        output = {}

        # Create groups
        # Now we go in reverse direction
        dicom_dict = {}
        for (group_key, dicom_group) in dict.items():

            # Now we go for each DICOM inside each object
            for dicom in dicom_group.GetList():  # GetList returns a list of DICOM objects
                # Now each DICOM will be grouped by description
                
                # Retrieve DICOM fields: key and object
                patient_name, id_study, serie_number, orientation_label, index = group_key

                # Use slice description to compare with group (series), and check
                # if should really create a new group
                description = dicom.acquisition.series_description or "NoSeries"

                group_key = (description, orientation_label)

                # This dicom_dict will have a dict of dicts
                # First level:
                # key is the series_description (one for each created group),
                # object is a dict of objects: dicom_list
                # Inside dicom_list, key is dicom.image.number, value is dicom object
                if group_key not in dicom_dict.keys():
                    dicom_dict[group_key] = {}

                dicom_list = dicom_dict[group_key]
                # dicom_list[dicom.image.position] = dicom
                dicom_list[dicom.image.number] = dicom

        # Now re-create DicomGroup, using our new group schem
        for (group_key, dicom_dict_group) in dicom_dict.items():
            # Create a fake DICOM group
            # Groups already separated
            new_group = DicomGroup()

            # Based on the first slice of each group
            first_dicom = list(dicom_dict_group.values())[0]

            # Add slice by slice
            for dicom in dicom_dict_group.values():
                new_group.AddSlice(dicom)
                description, orientation_label = group_key
                new_key = (
                    patient_name,
                    id_study,
                    first_dicom.acquisition.serie_number,
                    orientation_label,
                    0,
                )
                new_group.key = new_key
                new_group.title = description

            new_group.UpdateZSpacing()

            # Add group to our dictionary
            output[new_group.key] = new_group

        # Return fixed dict
        return output


class DicomPatientGrouper:
    """
    Responsible for manage data regarding each patient, such as personal
    information and groups of DICOM files.
    """

    def __init__(self):
        # Main dict. Patients that are being read.
        # key: (dicom.patient.name, dicom.patient.id)
        self.patients_dict = {}  # patient_key: PatientGroup

    @handle_errors(
        error_message="Error adding DICOM file to patient grouper",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.WARNING,
    )
    def AddFile(self, dicom):
        """
        Add DICOM object to its corresponding patient.
        """
        patient_key = (dicom.patient.name, dicom.patient.id)
        # Is this a new patient?
        # TODO: Consider: what if patient_id is None?
        if patient_key not in self.patients_dict.keys():
            patient_group = PatientGroup()
            patient_group.key = patient_key
            patient_group.AddFile(dicom)
            self.patients_dict[patient_key] = patient_group
        # Patient exists... Lets add this DICOM
        else:
            patient_group = self.patients_dict[patient_key]
            patient_group.AddFile(dicom)

    @handle_errors(
        error_message="Error updating patient grouper",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def Update(self):
        """
        Update patient groups.
        """
        # Process all patient groups
        for patient_group in self.patients_dict.values():
            patient_group.Update()
            
        # Log diagnostic information
        total_patients = len(self.patients_dict)
        total_groups = sum(pg.ngroups for pg in self.patients_dict.values())
        total_slices = sum(pg.nslices for pg in self.patients_dict.values())
        
        logger.info(f"Updated DicomPatientGrouper with {total_patients} patient(s), {total_groups} group(s), {total_slices} slice(s)")
        
        # Verify we have valid data
        if total_patients == 0 or total_groups == 0 or total_slices == 0:
            logger.warning("No valid DICOM data found after updating patient grouper")
            return False
            
        return True

    def GetPatientsGroups(self):
        """
        Return list of patients.
        """
        patients_groups = []
        for key in self.patients_dict:
            patients_groups.append(self.patients_dict[key])
        return patients_groups
