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
import tempfile
import textwrap

import wx
import numpy as np

from invesalius.pubsub import pub as Publisher

import invesalius.constants as const
import invesalius.data.imagedata_utils as image_utils
import invesalius.data.mask as msk
import invesalius.data.measures as measures
import invesalius.data.slice_ as sl
import invesalius.data.surface as srf
import invesalius.data.transformations as tr
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

from invesalius import inv_paths
from invesalius import plugins

DEFAULT_THRESH_MODE = 0

class Controller():

    def __init__(self, frame):
        self.surface_manager = srf.SurfaceManager()
        self.volume = volume.Volume()
        self.plugin_manager = plugins.PluginManager()
        self.__bind_events()
        self.frame = frame
        self.progress_dialog = None
        self.cancel_import = False

        #type of imported image
        #None, others and opened Project = 0
        #DICOM = 1
        #TIFF uCT = 2
        self.img_type = 0
        self.affine = np.identity(4)

        #Init session
        session = ses.Session()
        self.measure_manager = measures.MeasurementManager()

        Publisher.sendMessage('Load Preferences')

        self.plugin_manager.find_plugins()

    def __bind_events(self):
        Publisher.subscribe(self.OnImportMedicalImages, 'Import directory')
        Publisher.subscribe(self.OnImportGroup, 'Import group')
        Publisher.subscribe(self.OnImportFolder, 'Import folder')
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

        Publisher.subscribe(self.OnSaveProject, 'Save project')

        Publisher.subscribe(self.create_project_from_matrix, 'Create project from matrix')

        Publisher.subscribe(self.show_mask_preview, 'Show mask preview')

        Publisher.subscribe(self.enable_mask_preview, 'Enable mask 3D preview')
        Publisher.subscribe(self.disable_mask_preview, 'Disable mask 3D preview')
        Publisher.subscribe(self.update_mask_preview, 'Update mask 3D preview')

    def SetBitmapSpacing(self, spacing):
        proj = prj.Project()
        proj.spacing = spacing

    def OnCancelImport(self):
        #self.cancel_import = True
        Publisher.sendMessage('Hide import panel')


    def OnCancelImportBitmap(self):
        #self.cancel_import = True
        Publisher.sendMessage('Hide import bitmap panel')

###########################
###########################

    def OnShowDialogImportDirectory(self):
        self.ShowDialogImportDirectory()

    def OnShowDialogImportOtherFiles(self, id_type):
        self.ShowDialogImportOtherFiles(id_type)

    def OnShowDialogOpenProject(self):
        self.ShowDialogOpenProject()

    def OnShowDialogSaveProject(self, save_as):
        self.ShowDialogSaveProject(save_as)

    def OnShowDialogCloseProject(self):
        self.ShowDialogCloseProject()

    def OnShowBitmapFile(self):
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
            #Publisher.sendMessage("Enable state project", state=False)
            Publisher.sendMessage('Set project name')
            Publisher.sendMessage("Stop Config Recording")
            Publisher.sendMessage("Enable style", style=const.STATE_DEFAULT)

        # Import TIFF, BMP, JPEG or PNG
        dirpath = dialog.ShowImportBitmapDirDialog(self.frame)

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
            #Publisher.sendMessage("Enable state project", state=False)
            Publisher.sendMessage('Set project name')
            Publisher.sendMessage("Stop Config Recording")
            Publisher.sendMessage("Enable style", style=const.STATE_DEFAULT)
        # Import project
        dirpath = dialog.ShowImportDirDialog(self.frame)
        if dirpath and not os.listdir(dirpath):
            dialog.ImportEmptyDirectory(dirpath)
        elif dirpath:
            self.StartImportPanel(dirpath)

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
            # Publisher.sendMessage("Enable state project", state=False)
            Publisher.sendMessage('Set project name')
            Publisher.sendMessage("Stop Config Recording")
            Publisher.sendMessage("Enable style", style=const.STATE_DEFAULT)

        # Warning for limited support to Analyze format
        if id_type == const.ID_ANALYZE_IMPORT:
            dialog.ImportAnalyzeWarning()

        filepath = dialog.ShowImportOtherFilesDialog(id_type)
        Publisher.sendMessage("Open other files", filepath=filepath)

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
            filepath, compress = dialog.ShowSaveAsProjectDialog(proj.name)
            if not filepath:
                return
        else:
            proj = prj.Project()
            compress = proj.compress
            dirpath, filename = session.project_path
            filepath = os.path.join(dirpath, filename)

        self.SaveProject(filepath, compress)


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
                    Publisher.sendMessage("Enable state project", state=False)
                    Publisher.sendMessage('Set project name')
                    Publisher.sendMessage("Stop Config Recording")
                elif answer == 1:
                    self.ShowDialogSaveProject()
                    utils.debug("Save changes and close")
                    self.CloseProject()
                    Publisher.sendMessage("Enable state project", state=False)
                    Publisher.sendMessage('Set project name')
                    Publisher.sendMessage("Stop Config Recording")
                elif answer == -1:
                    utils.debug("Cancel")
            else:
                self.CloseProject()
                Publisher.sendMessage("Enable state project", state=False)
                Publisher.sendMessage('Set project name')
                Publisher.sendMessage("Stop Config Recording")

        else:
            Publisher.sendMessage('Stop Config Recording')


