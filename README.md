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

1. [Python 2.7.8](http://bit.ly/1W6JQ6L)

* Create a system variable named %PYTHONPATH% with values: C:\Python27;C:\Python27\Lib;C:\Python27\Lib\site-packages;C:\Python27\Scripts; 

2. [wxPython 3.0](http://bit.ly/1YJesZT)
