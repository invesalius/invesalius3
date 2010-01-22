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
import tempfile

import wx.lib.pubsub as ps

import constants as const
import project as prj

import data.imagedata_utils as utils
import data.mask as msk
import data.surface as srf
import data.volume as volume
import reader.dicom_grouper as dg
import gui.dialogs as dialog
import reader.dicom_reader as dcm
import reader.analyze_reader as analyze
import session as ses

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

    def __bind_events(self):
        ps.Publisher().subscribe(self.OnImportMedicalImages, 'Import directory')
        ps.Publisher().subscribe(self.OnShowDialogImportDirectory,
                                 'Show import directory dialog')
        ps.Publisher().subscribe(self.OnShowDialogOpenProject,
                                 'Show open project dialog')

        ps.Publisher().subscribe(self.OnShowDialogSaveProject, 'Show save dialog')

        ps.Publisher().subscribe(self.LoadRaycastingPreset,
                                 'Load raycasting preset')
        ps.Publisher().subscribe(self.SaveRaycastingPreset,
                                 'Save raycasting preset')
        ps.Publisher().subscribe(self.OnOpenDicomGroup,
                                 'Open DICOM group')
        ps.Publisher().subscribe(self.Progress, "Update dicom load")
        ps.Publisher().subscribe(self.OnLoadImportPanel, "End dicom load")
        ps.Publisher().subscribe(self.OnCancelImport, 'Cancel DICOM load')
        ps.Publisher().subscribe(self.OnShowDialogCloseProject, 'Close Project')
        ps.Publisher().subscribe(self.OnOpenProject, 'Open project')

    def OnCancelImport(self, pubsub_evt):
        #self.cancel_import = True
        ps.Publisher().sendMessage('Hide import panel')


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
        ###
        print dirpath
        if dirpath and not os.listdir(dirpath):
            dialog.ImportEmptyDirectory(dirpath)
        elif dirpath:
            self.StartImportPanel(dirpath)
            ps.Publisher().sendMessage("Load data to import panel", dirpath)

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
        print "ShowDialogCloseProject"
        session = ses.Session()
        st = session.project_status
        print "* st", st
        if st == const.PROJ_CLOSE:
            return -1
        filename = session.project_path[1]
        if (st == const.PROJ_NEW) or (st == const.PROJ_CHANGE):
            answer = dialog.SaveChangesDialog(filename)
            if not answer:
                print "Close without changes"
                self.CloseProject()
                ps.Publisher().sendMessage("Enable state project", False)
            elif answer == 1:
                self.ShowDialogSaveProject()
                print "Save changes and close"
                self.CloseProject()
                ps.Publisher().sendMessage("Enable state project", False)
            elif answer == -1:
                print "Cancel"
        else:
            self.CloseProject()
            ps.Publisher().sendMessage("Enable state project", False)

###########################
    def OnOpenProject(self, pubsub_evt):
        path = pubsub_evt.data
        self.OpenProject(path)


    def OpenProject(self, filepath):
        ps.Publisher().sendMessage('Begin busy cursor')
        path = os.path.abspath(filepath)

        proj = prj.Project()
        proj.OpenPlistProject(path)
        proj.SetAcquisitionModality(proj.modality)

        mask = msk.Mask()
        mask._set_class_index(proj.last_mask_index)

        surface = srf.Surface()
        surface._set_class_index(proj.last_surface_index)
        
        self.LoadProject()

        session = ses.Session()
        session.OpenProject(filepath)
        ps.Publisher().sendMessage("Enable state project", True)

    def SaveProject(self, path=None):
        ps.Publisher().sendMessage('Begin busy cursor')
        session = ses.Session()
        if path:
            dirpath, filename = os.path.split(path)
            session.SaveProject((dirpath, filename))
        else:
            dirpath, filename = session.project_path

        proj = prj.Project()
        prj.Project().SavePlistProject(dirpath, filename)

        session.SaveProject()
        ps.Publisher().sendMessage('End busy cursor')
        
    def CloseProject(self):
        proj = prj.Project()
        proj.Close()

        ps.Publisher().sendMessage('Hide content panel')
        ps.Publisher().sendMessage('Close project data')

        session = ses.Session()
        session.CloseProject()

