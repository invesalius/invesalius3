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
import os
import plistlib
import wx
from wx.lib.pubsub import pub as Publisher

import invesalius.constants as const
import invesalius.data.imagedata_utils as image_utils
import invesalius.data.mask as msk
import invesalius.data.measures as measures
import invesalius.data.slice_ as sl
import invesalius.data.surface as srf
import invesalius.data.volume as volume
import invesalius.gui.dialogs as dialog
import invesalius.project as prj
import invesalius.reader.dicom_grouper as dg
import invesalius.reader.dicom_reader as dcm
import invesalius.reader.bitmap_reader as bmp
import invesalius.reader.others_reader as oth
import invesalius.session as ses


import invesalius.utils  as utils
import invesalius.gui.dialogs as dialogs
import subprocess
import sys

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
        self.measure_manager = measures.MeasurementManager()

        Publisher.sendMessage('Load Preferences')

    def __bind_events(self):
        Publisher.subscribe(self.OnImportMedicalImages, 'Import directory')
        Publisher.subscribe(self.OnShowDialogImportDirectory,
                                 'Show import directory dialog')
        Publisher.subscribe(self.OnShowDialogImportOtherFiles,
                                 'Show import other files dialog')
        Publisher.subscribe(self.OnShowDialogOpenProject,
                                 'Show open project dialog')

        Publisher.subscribe(self.OnShowDialogSaveProject, 'Show save dialog')

        Publisher.subscribe(self.LoadRaycastingPreset,
                                 'Load raycasting preset')
        Publisher.subscribe(self.SaveRaycastingPreset,
                                 'Save raycasting preset')
        Publisher.subscribe(self.OnOpenDicomGroup,
                                 'Open DICOM group')
        Publisher.subscribe(self.OnOpenBitmapFiles,
                                 'Open bitmap files')
        Publisher.subscribe(self.OnOpenOtherFiles,
                                 'Open other files')
        Publisher.subscribe(self.Progress, "Update dicom load")
        Publisher.subscribe(self.Progress, "Update bitmap load")
        Publisher.subscribe(self.OnLoadImportPanel, "End dicom load")
        Publisher.subscribe(self.OnLoadImportBitmapPanel, "End bitmap load")
        Publisher.subscribe(self.OnCancelImport, 'Cancel DICOM load')
        Publisher.subscribe(self.OnCancelImportBitmap, 'Cancel bitmap load')

        Publisher.subscribe(self.OnShowDialogCloseProject, 'Close Project')
        Publisher.subscribe(self.OnOpenProject, 'Open project')
        Publisher.subscribe(self.OnOpenRecentProject, 'Open recent project')
        Publisher.subscribe(self.OnShowBitmapFile, 'Show bitmap dialog')

        Publisher.subscribe(self.ShowBooleanOpDialog, 'Show boolean dialog')

        Publisher.subscribe(self.ApplyReorientation, 'Apply reorientation')

        Publisher.subscribe(self.SetBitmapSpacing, 'Set bitmap spacing')

    def SetBitmapSpacing(self, pubsub_evt):
        proj = prj.Project()
        proj.spacing = pubsub_evt.data

    def OnCancelImport(self, pubsub_evt):
        #self.cancel_import = True
        Publisher.sendMessage('Hide import panel')


    def OnCancelImportBitmap(self, pubsub_evt):
        #self.cancel_import = True
        Publisher.sendMessage('Hide import bitmap panel')

###########################
###########################

    def OnShowDialogImportDirectory(self, pubsub_evt):
        self.ShowDialogImportDirectory()

    def OnShowDialogImportOtherFiles(self, pubsub_evt):
        id_type = pubsub_evt.data
        self.ShowDialogImportOtherFiles(id_type)

    def OnShowDialogOpenProject(self, pubsub_evt):
        self.ShowDialogOpenProject()

    def OnShowDialogSaveProject(self, pubsub_evt):
        saveas = pubsub_evt.data
        self.ShowDialogSaveProject(saveas)

    def OnShowDialogCloseProject(self, pubsub_evt):
        self.ShowDialogCloseProject()

    def OnShowBitmapFile(self, pubsub_evt):
        self.ShowDialogImportBitmapFile()
