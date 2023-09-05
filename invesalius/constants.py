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

import os.path
import platform
import psutil
import sys
import wx
import itertools

from invesalius import utils
from invesalius import inv_paths

#from invesalius.project import Project
INVESALIUS_VERSION = "3.1.99998"

INVESALIUS_ACTUAL_FORMAT_VERSION = 1.1

#---------------

# Measurements
MEASURE_NAME_PATTERN = _("M %d")
MEASURE_LINEAR = 101
MEASURE_ANGULAR = 102

DEFAULT_MEASURE_COLOUR = (1,0,0)
DEFAULT_MEASURE_BG_COLOUR = (250/255.0, 247/255.0, 218/255.0)
DEFAULT_MEASURE_RADIUS = 1
DEFAULT_MEASURE_TYPE = MEASURE_LINEAR

PROP_MEASURE = 0.8


STEREO_OFF = _(" Off")
STEREO_RED_BLUE = _("Red-blue")
STEREO_CRISTAL = _("CristalEyes")
STEREO_INTERLACED = _("Interlaced")
STEREO_LEFT = _("Left")
STEREO_RIGHT = _("Right")
STEREO_DRESDEN = _("Dresden")
STEREO_CHECKBOARD = _("Checkboard")
STEREO_ANAGLYPH = _("Anaglyph")


# VTK text
TEXT_SIZE_SMALL = 11
TEXT_SIZE = 12
TEXT_SIZE_LARGE = 16
TEXT_SIZE_EXTRA_LARGE = 20
TEXT_SIZE_DIST_NAV = 32
TEXT_COLOUR = (1,1,1)

(X,Y) = (0.03, 0.97)
(XZ, YZ) = (0.05, 0.93)
TEXT_POS_LEFT_UP = (X, Y)
#------------------------------------------------------------------
TEXT_POS_LEFT_DOWN = (X, 1-Y) # SetVerticalJustificationToBottom

TEXT_POS_LEFT_DOWN_ZERO = (X, 1-YZ)
#------------------------------------------------------------------
TEXT_POS_RIGHT_UP = (1-X, Y) # SetJustificationToRight
#------------------------------------------------------------------
TEXT_POS_RIGHT_DOWN = (1-X, 1-Y) # SetVerticalJustificationToBottom &
                                 # SetJustificationToRight
#------------------------------------------------------------------
TEXT_POS_HCENTRE_DOWN = (0.5, 1-Y) # SetJustificationToCentered
                                   # ChildrticalJustificationToBottom

TEXT_POS_HCENTRE_DOWN_ZERO = (0.5, 1-YZ)
#------------------------------------------------------------------
TEXT_POS_HCENTRE_UP = (0.5, Y)  # SetJustificationToCentered
#------------------------------------------------------------------
TEXT_POS_VCENTRE_RIGHT = (1-X, 0.5) # SetVerticalJustificationToCentered
                                    # SetJustificationToRight
TEXT_POS_VCENTRE_RIGHT_ZERO = (1-XZ, 0.5)
#------------------------------------------------------------------
TEXT_POS_VCENTRE_LEFT = (X, 0.5) # SetVerticalJustificationToCentered
#------------------------------------------------------------------


# Slice orientation
AXIAL = 1
CORONAL = 2
SAGITAL = 3
VOLUME = 4
SURFACE = 5

AXIAL_STR="AXIAL"
CORONAL_STR="CORONAL"
SAGITAL_STR="SAGITAL"

# Measure type
LINEAR = 6
ANGULAR = 7
DENSITY_ELLIPSE = 8
DENSITY_POLYGON = 9

# Colour representing each orientation
ORIENTATION_COLOUR = {'AXIAL': (1,0,0), # Red
                      'CORONAL': (0,1,0), # Green
                      'SAGITAL': (0,0,1)} # Blue

IMPORT_INTERVAL = [_("Keep all slices"), _("Skip 1 for each 2 slices"),
                   _("Skip 2 for each 3 slices"), _("Skip 3 for each 4 slices"),
                   _("Skip 4 for each 5 slices"),_("Skip 5 for each 6 slices")]

# Camera according to slice's orientation
#CAM_POSITION = {"AXIAL":(0, 0, 1), "CORONAL":(0, -1, 0), "SAGITAL":(1, 0, 0)}
#CAM_VIEW_UP =  {"AXIAL":(0, 1, 0), "CORONAL":(0, 0, 1), "SAGITAL":(0, 0, 1)}
AXIAL_SLICE_CAM_POSITION = {"AXIAL":(0, 0, 1), "CORONAL":(0, -1, 0), "SAGITAL":(1, 0, 0)}
AXIAL_SLICE_CAM_VIEW_UP =  {"AXIAL":(0, 1, 0), "CORONAL":(0, 0, 1), "SAGITAL":(0, 0, 1)}

