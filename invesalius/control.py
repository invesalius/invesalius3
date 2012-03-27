#--------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
#--------------------------------------------------------------------------
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
#--------------------------------------------------------------------------
import math
import os
import plistlib

import numpy
from wx.lib.pubsub import pub as Publisher

import constants as const
import data.imagedata_utils as utils
import data.mask as msk
import data.measures
import data.slice_ as sl
import data.surface as srf
import data.volume as volume
import gui.dialogs as dialog
import project as prj
import reader.analyze_reader as analyze
import reader.dicom_grouper as dg
import reader.dicom_reader as dcm
import session as ses

from utils import debug

DEFAULT_THRESH_MODE = 0

class Controller():

    def __init__(self, frame):
        self.surface_manager = srf.SurfaceManager()
        self.volume = volume.Volume()
        self.__bind_events()
        self.frame = frame
        self.progress_dialog = None
        self.cancel_import = False
        #Init session
        session = ses.Session()
        self.measure_manager = data.measures.MeasurementManager()

        Publisher.sendMessage('Load Preferences')


    def __bind_events(self):
        Publisher.subscribe(self.OnImportMedicalImages, 'Import directory')
        Publisher.subscribe(self.OnShowDialogImportDirectory,
                                 'Show import directory dialog')
        Publisher.subscribe(self.OnShowDialogOpenProject,
                                 'Show open project dialog')

        Publisher.subscribe(self.OnShowDialogSaveProject, 'Show save dialog')

        Publisher.subscribe(self.LoadRaycastingPreset,
                                 'Load raycasting preset')
        Publisher.subscribe(self.SaveRaycastingPreset,
                                 'Save raycasting preset')
        Publisher.subscribe(self.OnOpenDicomGroup,
                                 'Open DICOM group')
        Publisher.subscribe(self.Progress, "Update dicom load")
        Publisher.subscribe(self.OnLoadImportPanel, "End dicom load")
        Publisher.subscribe(self.OnCancelImport, 'Cancel DICOM load')
        Publisher.subscribe(self.OnShowDialogCloseProject, 'Close Project')
        Publisher.subscribe(self.OnOpenProject, 'Open project')
        Publisher.subscribe(self.OnOpenRecentProject, 'Open recent project')
        Publisher.subscribe(self.OnShowAnalyzeFile, 'Show analyze dialog')

    def OnCancelImport(self, pubsub_evt):
        #self.cancel_import = True
        Publisher.sendMessage('Hide import panel')


###########################
###########################

    def OnShowDialogImportDirectory(self, pubsub_evt):
        self.ShowDialogImportDirectory()

    def OnShowDialogOpenProject(self, pubsub_evt):
        self.ShowDialogOpenProject()

    def OnShowDialogSaveProject(self, pubsub_evt):
        saveas = pubsub_evt.data
        self.ShowDialogSaveProject(saveas)

    def OnShowDialogCloseProject(self, pubsub_evt):
        self.ShowDialogCloseProject()

    def OnShowAnalyzeFile(self, pubsub_evt):
        dirpath = dialog.ShowOpenAnalyzeDialog()
        imagedata = analyze.ReadAnalyze(dirpath)
        if imagedata:
            self.CreateAnalyzeProject(imagedata)
            
        self.LoadProject()
        Publisher.sendMessage("Enable state project", True)


