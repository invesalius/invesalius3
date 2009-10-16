import os.path

import wx

from project import Project

# VTK text
TEXT_SIZE = 12
TEXT_COLOUR = (1,1,1)
TEXT_POSITION = (0.03, 0.97)

# Slice orientation
AXIAL = 0
CORONAL = 1
SAGITAL = 2

# Colour representing each orientation
ORIENTATION_COLOUR = {'AXIAL': (1,0,0), # Red
                      'CORONAL': (0,1,0), # Green
                      'SAGITAL': (0,0,1)} # Blue

# Camera according to slice's orientation
#CAM_POSITION = {"AXIAL":(0, 0, 1), "CORONAL":(0, -1, 0), "SAGITAL":(1, 0, 0)}
#CAM_VIEW_UP =  {"AXIAL":(0, 1, 0), "CORONAL":(0, 0, 1), "SAGITAL":(0, 0, 1)}
AXIAL_SLICE_CAM_POSITION = {"AXIAL":(0, 0, 1), "CORONAL":(0, -1, 0), "SAGITAL":(1, 0, 0)}
AXIAL_SLICE_CAM_VIEW_UP =  {"AXIAL":(0, 1, 0), "CORONAL":(0, 0, 1), "SAGITAL":(0, 0, 1)}

SAGITAL_SLICE_CAM_POSITION = {"AXIAL":(0, -1, 0), "CORONAL":(1, 0, 0), "SAGITAL":(0, 0, 1)}
SAGITAL_SLICE_CAM_VIEW_UP =  {"AXIAL":(-1, 0, 0), "CORONAL":(0, 1, 0), "SAGITAL":(0, 1, 0)}

CORONAL_SLICE_CAM_POSITION = {"AXIAL":(0, -1, 0), "CORONAL":(0, 0, 1), "SAGITAL":(1, 0, 0)}
CORONAL_SLICE_CAM_VIEW_UP =  {"AXIAL":(0, 0, -1), "CORONAL":(0, 1, 0), "SAGITAL":(0, 1, 0)}

SLICE_POSITION = {AXIAL:[AXIAL_SLICE_CAM_VIEW_UP, AXIAL_SLICE_CAM_POSITION],
                  SAGITAL:[SAGITAL_SLICE_CAM_VIEW_UP, SAGITAL_SLICE_CAM_POSITION],
                  CORONAL:[CORONAL_SLICE_CAM_VIEW_UP, CORONAL_SLICE_CAM_POSITION]}

#Color Table from Slice
#NumberOfColors, SaturationRange, HueRange, ValueRange
SLICE_COLOR_TABLE = {"Default ":(None,(0,0),(0,0),(0,1)),
                     "Hue":(None,(1,1),(0,1),(1,1)),
                     "Saturation":(None,(0,1),(0.6,0.6),(1,1)),
                     "Desert":(256, (1,1), (0, 0.1), (1,1)),
                     "Rainbow":(256,(1,1),(0,0.8),(1,1)),
                     "Ocen":(256,(1,1),(0.667, 0.5),(1,1)),
                     "Inverse Gray":(256, (0, 0), (0, 0), (1,0)),
                     }

# Volume view angle
VOL_FRONT = wx.NewId()
VOL_BACK = wx.NewId()
VOL_RIGHT = wx.NewId()
VOL_LEFT = wx.NewId()
VOL_TOP = wx.NewId()
VOL_BOTTOM = wx.NewId()
VOL_ISO = wx.NewId()

# Camera according to volume's orientation
AXIAL_VOLUME_CAM_VIEW_UP = {VOL_FRONT:(0,0,1), VOL_BACK:(0,0,1), VOL_RIGHT:(0,0,1),\
                            VOL_LEFT:(0,0,1), VOL_TOP:(0,1,0), VOL_BOTTOM:(0,-1,0),\
                            VOL_ISO:(0,0,1)}
AXIAL_VOLUME_CAM_POSITION = {VOL_FRONT:(0,-1,0), VOL_BACK:(0,1,0), VOL_RIGHT:(-1,0,0),\
                             VOL_LEFT:(1,0,0), VOL_TOP:(0,0,1), VOL_BOTTOM:(0,0,-1),\
                             VOL_ISO:(0.5,-1,0.5)}