SAGITAL_SLICE_CAM_POSITION = {"AXIAL":(0, 0, 1), "CORONAL":(0, 1, 0), "SAGITAL":(-1, 0, 0)}
SAGITAL_SLICE_CAM_VIEW_UP =  {"AXIAL":(0, -1, 0), "CORONAL":(0, 0, 1), "SAGITAL":(0, 0, 1)}

CORONAL_SLICE_CAM_POSITION = {"AXIAL":(0, 0, 1), "CORONAL":(0, 1, 0), "SAGITAL":(-1, 0, 0)}
CORONAL_SLICE_CAM_VIEW_UP =  {"AXIAL":(0, -1, 0), "CORONAL":(0, 0, 1), "SAGITAL":(0, 0, 1)}

SLICE_POSITION = {AXIAL:[AXIAL_SLICE_CAM_VIEW_UP, AXIAL_SLICE_CAM_POSITION],
                  SAGITAL:[SAGITAL_SLICE_CAM_VIEW_UP, SAGITAL_SLICE_CAM_POSITION],
                  CORONAL:[CORONAL_SLICE_CAM_VIEW_UP, CORONAL_SLICE_CAM_POSITION]}

# Project Status

PROJECT_STATUS_NEW = 0
PROJECT_STATUS_OPENED = 1
PROJECT_STATUS_CHANGED = 2
PROJECT_STATUS_CLOSED = 3

RECENT_PROJECTS_MAXIMUM = 4


####
MODE_RP = 0
MODE_NAVIGATOR = 1
MODE_RADIOLOGY = 2
MODE_ODONTOLOGY = 3

#Crop box sides code

AXIAL_RIGHT = 1
AXIAL_LEFT = 2
AXIAL_UPPER = 3
AXIAL_BOTTOM = 4

SAGITAL_RIGHT = 5
SAGITAL_LEFT = 6
SAGITAL_UPPER = 7
SAGITAL_BOTTOM = 8

CORONAL_RIGHT = 9
CORONAL_LEFT = 10
CORONAL_UPPER = 11
CORONAL_BOTTOM = 12

CROP_PAN = 13

#Color Table from Slice
#NumberOfColors, SaturationRange, HueRange, ValueRange
SLICE_COLOR_TABLE = {_("Default "):(None,(0,0),(0,0),(0,1)),
                     _("Hue"):(None,(1,1),(0,1),(1,1)),
                     _("Saturation"):(None,(0,1),(0.6,0.6),(1,1)),
                     _("Desert"):(256, (1,1), (0, 0.1), (1,1)),
                     _("Rainbow"):(256,(1,1),(0,0.8),(1,1)),
                     _("Ocean"):(256,(1,1),(0.667, 0.5),(1,1)),
                     _("Inverse Gray"):(256, (0, 0), (0, 0), (1,0)),
                     }

#Colors for errors and positives
RED_COLOR_FLOAT = (0.99, 0.55, 0.38)
GREEN_COLOR_FLOAT = (0.40, 0.76, 0.65)
RED_COLOR_RGB = (252, 141, 98)
GREEN_COLOR_RGB = (102, 194, 165)

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

#proj = Project()
#THRESHOLD_RANGE = proj.threshold_modes[_("Bone")]
THRESHOLD_RANGE = [0,3033]
THRESHOLD_PRESETS_INDEX = _("Bone")
THRESHOLD_HUE_RANGE = (0, 0.6667)
THRESHOLD_INVALUE = 5000
THRESHOLD_OUTVALUE = 0

# Mask properties
MASK_NAME_PATTERN = _("Mask %d")
MASK_OPACITY = 0.40
#MASK_OPACITY = 0.35
MASK_COLOUR =  [[0.33, 1, 0.33],
                [1, 1, 0.33],
                [0.33, 0.91, 1],
                [1, 0.33, 1],
                [1, 0.68, 0.33],
                [1, 0.33, 0.33],
                [0.33333333333333331, 0.33333333333333331, 1.0],
                #(1.0, 0.33333333333333331, 0.66666666666666663),
                [0.74901960784313726, 1.0, 0.0],
                [0.83529411764705885, 0.33333333333333331, 1.0]]#,
                #(0.792156862745098, 0.66666666666666663, 1.0),
                #(1.0, 0.66666666666666663, 0.792156862745098), # too "light"
                #(0.33333333333333331, 1.0, 0.83529411764705885),#],
                #(1.0, 0.792156862745098, 0.66666666666666663),
                #(0.792156862745098, 1.0, 0.66666666666666663), # too "light"
                #(0.66666666666666663, 0.792156862745098, 1.0)]