###########################

    def ShowDialogImportDirectory(self):
        # Offer to save current project if necessary
        session = ses.Session()
        st = session.project_status
        if (st == const.PROJ_NEW) or (st == const.PROJ_CHANGE):
            filename = session.project_path[1]
            answer = dialog.SaveChangesDialog2(filename)
            if answer:
                self.ShowDialogSaveProject()
        # Import project
        dirpath = dialog.ShowImportDirDialog()
        if dirpath and not os.listdir(dirpath):
            dialog.ImportEmptyDirectory(dirpath)
        elif dirpath:
            self.StartImportPanel(dirpath)
            Publisher.sendMessage("Load data to import panel", dirpath)

    def ShowDialogOpenProject(self):
        # Offer to save current project if necessary
        session = ses.Session()
        st = session.project_status
        if (st == const.PROJ_NEW) or (st == const.PROJ_CHANGE):
            filename = session.project_path[1]
            answer = dialog.SaveChangesDialog2(filename)
            if answer:
                self.ShowDialogSaveProject()

        # Open project
        filepath = dialog.ShowOpenProjectDialog()
        if filepath:
            self.CloseProject()
            self.OpenProject(filepath)

    def ShowDialogSaveProject(self, saveas=False):
        session = ses.Session()
        if saveas or session.temp_item:
            proj = prj.Project()
            filepath = dialog.ShowSaveAsProjectDialog(proj.name)
            if filepath:
                #session.RemoveTemp()
                session.OpenProject(filepath)
            else:
                return
        else:
            dirpath, filename = session.project_path
            filepath = os.path.join(dirpath, filename)

        self.SaveProject(filepath)


    def ShowDialogCloseProject(self):
        session = ses.Session()
        st = session.project_status
        if st == const.PROJ_CLOSE:
            return -1
        try:
            filename = session.project_path[1]
        except(AttributeError):
            debug("Project doesn't exist")
            filename = None

        if (filename):
            if (st == const.PROJ_NEW) or (st == const.PROJ_CHANGE):
                answer = dialog.SaveChangesDialog(filename, self.frame)
                if not answer:
                    debug("Close without changes")
                    self.CloseProject()
                    Publisher.sendMessage("Enable state project", False)
                    Publisher.sendMessage('Set project name')
                    Publisher.sendMessage("Stop Config Recording")
                    Publisher.sendMessage("Exit")
                elif answer == 1:
                    self.ShowDialogSaveProject()
                    debug("Save changes and close")
                    self.CloseProject()
                    Publisher.sendMessage("Enable state project", False)
                    Publisher.sendMessage('Set project name')
                    Publisher.sendMessage("Stop Config Recording")
                    Publisher.sendMessage("Exit")
                elif answer == -1:
                    debug("Cancel")
            else:
                self.CloseProject()
                Publisher.sendMessage("Enable state project", False)
                Publisher.sendMessage('Set project name')
                Publisher.sendMessage("Stop Config Recording")
                Publisher.sendMessage("Exit")

        else:
            Publisher.sendMessage('Stop Config Recording')
            Publisher.sendMessage('Exit')


###########################
    def OnOpenProject(self, pubsub_evt):
        path = pubsub_evt.data
        self.OpenProject(path)

    def OnOpenRecentProject(self, pubsub_evt):
        filepath = pubsub_evt.data

        if os.path.exists(filepath):
            session = ses.Session()
            st = session.project_status
            if (st == const.PROJ_NEW) or (st == const.PROJ_CHANGE):
                filename = session.project_path[1]
                answer = dialog.SaveChangesDialog2(filename)
                if answer:
                    self.ShowDialogSaveProject()
            self.CloseProject()
            self.OpenProject(filepath)
        else:
            dialog.InexistentPath(filepath)



    def OpenProject(self, filepath):
        Publisher.sendMessage('Begin busy cursor')
        path = os.path.abspath(filepath)

        proj = prj.Project()
        proj.OpenPlistProject(path)
        proj.SetAcquisitionModality(proj.modality)
        self.Slice = sl.Slice()
        self.Slice._open_image_matrix(proj.matrix_filename,
                                      tuple(proj.matrix_shape),
                                      proj.matrix_dtype)

        self.Slice.window_level = proj.level
        self.Slice.window_width = proj.window

        mask = msk.Mask()
        mask._set_class_index(proj.last_mask_index)
        self.mask_dict_copy = proj.mask_dict.copy()

        surface = srf.Surface()
        surface._set_class_index(proj.last_surface_index)

        self.LoadProject()

        Publisher.sendMessage('Update threshold limits',
                                   proj.threshold_range)
        session = ses.Session()
        session.OpenProject(filepath)
        Publisher.sendMessage("Enable state project", True)

    def SaveProject(self, path=None):
        Publisher.sendMessage('Begin busy cursor')
        session = ses.Session()
        if path:
            dirpath, filename = os.path.split(path)
            session.SaveProject((dirpath, filename))
        else:
            dirpath, filename = session.project_path

        proj = prj.Project()
        prj.Project().SavePlistProject(dirpath, filename)

        session.SaveProject()
        Publisher.sendMessage('End busy cursor')

    def CloseProject(self):
        proj = prj.Project()
        proj.Close()

        Publisher.sendMessage('Hide content panel')
        Publisher.sendMessage('Close project data')
        session = ses.Session()
        session.CloseProject()