SAGITAL_VOLUME_CAM_VIEW_UP = {VOL_FRONT:(0,-1,0), VOL_BACK:(0,-1,0), VOL_RIGHT:(0,-1,1),\
                              VOL_LEFT:(0,-1,1), VOL_TOP:(1,-1,0), VOL_BOTTOM:(-1,1,0),\
                              VOL_ISO:(0,-1,0)}
SAGITAL_VOLUME_CAM_POSITION = {VOL_FRONT:(-1,0,0), VOL_BACK:(1,0,0), VOL_RIGHT:(0,0,1),\
                               VOL_LEFT:(0,0,-1), VOL_TOP:(0,-1,0), VOL_BOTTOM:(0,1,0),\
                               VOL_ISO:(-1,-0.5,-0.5)}

CORONAL_VOLUME_CAM_VIEW_UP = {VOL_FRONT:(0,-1,0), VOL_BACK:(0,-1,0), VOL_RIGHT:(0,-1,0),\
                              VOL_LEFT:(0,-1,0), VOL_TOP:(0,1,0), VOL_BOTTOM:(0,-1,0),\
                              VOL_ISO:(0,-1,0)}
CORONAL_VOLUME_CAM_POSITION = {VOL_FRONT:(0,0,-1), VOL_BACK:(0,0,1), VOL_RIGHT:(-1,0,0),\
                               VOL_LEFT:(1,0,0), VOL_TOP:(0,-1,0), VOL_BOTTOM:(0,1,0),\
                               VOL_ISO:(0.5,-0.5,-1)}

VOLUME_POSITION = {AXIAL: [AXIAL_VOLUME_CAM_VIEW_UP, AXIAL_VOLUME_CAM_POSITION],
                 SAGITAL: [SAGITAL_VOLUME_CAM_VIEW_UP, SAGITAL_VOLUME_CAM_POSITION],
                 CORONAL: [CORONAL_VOLUME_CAM_VIEW_UP, CORONAL_VOLUME_CAM_POSITION]}


# Mask threshold options
proj = Project()
THRESHOLD_RANGE = proj.threshold_modes["Bone"]
THRESHOLD_PRESETS_INDEX = 0 #Bone
THRESHOLD_HUE_RANGE = (0, 0.6667)
THRESHOLD_INVALUE = 5000
THRESHOLD_OUTVALUE = 0

# Mask properties
MASK_NAME_PATTERN = "Mask %d"
MASK_OPACITY = 0.3
MASK_COLOUR =  [(0.33, 1, 0.33),
                (1, 1, 0.33),
                (0.33, 0.91, 1),
                (1, 0.33, 1),
                (1, 0.68, 0.33),
                (1, 0.33, 0.33),
                (0.33333333333333331, 0.33333333333333331, 1.0),
                #(1.0, 0.33333333333333331, 0.66666666666666663),
                (0.74901960784313726, 1.0, 0.0),
                (0.83529411764705885, 0.33333333333333331, 1.0)]#,
                #(0.792156862745098, 0.66666666666666663, 1.0),
                #(1.0, 0.66666666666666663, 0.792156862745098), # too "light"
                #(0.33333333333333331, 1.0, 0.83529411764705885),#],
                #(1.0, 0.792156862745098, 0.66666666666666663),
                #(0.792156862745098, 1.0, 0.66666666666666663), # too "light"
                #(0.66666666666666663, 0.792156862745098, 1.0)]

# Related to slice editor brush
BRUSH_CIRCLE = 0 #
BRUSH_SQUARE = 1
DEFAULT_BRUSH_FORMAT = BRUSH_CIRCLE

BRUSH_DRAW = 0
BRUSH_ERASE = 1
BRUSH_THRESH = 2
DEFAULT_BRUSH_OP = BRUSH_THRESH
BRUSH_OP_NAME = ["Draw", "Erase", "Threshold"]

BRUSH_COLOUR = (0,0,1.0)
BRUSH_SIZE = 30

# Surface creation values. Each element's list contains:
# 0: imagedata reformat ratio
# 1: smooth_iterations
# 2: smooth_relaxation_factor
# 3: decimate_reduction
SURFACE_QUALITY = {
    "Low": (3, 2, 0.3000, 0.4),
    "Medium": (2, 2, 0.3000, 0.4),
    "High": (0, 1, 0.3000, 0.1),
    "Optimal": (0, 2, 0.3000, 0.4),
    "Custom": (None, None, None, None)}
DEFAULT_SURFACE_QUALITY = "Optimal"