###########################


    def StartImportPanel(self, path):

        # retrieve DICOM files splited into groups
        reader = dcm.ProgressDicomReader()
        reader.SetWindowEvent(self.frame)
        reader.SetDirectoryPath(path)
        ps.Publisher().sendMessage('End busy cursor')

    def Progress(self, evt):
        data = evt.data
        if (data):
            message = _("Loading file %d of %d")%(data[0],data[1])

        if (data):
            if not(self.progress_dialog):
                self.progress_dialog = dialog.ProgressDialog(
                                    maximum = data[1])
            else:
                if not(self.progress_dialog.Update(data[0],message)):
                    self.progress_dialog.Close()
                    self.progress_dialog = None
                    ps.Publisher().sendMessage('Begin busy cursor')
        else:
            #Is None if user canceled the load
            self.progress_dialog.Close()
            self.progress_dialog = None

    def OnLoadImportPanel(self, evt):
        patient_series = evt.data
        ok = self.LoadImportPanel(patient_series)
        if ok:
            ps.Publisher().sendMessage('Show import panel')
            ps.Publisher().sendMessage("Show import panel in frame")


    def LoadImportPanel(self, patient_series):
        if patient_series and isinstance(patient_series, list):
            ps.Publisher().sendMessage("Load import panel", patient_series)
            first_patient = patient_series[0]
            ps.Publisher().sendMessage("Load dicom preview", first_patient)
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
            imagedata, dicom = self.OpenDicomGroup(group, gui=True)
            self.CreateDicomProject(imagedata, dicom)
        # OPTION 2: ANALYZE?
        else:
            imagedata = analyze.ReadDirectory(directory)
            if imagedata:
                self.CreateAnalyzeProject(imagedata)
            # OPTION 3: Nothing...
            else:
                print "No medical images found on given directory"
                return
        self.LoadProject()
        ps.Publisher().sendMessage("Enable state project", True)

    def LoadProject(self):
        proj = prj.Project()

        const.THRESHOLD_OUTVALUE = proj.threshold_range[0]
        const.THRESHOLD_INVALUE = proj.threshold_range[1]
        const.WINDOW_LEVEL[_('Default')] = (proj.window, proj.level)
        const.WINDOW_LEVEL[_('Manual')] = (proj.window, proj.level)


        ps.Publisher().sendMessage('Set project name', proj.name)
        ps.Publisher().sendMessage('Load slice to viewer',
                                (proj.imagedata,
                                proj.mask_dict))
        ps.Publisher().sendMessage('Load surface dict',
                                    proj.surface_dict)
        self.LoadImagedataInfo() # TODO: where do we insert this <<<?
        ps.Publisher().sendMessage('Bright and contrast adjustment image',\
                                   (proj.window, proj.level))
        ps.Publisher().sendMessage('Update window level value',\
                                    (proj.window, proj.level))
        ps.Publisher().sendMessage('Show content panel')
        ps.Publisher().sendMessage('Update AUI')
        ps.Publisher().sendMessage('Load slice plane')
        ps.Publisher().sendMessage('End busy cursor')

    def CreateAnalyzeProject(self, imagedata):
        proj = prj.Project()
        proj.name = _("Untitled")
        proj.SetAcquisitionModality("MRI")
        proj.imagedata = imagedata
        #TODO: Verify if all Analyse are in AXIAL orientation
        proj.original_orientation =  const.AXIAL
        proj.threshold_range = imagedata.GetScalarRange()
        proj.window = proj.threshold_range[1] - proj.threshold_range[0]
        proj.level =  (0.5 * (proj.threshold_range[1] + proj.threshold_range[0]))


    def CreateDicomProject(self, imagedata, dicom):
        name_to_const = {"AXIAL":const.AXIAL,
                         "CORONAL":const.CORONAL,
                         "SAGITTAL":const.SAGITAL}

        proj = prj.Project()
        proj.name = dicom.patient.name
        proj.modality = dicom.acquisition.modality
        proj.SetAcquisitionModality(dicom.acquisition.modality)
        proj.imagedata = imagedata
        #proj.dicom = dicom
        proj.original_orientation =\
                    name_to_const[dicom.image.orientation_label]
        proj.window = float(dicom.image.window)
        proj.level = float(dicom.image.level)
        proj.threshold_range = imagedata.GetScalarRange()


        ######
        session = ses.Session()
        filename = proj.name+".inv3"

        filename = filename.replace("/", "") #Fix problem case other/Skull_DICOM

        dirpath = session.CreateProject(filename)
        proj.SavePlistProject(dirpath, filename)



    def OnOpenDicomGroup(self, pubsub_evt):
        group = pubsub_evt.data
        imagedata, dicom = self.OpenDicomGroup(group, gui=True)
        self.CreateDicomProject(imagedata, dicom)
        self.LoadProject()
        ps.Publisher().sendMessage("Enable state project", True)

    def OpenDicomGroup(self, dicom_group, gui=True):

        # Retrieve general DICOM headers
        dicom = dicom_group.GetDicomSample()

        # Create imagedata
        filelist = dicom_group.GetFilenameList()
        if not filelist:
            print ">Not used the IPPSorter"
            filelist = [i.image.file for i in dicom_group.GetHandSortedList()]
        zspacing = dicom_group.zspacing
        size = dicom.image.size
        bits = dicom.image.bits_allocad

        imagedata = utils.CreateImageData(filelist, zspacing, size, bits)

        # 1(a): Fix gantry tilt, if any
        tilt_value = dicom.acquisition.tilt
        if (tilt_value) and (gui):
            # Tell user gantry tilt and fix, according to answer
            message = _("Fix gantry tilt applying the degrees bellow")
            value = -1*tilt_value
            tilt_value = dialog.ShowNumberDialog(message, value)
            imagedata = utils.FixGantryTilt(imagedata, tilt_value)
        elif (tilt_value) and not (gui):
            tilt_value = -1*tilt_value
            imagedata = utils.FixGantryTilt(imagedata, tilt_value)

        return imagedata, dicom

    def LoadImagedataInfo(self):
        proj = prj.Project()

        thresh_modes =  proj.threshold_modes.keys()
        thresh_modes.sort()

        default_threshold = const.THRESHOLD_PRESETS_INDEX
        if proj.mask_dict:
            last = max(proj.mask_dict.keys())
            default_threshold = proj.mask_dict[last].threshold_range
        ps.Publisher().sendMessage('Set threshold modes',
                                (thresh_modes,default_threshold))

    def LoadRaycastingPreset(self, pubsub_evt):
        label = pubsub_evt.data
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
            ps.Publisher().sendMessage('Update raycasting preset')
        else:
            prj.Project().raycasting_preset = 0
            ps.Publisher().sendMessage('Update raycasting preset')
            ps.Publisher().sendMessage("Hide raycasting volume")

    def SaveRaycastingPreset(self, pubsub_evt):
        preset_name = pubsub_evt.data
        preset = prj.Project().raycasting_preset
        preset['name'] = preset_name
        preset_dir = os.path.join(const.USER_RAYCASTING_PRESETS_DIRECTORY,
                                  preset_name + '.plist')
        plistlib.writePlist(preset, preset_dir)