MEASURE_COLOUR =  itertools.cycle([[1, 0, 0],
                                   [1, 0.4, 0],
                                   [0, 0, 1],
                                   [1, 0, 1],
                                   [0, 0.6, 0]])

SURFACE_COLOUR =  [(0.33, 1, 0.33),
                (1, 1, 0.33),
                (0.33, 0.91, 1),
                (1, 0.33, 1),
                (1, 0.68, 0.33),
                (1, 0.33, 0.33),
                (0.33333333333333331, 0.33333333333333331, 1.0),
                (1.0, 0.33333333333333331, 0.66666666666666663),
                (0.74901960784313726, 1.0, 0.0),
                (0.83529411764705885, 0.33333333333333331, 1.0),
                (0.792156862745098, 0.66666666666666663, 1.0),
                (1.0, 0.66666666666666663, 0.792156862745098),
                (0.33333333333333331, 1.0, 0.83529411764705885),
                (1.0, 0.792156862745098, 0.66666666666666663),
                (0.792156862745098, 1.0, 0.66666666666666663),
                (0.66666666666666663, 0.792156862745098, 1.0)]

# Related to slice editor brush
BRUSH_CIRCLE = 0 #
BRUSH_SQUARE = 1
DEFAULT_BRUSH_FORMAT = BRUSH_CIRCLE

BRUSH_DRAW = 0
BRUSH_ERASE = 1
BRUSH_THRESH = 2
BRUSH_THRESH_ERASE = 3
BRUSH_THRESH_ADD_ONLY = 4
BRUSH_THRESH_ERASE_ONLY = 5
DEFAULT_BRUSH_OP = BRUSH_THRESH
BRUSH_OP_NAME = [_("Draw"), _("Erase"), _("Threshold")]

BRUSH_COLOUR = (0,0,1.0)
BRUSH_SIZE = 30
BRUSH_MAX_SIZE = 100

# Surface creation values. Each element's list contains:
# 0: imagedata reformat ratio
# 1: smooth_iterations
# 2: smooth_relaxation_factor
# 3: decimate_reduction
SURFACE_QUALITY = {
    _("Low"): (3, 2, 0.3000, 0.4),
    _("Medium"): (2, 2, 0.3000, 0.4),
    _("High"): (0, 1, 0.3000, 0.1),
    _("Optimal *"): (0, 2, 0.3000, 0.4)}
DEFAULT_SURFACE_QUALITY = _("Optimal *")
SURFACE_QUALITY_LIST = [_("Low"),_("Medium"),_("High"),_("Optimal *")]


# Surface properties
SURFACE_TRANSPARENCY = 0.0
SURFACE_NAME_PATTERN = _("Surface %d")

# Surface importing/exporting options
SURFACE_SPACE_WORLD = 0
SURFACE_SPACE_INV = 1
SURFACE_SPACE_CHOICES = [_("world/scanner space"), _("InVesalius space")]

# Imagedata - window and level presets
WINDOW_LEVEL = {_("Abdomen"):(350,50),
                _("Bone"):(2000, 300),
                _("Brain posterior fossa"):(120,40),
                _("Brain"):(80,40),
                _("Default"):(None, None), #Control class set window and level from DICOM
                _("Emphysema"):(500,-850),
                _("Ischemia - Hard, non contrast"):(15,32),
                _("Ischemia - Soft, non contrast"):(80,20),
                _("Larynx"):(180, 80),
                _("Liver"):(2000, -500),
                _("Lung - Soft"):(1600,-600),
                _("Lung - Hard"):(1000,-600),
                _("Mediastinum"):(350,25),
                _("Manual"):(None, None), #Case the user change window and level
                _("Pelvis"): (450,50),
                _("Sinus"):(4000, 400),
                _("Vasculature - Hard"):(240,80),
                _("Vasculature - Soft"):(650,160),
                _("Contour"): (255, 127)}

REDUCE_IMAGEDATA_QUALITY = 0


# PATHS
FS_ENCODE = sys.getfilesystemencoding()

