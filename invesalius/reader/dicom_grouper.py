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
from invesalius.enhanced_logging import get_logger
from invesalius.error_handling import (
    DicomError,
    ErrorCategory,
    ErrorSeverity,
    handle_errors,
)

# Initialize logger
logger = get_logger("reader.dicom_grouper")

ORIENT_MAP = {"SAGITTAL": 0, "CORONAL": 1, "AXIAL": 2, "OBLIQUE": 2}


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
        logger.debug(f"DicomGroup initialized with index {self.index}")

    @handle_errors(
        error_message="Error adding slice to DICOM group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def AddSlice(self, dicom):
        if not self.dicom:
            self.dicom = dicom

        pos = tuple(dicom.image.position)
        logger.debug(f"Adding slice with position {pos} to group {self.index}")

        # Case to test: \other\higroma
        # condition created, if any dicom with the same
        # position, but 3D, leaving the same series.
        if "DERIVED" not in dicom.image.type:
            # if any dicom with the same position
            if pos not in self.slices_dict.keys():
                self.slices_dict[pos] = dicom
                self.nslices += dicom.image.number_of_frames
                logger.debug(f"Added slice to group {self.index}, now has {self.nslices} slices")
                return True
            else:
                logger.warning(
                    f"Position {pos} already exists in group {self.index}, slice not added"
                )
                return False
        else:
            self.slices_dict[dicom.image.number] = dicom
            self.nslices += dicom.image.number_of_frames
            logger.debug(
                f"Added DERIVED slice to group {self.index}, now has {self.nslices} slices"
            )
            return True

    @handle_errors(
        error_message="Error getting slice list from DICOM group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def GetList(self):
        # Should be called when user selects this group
        # This list will be used to create the vtkImageData
        # (interpolated)
        logger.debug(f"Getting slice list from group {self.index} with {self.nslices} slices")
        return self.slices_dict.values()

    @handle_errors(
        error_message="Error getting filename list from DICOM group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def GetFilenameList(self):
        # Should be called when user selects this group
        # This list will be used to create the vtkImageData
        # (interpolated)
        logger.debug(f"Getting filename list from group {self.index} with {self.nslices} slices")

        if _has_win32api:
            filelist = [
                win32api.GetShortPathName(dicom.image.file) for dicom in self.slices_dict.values()
            ]
        else:
            filelist = [dicom.image.file for dicom in self.slices_dict.values()]

        # Sort slices using GDCM
        # if (self.dicom.image.orientation_label != "CORONAL"):
        # Organize reversed image
        sorter = gdcm.IPPSorter()
        sorter.SetComputeZSpacing(True)
        sorter.SetZSpacingTolerance(1e-10)
        try:
            logger.debug(f"Sorting {len(filelist)} files using GDCM IPPSorter")
            sorter.Sort([utils.encode(i, const.FS_ENCODE) for i in filelist])
        except TypeError:
            sorter.Sort(filelist)
        filelist = sorter.GetFilenames()

        # for breast-CT of koning manufacturing (KBCT)
        if list(self.slices_dict.values())[0].parser.GetManufacturerName() == "Koning":
            logger.debug("Special sorting for Koning manufacturer")
            filelist.sort()

        return filelist

    @handle_errors(
        error_message="Error getting hand-sorted list from DICOM group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def GetHandSortedList(self):
        # This will be used to fix problem 1, after merging
        # single DicomGroups of same study_id and orientation
        list_ = list(self.slices_dict.values())
        # dicom = list_[0]
        # axis = ORIENT_MAP[dicom.image.orientation_label]
        # list_ = sorted(list_, key = lambda dicom:dicom.image.position[axis])
        logger.debug(f"Getting hand-sorted list from group {self.index} with {len(list_)} slices")
        list_ = sorted(list_, key=lambda dicom: dicom.image.number)
        return list_

    @handle_errors(
        error_message="Error updating Z spacing in DICOM group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def UpdateZSpacing(self):
        list_ = self.GetHandSortedList()

        if len(list_) > 1:
            dicom = list_[0]
            axis = ORIENT_MAP[dicom.image.orientation_label]
            p1 = dicom.image.position[axis]

            dicom = list_[1]
            p2 = dicom.image.position[axis]

            self.zspacing = abs(p1 - p2)
            logger.debug(f"Updated Z spacing for group {self.index}: {self.zspacing}")
        else:
            self.zspacing = 1
            logger.debug(f"Only one slice in group {self.index}, setting Z spacing to 1")

    @handle_errors(
        error_message="Error getting DICOM sample from group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def GetDicomSample(self):
        size = len(self.slices_dict)
        dicom = self.GetHandSortedList()[size // 2]
        logger.debug(f"Getting DICOM sample from group {self.index}, sample index: {size // 2}")
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
        logger.debug("PatientGroup initialized")

    @handle_errors(
        error_message="Error adding file to patient group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
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
        logger.debug(f"Adding file to patient group, current slices: {self.nslices}")

        # Does this group exist? Best case ;)
        if group_key not in self.groups_dict.keys():
            group = DicomGroup()
            group.key = group_key
            group.title = dicom.acquisition.series_description
            group.AddSlice(dicom)
            self.ngroups += 1
            self.groups_dict[group_key] = group
            logger.debug(f"Created new group with key {group_key}, total groups: {self.ngroups}")
        # Group exists... Lets try to add slice
        else:
            group = self.groups_dict[group_key]
            slice_added = group.AddSlice(dicom)
            if not slice_added:
                # If we're here, then Problem 2 occured
                # TODO: Optimize recursion
                logger.warning(
                    f"Problem 2 occurred, recursively adding file with index {index + 1}"
                )
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
        logger.debug(f"Number of slices: {self.nslices}, number of groups: {len(self.groups_dict)}")
        if (self.nslices == len(self.groups_dict)) and (self.nslices > 1):
            is_there_problem_1 = True

        # Fix Problem 1
        if is_there_problem_1:
            logger.warning("Problem 1 detected, fixing...")
            self.groups_dict = self.FixProblem1(self.groups_dict)

        logger.debug(f"Patient group updated, contains {len(self.groups_dict)} groups")

    @handle_errors(
        error_message="Error getting groups from patient",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def GetGroups(self):
        groups = list(self.groups_dict.values())
        logger.debug(f"Getting {len(groups)} groups from patient")
        return groups

    @handle_errors(
        error_message="Error getting DICOM sample from patient",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def GetDicomSample(self):
        sample = list(self.groups_dict.values())[0].GetDicomSample()
        logger.debug("Getting DICOM sample from patient group")
        return sample

    @handle_errors(
        error_message="Error fixing Problem 1 in patient group",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def FixProblem1(self, dict):
        # Let's check if <dicom.acquisition.series_number> and
        # <dicom.image.number> were swapped and fix it.
        # TODO: Check if this is the optimal solution:
        # dict_ is a dict of DicomGroup objects
        # TODO: Optimize this algorithm to handle few groups with many slices
        # mixed with many groups with a slice each
        # (maybe two passes?)
        # ---------------------------------------------------------
        # Sort groups by series_number as well by patient orientation.
        dict2 = {}
        for key in dict.keys():
            spname, idstudy, serie_number, patient_orientation, index = key
            if not (spname, idstudy, patient_orientation) in dict2:
                dict2[(spname, idstudy, patient_orientation)] = []
            dict2[(spname, idstudy, patient_orientation)].append(dict[key])

        dict3 = {}
        # Merge groups with only one slice
        logger.debug("Fixing Problem 1 by merging groups with only one slice")
        for key in dict2.keys():
            group_list = dict2[key]

            # Groups with several slices
            new_list = [g for g in group_list if g.nslices > 1]

            # Groups with a slice each
            if len(new_list) != len(group_list):
                temp_list = [g for g in group_list if g.nslices == 1]
                if temp_list:
                    # Check if all slices are from the same series
                    # (means Problem 1 is happening)
                    # By now, all Dicoms inside a group have the
                    # same series_number. So we can check the first
                    # dicom.acquisition.series_number of each group inside
                    # temp_list.

                    # Compare first item's class
                    class0 = temp_list[0].GetHandSortedList()[0].acquisition.series_class
                    all_same_class = True
                    for i in range(1, len(temp_list)):
                        # Compare class with first item's class
                        if class0 != temp_list[i].GetHandSortedList()[0].acquisition.series_class:
                            all_same_class = False
                            break

                    if all_same_class:
                        # Create merged group
                        merged_group = DicomGroup()
                        merged_group.key = temp_list[0].key
                        # TODO: Create a better name
                        merged_group.title = temp_list[0].title

                        for dg in temp_list:
                            dicom = dg.GetHandSortedList()[0]
                            merged_group.AddSlice(dicom)

                        # Update Z Spacing
                        merged_group.UpdateZSpacing()

                        # Add to new_list
                        new_list.append(merged_group)

            dict2[key] = new_list

        # For each key, add back the groups (already fixed)
        for key in dict2.keys():
            for g in dict2[key]:
                # Create new key with original group information
                # and add it to the group
                if key not in dict3:
                    dict3[key] = {}
                group_key = (g.key[0], g.key[1], g.key[2], g.key[3], 0)
                dict3[key][group_key] = g
                # Update z_spacing once more (TODO: Necessary?)
                g.UpdateZSpacing()

        # Now, for each dict3[key], check if values can be merged
        # based on number slices (autonumber)
        # eg.
        # 1° slice of first series
        # 2° slice of first series
        # ...
        # n° slice of first series
        # 1° slice of second series
        # ...
        # dict3[key] = {group_key: dicom_group}
        # groups_by_num = {number_of_slices: [dicom_group, ...]}
        groups_dict = {}
        for key in dict3.keys():
            groups_by_num = {}
            for gkey in dict3[key]:
                g = dict3[key][gkey]
                if g.nslices not in groups_by_num:
                    groups_by_num[g.nslices] = []
                groups_by_num[g.nslices].append(g)

            # Now, if we have multiple groups with same number of slices,
            # check if we can group them
            for n in groups_by_num.keys():
                if len(groups_by_num[n]) > 1:
                    # As we have different DICOMs, we need to
                    # know what distinguishes two series from one
                    # another

                    # 1° of 1° series - d1
                    # 1° of 2° series - d2
                    # TODO: Create a good rule here to differentiate more
                    # than 2 series with n slices each
                    d1 = groups_by_num[n][0].GetHandSortedList()[0]
                    d2 = groups_by_num[n][1].GetHandSortedList()[0]
                    if d1.acquisition.series_description == d2.acquisition.series_description:
                        if d1.acquisition.serie_number != d2.acquisition.serie_number:
                            # Create merged group
                            for g in groups_by_num[n][1:]:
                                # Add slices from subsequent groups to our
                                # first group
                                list_ = g.GetHandSortedList()
                                for item in list_:
                                    groups_by_num[n][0].AddSlice(item)
                            # Update our list with only first group
                            groups_by_num[n] = [groups_by_num[n][0]]

            # Back to our original dict structure
            for n in groups_by_num.keys():
                for g in groups_by_num[n]:
                    # Group key needed for reference (same as the one used in CreateDicomGroup)
                    if g.key not in groups_dict:
                        groups_dict[g.key] = g

        return groups_dict


# This class is used by dicom_reader.py to group DICOM files
class DicomGroups:
    def __init__(self):
        self.patients = {}
        logger.debug("DicomGroups initialized")

    @handle_errors(
        error_message="Error adding file to DICOM groups",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def AddFile(self, dicom):
        patient_key = (dicom.patient.name, dicom.patient.id)
        logger.debug(f"Adding file to DICOM groups, patient key: {patient_key}")

        if patient_key not in self.patients:
            self.patients[patient_key] = PatientGroup()
            logger.debug(f"Created new patient group with key {patient_key}")

        self.patients[patient_key].AddFile(dicom)

    @handle_errors(
        error_message="Error updating DICOM groups",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.WARNING,
    )
    def Update(self):
        for patient_group in self.patients.values():
            patient_group.Update()
        logger.debug("Updated all DICOM groups")

    @handle_errors(
        error_message="Error getting patients groups",
        category=ErrorCategory.DICOM,
        severity=ErrorSeverity.ERROR,
    )
    def GetPatientsGroups(self):
        patients_groups = list(self.patients.values())
        logger.info(f"Returning {len(patients_groups)} patient groups")
        return patients_groups


# Legacy class for backward compatibility
# This class is being replaced by DicomGroups
class DicomPatientGrouper:
    """
    DEPRECATED: Use DicomGroups instead.
    This class is maintained for backward compatibility.
    """

    def __init__(self):
        self.dicom_groups = DicomGroups()
        logger.warning("DicomPatientGrouper is deprecated, use DicomGroups instead")

    def AddFile(self, dicom):
        return self.dicom_groups.AddFile(dicom)

    def Update(self):
        return self.dicom_groups.Update()

    def GetPatientsGroups(self):
        return self.dicom_groups.GetPatientsGroups()