###########################

    def ShowDialogImportBitmapFile(self):
        # Offer to save current project if necessary
        session = ses.Session()
        st = session.project_status
        if (st == const.PROJ_NEW) or (st == const.PROJ_CHANGE):
            filename = session.project_path[1]
            answer = dialog.SaveChangesDialog2(filename)
            if answer:
                self.ShowDialogSaveProject()
            self.CloseProject()
            #Publisher.sendMessage("Enable state project", False)
            Publisher.sendMessage('Set project name')
            Publisher.sendMessage("Stop Config Recording")
            Publisher.sendMessage("Set slice interaction style", const.STATE_DEFAULT)

        # Import TIFF, BMP, JPEG or PNG
        dirpath = dialog.ShowImportBitmapDirDialog()

        if dirpath and not os.listdir(dirpath):
            dialog.ImportEmptyDirectory(dirpath)
        elif dirpath:
            self.StartImportBitmapPanel(dirpath)
        #    Publisher.sendMessage("Load data to import panel", dirpath)

    def ShowDialogImportDirectory(self):
        # Offer to save current project if necessary
        session = ses.Session()
        st = session.project_status
        if (st == const.PROJ_NEW) or (st == const.PROJ_CHANGE):
            filename = session.project_path[1]
            answer = dialog.SaveChangesDialog2(filename)
            if answer:
                self.ShowDialogSaveProject()
            self.CloseProject()
            #Publisher.sendMessage("Enable state project", False)
            Publisher.sendMessage('Set project name')
            Publisher.sendMessage("Stop Config Recording")
            Publisher.sendMessage("Set slice interaction style", const.STATE_DEFAULT)
        # Import project
        dirpath = dialog.ShowImportDirDialog()
        if dirpath and not os.listdir(dirpath):
            dialog.ImportEmptyDirectory(dirpath)
        elif dirpath:
            self.StartImportPanel(dirpath)
            Publisher.sendMessage("Load data to import panel", dirpath)

    def ShowDialogImportOtherFiles(self, id_type):
        # Offer to save current project if necessary
        session = ses.Session()
        st = session.project_status
        if (st == const.PROJ_NEW) or (st == const.PROJ_CHANGE):
            filename = session.project_path[1]
            answer = dialog.SaveChangesDialog2(filename)
            if answer:
                self.ShowDialogSaveProject()
            self.CloseProject()
            # Publisher.sendMessage("Enable state project", False)
            Publisher.sendMessage('Set project name')
            Publisher.sendMessage("Stop Config Recording")
            Publisher.sendMessage("Set slice interaction style", const.STATE_DEFAULT)

        # Warning for limited support to Analyze format
        if id_type == const.ID_ANALYZE_IMPORT:
            dialog.ImportAnalyzeWarning()

        # Import project treating compressed nifti exception
        suptype = ('hdr', 'nii', 'nii.gz', 'par')
        filepath = dialog.ShowImportOtherFilesDialog(id_type)
        name = filepath.rpartition('\\')[-1].split('.')

        if name[-1] == 'gz':
            name[1] = 'nii.gz'

        filetype = name[1].lower()

        if filetype in suptype:
            Publisher.sendMessage("Open other files", filepath)
        else:
            dialog.ImportInvalidFiles()

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
            if session.IsOpen():
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
            utils.debug("Project doesn't exist")
            filename = None

        if (filename):
            if (st == const.PROJ_NEW) or (st == const.PROJ_CHANGE):
                answer = dialog.SaveChangesDialog(filename, self.frame)
                if not answer:
                    utils.debug("Close without changes")
                    self.CloseProject()
                    Publisher.sendMessage("Enable state project", False)
                    Publisher.sendMessage('Set project name')
                    Publisher.sendMessage("Stop Config Recording")
                elif answer == 1:
                    self.ShowDialogSaveProject()
                    utils.debug("Save changes and close")
                    self.CloseProject()
                    Publisher.sendMessage("Enable state project", False)
                    Publisher.sendMessage('Set project name')
                    Publisher.sendMessage("Stop Config Recording")
                elif answer == -1:
                    utils.debug("Cancel")
            else:
                self.CloseProject()
                Publisher.sendMessage("Enable state project", False)
                Publisher.sendMessage('Set project name')
                Publisher.sendMessage("Stop Config Recording")

        else:
            Publisher.sendMessage('Stop Config Recording')


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
            if session.IsOpen():
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

        Publisher.sendMessage('Update threshold limits list',
                                   proj.threshold_range)

        self.LoadProject()

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
        Publisher.sendMessage('Set slice interaction style', const.STATE_DEFAULT)
        session = ses.Session()
        session.CloseProject()