ID_TO_BMP = {VOL_FRONT: [_("Front"), str(inv_paths.ICON_DIR.joinpath("view_front.png"))],
             VOL_BACK: [_("Back"), str(inv_paths.ICON_DIR.joinpath("view_back.png"))],
             VOL_TOP: [_("Top"), str(inv_paths.ICON_DIR.joinpath("view_top.png"))],
             VOL_BOTTOM: [_("Bottom"), str(inv_paths.ICON_DIR.joinpath("view_bottom.png"))],
             VOL_RIGHT: [_("Right"), str(inv_paths.ICON_DIR.joinpath("view_right.png"))],
             VOL_LEFT: [_("Left"), str(inv_paths.ICON_DIR.joinpath("view_left.png"))],
             VOL_ISO:[_("Isometric"), str(inv_paths.ICON_DIR.joinpath("view_isometric.png"))]
             }

# if 1, use vtkVolumeRaycastMapper, if 0, use vtkFixedPointVolumeRayCastMapper
TYPE_RAYCASTING_MAPPER = 0


RAYCASTING_FILES = {_("Airways"): "Airways.plist",
                   _("Airways II"): "Airways II.plist",
                   _("Black & White"): "Black & White.plist",
                   _("Bone + Skin"): "Bone + Skin.plist",
                   _("Bone + Skin II"): "Bone + Skin II.plist",
                   _("Dark bone"): "Dark Bone.plist",
                   _("Glossy"): "Glossy.plist",
                   _("Glossy II"): "Glossy II.plist",
                   _("Gold bone"): "Gold Bone.plist",
                   _("High contrast"): "High Contrast.plist",
                   _("Low contrast"): "Low Contrast.plist",
                   _("Soft on white"): "Soft on White.plist",
                   _("Mid contrast"): "Mid Contrast.plist",
                   _("MIP"): "MIP.plist",
                   _("No shading"): "No Shading.plist",
                   _("Pencil"): "Pencil.plist",
                   _("Red on white"): "Red on White.plist",
                   _("Skin on blue"): "Skin On Blue.plist",
                   _("Skin on blue II"): "Skin On Blue II.plist",
                   _("Soft on white"): "Soft on White.plist",
                   _("Soft + Skin"): "Soft + Skin.plist",
                   _("Soft + Skin II"): "Soft + Skin II.plist",
                   _("Soft + Skin III"): "Soft + Skin III.plist",
                   _("Soft on blue"): "Soft On Blue.plist",
                   _("Soft"): "Soft.plist",
                   _("Standard"): "Standard.plist",
                   _("Vascular"): "Vascular.plist",
                   _("Vascular II"): "Vascular II.plist",
                   _("Vascular III"): "Vascular III.plist",
                   _("Vascular IV"): "Vascular IV.plist",
                   _("Yellow bone"): "Yellow Bone.plist"}



#RAYCASTING_TYPES = [_(filename.split(".")[0]) for filename in
#                    os.listdir(folder) if
#                    os.path.isfile(os.path.join(folder,filename))]


RAYCASTING_TYPES = [_(filename.name.split(".")[0]) for filename in
                    inv_paths.USER_RAYCASTING_PRESETS_DIRECTORY.glob('*') if
                    filename.is_file()]
RAYCASTING_TYPES += RAYCASTING_FILES.keys()
RAYCASTING_TYPES.append(_(' Off'))
RAYCASTING_TYPES.sort()
RAYCASTING_OFF_LABEL = _(' Off')
RAYCASTING_TOOLS = [_("Cut plane")]

# If 0 dont't blur, 1 blur
RAYCASTING_WWWL_BLUR = 0

RAYCASTING_PRESETS_FOLDERS = (inv_paths.RAYCASTING_PRESETS_DIRECTORY,
                              inv_paths.USER_RAYCASTING_PRESETS_DIRECTORY)


####
#MODE_ZOOM = 0 #"Set Zoom Mode",
#MODE_ZOOM_SELECTION = 1 #:"Set Zoom Select Mode",
#MODE_ROTATE = 2#:"Set Spin Mode",
#MODE_MOVE = 3#:"Set Pan Mode",
#MODE_WW_WL = 4#:"Bright and contrast adjustment"}
#MODE_LINEAR_MEASURE = 5


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
FILETYPE_STL_ASCII = wx.NewId()
FILETYPE_VRML = wx.NewId()
FILETYPE_OBJ = wx.NewId()
FILETYPE_VTP = wx.NewId()
FILETYPE_PLY = wx.NewId()
FILETYPE_X3D = wx.NewId()

