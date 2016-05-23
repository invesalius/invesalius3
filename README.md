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

#### Linux 64 bits (tested on Ubuntu 16.04)

1) Install the dependencies: `sudo apt-get install python-wxgtk3.0 python-numpy python-scipy python-pil python-matplotlib python-skimage python-nibabel python-serial python-psutil python-vtk6 python-vtkgdcm python-gdcm python-casmoothing cython`

2) Enter on invesalius3 folder and execute: `python setup.py build_ext --inplace`

#### Windows 64 bits (tested on Windows 7)

1) **Python 2.7.8** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/python-2.7.8.amd64.msi

* Create a system variable named `%PYTHONPATH%` with values: `C:\Python27;C:\Python27\Lib;C:\Python27\Lib\site-packages;C:\Python27\Scripts;`
* Insert into `Path` varibale the value `%PYTHONPATH%`

2) **wxPython 3.0.2** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/wxPython3.0-win64-3.0.2.0-py27.exe

3) **PIP** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/get-pip.py
* Download the script and execute `python get-pip.py` 

4) **Numpy 1.11.0** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/numpy-1.11.0+mkl-cp27-cp27m-win_amd64.whl
* Download and execute `pip install numpy-1.11.0+mkl-cp27-cp27m-win_amd64.whl`

5) **Scipy 0.17.1** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/scipy-0.17.1-cp27-cp27m-win_amd64.whl
* Download and execute `pip install scipy-0.17.1-cp27-cp27m-win_amd64.whl`

6) **Pillow (new Python Image Library)** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/Pillow-3.2.0-cp27-cp27m-win_amd64.whl
* Download and execute `pip install Pillow-3.2.0-cp27-cp27m-win_amd64.whl`

7) **Matplotlib 1.5.1** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/matplotlib-1.5.1-cp27-none-win_amd64.whl
* Download and execute `pip install matplotlib-1.5.1-cp27-none-win_amd64.whl`

8) **Scikit Image 0.12.3** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/scikit_image-0.12.3-cp27-cp27m-win_amd64.whl 
* Download and execute `pip install scikit_image-0.12.3-cp27-cp27m-win_amd64.whl`

9) **Nibabel 2.0.2** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/nibabel-2.0.2-py2.py3-none-any.whl
* Download and execute `pip install nibabel-2.0.2-py2.py3-none-any.whl`

10) **PySerial 3.0.1** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/pyserial-3.0.1-py2.py3-none-any.whl
* Download and execute `pip install pyserial-3.0.1-py2.py3-none-any.whl`

11) **PSUtil 4.2.0** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/psutil-4.2.0-cp27-cp27m-win_amd64.whl
* Download and execute `pip install psutil-4.2.0-cp27-cp27m-win_amd64.whl`

12) **VTK 6.3.0** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/vtk.zip
* Download and unzip on `C:\Python27\Lib\site-packages` and add on `%PYTHONPATH%` variable the value `C:\Python27\Lib\site-packages\vtk\vtk;`

13) **GDCM (trunk)** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/gdcm.zip
* Download and unzip on `C:\Python27\Lib\site-packages` and add on `%PYTHONPATH%` variable the value `C:\Python27\Lib\site-packages\gdcm;`

14) **CA Smoothing** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/python_ca_smoothing.zip
* Download and unzip the two files on `C:\Python27\Lib\site-packages`

15) **Visual C++ 2015 Runtime** - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/vcredist_x64.exe
* Download and install

16) **Cython**
* Execute `python install cython`

17) **Compiled InVesalius parts**

* Option 1: Install [Microsoft Visual Studio Community 2015](https://www.visualstudio.com/pt-br/downloads/download-visual-studio-vs.aspx) and execute `python setup.py build_ext --inplace` on invesalius3 folder.

* Option 2: Download pre-compiled parts and unzip on `invesalius3/invesalius/data` - ftp://ftp.cti.gov.br/pub/dt3d/invesalius/files/dev/win64/invesalius-compiled_parts.zip


Special thank's to Christoph Gohlke, Laboratory for Fluorescence Dynamics, University of California, Irvine for providing the pre-compiled of various [python packages for Windows 64 bits](http://www.lfd.uci.edu/~gohlke/pythonlibs/)
