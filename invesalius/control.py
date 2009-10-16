import os
import plistlib

import wx.lib.pubsub as ps

import constants as const
import project as prj

import data.imagedata_utils as utils
import data.surface as surface
import data.volume as volume
import reader.dicom_grouper
import gui.dialogs as dialog
import reader.dicom_reader as dcm
import reader.analyze_reader as analyze

DEFAULT_THRESH_MODE = 0

class Controller():

    def __init__(self, frame):
        self.surface_manager = surface.SurfaceManager()
        self.volume = volume.Volume()
        self.__bind_events()

    def __bind_events(self):
        ps.Publisher().subscribe(self.OnImportMedicalImages, 'Import directory')
        ps.Publisher().subscribe(self.StartImportPanel, "Load data to import panel")
        ps.Publisher().subscribe(self.LoadRaycastingPreset,
                                 'Load raycasting preset')
        ps.Publisher().subscribe(self.SaveRaycastingPreset,
                                 'Save raycasting preset')
        ps.Publisher().subscribe(self.OnOpenDicomGroup,
                                 'Open DICOM group')

    def StartImportPanel(self, pubsub_evt):
        # path to directory
        path = pubsub_evt.data

        # retrieve DICOM files splited into groups
        patient_series = dcm.GetDicomGroups(path)
        ps.Publisher().sendMessage("Load import panel", patient_series)
        first_patient = patient_series[0]
        #ps.Publisher().sendMessage("Load dicom preview", first_patient)

    def OnImportMedicalImages(self, pubsub_evt):
        directory = pubsub_evt.data
        self.ImportMedicalImages(directory)

    def ImportMedicalImages(self, directory): 
        # OPTION 1: DICOM?
        patients_groups = dcm.GetDicomGroups(directory)
        if len(patients_groups):
            group = dcm.SelectLargerDicomGroup(patients_groups)
            imagedata, dicom = self.OpenDicomGroup(group, gui=False)
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

    def LoadProject(self):
        proj = prj.Project()
        ps.Publisher().sendMessage('Set project name', proj.name)
        ps.Publisher().sendMessage('Load slice to viewer', (proj.imagedata))
        self.LoadImagedataInfo() # TODO: where do we insert this <<<?
        ps.Publisher().sendMessage('Bright and contrast adjustment image',\
                                   (proj.window, proj.level))
        ps.Publisher().sendMessage('Update window level value',\
                                    (proj.window, proj.level))
        ps.Publisher().sendMessage('Show content panel')
        ps.Publisher().sendMessage('Update AUI')

    def CreateAnalyzeProject(self, imagedata):
        proj = prj.Project()
        proj.name = "Untitled"
        proj.SetAcquisitionModality("MRI")
        proj.imagedata = imagedata
        #TODO: Verify if all Analyse are in AXIAL orientation
        proj.original_orientation =  const.AXIAL
        proj.threshold_range = imagedata.GetScalarRange()
        proj.window = proj.threshold_range[1] - proj.threshold_range[0]
        proj.level  (0.5 * (proj.threshold_range[1] + proj.threshold_range[0]))

        const.THRESHOLD_OUTVALUE = proj.threshold_range[0]
        const.THRESHOLD_INVALUE = proj.threshold_range[1]
        const.WINDOW_LEVEL['Default'] = (proj.window, proj.level)
        const.WINDOW_LEVEL['Manual'] = (proj.window, proj.level)


    def CreateDicomProject(self, imagedata, dicom):
        name_to_const = {"AXIAL":const.AXIAL,
                         "CORONAL":const.CORONAL,
                         "SAGITTAL":const.SAGITAL}

        proj = prj.Project()
        proj.name = dicom.patient.name
        proj.SetAcquisitionModality(dicom.acquisition.modality)
        proj.imagedata = imagedata
        proj.original_orientation =\
                    name_to_const[dicom.image.orientation_label]
        proj.window = float(dicom.image.window)
        proj.level = float(dicom.image.level)
        proj.threshold_range = imagedata.GetScalarRange()

        const.THRESHOLD_OUTVALUE = proj.threshold_range[0]
        const.THRESHOLD_INVALUE = proj.threshold_range[1]
        const.WINDOW_LEVEL['Default'] = (proj.window, proj.level)
        const.WINDOW_LEVEL['Manual'] = (proj.window, proj.level)

    def OnOpenDicomGroup(self, pubsub_evt):
        group = pubsub_evt.data
        imagedata, dicom = self.OpenDicomGroup(group, gui=False)
        self.CreateDicomProject(imagedata, dicom)
        self.LoadProject()
    
    def OpenDicomGroup(self, dicom_group, gui=True):

        # Retrieve general DICOM headers
        dicom = dicom_group.GetDicomSample()

        # Create imagedata
        filelist = dicom_group.GetFilenameList()
        zspacing = dicom_group.zspacing
        imagedata = utils.CreateImageData(filelist, zspacing)

        # 1(a): Fix gantry tilt, if any
        tilt_value = dicom.acquisition.tilt
        if (tilt_value) and (gui):
            # Tell user gantry tilt and fix, according to answer
            message = "Fix gantry tilt applying the degrees bellow"
            value = -1*tilt_value
            tilt_value = dialog.ShowNumberDialog(message, value)
            imagedata = utils.FixGantryTilt(imagedata, tilt_value)
        elif (tilt_value) and not (gui):
            tilt_value = -1*tilt_value
            imagedata = utils.FixGantryTilt(imagedata, tilt_value)

        return imagedata, dicom

    def ImportDirectory(self, pubsub_evt=None, dir_=None):
        """
        Import medical images (if any) and generate vtkImageData, saving data
        inside Project instance.
        """

        if not dir_:
            dir_ = pubsub_evt.data

        # Select medical images from directory and generate vtkImageData
        output = dcm.LoadImages(dir_)
        proj = prj.Project()
        proj.name = "Untitled"

        if output:
            # In this case, there were DICOM files on the folder
            imagedata, dicom = output

            # Set orientation
            orientation = dicom.image.orientation_label
            if (orientation == "CORONAL"):
                orientation = const.CORONAL
            elif(orientation == "SAGITTAL"):
                orientation = const.SAGITAL
            else:
                orientation = const.AXIAL
            
            # Retrieve window, level, modalit
            window = float(dicom.image.window)
            level = float(dicom.image.level)
            acquisition_modality = dicom.acquisition.modality

            # If there was gantry tilt, fix it:
            tilt_value = dicom.acquisition.tilt
            if (tilt_value):
                # Tell user gantry tilt and fix, according to answer
                message = "Fix gantry tilt applying the degrees bellow"
                value = -1*tilt_value
                tilt_value = dialog.ShowNumberDialog(message, value)
                imagedata = utils.FixGantryTilt(imagedata, tilt_value)
        else:
            "No DICOM files were found. Trying to read with ITK..."
            imagedata = analyze.ReadDirectory(dir_)
            if imagedata:
                acquisition_modality = "MRI"

                #TODO: Verify if all Analyse is AXIAL orientation
                orientation = const.AXIAL

                proj.SetAcquisitionModality(acquisition_modality)
                proj.imagedata = imagedata
                proj.original_orientation = orientation
                threshold_range = proj.imagedata.GetScalarRange()
                proj.window = window = threshold_range[1] - threshold_range[0]
                proj.level = level = (0.5 * (threshold_range[1] + threshold_range[0]))
            
                ps.Publisher().sendMessage('Update window level value',\
                           (proj.window, proj.level))

        if not imagedata:
            print "Sorry, but there are no medical images supported on this dir."
        else:
            # Create new project
            proj.SetAcquisitionModality(acquisition_modality)
            proj.imagedata = imagedata
            proj.original_orientation = orientation
            proj.window = window
            proj.level = level           

            threshold_range = proj.imagedata.GetScalarRange()
        
            const.WINDOW_LEVEL['Default'] = (window, level)
            const.WINDOW_LEVEL['Manual'] = (window, level)
                        
            const.THRESHOLD_OUTVALUE = threshold_range[0]
            const.THRESHOLD_INVALUE = threshold_range[1]

            # Based on imagedata, load data to GUI
            ps.Publisher().sendMessage('Load slice to viewer', (imagedata))

            # TODO: where to insert!!!
            self.LoadImagedataInfo()

            #Initial Window and Level
            ps.Publisher().sendMessage('Bright and contrast adjustment image',\
                                   (proj.window, proj.level))

            ps.Publisher().sendMessage('Update window level value',\
                                       (proj.window, proj.level))

            # Call frame so it shows slice and volume related panels
            ps.Publisher().sendMessage('Show content panel')

            ps.Publisher().sendMessage('Update AUI')
            
            ps.Publisher().sendMessage('Load slice plane')

    def LoadImagedataInfo(self):
        proj = prj.Project()

        thresh_modes =  proj.threshold_modes.keys()
        thresh_modes.sort()
        ps.Publisher().sendMessage('Set threshold modes',
                                (thresh_modes,const.THRESHOLD_PRESETS_INDEX))

        # Set default value into slices' default mask
        key= thresh_modes[const.THRESHOLD_PRESETS_INDEX]
        (min_thresh, max_thresh) = proj.threshold_modes.get_value(key)

    def LoadRaycastingPreset(self, pubsub_evt):
        label = pubsub_evt.data
        if label != const.RAYCASTING_OFF_LABEL:
            try:
                path = os.path.join(const.RAYCASTING_PRESETS_DIRECTORY,
                                    label+".plist")
                preset = plistlib.readPlist(path)
            except IOError:
                path = os.path.join(const.USER_RAYCASTING_PRESETS_DIRECTORY,
                                    label+".plist")
                preset = plistlib.readPlist(path)
            prj.Project().raycasting_preset = preset
            # Notify volume
            # TODO: Chamar grafico tb!
            ps.Publisher().sendMessage('Update raycasting preset')
        else:
            prj.Project().raycasting_preset = None
            ps.Publisher().sendMessage("Hide raycasting volume")

    def SaveRaycastingPreset(self, pubsub_evt):
        preset_name = pubsub_evt.data + '.plist'
        preset = prj.Project().raycasting_preset
        preset_dir = os.path.join(const.USER_RAYCASTING_PRESETS_DIRECTORY, preset_name)
        plistlib.writePlist(preset, preset_dir)
