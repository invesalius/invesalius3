# -*- mode: python ; coding: utf-8 -*-

#--------- custom -----------------------------------------------------------------

#take VTK files
import os
import sys
import glob
from pathlib import Path

SOURCE_DIR = Path("./").resolve()
print("SOURCE_DIR", SOURCE_DIR)

from PyInstaller.utils.hooks import get_module_file_attribute,\
                                    collect_dynamic_libs, collect_data_files, collect_all


python_dir = os.path.dirname(sys.executable)
venv_dir = os.path.dirname(python_dir) 
# Get Python version dynamically
python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
site_packages = os.path.join(venv_dir, 'lib', python_version, 'site-packages')

def check_extension(item): 
    exts = ['pyc', '__pycache__'] 
    for ext in exts: 
        if ext in item: 
            return True 
    return False 

def get_all_files(dirName):
    listOfFile = os.listdir(dirName)
    allFiles = list()
    for entry in listOfFile:
        fullPath = os.path.join(dirName, entry)
        if os.path.isdir(fullPath):
            allFiles = allFiles + get_all_files(fullPath)
        else:
            allFiles.append(fullPath)
    return allFiles

libraries = []

# Get all files in vtkmodules installation
vtk_files = get_all_files(os.path.join(site_packages, 'vtkmodules'))
libraries.append((os.path.join(site_packages, 'vtk.py'), '.'))

for v in vtk_files:
    if not(check_extension(v)):
        dest_dir = os.path.dirname(v.replace(site_packages, ''))[1:]
        libraries.append((v, dest_dir))

# Add interpolation module
libraries.append((glob.glob(os.path.join(SOURCE_DIR, 'invesalius_cy', 
    'interpolation.*.so'))[0], 'invesalius_cy'))  # .so files for macOS

# -- data files -----

data_files = []

# Add models and weights from A.I folder
ai_data = get_all_files(os.path.join('ai'))
for ai in ai_data:
    dest_dir = os.path.dirname(ai)
    data_files.append((ai, dest_dir))

# Add licenses
data_files.append(('LICENSE.pt.txt', '.'))
data_files.append(('LICENSE.txt', '.'))

# Add user guides
data_files.append(('docs/user_guide_en.pdf', 'docs'))
data_files.append(('docs/user_guide_pt_BR.pdf', 'docs'))

# Add icons
icons_files = glob.glob(os.path.join(SOURCE_DIR, 'icons', '*'))
for ic in icons_files:
    data_files.append((ic, 'icons'))

# Add locale
locale_data = get_all_files(os.path.join('locale'))
for ld in locale_data:
    dest_dir = os.path.dirname(ld)
    data_files.append((ld, dest_dir))

# Add neuro navigation files
neuro_data = get_all_files(os.path.join('navigation'))
for nd in neuro_data:
    dest_dir = os.path.dirname(nd)
    data_files.append((nd, dest_dir))

# Add presets files
preset_data = get_all_files(os.path.join('presets'))
for pd in preset_data:
    dest_dir = os.path.dirname(pd)
    data_files.append((pd, dest_dir))

# Add sample files
sample_data = get_all_files(os.path.join('samples'))
for sd in sample_data:
    dest_dir = os.path.dirname(sd)
    data_files.append((sd, dest_dir))

tinygrad_data, tinygrad_binaries, tinygrad_hiddenimports = collect_all("tinygrad")
data_files += tinygrad_data
libraries += tinygrad_binaries

onnx_data, onnx_binaries, onnx_hiddenimports = collect_all("onnxruntime")

data_files += onnx_data
libraries += onnx_binaries

#---------------------------------------------------------------------------------

block_cipher = None
#print("data files are : \n\n\n\n\n\n\n", data_files)
#print('done with data files \n\n\n\n\n\n\n\n\n\n')
a = Analysis(['app.py'],
             pathex=[SOURCE_DIR],
             binaries=libraries,
             datas=data_files,
             hiddenimports=['scipy._lib.messagestream',
                          'skimage.restoration._denoise',
                          'scipy.linalg',
                          'scipy.linalg.blas',
                          'scipy.interpolate',
                          'pywt._extensions._cwt',
                          'skimage.filters.rank.core_cy_3d',
                          'encodings',
                          'setuptools'] + onnx_hiddenimports + tinygrad_hiddenimports,
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
          icon='./icons/invesalius.icns',  # macOS uses .icns format
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True)

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='app')

# Create macOS app bundle
app = BUNDLE(coll,
             name='InVesalius 3.1.app',
             icon='./icons/invesalius.icns',
             bundle_identifier='org.invesalius.app',
             info_plist={
                 'NSHighResolutionCapable': 'True',
                 'LSBackgroundOnly': 'False',
                 'CFBundleShortVersionString': '3.1',
                 'CFBundleVersion': '3.1',
                 'NSHumanReadableCopyright': '© 2024 InVesalius Team',
                 'CFBundleDocumentTypes': [{
                     'CFBundleTypeName': 'InVesalius Document',
                     'CFBundleTypeRole': 'Viewer',
                     'LSHandlerRank': 'Owner'
                 }]
             }) 