FILETYPE_IMAGEDATA = wx.NewId()

FILETYPE_BMP = wx.NewId()
FILETYPE_JPG = wx.NewId()
FILETYPE_PNG = wx.NewId()
FILETYPE_PS = wx.NewId()
FILETYPE_POV = wx.NewId()
FILETYPE_TIF = wx.NewId()

IMAGE_TILING = {"1 x 1":(1,1), "1 x 2":(1,2),
                "1 x 3":(1,3), "1 x 4":(1,4),
                "2 x 1":(2,1), "2 x 2":(2,2),
                "2 x 3":(2,3), "2 x 4":(2,4),
                "3 x 1":(3,1), "3 x 2":(3,2),
                "3 x 3":(3,3), "3 x 4":(3,4),
                "4 x 1":(4,1), "4 x 2":(4,2),
                "4 x 3":(4,3), "4 x 4":(4,4),
                "4 x 5":(4,5), "5 x 4":(5,4)}

VTK_WARNING = 0

#----------------------------------------------------------

[ID_DICOM_IMPORT, ID_PROJECT_OPEN, ID_PROJECT_SAVE_AS, ID_PROJECT_SAVE,
 ID_PROJECT_CLOSE, ID_EXPORT_SLICE, ID_PROJECT_PROPERTIES, ID_EXPORT_MASK, ID_PROJECT_INFO,
 ID_SAVE_SCREENSHOT, ID_DICOM_LOAD_NET, ID_PRINT_SCREENSHOT,
 ID_IMPORT_OTHERS_FILES, ID_PREFERENCES, ID_DICOM_NETWORK, ID_TIFF_JPG_PNG,
 ID_VIEW_INTERPOLATED, ID_MODE_NAVIGATION, ID_ANALYZE_IMPORT, ID_NIFTI_IMPORT,
 ID_PARREC_IMPORT, ID_MODE_DBS] = [wx.NewId() for number in range(22)]
ID_EXIT = wx.ID_EXIT
ID_ABOUT = wx.ID_ABOUT


[ID_EDIT_UNDO, ID_EDIT_REDO, ID_EDIT_LIST] =\
    [wx.NewId() for number in range(3)]
[ID_TOOL_PROJECT, ID_TOOL_LAYOUT, ID_TOOL_OBJECT, ID_TOOL_SLICE] =\
    [wx.NewId() for number in range(4)]
[ID_TASK_BAR, ID_VIEW_FOUR] =\
    [wx.NewId() for number in range(2)]
[ID_VIEW_FULL, ID_VIEW_TEXT, ID_VIEW_3D_BACKGROUND] =\
    [wx.NewId() for number in range(3)]

ID_START = wx.NewId()
ID_PLUGINS_SHOW_PATH = wx.NewId()

ID_FLIP_X = wx.NewId()
ID_FLIP_Y = wx.NewId()
ID_FLIP_Z = wx.NewId()

ID_SWAP_XY = wx.NewId()
ID_SWAP_XZ = wx.NewId()
ID_SWAP_YZ = wx.NewId()

ID_BOOLEAN_MASK = wx.NewId()
ID_CLEAN_MASK = wx.NewId()

ID_REORIENT_IMG = wx.NewId()
ID_FLOODFILL_MASK = wx.NewId()
ID_FILL_HOLE_AUTO = wx.NewId()
ID_REMOVE_MASK_PART = wx.NewId()
ID_SELECT_MASK_PART = wx.NewId()
ID_MANUAL_SEGMENTATION = wx.NewId()
ID_WATERSHED_SEGMENTATION = wx.NewId()
ID_THRESHOLD_SEGMENTATION = wx.NewId()
ID_FLOODFILL_SEGMENTATION = wx.NewId()
ID_FLOODFILL_SEGMENTATION = wx.NewId()
ID_SEGMENTATION_BRAIN = wx.NewId()
ID_SEGMENTATION_TRACHEA = wx.NewId()
ID_SEGMENTATION_MANDIBLE_CT = wx.NewId()
ID_CROP_MASK = wx.NewId()
ID_DENSITY_MEASURE = wx.NewId()
ID_MASK_DENSITY_MEASURE = wx.NewId()
ID_CREATE_SURFACE = wx.NewId()
ID_CREATE_MASK = wx.NewId()
ID_MASK_3D_PREVIEW = wx.NewId()
ID_MASK_3D_RELOAD = wx.NewId()
ID_MASK_3D_AUTO_RELOAD = wx.NewId()

