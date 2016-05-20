# InVesalius

InVesalius generates 3D medical imaging reconstructions based on a sequence of 2D DICOM files acquired with CT or MRI equipments.  InVesalius is internationalized (currently available in English, Portuguese, French, German, Spanish, Catalan, Romanian, Korean, Italian and Czech), multi-platform (GNU Linux, Windows and MacOS) and provides several tools:
  * DICOM-support including: (a) ACR-NEMA version 1 and 2; (b) DICOM version 3.0 (including various encodings of JPEG -lossless and lossy-, RLE)
  * Image manipulation facilities (zoom, pan, rotation, brightness/contrast, etc)
  * Segmentation based on 2D slices
  * Pre-defined threshold ranges according to tissue of interest
  * Edition tools (similar to Paint Brush) based on 2D slices
  * 3D surface creation
  * 3D surface connectivity tools 
  * 3D surface exportation (including: binary and ASCII STL, OBJ, VRML, Inventor)
  * High-quality volume rendering projection
  * Pre-defined volume rendering presets
  * Volume rendering crop plane
  * Picture exportation (including: BMP, TIFF, JPG, PostScript, POV-Ray)

### Development

#### Windows 64 bits (tested on Windows 7)

1) **Python 2.7.8** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/python-2.7.8.amd64.msi

* Create a system variable named *%PYTHONPATH%* with values: *C:\Python27;C:\Python27\Lib;C:\Python27\Lib\site-packages;C:\Python27\Scripts;*
* Insert into *Path* varibale the value *%PYTHONPATH%*

2) **wxPython 3.0.2** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/wxPython3.0-win64-3.0.2.0-py27.exe

3) **PIP** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/get-pip.py
* Download the script and execute *python get-pip.py* 

4) **Numpy 1.11.0** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/numpy-1.11.0+mkl-cp27-cp27m-win_amd64.whl
* Download and execute pip install numpy-1.11.0+mkl-cp27-cp27m-win_amd64.whl

5) **Scipy 0.17.1** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/scipy-0.17.1-cp27-cp27m-win_amd64.whl
* Download and execute pip install scipy-0.17.1-cp27-cp27m-win_amd64.whl