###########################
    def OnOpenProject(self, filepath):
        self.OpenProject(filepath)

    def OnOpenRecentProject(self, filepath):
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
        if proj.affine:
            self.Slice.affine = np.asarray(proj.affine).reshape(4, 4)
        else:
            self.Slice.affine = np.identity(4)

        Publisher.sendMessage('Update threshold limits list',
                              threshold_range=proj.threshold_range)

        self.LoadProject()

        session = ses.Session()
        session.OpenProject(filepath)
        Publisher.sendMessage("Enable state project", state=True)

    def OnSaveProject(self, filepath):
        self.SaveProject(filepath)

    def SaveProject(self, path=None, compress=False):
        Publisher.sendMessage('Begin busy cursor')
        session = ses.Session()
        if path:
            dirpath, filename = os.path.split(path)
        else:
            dirpath, filename = session.project_path

        if isinstance(filename, str):
            filename = utils.decode(filename, const.FS_ENCODE)

        proj = prj.Project()
        try:
            prj.Project().SavePlistProject(dirpath, filename, compress)
        except PermissionError as err:
            if wx.GetApp() is None:
                print("Error: Permission denied, you don't have permission to write at {}".format(dirpath))
            else:
                dlg = dialogs.ErrorMessageBox(
                    None,
                    "Save project error",
                    "It was not possible to save because you don't have permission to write at {}\n{}".format(dirpath, err)
                )
                dlg.ShowModal()
                dlg.Destroy()
        else:
            session.SaveProject((dirpath, filename))

        Publisher.sendMessage('End busy cursor')

    def CloseProject(self):
        Publisher.sendMessage('Enable style', style=const.STATE_DEFAULT)
        Publisher.sendMessage('Hide content panel')
        Publisher.sendMessage('Close project data')

        if self.img_type == 1:
            Publisher.sendMessage('Show import panel in frame')

        if self.img_type == 2:
            Publisher.sendMessage('Show import bitmap panel in frame')


        proj = prj.Project()
        proj.Close()

        session = ses.Session()
        session.CloseProject()

        Publisher.sendMessage('Update status text in GUI', label=_("Ready"))
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

    def Progress(self, data):
        if (data):
            message = _("Loading file %d of %d ...")%(data[0],data[1])
            if not(self.progress_dialog):
                self.progress_dialog = dialog.ProgressDialog(
                                    parent=self.frame, maximum = data[1], abort=1)
            else:
                if not(self.progress_dialog.Update(data[0],message)):
                    self.progress_dialog.Close()
                    self.progress_dialog = None
                    Publisher.sendMessage('Begin busy cursor')
        else:
            #Is None if user canceled the load
            if self.progress_dialog is not None:
                self.progress_dialog.Close()
                self.progress_dialog = None

    def OnLoadImportPanel(self, patient_series):
        ok = self.LoadImportPanel(patient_series)
        if ok:
            Publisher.sendMessage('Show import panel')
            Publisher.sendMessage("Show import panel in frame")
            self.img_type = 1

    def OnLoadImportBitmapPanel(self, data):
        ok = self.LoadImportBitmapPanel(data)
        if ok:
            Publisher.sendMessage('Show import bitmap panel in frame')
            self.img_type = 2
            #Publisher.sendMessage("Show import panel in invesalius.gui.frame") as frame

    def LoadImportBitmapPanel(self, data):
        #if patient_series and isinstance(patient_series, list):
            #Publisher.sendMessage("Load import panel", patient_series)
            #first_patient = patient_series[0]
            #Publisher.sendMessage("Load bitmap preview", first_patient)
        if  data:
            Publisher.sendMessage("Load import bitmap panel", data=data)
            return True
        else:
            dialog.ImportInvalidFiles("Bitmap")
        return False


    def LoadImportPanel(self, patient_series):
        if patient_series and isinstance(patient_series, list):
            Publisher.sendMessage("Load import panel", dicom_groups=patient_series)
            first_patient = patient_series[0]
            Publisher.sendMessage("Load dicom preview", patient=first_patient)
            return True
        else:
            dialog.ImportInvalidFiles("DICOM")
        return False


    #----------- to import by command line ---------------------------------------------------

    def OnImportMedicalImages(self, directory, use_gui):
        self.ImportMedicalImages(directory, use_gui)

    def ImportMedicalImages(self, directory, gui=True):
        patients_groups = dcm.GetDicomGroups(directory)
        name = directory.rpartition('\\')[-1].split('.')

        if len(patients_groups):
            # OPTION 1: DICOM
            group = dcm.SelectLargerDicomGroup(patients_groups)
            matrix, matrix_filename, dicom = self.OpenDicomGroup(group, 0, [0, 0], gui=gui)
            if matrix is None:
                return
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

            if group:
                matrix, matrix_filename = self.OpenOtherFiles(group)
                self.CreateOtherProject(str(name[0]), matrix, matrix_filename)
            # OPTION 4: Nothing...

        self.LoadProject()
        Publisher.sendMessage("Enable state project", state=True)

    def OnImportGroup(self, group, use_gui):
        self.ImportGroup(group, use_gui)

    def ImportGroup(self, group, gui=True):

        matrix, matrix_filename, dicom = self.OpenDicomGroup(group, 0, [0, 0], gui=gui)
        if matrix is None:
            return
        self.CreateDicomProject(dicom, matrix, matrix_filename)

        self.LoadProject()
        Publisher.sendMessage("Enable state project", state=True)

    def OnImportFolder(self, folder):
        Publisher.sendMessage('Begin busy cursor')
        folder = os.path.abspath(folder)

        proj = prj.Project()
        proj.load_from_folder(folder)

        self.Slice = sl.Slice()
        self.Slice._open_image_matrix(proj.matrix_filename,
                                      tuple(proj.matrix_shape),
                                      proj.matrix_dtype)

        self.Slice.window_level = proj.level
        self.Slice.window_width = proj.window

        Publisher.sendMessage('Update threshold limits list',
                              threshold_range=proj.threshold_range)

        session = ses.Session()
        filename = proj.name+".inv3"
        filename = filename.replace("/", "") #Fix problem case other/Skull_DICOM
        dirpath = session.CreateProject(filename)
        self.LoadProject()
        Publisher.sendMessage("Enable state project", state=True)

        Publisher.sendMessage('End busy cursor')

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
                              mask_dict=proj.mask_dict)

        
        Publisher.sendMessage('Load slice plane') 

        Publisher.sendMessage('Bright and contrast adjustment image',
                              window=proj.window,
                              level=proj.level)
        Publisher.sendMessage('Update window level value',
                              window=proj.window,
                              level=proj.level)

        Publisher.sendMessage('Set project name', proj_name=proj.name)
        Publisher.sendMessage('Load surface dict',
                                surface_dict=proj.surface_dict)
        Publisher.sendMessage('Hide surface items',
                              surface_dict=proj.surface_dict)
        self.LoadImagedataInfo() # TODO: where do we insert this <<<?
        
        Publisher.sendMessage('Show content panel')
        Publisher.sendMessage('Update AUI')

        if len(proj.mask_dict):
            self.Slice.current_mask = None
            mask_index = len(proj.mask_dict) -1
            for key, m in proj.mask_dict.items():
                Publisher.sendMessage('Add mask', mask=m)
                if m.is_shown:
                    self.Slice.current_mask = m
                    visible_mask_idx = key
            if self.Slice.current_mask is not None:
                Publisher.sendMessage('Show mask', index=visible_mask_idx, value=True)
                Publisher.sendMessage('Change mask selected', index=visible_mask_idx)
        else:
            mask_name = const.MASK_NAME_PATTERN % (1,)

            if proj.modality != "UNKNOWN":
                thresh = const.THRESHOLD_RANGE
            else:
                thresh = proj.threshold_range

            colour = const.MASK_COLOUR[0]
            Publisher.sendMessage('Create new mask',
                                  mask_name=mask_name,
                                  thresh=thresh,
                                  colour=colour)

        Publisher.sendMessage('Load measurement dict',
                              measurement_dict=proj.measurement_dict,
                              spacing=self.Slice.spacing)

        Publisher.sendMessage(('Set scroll position', 'AXIAL'), index=proj.matrix_shape[0]/2)
        Publisher.sendMessage(('Set scroll position', 'SAGITAL'),index=proj.matrix_shape[1]/2)
        Publisher.sendMessage(('Set scroll position', 'CORONAL'),index=proj.matrix_shape[2]/2)

        # TODO: Check that this is needed with the new way of using affine
        #  now the affine should be at least the identity(4) and never None
        if self.Slice.affine is not None:
            Publisher.sendMessage('Enable Go-to-Coord', status=True)
        else:
            Publisher.sendMessage('Enable Go-to-Coord', status=False)
        
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
        # Forcing to Axial
        #  proj.original_orientation = const.AXIAL
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
        # TODO: Check that this is needed with the new way of using affine
        #  now the affine should be at least the identity(4) and never None
        if self.Slice.affine is not None:
            proj.affine = self.Slice.affine.tolist()

        ######
        session = ses.Session()
        filename = proj.name + ".inv3"

        filename = filename.replace("/", "")  # Fix problem case other/Skull_DICOM

        dirpath = session.CreateProject(filename)


    def create_project_from_matrix(self, name, matrix, orientation="AXIAL", spacing=(1.0, 1.0, 1.0), modality="CT", window_width=None, window_level=None, new_instance=False):
        """
        Creates a new project from a Numpy 3D array.

        name: Name of the project.
        matrix: A Numpy 3D array. It only works with int16 arrays.
        spacing: The spacing between the center of the voxels in X, Y and Z direction.
        modality: Imaging modality.
        """
        if window_width is None:
            window_width = (matrix.max() - matrix.min())
        if window_level is None:
            window_level = (matrix.max() + matrix.min()) // 2

        window_width = int(window_width)
        window_level = int(window_level)

        name_to_const = {"AXIAL": const.AXIAL,
                         "CORONAL": const.CORONAL,
                         "SAGITTAL": const.SAGITAL}

        if new_instance:
            self.start_new_inv_instance(matrix, name, spacing, modality, name_to_const[orientation], window_width, window_level)
        else:
            # Verifying if there is a project open
            s = ses.Session()
            if s.IsOpen():
                Publisher.sendMessage('Close Project')
                Publisher.sendMessage('Disconnect tracker')

            # Check if user really closed the project, if not, stop project creation
            if s.IsOpen():
                return

            mmap_matrix = image_utils.array2memmap(matrix)

            self.Slice = sl.Slice()
            self.Slice.matrix = mmap_matrix
            self.Slice.matrix_filename = mmap_matrix.filename
            self.Slice.spacing = spacing

            self.Slice.window_width = window_width
            self.Slice.window_level = window_level

            proj = prj.Project()
            proj.name = name
            proj.modality = modality
            proj.SetAcquisitionModality(modality)
            proj.matrix_shape = matrix.shape
            proj.matrix_dtype = matrix.dtype.name
            proj.matrix_filename = self.Slice.matrix_filename
            proj.window = window_width
            proj.level = window_level


            proj.original_orientation =\
                name_to_const[orientation]

            proj.threshold_range = int(matrix.min()), int(matrix.max())
            proj.spacing = self.Slice.spacing

            Publisher.sendMessage('Update threshold limits list',
                                  threshold_range=proj.threshold_range)

            ######
            session = ses.Session()
            filename = proj.name + ".inv3"

            filename = filename.replace("/", "")

            dirpath = session.CreateProject(filename)

            self.LoadProject()
            Publisher.sendMessage("Enable state project", state=True)


    def OnOpenBitmapFiles(self, rec_data):
        bmp_data = bmp.BitmapData()

        if bmp_data.IsAllBitmapSameSize():

            matrix, matrix_filename = self.OpenBitmapFiles(bmp_data, rec_data)
            
            self.CreateBitmapProject(bmp_data, rec_data, matrix, matrix_filename)

            self.LoadProject()
            Publisher.sendMessage("Enable state project", state=True)
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
       Publisher.sendMessage('Update threshold limits list',
                             threshold_range=scalar_range)

       return self.matrix, self.filename#, dicom


    def OnOpenDicomGroup(self, group, interval, file_range):
        dicom = group.GetDicomSample()
        samples_per_pixel = dicom.image.samples_per_pixel
        if samples_per_pixel == 3:
            dlg = wx.MessageDialog(wx.GetApp().GetTopWindow(), _("this is a rgb image, it's necessary to convert to grayscale to open on invesalius.\ndo you want to convert it to grayscale?"), _("Confirm"), wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION)
            if dlg.ShowModal() != wx.ID_YES:
                return
        matrix, matrix_filename, dicom = self.OpenDicomGroup(group, interval, file_range, gui=True)
        if matrix is None:
            return
        self.CreateDicomProject(dicom, matrix, matrix_filename)
        self.LoadProject()
        Publisher.sendMessage("Enable state project", state=True)

    def OnOpenOtherFiles(self, filepath):
        filepath = utils.decode(filepath, const.FS_ENCODE)
        if not(filepath) == None:
            name = os.path.basename(filepath).split(".")[0]
            group = oth.ReadOthers(filepath)
            if group:
                matrix, matrix_filename = self.OpenOtherFiles(group)
                self.CreateOtherProject(name, matrix, matrix_filename)
                self.LoadProject()

                Publisher.sendMessage("Enable state project", state=True)
            else:
                dialog.ImportInvalidFiles(ftype="Others")

    def OpenDicomGroup(self, dicom_group, interval, file_range, gui=True):
        # Retrieve general DICOM headers
        dicom = dicom_group.GetDicomSample()

        # Create imagedata
        interval += 1
        filelist = dicom_group.GetFilenameList()[::interval]
        if not filelist:
            utils.debug("Not used the IPPSorter")
            filelist = [i.image.file for i in dicom_group.GetHandSortedList()[::interval]]
        
        if file_range is not None and file_range[0] is not None and file_range[1] > file_range[0]:
            filelist = filelist[file_range[0]:file_range[1] + 1]

        zspacing = dicom_group.zspacing * interval

        size = dicom.image.size
        bits = dicom.image.bits_allocad
        sop_class_uid = dicom.acquisition.sop_class_uid
        xyspacing = dicom.image.spacing
        orientation = dicom.image.orientation_label
        samples_per_pixel = dicom.image.samples_per_pixel

        wl = float(dicom.image.level)
        ww = float(dicom.image.window)

        if sop_class_uid == '1.2.840.10008.5.1.4.1.1.7': #Secondary Capture Image Storage
            use_dcmspacing = 1
        else:
            use_dcmspacing = 0

        imagedata = None

        if dicom.image.number_of_frames == 1:
            sx, sy = size
            n_slices = len(filelist)
            resolution_percentage = utils.calculate_resizing_tofitmemory(int(sx), int(sy), n_slices, bits/8)

            if resolution_percentage < 1.0 and gui:
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

            self.matrix, scalar_range, self.filename = image_utils.dcm2memmap(filelist, size,
                                                                        orientation, resolution_percentage)

            if orientation == 'AXIAL':
                spacing = xyspacing[0], xyspacing[1], zspacing
            elif orientation == 'CORONAL':
                spacing = xyspacing[0], zspacing, xyspacing[1]
            elif orientation == 'SAGITTAL':
                spacing = zspacing, xyspacing[1], xyspacing[0]
        else:
            self.matrix, scalar_range, spacing, self.filename = image_utils.dcmmf2memmap(filelist[0], orientation)

        self.Slice = sl.Slice()
        self.Slice.matrix = self.matrix
        self.Slice.matrix_filename = self.filename

        if gui and (spacing[0] == 0.0 or spacing[1] == 0.0 or spacing[2] == 0.0):
            sx, sy, sz = spacing
            dlg = dialogs.SetSpacingDialog(wx.GetApp().GetTopWindow(), sx, sy, sz)
            if dlg.ShowModal() == wx.ID_OK:
                spacing = dlg.spacing_new_x, dlg.spacing_new_y, dlg.spacing_new_z
            else:
                return None, None, None

        self.Slice.spacing = spacing

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

        Publisher.sendMessage('Update threshold limits list',
                              threshold_range=scalar_range)

        return self.matrix, self.filename, dicom

    def OpenOtherFiles(self, group):
        # Retreaving matrix from image data
        self.matrix, scalar_range, self.filename = image_utils.img2memmap(group)

        hdr = group.header
        hdr.set_data_dtype('int16')

        wl = float((scalar_range[0] + scalar_range[1]) * 0.5)
        ww = float((scalar_range[1] - scalar_range[0]))

        self.Slice = sl.Slice()
        self.Slice.matrix = self.matrix
        self.Slice.matrix_filename = self.filename
        # even though the axes 0 and 2 are swapped when creating self.matrix
        # the spacing should be kept the original, as it is modified somewhere later
        # otherwise generate wrong results
        # also need to convert to float because original get_zooms return numpy.float32
        # which is unsupported by the plist for saving the project
        self.Slice.spacing = tuple([float(s) for s in hdr.get_zooms()])
        self.Slice.window_level = wl
        self.Slice.window_width = ww

        if group.affine.any():
            # remove scaling factor for non-unitary voxel dimensions
            scale, shear, angs, trans, persp = tr.decompose_matrix(group.affine)
            self.Slice.affine = np.linalg.inv(tr.compose_matrix(scale=None, shear=shear,
                                                                angles=angs, translate=trans, perspective=persp))
        else:
            self.Slice.affine = None

        scalar_range = int(scalar_range[0]), int(scalar_range[1])

        Publisher.sendMessage('Update threshold limits list',
                              threshold_range=scalar_range)

        return self.matrix, self.filename

    def LoadImagedataInfo(self):
        proj = prj.Project()

        thresh_modes =  proj.threshold_modes.keys()
        thresh_modes = sorted(thresh_modes)
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
                              thresh_modes_names=thresh_modes,
                              default_thresh=default_threshold)

    def LoadRaycastingPreset(self, preset_name):
        if preset_name != const.RAYCASTING_OFF_LABEL:
            if preset_name in const.RAYCASTING_FILES.keys():
                path = os.path.join(inv_paths.RAYCASTING_PRESETS_DIRECTORY,
                                    const.RAYCASTING_FILES[preset_name])
            else:
                path = os.path.join(inv_paths.RAYCASTING_PRESETS_DIRECTORY,
                                        preset_name+".plist")
                if not os.path.isfile(path):
                    path = os.path.join(inv_paths.USER_RAYCASTING_PRESETS_DIRECTORY,
                                    preset_name+".plist")
            with open(path, 'rb') as f:
                preset = plistlib.load(f, fmt=plistlib.FMT_XML)
            prj.Project().raycasting_preset = preset
            # Notify volume
            # TODO: Chamar grafico tb!
            Publisher.sendMessage('Update raycasting preset')
        else:
            prj.Project().raycasting_preset = 0
            Publisher.sendMessage('Update raycasting preset')

    def SaveRaycastingPreset(self, preset_name):
        preset = prj.Project().raycasting_preset
        preset['name'] = preset_name
        preset_dir = os.path.join(inv_paths.USER_RAYCASTING_PRESETS_DIRECTORY,
                                  preset_name + '.plist')
        with open(preset_dir, 'w+b') as f:
            plistlib.dump(preset, f)

    def ShowBooleanOpDialog(self):
        dlg = dialogs.MaskBooleanDialog(prj.Project().mask_dict)
        dlg.Show()

    def ApplyReorientation(self):
        self.Slice.apply_reorientation()

    def start_new_inv_instance(self, image, name, spacing, modality, orientation, window_width, window_level):
        p = prj.Project()
        project_folder = tempfile.mkdtemp()
        p.create_project_file(name, spacing, modality, orientation, window_width, window_level, image, folder=project_folder)
        err_msg = ''
        try:
            sp = subprocess.Popen([sys.executable, sys.argv[0], '--import-folder', project_folder],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.getcwd())
        except Exception as err:
            err_msg = str(err)
        else:
            try:
                if sp.wait(2):
                    err_msg = sp.stderr.read().decode('utf8')
                    sp.terminate()
            except subprocess.TimeoutExpired:
                pass

        if err_msg:
            dialog.MessageBox(None, "It was not possible to launch new instance of InVesalius3", err_msg)

    def show_mask_preview(self, index, flag=True):
        proj = prj.Project()
        mask = proj.mask_dict[index]
        self.Slice.do_threshold_to_all_slices(mask)
        mask.create_3d_preview()
        Publisher.sendMessage("Load mask preview", mask_3d_actor=mask.volume._actor, flag=flag)
        Publisher.sendMessage("Reload actual slice")

    def enable_mask_preview(self):
        ses.Session().mask_3d_preview = True
        mask = self.Slice.current_mask
        if mask is not None:
            self.Slice.do_threshold_to_all_slices(mask)
            mask.create_3d_preview()
            Publisher.sendMessage("Load mask preview", mask_3d_actor=mask.volume._actor, flag=True)
            Publisher.sendMessage("Render volume viewer")

    def disable_mask_preview(self):
        ses.Session().mask_3d_preview = False
        mask = self.Slice.current_mask
        if mask is not None:
            Publisher.sendMessage("Remove mask preview", mask_3d_actor=mask.volume._actor)
            Publisher.sendMessage("Render volume viewer")

    def update_mask_preview(self):
        mask = self.Slice.current_mask
        if mask is not None:
            mask._update_imagedata()
