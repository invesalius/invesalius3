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

    def GetFilenameList(self):
        # Should be called when user selects this group
        # This list will be used to create the vtkImageData
        # (interpolated)

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
            sorter.Sort([utils.encode(i, const.FS_ENCODE) for i in filelist])
        except TypeError:
            sorter.Sort(filelist)
        filelist = sorter.GetFilenames()

        # for breast-CT of koning manufacturing (KBCT)
        if list(self.slices_dict.values())[0].parser.GetManufacturerName() == "Koning":
            filelist.sort()

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

    def UpdateZSpacing(self):
        list_ = self.GetHandSortedList()

        if len(list_) > 1:
            dicom = list_[0]
            axis = ORIENT_MAP[dicom.image.orientation_label]
            p1 = dicom.image.position[axis]

            dicom = list_[1]
            p2 = dicom.image.position[axis]

            self.zspacing = abs(p1 - p2)
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
                # TODO: Optimize recursion
                self.AddFile(dicom, index + 1)

            # Getting the spacing in the Z axis
            group.UpdateZSpacing()

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
            utils.debug("Problem1")
            self.groups_dict = self.FixProblem1(self.groups_dict)

    def GetGroups(self):
        glist = self.groups_dict.values()
        glist = sorted(glist, key=lambda group: group.title, reverse=True)
        return glist

    def GetDicomSample(self):
        return self.dicom

    def FixProblem1(self, dict):
        """
        Merge multiple DICOM groups in case Problem 1 (description
        above) occurs.

        WARN: We've implemented an heuristic to try to solve
        the problem. There is no scientific background and this aims
        to be a workaround to exams which are not in conformance with
        the DICOM protocol.
        """
        # Divide existing groups into 2 groups:
        dict_final = {}  # 1
        # those containing "3D photos" and undefined
        # orientation - these won't be changed (groups_lost).

        dict_to_change = {}  # 2
        # which can be re-grouped according to our heuristic

        # split existing groups in these two types of group, based on
        # orientation label

        # 1st STEP: RE-GROUP
        for group_key in dict:
            # values used as key of the new dictionary
            dicom = dict[group_key].GetList()[0]
            orientation = dicom.image.orientation_label
            study_id = dicom.acquisition.id_study
            # if axial, coronal or sagittal
            if orientation in ORIENT_MAP:
                group_key_s = (orientation, study_id)
                # If this method was called, there is only one slice
                # in this group (dicom)
                dicom = dict[group_key].GetList()[0]
                if group_key_s not in dict_to_change.keys():
                    group = DicomGroup()
                    group.AddSlice(dicom)
                    dict_to_change[group_key_s] = group
                else:
                    group = dict_to_change[group_key_s]
                    group.AddSlice(dicom)
            else:
                dict_final[group_key] = dict[group_key]

        # group_counter will be used as key to DicomGroups created
        # while checking differences
        group_counter = 0
        for group_key in dict_to_change:
            # 2nd STEP: SORT
            sorted_list = dict_to_change[group_key].GetHandSortedList()

            # 3rd STEP: CHECK DIFFERENCES
            axis = ORIENT_MAP[group_key[0]]  # based on orientation
            for index in range(len(sorted_list) - 1):
                current = sorted_list[index]
                # next = sorted_list[index + 1]

                pos_current = current.image.position[axis]
                pos_next = current.image.position[axis]
                spacing = current.image.spacing

                if (pos_next - pos_current) <= (spacing[2] * 2):
                    if group_counter in dict_final:
                        dict_final[group_counter].AddSlice(current)
                    else:
                        group = DicomGroup()
                        group.AddSlice(current)
                        dict_final[group_counter] = group
                        # Getting the spacing in the Z axis
                        group.UpdateZSpacing()
                else:
                    group_counter += 1
                    group = DicomGroup()
                    group.AddSlice(current)
                    dict_final[group_counter] = group
                    # Getting the spacing in the Z axis
                    group.UpdateZSpacing()

        return dict_final


class DicomPatientGrouper:
    # read file, check if it is dicom...
    # dicom = dicom.Dicom
    # grouper = DicomPatientGrouper()
    # grouper.AddFile(dicom)
    # ... (repeat to all files on folder)
    # grouper.Update()
    # groups = GetPatientGroups()

    def __init__(self):
        self.patients_dict = {}

    def AddFile(self, dicom):
        patient_key = (dicom.patient.name, dicom.patient.id)

        # Does this patient exist?
        if patient_key not in self.patients_dict.keys():
            patient = PatientGroup()
            patient.key = patient_key
            patient.AddFile(dicom)
            self.patients_dict[patient_key] = patient
        # Patient exists... Lets add group to it
        else:
            patient = self.patients_dict[patient_key]
            patient.AddFile(dicom)

    def Update(self):
        for patient in self.patients_dict.values():
            patient.Update()

    def GetPatientsGroups(self):
        """
        How to use:
        patient_list = grouper.GetPatientsGroups()
        for patient in patient_list:
            group_list = patient.GetGroups()
            for group in group_list:
                group.GetList()
                # :) you've got a list of dicom.Dicom
                # of the same series
        """
        plist = self.patients_dict.values()
        plist = sorted(plist, key=lambda patient: patient.key[0])
        return plist