ID_GOTO_SLICE = wx.NewId()
ID_GOTO_COORD = wx.NewId()

ID_MANUAL_WWWL = wx.NewId()

# Tractography with Trekker
ID_TREKKER_MASK = wx.NewId()
ID_TREKKER_IMG = wx.NewId()
ID_TREKKER_FOD = wx.NewId()
ID_TREKKER_ACT = wx.NewId()

#---------------------------------------------------------
STATE_DEFAULT = 1000
STATE_WL = 1001
STATE_SPIN = 1002
STATE_ZOOM = 1003
STATE_ZOOM_SL = 1004
STATE_PAN = 1005
STATE_ANNOTATE = 1006
STATE_MEASURE_DISTANCE = 1007
STATE_MEASURE_ANGLE = 1008
STATE_MEASURE_DENSITY = 1009
STATE_MEASURE_DENSITY_ELLIPSE = 1010
STATE_MEASURE_DENSITY_POLYGON = 1011

SLICE_STATE_CROSS = 3006
SLICE_STATE_SCROLL = 3007
SLICE_STATE_EDITOR = 3008
SLICE_STATE_WATERSHED = 3009
SLICE_STATE_REORIENT = 3010
SLICE_STATE_MASK_FFILL = 3011
SLICE_STATE_REMOVE_MASK_PARTS = 3012
SLICE_STATE_SELECT_MASK_PARTS = 3013
SLICE_STATE_FFILL_SEGMENTATION = 3014
SLICE_STATE_CROP_MASK = 3015
SLICE_STATE_TRACTS = 3016

VOLUME_STATE_SEED = 2001
#  STATE_LINEAR_MEASURE = 3001
#  STATE_ANGULAR_MEASURE = 3002

TOOL_STATES = [STATE_WL, STATE_SPIN, STATE_ZOOM,
               STATE_ZOOM_SL, STATE_PAN, STATE_MEASURE_DISTANCE,
               STATE_MEASURE_ANGLE, STATE_MEASURE_DENSITY_ELLIPSE,
               STATE_MEASURE_DENSITY_POLYGON,
               ]  #, STATE_ANNOTATE]



TOOL_SLICE_STATES = [SLICE_STATE_CROSS, SLICE_STATE_SCROLL,
                     SLICE_STATE_REORIENT, SLICE_STATE_TRACTS]


SLICE_STYLES = TOOL_STATES + TOOL_SLICE_STATES
SLICE_STYLES.append(STATE_DEFAULT)
SLICE_STYLES.append(SLICE_STATE_EDITOR)
SLICE_STYLES.append(SLICE_STATE_WATERSHED)
SLICE_STYLES.append(SLICE_STATE_MASK_FFILL)
SLICE_STYLES.append(SLICE_STATE_REMOVE_MASK_PARTS)
SLICE_STYLES.append(SLICE_STATE_SELECT_MASK_PARTS)
SLICE_STYLES.append(SLICE_STATE_FFILL_SEGMENTATION)
SLICE_STYLES.append(SLICE_STATE_CROP_MASK)
SLICE_STYLES.append(STATE_MEASURE_DENSITY)
SLICE_STYLES.append(STATE_MEASURE_DENSITY_ELLIPSE)
SLICE_STYLES.append(STATE_MEASURE_DENSITY_POLYGON)

STYLE_LEVEL = {SLICE_STATE_EDITOR: 1,
               SLICE_STATE_WATERSHED: 1,
               SLICE_STATE_MASK_FFILL: 2,
               SLICE_STATE_REMOVE_MASK_PARTS: 2,
               SLICE_STATE_SELECT_MASK_PARTS: 2,
               SLICE_STATE_FFILL_SEGMENTATION: 2,
               SLICE_STATE_CROSS: 2,
               SLICE_STATE_SCROLL: 2,
               SLICE_STATE_REORIENT: 2,
               SLICE_STATE_CROP_MASK: 1,
               STATE_ANNOTATE: 2,
               STATE_DEFAULT: 0,
               STATE_MEASURE_ANGLE: 2,
               STATE_MEASURE_DISTANCE: 2,
               STATE_MEASURE_DENSITY_ELLIPSE: 2,
               STATE_MEASURE_DENSITY_POLYGON: 2,
               STATE_MEASURE_DENSITY: 2,
               STATE_WL: 2,
               STATE_SPIN: 2,
               STATE_ZOOM: 2,
               STATE_ZOOM_SL: 2,
               STATE_PAN:2,
               VOLUME_STATE_SEED:1}

