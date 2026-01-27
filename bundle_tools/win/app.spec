# -*- mode: python ; coding: utf-8 -*-

#--------- custom -----------------------------------------------------------------

#take VTK files
import os
import sys
import glob
from pathlib import Path

SOURCE_DIR = Path("./").resolve()
print("SOURCE_DIR", SOURCE_DIR)

from PyInstaller.utils.hooks import get_module_file_attribute, collect_dynamic_libs
from PyInstaller.compat import is_win
from PyInstaller.utils.hooks import collect_all

tinygrad_data, tinygrad_binaries, tinygrad_hiddenimports = collect_all("tinygrad")
onnx_data, onnx_binaries, onnx_hiddenimports = collect_all("onnxruntime")

python_dir = os.path.dirname(sys.executable)
venv_dir = os.path.dirname(python_dir) 
site_packages = os.path.join(venv_dir,'Lib','site-packages') #because Lib is inside .venv directory


def check_extension(item): 
    exts = ['exe','pyc','__pycache__'] 
    for ext in exts: 
        if ext in item: 
            return True 
    return False 



def get_all_files(dirName):
    # create a list of file and sub directories 
    # names in the given directory 
    listOfFile = os.listdir(dirName)
    allFiles = list()
    # Iterate over all the entries
    for entry in listOfFile:
        # Create full path
        fullPath = os.path.join(dirName, entry)
        # If entry is a directory then get the list of files in this directory 
        if os.path.isdir(fullPath):
            allFiles = allFiles + get_all_files(fullPath)
        else:
            allFiles.append(fullPath)
                
    return allFiles


libraries = []

#get all files in vtkmodules installation
vtk_files = get_all_files(os.path.join(site_packages,'vtkmodules'))

libraries.append((os.path.join(site_packages,'vtk.py'),'.'))

#define destiny as vtkmodules
for v in vtk_files:
    if not(check_extension(v)):
        #take only folder name and remove first '\\'
        dest_dir = os.path.dirname(v.replace(site_packages,''))[1:]
        libraries.append((v, dest_dir))

#add interpolation module (pyinstaller not take automatically)
libraries.append((glob.glob(os.path.join(SOURCE_DIR,'invesalius_cy', 
    'interpolation.*.pyd'))[0],'invesalius_cy')) #.pyd files are inside of invesalius_cy

#add plaidml modules and files
#libraries.append((os.path.join(venv_dir,'library','bin','plaidml.dll'),'library\\bin'))
#
#plaidml_files = get_all_files(os.path.join(venv_dir,'share','plaidml'))
#
#for v in plaidml_files:
#    if not(check_extension(v)):
#        #take only folder name and remove first '\\'
#        dest_dir = os.path.dirname(v.replace(venv_dir,''))[1:]
#        libraries.append((v, dest_dir))
#
#
#plaidml_files = get_all_files(os.path.join(site_packages,'plaidml'))
#
#for v in plaidml_files:
#    if not(check_extension(v)):
#        #take only folder name and remove first '\\'
#        dest_dir = os.path.dirname(v.replace(site_packages,''))[1:]
#        libraries.append((v, dest_dir))

# -- data files -----

data_files = []

#Add models and weights from A.I folder
ai_data = get_all_files(os.path.join('ai'))
for ai in ai_data:
    dest_dir = os.path.dirname(ai)
    data_files.append((ai,dest_dir))

#Add licences
data_files.append(('LICENSE.pt.txt','.'))
data_files.append(('LICENSE.txt','.'))

#Add user guides
data_files.append(('docs\\user_guide_en.pdf','docs'))
data_files.append(('docs\\user_guide_pt_BR.pdf','docs'))

#Add icons
icons_files = glob.glob(os.path.join(SOURCE_DIR,'icons','*'))

for ic in icons_files:
    data_files.append((ic,'icons'))

#Add locale
locale_data = get_all_files(os.path.join('locale'))
for ld in locale_data:
    dest_dir = os.path.dirname(ld)
    data_files.append((ld,dest_dir))

#Add neuro navegation files
neuro_data = get_all_files(os.path.join('navigation'))
for nd in neuro_data:
    dest_dir = os.path.dirname(nd)
    data_files.append((nd,dest_dir))

#Add presets files
preset_data = get_all_files(os.path.join('presets'))
for pd in preset_data:
    dest_dir = os.path.dirname(pd)
    data_files.append((pd,dest_dir))

#Add sample files
sample_data = get_all_files(os.path.join('samples'))
for sd in sample_data:
    dest_dir = os.path.dirname(sd)
    data_files.append((sd,dest_dir))


# Add FastSurfer LUT and auxiliary file
fastsurfer_dir = os.path.join(
    'invesalius',
    'segmentation',
    'deep_learning',
    'fastsurfer_subpart'
)
data_files.append((os.path.join(fastsurfer_dir,'LUT.tsv'),fastsurfer_dir))

#---------------------------------------------------------------------------------

block_cipher = None


#'wx.lib.pubsub.core.listenerbase','wx.lib.pubsub.core.kwargs',\
                            #'wx.lib.pubsub.core.kwargs.publisher', 'wx.lib.pubsub.core.topicmgrimpl',\
                            #'wx.lib.pubsub.core.kwargs.topicmgrimpl', 'wx.lib.pubsub.core.publisherbase',\
                            #'wx.lib.pubsub.core.topicargspecimpl','wx.lib.pubsub.core.kwargs.listenerbase',\
                            #'wx.lib.pubsub.core.kwargs.publishermixin',\
                            #'wx.lib.pubsub.core.kwargs.listenerimpl',\
                            #'wx.lib.pubsub.core.kwargs.topicargspecimpl',\
                            #'wx._core'

a = Analysis(['app.py'],
             pathex=[SOURCE_DIR],
             binaries=libraries + tinygrad_binaries + onnx_binaries,
             datas=data_files + tinygrad_data + onnx_data,
             hiddenimports=['scipy._lib.messagestream','skimage.restoration._denoise',\
                            'scipy.linalg', 'scipy.linalg.blas', 'scipy.interpolate',\
                            'pywt._extensions._cwt','skimage.filters.rank.core_cy_3d',\
                            'encodings','setuptools','tinygrad'] + tinygrad_hiddenimports + onnx_hiddenimports, #,'keras','plaidml.keras','plaidml.keras.backend'
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='InVesalius 3.1',
		  icon='./icons/invesalius.ico',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='app')




#print("1 >>>>>>>>>> ",a.zipped_data)

#print("2 >>>>>>>>>> ",a.pure)


