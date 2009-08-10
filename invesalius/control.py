import wx.lib.pubsub as ps

import constants as const
import project as prj

import data.imagedata_utils as utils
import data.surface as surface
import data.volume as volume
import reader.dicom_reader as dicom
import reader.analyze_reader as analyze

DEFAULT_THRESH_MODE = 0

class Controller():

    def __init__(self, frame):
        self.surface_manager = surface.SurfaceManager()
        self.volume = volume.Volume()
        self.__bind_events()


    def __bind_events(self):
        ps.Publisher().subscribe(self.ImportDirectory, 'Import directory')
        ps.Publisher().subscribe(self.StartImportPanel, "Load data to import panel")

    def StartImportPanel(self, pubsub_evt):
        path = pubsub_evt.data
        # TODO: Load information
        dict = {"Joao": {"Serie 1": (0, 1, 2, 3, 4, 5, 6, 7),
                        "Serie 2": (1, 2, 3, 4, 5, 6, 7, 8)}
                }
        ps.Publisher().sendMessage("Load import panel", dict)

    def ImportDirectory(self, pubsub_evt=None, dir_=None):
        """
        Import medical images (if any) and generate vtkImageData, saving data
        inside Project instance.
        """

        if not dir_:
            dir_ = pubsub_evt.data

        # Select medical images from directory and generate vtkImageData
        output = dicom.LoadImages(dir_)

        if output:
            imagedata, acquisition_modality, tilt_value, orientation = output
            print orientation
            if (orientation == "CORONAL"):
                orientation = const.CORONAL
            elif(orientation == "SAGITTAL"):
                orientation = const.SAGITAL
            else:
                orientation = const.AXIAL
                
            if (tilt_value):
                #TODO: Show dialog so user can set not other value
                tilt_value *= -1
                imagedata = utils.FixGantryTilt(imagedata, tilt_value)
                print "Fixed Gantry Tilt", str(tilt_value)
        else:
            "No DICOM files were found. Trying to read with ITK..."
            imagedata = analyze.ReadDirectory(dir_)
            acquisition_modality = "MRI"
            
            #TODO: Verify if all Analyse is AXIAL orientation
            orientation = const.AXIAL
        
        if not imagedata:
            print "Sorry, but there are no medical images supported on this dir."
        else:
            # Create new project
            proj = prj.Project()
            proj.name = "Untitled"
            proj.SetAcquisitionModality(acquisition_modality)
            proj.imagedata = imagedata
            proj.original_orientation = orientation
            
            threshold_range = proj.imagedata.GetScalarRange()
            const.THRESHOLD_OUTVALUE = threshold_range[0]
            const.THRESHOLD_INVALUE = threshold_range[1]

            # Based on imagedata, load data to GUI
            ps.Publisher().sendMessage('Load slice to viewer', (imagedata))

            # TODO: where to insert!!!
            self.LoadImagedataInfo()

            # Call frame so it shows slice and volume related panels
            ps.Publisher().sendMessage('Show content panel')

    def LoadImagedataInfo(self):
        proj = prj.Project()

        thresh_modes =  proj.threshold_modes.keys()
        thresh_modes.sort()
        ps.Publisher().sendMessage('Set threshold modes',
                                (thresh_modes,const.THRESHOLD_PRESETS_INDEX))

        # Set default value into slices' default mask
        key= thresh_modes[const.THRESHOLD_PRESETS_INDEX]
        (min_thresh, max_thresh) = proj.threshold_modes.get_value(key)