# Surface properties
SURFACE_TRANSPARENCY = 0.0
SURFACE_NAME_PATTERN = "Surface %d"

# Imagedata - window and level presets
WINDOW_LEVEL = {"Abdomen":(350,50),
                 "Bone":(2000, 300),
                 "Brain Posterior Fossa":(120,40),
                 "Brain":(80,40),
                 "Default":(None, None), #Control class set window and level from DICOM
                 "Emphysema":(500,-850),
                 "Ischemia - Hard Non Contrast":(15,32),
                 "Ischemia - Soft Non Contrast":(80,20),
                 "Larynx":(180, 80),
                 "Liver":(2000, -500),
                 "Lung - Soft":(1600,-600),
                 "Lung - Hard":(1000,-600),
                 "Mediastinum":(350,25),
                 "Manual":(None, None), #Case the user change window and level
                 "Pelvis": (450,50),
                 "Sinus":(4000, 400),
                 "Vasculature - Hard":(240,80),
                 "Vasculature - Soft":(650,160)}

REDUCE_IMAGEDATA_QUALITY = 1


# if 1, use vtkVolumeRaycastMapper, if 0, use vtkFixedPointVolumeRayCastMapper
TYPE_RAYCASTING_MAPPER = 0

folder=RAYCASTING_PRESETS_DIRECTORY= os.path.abspath(os.path.join("..",
                                                                  "presets",
                                                                  "raycasting"))

RAYCASTING_TYPES = [filename.split(".")[0] for filename in
                    os.listdir(folder) if
                    os.path.isfile(os.path.join(folder,filename))]
folder = os.path.join(os.path.expanduser('~'), '.invesalius', 'presets')
USER_RAYCASTING_PRESETS_DIRECTORY = folder
RAYCASTING_TYPES += [filename.split(".")[0] for filename in
                     os.listdir(folder) if
                     os.path.isfile(os.path.join(folder,filename))]
RAYCASTING_TYPES.append(' Off')
RAYCASTING_TYPES.sort()
RAYCASTING_OFF_LABEL = ' Off'
RAYCASTING_TOOLS = ["Cut plane"]

# If 0 dont't blur, 1 blur
RAYCASTING_WWWL_BLUR = 0


####
MODE_ZOOM = 0 #"Set Zoom Mode",
MODE_ZOOM_SELECTION = 1 #:"Set Zoom Select Mode",
MODE_ROTATE = 2#:"Set Spin Mode",
MODE_MOVE = 3#:"Set Pan Mode",
MODE_WW_WL = 4#:"Bright and contrast adjustment"}


#        self.states = {0:"Set Zoom Mode", 1:"Set Zoom Select Mode",
#                       2:"Set Spin Mode", 3:"Set Pan Mode",
#                       4:"Bright and contrast adjustment"}


#ps.Publisher().sendMessage('Set interaction mode %d'%
#                                        (MODE_BY_ID[id]))

#('Set Editor Mode')
#{0:"Set Change Slice Mode"}

####
MODE_SLICE_SCROLL = -1
MODE_SLICE_EDITOR = -2
MODE_SLICE_CROSS = -3

############


FILETYPE_IV = wx.NewId()
FILETYPE_RIB = wx.NewId()
FILETYPE_STL = wx.NewId()
FILETYPE_VRML = wx.NewId()
FILETYPE_OBJ = wx.NewId()
FILETYPE_VTP = wx.NewId()
FILETYPE_PLY = wx.NewId()

FILETYPE_IMAGEDATA = wx.NewId()

FILETYPE_BMP = wx.NewId()
FILETYPE_JPG = wx.NewId()
FILETYPE_PNG = wx.NewId()
FILETYPE_PS = wx.NewId()
FILETYPE_POV = wx.NewId()
FILETYPE_OBJ = wx.NewId()

IMAGE_TILING = {"1 x 1":(1,1), "1 x 2":(1,2),
                "1 x 3":(1,3), "1 x 4":(1,4),
                "2 x 1":(2,1), "2 x 2":(2,2),
                "2 x 3":(2,3), "2 x 4":(2,4),
                "3 x 1":(3,1), "3 x 2":(3,2),
                "3 x 3":(3,3), "3 x 4":(3,4),
                "4 x 1":(4,1), "4 x 2":(4,2),
                "4 x 3":(4,3), "4 x 4":(4,4),
                "4 x 5":(4,5), "5 x 4":(5,4)}