###########################

    def StartImportBitmapPanel(self, path):
        # retrieve DICOM files splited into groups
        reader = bmp.ProgressBitmapReader()
        reader.SetWindowEvent(self.frame)
        reader.SetDirectoryPath(path)
        Publisher.sendMessage('End busy cursor')

    def StartImportPanel(self, path):

        # retrieve DICOM files split into groups
        reader = dcm.ProgressDicomReader()
        reader.SetWindowEvent(self.frame)
        reader.SetDirectoryPath(path)
        Publisher.sendMessage('End busy cursor')

    def Progress(self, evt):
        data = evt.data
        if (data):
            message = _("Loading file %d of %d ...")%(data[0],data[1])
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

    def OnLoadImportBitmapPanel(self, evt):
        data = evt.data
        ok = self.LoadImportBitmapPanel(data)
        if ok:
            Publisher.sendMessage('Show import bitmap panel in frame')            
            #Publisher.sendMessage("Show import panel in invesalius.gui.frame") as frame

    def LoadImportBitmapPanel(self, data):
        #if patient_series and isinstance(patient_series, list):
            #Publisher.sendMessage("Load import panel", patient_series)
            #first_patient = patient_series[0]
            #Publisher.sendMessage("Load bitmap preview", first_patient)
        if  data:
            Publisher.sendMessage("Load import bitmap panel", data)
            return True
        else:
            dialog.ImportInvalidFiles("Bitmap")
        return False


    def LoadImportPanel(self, patient_series):
        if patient_series and isinstance(patient_series, list):
            Publisher.sendMessage("Load import panel", patient_series)
            first_patient = patient_series[0]
            Publisher.sendMessage("Load dicom preview", first_patient)
            return True
        else:
            dialog.ImportInvalidFiles("DICOM")
        return False


    #----------- to import by command line ---------------------------------------------------

    def OnImportMedicalImages(self, pubsub_evt):
        directory = pubsub_evt.data
        self.ImportMedicalImages(directory)

    def ImportMedicalImages(self, directory):
        patients_groups = dcm.GetDicomGroups(directory)
        name = directory.rpartition('\\')[-1].split('.')
        print "patients: ", patients_groups

        if len(patients_groups):
            # OPTION 1: DICOM
            group = dcm.SelectLargerDicomGroup(patients_groups)
            matrix, matrix_filename, dicom = self.OpenDicomGroup(group, 0, [0, 0], gui=True)
            self.CreateDicomProject(dicom, matrix, matrix_filename)
        else:
            # OPTION 2: NIfTI, Analyze or PAR/REC
            if name[-1] == 'gz':
                name[1] = 'nii.gz'

            suptype = ('hdr', 'nii', 'nii.gz', 'par')
            filetype = name[1].lower()

            if filetype in suptype:
                group = oth.ReadOthers(directory)
            else:
                utils.debug("No medical images found on given directory")
                return

            matrix, matrix_filename = self.OpenOtherFiles(group)
            self.CreateOtherProject(str(name[0]), matrix, matrix_filename)
            # OPTION 4: Nothing...

        self.LoadProject()
        Publisher.sendMessage("Enable state project", True)

    #-------------------------------------------------------------------------------------

    def LoadProject(self):
        proj = prj.Project()
        
        const.THRESHOLD_OUTVALUE = proj.threshold_range[0]
        const.THRESHOLD_INVALUE = proj.threshold_range[1]
        const.THRESHOLD_RANGE = proj.threshold_modes[_("Bone")]

        const.WINDOW_LEVEL[_('Default')] = (proj.window, proj.level)
        const.WINDOW_LEVEL[_('Manual')] = (proj.window, proj.level)

        self.Slice = sl.Slice()
        self.Slice.spacing = proj.spacing

        Publisher.sendMessage('Load slice to viewer',
                        (proj.mask_dict))

        
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
                if m.is_shown:
                    self.Slice.current_mask = proj.mask_dict[mask_index]
                    Publisher.sendMessage('Show mask', (m.index, True))
                    Publisher.sendMessage('Change mask selected', m.index)
        else:
            mask_name = const.MASK_NAME_PATTERN % (1,)

            if proj.modality != "UNKNOWN":
                thresh = const.THRESHOLD_RANGE
            else:
                thresh = proj.threshold_range

            colour = const.MASK_COLOUR[0]
            Publisher.sendMessage('Create new mask',
                                       (mask_name, thresh, colour))

        Publisher.sendMessage('Load measurement dict',
                                    (proj.measurement_dict, self.Slice.spacing))

        Publisher.sendMessage(('Set scroll position', 'AXIAL'),proj.matrix_shape[0]/2)
        Publisher.sendMessage(('Set scroll position', 'SAGITAL'),proj.matrix_shape[1]/2)
        Publisher.sendMessage(('Set scroll position', 'CORONAL'),proj.matrix_shape[2]/2)
        
        Publisher.sendMessage('End busy cursor')

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
        proj.threshold_range = int(matrix.min()), int(matrix.max())
        proj.spacing = self.Slice.spacing

        ######
        session = ses.Session()
        filename = proj.name+".inv3"

        filename = filename.replace("/", "") #Fix problem case other/Skull_DICOM

        dirpath = session.CreateProject(filename)
        #proj.SavePlistProject(dirpath, filename)


    def CreateBitmapProject(self, bmp_data, rec_data, matrix, matrix_filename):
        name_to_const = {"AXIAL":const.AXIAL,
                         "CORONAL":const.CORONAL,
                         "SAGITTAL":const.SAGITAL}

        name = rec_data[0]
        orientation = rec_data[1]
        sp_x = float(rec_data[2])
        sp_y = float(rec_data[3])
        sp_z = float(rec_data[4])
        interval = int(rec_data[5])
        
        bits = bmp_data.GetFirstPixelSize()
        sx, sy = size =  bmp_data.GetFirstBitmapSize()
        
        proj = prj.Project()
        proj.name = name
        proj.modality = 'UNKNOWN'
        proj.SetAcquisitionModality(proj.modality)
        proj.matrix_shape = matrix.shape
        proj.matrix_dtype = matrix.dtype.name
        proj.matrix_filename = matrix_filename
        #proj.imagedata = imagedata
        #proj.dicom_sample = dicom

        proj.original_orientation =\
                    name_to_const[orientation.upper()]
        proj.window = float(matrix.max())
        proj.level = float(matrix.max()/4)
        
        proj.threshold_range = int(matrix.min()), int(matrix.max())
        #const.THRESHOLD_RANGE = proj.threshold_range

        proj.spacing = self.Slice.spacing

        ######
        session = ses.Session()
        filename = proj.name+".inv3"

        filename = filename.replace("/", "") #Fix problem case other/Skull_DICOM

        dirpath = session.CreateProject(filename)

    def CreateOtherProject(self, name, matrix, matrix_filename):
        name_to_const = {"AXIAL": const.AXIAL,
                         "CORONAL": const.CORONAL,
                         "SAGITTAL": const.SAGITAL}

        proj = prj.Project()
        proj.name = name
        proj.modality = 'MRI'
        proj.SetAcquisitionModality('MRI')
        proj.matrix_shape = matrix.shape
        proj.matrix_dtype = matrix.dtype.name
        proj.matrix_filename = matrix_filename

        # Orientation must be CORONAL in order to as_closes_canonical and
        # swap axis in img2memmap to work in a standardized way.
        # TODO: Create standard import image for all acquisition orientations
        orientation = 'CORONAL'

        proj.original_orientation =\
            name_to_const[orientation]

        proj.window = self.Slice.window_width
        proj.level = self.Slice.window_level
        proj.threshold_range = int(matrix.min()), int(matrix.max())
        proj.spacing = self.Slice.spacing

        ######
        session = ses.Session()
        filename = proj.name + ".inv3"

        filename = filename.replace("/", "")  # Fix problem case other/Skull_DICOM

        dirpath = session.CreateProject(filename)

    def OnOpenBitmapFiles(self, pubsub_evt):
        rec_data = pubsub_evt.data
        bmp_data = bmp.BitmapData()

        if bmp_data.IsAllBitmapSameSize():

            matrix, matrix_filename = self.OpenBitmapFiles(bmp_data, rec_data)
            
            self.CreateBitmapProject(bmp_data, rec_data, matrix, matrix_filename)

            self.LoadProject()
            Publisher.sendMessage("Enable state project", True)
        else:
            dialogs.BitmapNotSameSize()

    def OpenBitmapFiles(self, bmp_data, rec_data):

       name = rec_data[0]
       orientation = rec_data[1]
       sp_x = float(rec_data[2])
       sp_y = float(rec_data[3])
       sp_z = float(rec_data[4])
       interval = int(rec_data[5])
       
       interval += 1
       
       filelist = bmp_data.GetOnlyBitmapPath()[::interval]
       bits = bmp_data.GetFirstPixelSize()

       sx, sy = size =  bmp_data.GetFirstBitmapSize()
       n_slices = len(filelist)
       resolution_percentage = utils.calculate_resizing_tofitmemory(int(sx), int(sy), n_slices, bits/8)
       
       zspacing = sp_z * interval
       xyspacing = (sp_y, sp_x)

       if resolution_percentage < 1.0:

           re_dialog = dialog.ResizeImageDialog()
           re_dialog.SetValue(int(resolution_percentage*100))
           re_dialog_value = re_dialog.ShowModal()
           re_dialog.Close() 
           
           if re_dialog_value == wx.ID_OK:
               percentage = re_dialog.GetValue()
               resolution_percentage = percentage / 100.0
           else:
               return

           xyspacing = xyspacing[0] / resolution_percentage, xyspacing[1] / resolution_percentage
 

       
       self.matrix, scalar_range, self.filename = image_utils.bitmap2memmap(filelist, size,
                                                               orientation, (sp_z, sp_y, sp_x),resolution_percentage)


       self.Slice = sl.Slice()
       self.Slice.matrix = self.matrix
       self.Slice.matrix_filename = self.filename

       if orientation == 'AXIAL':
           self.Slice.spacing = xyspacing[0], xyspacing[1], zspacing
       elif orientation == 'CORONAL':
           self.Slice.spacing = xyspacing[0], zspacing, xyspacing[1]
       elif orientation == 'SAGITTAL':
           self.Slice.spacing = zspacing, xyspacing[1], xyspacing[0]
       
       self.Slice.window_level = float(self.matrix.max()/4)
       self.Slice.window_width = float(self.matrix.max())

       scalar_range = int(self.matrix.min()), int(self.matrix.max())
       Publisher.sendMessage('Update threshold limits list', scalar_range)

       return self.matrix, self.filename#, dicom


    def OnOpenDicomGroup(self, pubsub_evt):
        group, interval, file_range = pubsub_evt.data
        matrix, matrix_filename, dicom = self.OpenDicomGroup(group, interval, file_range, gui=True)
        self.CreateDicomProject(dicom, matrix, matrix_filename)
        self.LoadProject()
        Publisher.sendMessage("Enable state project", True)

    def OnOpenOtherFiles(self, pubsub_evt):
        filepath = pubsub_evt.data
        name = filepath.rpartition('\\')[-1].split('.')

        if name[-1] == 'gz':
            name[1] = 'nii.gz'

        suptype = ('hdr', 'nii', 'nii.gz', 'par')
        filetype = name[1].lower()

        if filetype in suptype:
            group = oth.ReadOthers(filepath)
        else:
            dialog.ImportInvalidFiles()

        matrix, matrix_filename = self.OpenOtherFiles(group)
        self.CreateOtherProject(str(name[0]), matrix, matrix_filename)
        self.LoadProject()
        Publisher.sendMessage("Enable state project", True)

    def OpenDicomGroup(self, dicom_group, interval, file_range, gui=True):
        # Retrieve general DICOM headers
        dicom = dicom_group.GetDicomSample()

        # Create imagedata
        interval += 1
        filelist = dicom_group.GetFilenameList()[::interval]
        if not filelist:
            utils.debug("Not used the IPPSorter")
            filelist = [i.image.file for i in dicom_group.GetHandSortedList()[::interval]]
        
        if file_range != None and file_range[1] > file_range[0]:
            filelist = filelist[file_range[0]:file_range[1] + 1]

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

        imagedata = None
        
        sx, sy = size
        n_slices = len(filelist)
        resolution_percentage = utils.calculate_resizing_tofitmemory(int(sx), int(sy), n_slices, bits/8)
        
        if resolution_percentage < 1.0:
            re_dialog = dialog.ResizeImageDialog()
            re_dialog.SetValue(int(resolution_percentage*100))
            re_dialog_value = re_dialog.ShowModal()
            re_dialog.Close() 
            
            if re_dialog_value == wx.ID_OK:
                percentage = re_dialog.GetValue()
                resolution_percentage = percentage / 100.0
            else:
                return

            xyspacing = xyspacing[0] / resolution_percentage, xyspacing[1] / resolution_percentage
       
 
        wl = float(dicom.image.level)
        ww = float(dicom.image.window)
        self.matrix, scalar_range, self.filename = image_utils.dcm2memmap(filelist, size,
                                                                    orientation, resolution_percentage)

        self.Slice = sl.Slice()
        self.Slice.matrix = self.matrix
        self.Slice.matrix_filename = self.filename

        if orientation == 'AXIAL':
            self.Slice.spacing = xyspacing[0], xyspacing[1], zspacing
        elif orientation == 'CORONAL':
            self.Slice.spacing = xyspacing[0], zspacing, xyspacing[1]
        elif orientation == 'SAGITTAL':
            self.Slice.spacing = zspacing, xyspacing[1], xyspacing[0]

        # 1(a): Fix gantry tilt, if any
        tilt_value = dicom.acquisition.tilt
        if (tilt_value) and (gui):
            # Tell user gantry tilt and fix, according to answer
            message = _("Fix gantry tilt applying the degrees below")
            value = -1*tilt_value
            tilt_value = dialog.ShowNumberDialog(message, value)
            image_utils.FixGantryTilt(self.matrix, self.Slice.spacing, tilt_value)
        elif (tilt_value) and not (gui):
            tilt_value = -1*tilt_value
            image_utils.FixGantryTilt(self.matrix, self.Slice.spacing, tilt_value)

        self.Slice.window_level = wl
        self.Slice.window_width = ww

        scalar_range = int(self.matrix.min()), int(self.matrix.max())

        Publisher.sendMessage('Update threshold limits list', scalar_range)

        return self.matrix, self.filename, dicom

    def OpenOtherFiles(self, group):
        # Retreaving matrix from image data
        self.matrix, scalar_range, self.filename = image_utils.img2memmap(group)

        hdr = group.header
        hdr.set_data_dtype('int16')
        dims = hdr.get_zooms()
        dimsf = tuple([float(s) for s in dims])

        wl = float((scalar_range[0] + scalar_range[1]) * 0.5)
        ww = float((scalar_range[1] - scalar_range[0]))

        self.Slice = sl.Slice()
        self.Slice.matrix = self.matrix
        self.Slice.matrix_filename = self.filename

        self.Slice.spacing = dimsf
        self.Slice.window_level = wl
        self.Slice.window_width = ww

        scalar_range = int(scalar_range[0]), int(scalar_range[1])
        Publisher.sendMessage('Update threshold limits list', scalar_range)
        return self.matrix, self.filename

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

    def SaveRaycastingPreset(self, pubsub_evt):
        preset_name = pubsub_evt.data
        preset = prj.Project().raycasting_preset
        preset['name'] = preset_name
        preset_dir = os.path.join(const.USER_RAYCASTING_PRESETS_DIRECTORY,
                                  preset_name + '.plist')
        plistlib.writePlist(preset, preset_dir)

    def ShowBooleanOpDialog(self, pubsub_evt):
        dlg = dialogs.MaskBooleanDialog(prj.Project().mask_dict)
        dlg.Show()

    def ApplyReorientation(self, pubsub_evt):
        self.Slice.apply_reorientation()
