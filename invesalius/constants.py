from project import Project

AXIAL = 0
CORONAL = 1
SAGITAL = 2


proj = Project()

THRESHOLD_RANGE = proj.threshold_modes["Bone"]

THRESHOLD_PRESETS_INDEX = 0 #Bone

THRESHOLD_HUE_RANGE = (0, 0.6667)
THRESHOLD_INVALUE = 5000
THRESHOLD_OUTVALUE = 0

MASK_NAME_PATTERN = "Mask %d"

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

MASK_OPACITY = 0.3

OP_ADD = 0
OP_DEL = 1
OP_THRESH =2

# Surface creation default values. List contains:
# 0: imagedata reformat ratio
# 1: smooth_iterations
# 2: smooth_relaxation_factor
# 3: decimate_reduction

SURFACE_QUALITY = {
    "Low": (3, 2, 0.3000, 0.4),
    "Medium": (2, 2, 0.3000, 0.4),
    "High": (0, 1, 0.3000, 0.1),
    "Optimal": (0, 2, 0.3000, 0.4),
    "Custom": (None, None, None, None)
}

DEFAULT_SURFACE_QUALITY = "Optimal"


SURFACE_TRANSPARENCY = 0.0
SURFACE_NAME_PATTERN = "Surface %d"

WINDOW_LEVEL = ({"Abdomen":(350,50),
                 "Bone":(2000, 300),
                 "Brain Posterior Fossa":(120,40),
                 "Brain":(80,40),
                 "Emphysema":(500,-850),
                 "Ischemia - Hard Non Contrast":(15,32),
                 "Ischemia - Soft Non Contrast":(80,20),
                 "Larynx":(180, 80),
                 "Liver":(2000, -500),
                 "Lung - Soft":(1600,-600),
                 "Lung - Hard":(1000,-600),
                 "Lung":(1500,-6550),
                 "Mediastinum":(350,25),
                 "Pelvis": (450,50),
                 "Sinus":(4000, 400),
                 "Vasculature - Hard":(240,80),
                 "Vasculature - Soft":(650,160)
                 })
