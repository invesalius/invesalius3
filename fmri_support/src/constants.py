import os
import json
import numpy as np
from copy import deepcopy
import matplotlib.pyplot as plt
from matplotlib.pyplot import cm

import nilearn
import nibabel as nib
from nilearn import image as nimg
from nilearn import plotting as nplot
from nilearn import datasets
from nilearn.regions import connected_label_regions

from sklearn.cluster import KMeans
from brainspace.gradient import GradientMaps

# CONSTANTS DEFINITION

# Variables for Gradients Construction
embedding  = "dm" # diffusion map
aff_kernel = "pearson" #affinity matrix kernel
align_meth = "procrustes"
n_iter     = 10 # procrustes align number of iteration
nb_comp    = 3
rs         = 99


with open ('./src/constants.json', "r") as f:
    cst_dict = json.loads(f.read())

EXTENSION_FUNC = cst_dict["functionalslice-extension"]
EXTENSION_ANTS = cst_dict["antsbinspath"]
EXTENSION_REF = cst_dict["t1-refextension"]
EXTENSION_TRANSFORM = cst_dict["transform-extension"]