###########################


    def StartImportPanel(self, path):

        # retrieve DICOM files splited into groups
        reader = dcm.ProgressDicomReader()
        reader.SetWindowEvent(self.frame)
        reader.SetDirectoryPath(path)
        Publisher.sendMessage('End busy cursor')

    def Progress(self, evt):
        data = evt.data
        if (data):
            message = _("Loading file %d of %d")%(data[0],data[1])
            if not(self.progress_dialog):
                self.progress_dialog = dialog.ProgressDialog(
                                    maximum = data[1], abort=1)
            else:
                if not(self.progress_dialog.Update(data[0],message)):
                    self.progress_dialog.Close()
                    self.progress_dialog = None
                    Publisher.sendMessage('Begin busy cursor')
        else:
            #Is None if user canceled the load
            self.progress_dialog.Close()
            self.progress_dialog = None

    def OnLoadImportPanel(self, evt):
        patient_series = evt.data
        ok = self.LoadImportPanel(patient_series)
        if ok:
            Publisher.sendMessage('Show import panel')
            Publisher.sendMessage("Show import panel in frame")


    def LoadImportPanel(self, patient_series):
        if patient_series and isinstance(patient_series, list):
            Publisher.sendMessage("Load import panel", patient_series)
            first_patient = patient_series[0]
            Publisher.sendMessage("Load dicom preview", first_patient)
            return True
        else:
            dialog.ImportInvalidFiles()
        return False

    def OnImportMedicalImages(self, pubsub_evt):
        directory = pubsub_evt.data
        self.ImportMedicalImages(directory)

    def ImportMedicalImages(self, directory):
        # OPTION 1: DICOM?
        patients_groups = dcm.GetDicomGroups(directory)
        if len(patients_groups):
            group = dcm.SelectLargerDicomGroup(patients_groups)
            matrix, matrix_filename, dicom = self.OpenDicomGroup(group, 0, [0,0],gui=True)
            self.CreateDicomProject(dicom, matrix, matrix_filename)
        # OPTION 2: ANALYZE?
        else:
            imagedata = analyze.ReadDirectory(directory)
            if imagedata:
                self.CreateAnalyzeProject(imagedata)
            # OPTION 3: Nothing...
            else:
                debug("No medical images found on given directory")
                return
        self.LoadProject()
        Publisher.sendMessage("Enable state project", True)

    def LoadProject(self):
        proj = prj.Project()
        
        const.THRESHOLD_OUTVALUE = proj.threshold_range[0]
        const.THRESHOLD_INVALUE = proj.threshold_range[1]

        const.WINDOW_LEVEL[_('Default')] = (proj.window, proj.level)
        const.WINDOW_LEVEL[_('Manual')] = (proj.window, proj.level)

        self.Slice = sl.Slice()
        self.Slice.spacing = proj.spacing

        Publisher.sendMessage('Load slice to viewer',
                        (proj.imagedata,
                        proj.mask_dict))

        
        Publisher.sendMessage('Load slice plane') 

        Publisher.sendMessage('Bright and contrast adjustment image',\
                                   (proj.window, proj.level))
        Publisher.sendMessage('Update window level value',\
                                    (proj.window, proj.level))

        Publisher.sendMessage('Set project name', proj.name)
        Publisher.sendMessage('Load surface dict',
                                    proj.surface_dict)
        Publisher.sendMessage('Hide surface items',
                                     proj.surface_dict)
        self.LoadImagedataInfo() # TODO: where do we insert this <<<?
        
        Publisher.sendMessage('Show content panel')
        Publisher.sendMessage('Update AUI')

        if len(proj.mask_dict):
            mask_index = len(proj.mask_dict) -1
            for m in proj.mask_dict.values():
                Publisher.sendMessage('Add mask',
                                           (m.index, m.name,
                                            m.threshold_range, m.colour))
            self.Slice.current_mask = proj.mask_dict[mask_index]
            Publisher.sendMessage('Show mask', (mask_index, True))
        else:
            mask_name = const.MASK_NAME_PATTERN % (1,)
            thresh = const.THRESHOLD_RANGE
            colour = const.MASK_COLOUR[0]

            Publisher.sendMessage('Create new mask',
                                       (mask_name, thresh, colour))

        Publisher.sendMessage('Load measurement dict',
                                    proj.measurement_dict)

        proj.presets.thresh_ct[_('Custom')] = proj.threshold_range
        
        Publisher.sendMessage('End busy cursor')

    def CreateAnalyzeProject(self, imagedata):
        header = imagedata.get_header()
        proj = prj.Project()
        proj.imagedata = None
        proj.name = _("Untitled")
        proj.SetAcquisitionModality("MRI")
        #TODO: Verify if all Analyse are in AXIAL orientation

        # To get  Z, X, Y (used by InVesaliu), not X, Y, Z
        matrix, matrix_filename = utils.analyze2mmap(imagedata)
        if header['orient'] == 0:
            proj.original_orientation =  const.AXIAL
        elif header['orient'] == 1:
            proj.original_orientation = const.CORONAL
        elif header['orient'] == 2:
            proj.original_orientation = const.SAGITAL
        else:
            proj.original_orientation =  const.SAGITAL

        proj.threshold_range = (header['glmin'],
                                header['glmax'])
        proj.window = proj.threshold_range[1] - proj.threshold_range[0]
        proj.level =  (0.5 * (proj.threshold_range[1] + proj.threshold_range[0]))

        self.Slice = sl.Slice()
        self.Slice.matrix = matrix
        self.Slice.matrix_filename = matrix_filename

        self.Slice.window_level = proj.level
        self.Slice.window_width = proj.window
        self.Slice.spacing = header.get_zooms()[:3]

        Publisher.sendMessage('Update threshold limits',
                                   proj.threshold_range)

    def CreateDicomProject(self, dicom, matrix, matrix_filename):
        name_to_const = {"AXIAL":const.AXIAL,
                         "CORONAL":const.CORONAL,
                         "SAGITTAL":const.SAGITAL}

        proj = prj.Project()
        proj.name = dicom.patient.name
        proj.modality = dicom.acquisition.modality
        proj.SetAcquisitionModality(dicom.acquisition.modality)
        proj.matrix_shape = matrix.shape
        proj.matrix_dtype = matrix.dtype.name
        proj.matrix_filename = matrix_filename
        #proj.imagedata = imagedata
        proj.dicom_sample = dicom
        proj.original_orientation =\
                    name_to_const[dicom.image.orientation_label]
        proj.window = float(dicom.image.window)
        proj.level = float(dicom.image.level)
        proj.threshold_range = (-1024, 3033)
        proj.spacing = self.Slice.spacing

        ######
        session = ses.Session()
        filename = proj.name+".inv3"

        filename = filename.replace("/", "") #Fix problem case other/Skull_DICOM

        dirpath = session.CreateProject(filename)
        #proj.SavePlistProject(dirpath, filename)

    def OnOpenDicomGroup(self, pubsub_evt):
        group, interval, file_range = pubsub_evt.data
        matrix, matrix_filename, dicom = self.OpenDicomGroup(group, interval, file_range, gui=True)
        self.CreateDicomProject(dicom, matrix, matrix_filename)
        self.LoadProject()
        Publisher.sendMessage("Enable state project", True)

    def OpenDicomGroup(self, dicom_group, interval, file_range, gui=True):
        # Retrieve general DICOM headers
        dicom = dicom_group.GetDicomSample()

        # Create imagedata
        interval += 1
        filelist = dicom_group.GetFilenameList()[::interval]
        if not filelist:
            debug("Not used the IPPSorter")
            filelist = [i.image.file for i in dicom_group.GetHandSortedList()[::interval]]
        
        if file_range != None and file_range[1] > file_range[0]:
            filelist = filelist[file_range[0]:file_range[1] + 1]

        print ">>>>>>>>>>>>>>>>>>",filelist 
        zspacing = dicom_group.zspacing * interval
        size = dicom.image.size
        bits = dicom.image.bits_allocad
        sop_class_uid = dicom.acquisition.sop_class_uid
        xyspacing = dicom.image.spacing
        orientation = dicom.image.orientation_label

        if sop_class_uid == '1.2.840.10008.5.1.4.1.1.7': #Secondary Capture Image Storage
            use_dcmspacing = 1
        else:
            use_dcmspacing = 0

        #imagedata = utils.CreateImageData(filelist, zspacing, xyspacing,size,
                                          #bits, use_dcmspacing)

        imagedata = None

        # 1(a): Fix gantry tilt, if any
        tilt_value = dicom.acquisition.tilt
        if (tilt_value) and (gui):
            # Tell user gantry tilt and fix, according to answer
            message = _("Fix gantry tilt applying the degrees below")
            value = -1*tilt_value
            tilt_value = dialog.ShowNumberDialog(message, value)
            imagedata = utils.FixGantryTilt(imagedata, tilt_value)
        elif (tilt_value) and not (gui):
            tilt_value = -1*tilt_value
            imagedata = utils.FixGantryTilt(imagedata, tilt_value)

        wl = float(dicom.image.level)
        ww = float(dicom.image.window)
        self.matrix, scalar_range, self.filename = utils.dcm2memmap(filelist, size,
                                                                    orientation)
        self.Slice = sl.Slice()
        self.Slice.matrix = self.matrix
        self.Slice.matrix_filename = self.filename

        if orientation == 'AXIAL':
            self.Slice.spacing = xyspacing[0], xyspacing[1], zspacing
        elif orientation == 'CORONAL':
            self.Slice.spacing = xyspacing[0], zspacing, xyspacing[1]
        elif orientation == 'SAGITTAL':
            self.Slice.spacing = zspacing, xyspacing[1], xyspacing[0]


        self.Slice.window_level = wl
        self.Slice.window_width = ww

        Publisher.sendMessage('Update threshold limits', scalar_range)

        return self.matrix, self.filename, dicom

    def LoadImagedataInfo(self):
        proj = prj.Project()

        thresh_modes =  proj.threshold_modes.keys()
        thresh_modes.sort()
        default_threshold = const.THRESHOLD_PRESETS_INDEX
        if proj.mask_dict:
            keys = proj.mask_dict.keys()
            last = max(keys)
            (a,b) = proj.mask_dict[last].threshold_range
            default_threshold = [a,b]
            min_ = proj.threshold_range[0]
            max_ = proj.threshold_range[1]
            if default_threshold[0] < min_:
                default_threshold[0] = min_
            if default_threshold[1] > max_:
                default_threshold[1] = max_
            [a,b] = default_threshold
            default_threshold = (a,b)
        Publisher.sendMessage('Set threshold modes',
                                (thresh_modes,default_threshold))

    def LoadRaycastingPreset(self, pubsub_evt=None):
        if pubsub_evt:
            label = pubsub_evt.data
        else:
            return

        if label != const.RAYCASTING_OFF_LABEL:
            if label in const.RAYCASTING_FILES.keys():
                path = os.path.join(const.RAYCASTING_PRESETS_DIRECTORY,
                                    const.RAYCASTING_FILES[label])
            else:
                path = os.path.join(const.RAYCASTING_PRESETS_DIRECTORY,
                                        label+".plist")
                if not os.path.isfile(path):
                    path = os.path.join(const.USER_RAYCASTING_PRESETS_DIRECTORY,
                                    label+".plist")
            preset = plistlib.readPlist(path)
            prj.Project().raycasting_preset = preset
            # Notify volume
            # TODO: Chamar grafico tb!
            Publisher.sendMessage('Update raycasting preset')
        else:
            prj.Project().raycasting_preset = 0
            Publisher.sendMessage('Update raycasting preset')
            Publisher.sendMessage("Hide raycasting volume")

    def SaveRaycastingPreset(self, pubsub_evt):
        preset_name = pubsub_evt.data
        preset = prj.Project().raycasting_preset
        preset['name'] = preset_name
        preset_dir = os.path.join(const.USER_RAYCASTING_PRESETS_DIRECTORY,
                                  preset_name + '.plist')
        plistlib.writePlist(preset, preset_dir)