#------------ Prefereces options key ------------
RENDERING = 0
SURFACE_INTERPOLATION = 1
LANGUAGE = 2
SLICE_INTERPOLATION = 3

#Correlaction extracted from pyDicom
DICOM_ENCODING_TO_PYTHON = {
                            'None':'iso8859',
                            None:'iso8859',
                            '': 'iso8859',
                            'ISO_IR 6': 'iso8859',
                            'ISO_IR 100': 'latin_1',
                            'ISO 2022 IR 87': 'iso2022_jp',
                            'ISO 2022 IR 13': 'iso2022_jp',
                            'ISO 2022 IR 149': 'euc_kr',
                            'ISO_IR 192': 'UTF8',
                            'GB18030': 'GB18030',
                            'ISO_IR 126': 'iso_ir_126',
                            'ISO_IR 127': 'iso_ir_127',
                            'ISO_IR 138': 'iso_ir_138',
                            'ISO_IR 144': 'iso_ir_144',
                            }

#-------------------- Projections type ----------------
PROJECTION_NORMAL=0
PROJECTION_MaxIP=1
PROJECTION_MinIP=2
PROJECTION_MeanIP=3
PROJECTION_LMIP=4
PROJECTION_MIDA=5
PROJECTION_CONTOUR_MIP=6
PROJECTION_CONTOUR_LMIP=7
PROJECTION_CONTOUR_MIDA=8

#------------ Projections defaults ------------------
PROJECTION_BORDER_SIZE=1.0
PROJECTION_MIP_SIZE=2

# ------------- Boolean operations ------------------
BOOLEAN_UNION = 1
BOOLEAN_DIFF = 2
BOOLEAN_AND = 3
BOOLEAN_XOR = 4

# -------------- User interface ---------------------

# The column order in the marker panel
#
ID_COLUMN = 0
SESSION_COLUMN = 1
LABEL_COLUMN = 2
TARGET_COLUMN = 3
X_COLUMN = 4
Y_COLUMN = 5
Z_COLUMN = 6

#------------ Navigation defaults -------------------

MARKER_COLOUR = (1.0, 1.0, 0.)
MARKER_SIZE = 2
ARROW_MARKER_SIZE = 10
CALIBRATION_TRACKER_SAMPLES = 10
FIDUCIAL_REGISTRATION_ERROR_THRESHOLD = 3.0

SELECT = 0
MTC = 1
FASTRAK = 2
ISOTRAKII = 3
PATRIOT = 4
CAMERA = 5
POLARIS = 6
POLARISP4 = 7
OPTITRACK = 8
DEBUGTRACKRANDOM = 9
DEBUGTRACKAPPROACH = 10
DEFAULT_TRACKER = SELECT

NDICOMPORT = b'COM1'
NDI_IP = ['P9-13715.local', 'P9-13719.local']

TRACKERS = [_("Claron MicronTracker"),
           _("Polhemus FASTRAK"), _("Polhemus ISOTRAK II"),
           _("Polhemus PATRIOT"), _("Camera tracker"),
           _("NDI Polaris"), _("NDI Polaris P4"),
           _("Optitrack"),
           _("Debug tracker (random)"), _("Debug tracker (approach)")]

STATIC_REF = 0
DYNAMIC_REF = 1
DEFAULT_REF_MODE = DYNAMIC_REF
REF_MODE = [_("Static ref."), _("Dynamic ref.")]
FT_SENSOR_MODE = [_("Sensor 3"), _("Sensor 4")]

DEFAULT_COIL = SELECT
COIL = [_("Select coil:"), _("Neurosoft Figure-8"),
           _("Magstim 70 mm"), _("Nexstim")]

IR1 = wx.NewId()
IR2 = wx.NewId()
IR3 = wx.NewId()
TR1 = wx.NewId()
TR2 = wx.NewId()
TR3 = wx.NewId()
SET = wx.NewId()

FIDUCIAL_LABELS = ["Left Ear: ", "Right Ear: ", "Nose: "]
IMAGE_FIDUCIALS = [
    {
        'button_id': IR1,
        'label': 'Left Ear',
        'fiducial_name': 'LE',
        'fiducial_index': 0,
        'tip': _("Select left ear in image"),
    },
    {
        'button_id': IR2,
        'label': 'Right Ear',
        'fiducial_name': 'RE',
        'fiducial_index': 1,
        'tip': _("Select right ear in image"),
    },
    {
        'button_id': IR3,
        'label': 'Nasion',
        'fiducial_name': 'NA',
        'fiducial_index': 2,
        'tip': _("Select nasion in image"),
    },
]

