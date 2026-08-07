[![PythonVersion](https://img.shields.io/badge/python-3.8-blue)](https://www.python.org/downloads/release/python-380/)
# InVesalius

InVesalius generates 3D medical imaging reconstructions based on a sequence of 2D DICOM files acquired with CT or MRI equipments.  InVesalius is internationalized (currently available in English, Portuguese, French, German, Spanish, Catalan, Romanian, Korean, Italian and Czech), multi-platform (GNU Linux, Windows and MacOS) and provides several tools:
  * DICOM-support including: (a) ACR-NEMA version 1 and 2; (b) DICOM version 3.0 (including various encodings of JPEG -lossless and lossy-, RLE)
  * Support to Analyze files
  * Support to BMP, PNG, JPEG and TIF files
  * Image manipulation facilities (zoom, pan, rotation, brightness/contrast, etc)
  * Segmentation based on 2D slices
  * Pre-defined threshold ranges according to tissue of interest
  * Segmentation based on watershed
  * Edition tools (similar to Paint Brush) based on 2D slices
  * Linear and angular measurement tool
  * Volume reorientation tool
  * 3D surface creation
  * 3D surface volume measurement
  * 3D surface connectivity tools
  * 3D surface exportation (including: binary and ASCII STL, PLY, OBJ, VRML, Inventor)
  * High-quality volume rendering projection
  * Pre-defined volume rendering presets
  * Volume rendering crop plane
  * Picture exportation (including: BMP, TIFF, JPG, PostScript, POV-Ray)

## 🐍 Python Version Support

The primary development and testing target for InVesalius is Python 3.8, as indicated above.

*Important Note for Python 3.9+ Users: Some core dependencies, notably `pypolaris` (required for NDI Polaris/Vicra tracking hardware), have binary wheels publicly available only for Python 3.8. Attempting installation on newer Python versions may result in linking errors.

*   For clinical or stable use, we recommend using a Python 3.8 environment.
*   For development on newer Python versions, please see the workarounds and discussion in [issue #1026](https://github.com/invesalius/invesalius3/issues/1026).
*   Community help in resolving compatibility with newer Python versions is welcome.

### Development

* [Running InVesalius 3 in Linux](https://github.com/invesalius/invesalius3/wiki/Running-InVesalius-3-in-Linux)
* [Running InVesalius 3 in Mac](https://github.com/invesalius/invesalius3/wiki/Running-InVesalius-3-in-Mac)
* [Running InVesalius 3 in Windows](https://github.com/invesalius/invesalius3/wiki/Running-InVesalius-3-in-Windows)