TRACKER_FIDUCIALS = [
    {
        'button_id': TR1,
        'label': 'Left Ear',
        'fiducial_name': 'LE',
        'fiducial_index': 0,
        'tip': _("Select left ear with spatial tracker"),
    },
    {
        'button_id': TR2,
        'label': 'Right Ear',
        'fiducial_name': 'RE',
        'fiducial_index': 1,
        'tip': _("Select right ear with spatial tracker"),
    },
    {
        'button_id': TR3,
        'label': 'Nasion',
        'fiducial_name': 'NA',
        'fiducial_index': 2,
        'tip': _("Select nasion with spatial tracker"),
    },
]

BTNS_IMG_MARKERS = {IR1: {0: 'LEI'},
                    IR2: {1: 'REI'},
                    IR3: {2: 'NAI'}}

OBJL = wx.NewId()
OBJR = wx.NewId()
OBJA = wx.NewId()
OBJF = wx.NewId()

OBJECT_FIDUCIALS = [
    {
        'fiducial_index': 0,
        'button_id': OBJL,
        'label': _('Left'),
        'tip': _("Select left object fiducial"),
    },
    {
        'fiducial_index': 1,
        'button_id': OBJR,
        'label': _('Right'),
        'tip': _("Select right object fiducial"),
    },
    {
        'fiducial_index': 2,
        'button_id': OBJA,
        'label': _('Anterior'),
        'tip': _("Select anterior object fiducial"),
    },
    {
        'fiducial_index': 3,
        'button_id': OBJF,
        'label': _('Fixed'),
        'tip': _("Attach sensor to object"),
    },
]

MTC_PROBE_NAME = "1Probe"
MTC_REF_NAME = "2Ref"
MTC_OBJ_NAME = "3Coil"

# Object tracking
ARROW_SCALE = 6
ARROW_UPPER_LIMIT = 15
#COIL_ANGLES_THRESHOLD = 3 * ARROW_SCALE
COIL_ANGLES_THRESHOLD = 3
COIL_COORD_THRESHOLD = 3
TIMESTAMP = 2.0
COIL_ANGLE_ARROW_PROJECTION_THRESHOLD = 5

CAM_MODE = True
AIM_ACTOR_HIDDEN_OPACITY = 0.1
AIM_ACTOR_SHOWN_OPACITY = 0.8

# Tractography visualization
N_TRACTS = 200
PEEL_DEPTH = 10
MAX_PEEL_DEPTH = 40
SEED_OFFSET = 30
SEED_RADIUS = 1.5

#Efield Visualization
EFIELD_MAX_RANGE_SCALE = 0.90

# Increased the default sleep parameter from 0.1 to 0.15 to decrease CPU load during navigation.
SLEEP_NAVIGATION = 0.1
SLEEP_COORDINATES = 0.1

BRAIN_OPACITY = 0.6
N_CPU = psutil.cpu_count()
# the max_sampling_step can be set to something different as well. Above 100 is probably not necessary
TREKKER_CONFIG = {'seed_max': 1,
                  'step_size': 0.03125,
                  'min_fod': 0.05,
                  'probe_quality': 3,
                  'max_interval': 1,
                  'min_radius_curvature': 0.625,
                  'probe_length': 0.15625,
                  'write_interval': 50,
                  'numb_threads': '',
                  'max_length': 250,
                  'min_length': 10,
                  'max_sampling_step': 100,
                  'data_support_exponent': 0.5,
                  'use_best_init': True,
                  'init_max_est_trials': 100}

MARKER_FILE_MAGICK_STRING = "##INVESALIUS3_MARKER_FILE_"
CURRENT_MARKER_FILE_VERSION = 0
WILDCARD_MARKER_FILES = _("Marker scanner coord files (*.mkss)|*.mkss") 

# Serial port
BAUD_RATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
BAUD_RATE_DEFAULT_SELECTION = 4
PULSE_DURATION_IN_MILLISECONDS = 0.2

#Robot
ROBOT_IP = ['169.254.5.1', '192.168.200.251', '143.107.220.251', '169.254.153.251', '127.0.0.1']
ROBOT_MODEL = ['elfin', 'dobot']

MTMS_RADIUS = 15
