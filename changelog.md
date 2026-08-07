# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nightly build automation using GitHub Actions for Windows, macOS (Intel & Apple Silicon), and Linux
- Automatic nightly release generation at 00:00 UTC
- Dynamic version management using setuptools-scm
- Support for .app bundle creation for macOS
- Moving coil target on scalp functionality (neuronavigation)
- MEP (Motor Evoked Potential) values save/load support in .mkss files
- Loading support for old marker versions with version compatibility

### Changed
- Updated wxPython to latest version for improved UI compatibility
- Migrated from SVN revision to setuptools-scm for version tracking
- GDCM library updated from 3.0.24 to 3.0.24.1
- Nightly releases now marked as pre-releases
- Improved version checking using `requests` library instead of legacy methods
- Updated GitHub Actions to use latest versions of checkout and setup-python
- Defined `NPY_NO_DEPRECATED_API=NPY_1_7_API_VERSION` to avoid NumPy deprecation warnings
- Bumped marker file version with backward compatibility support

### Fixed
- Fixed conditional logic for nightly release deletion
- Fixed error handling when release not found during nightly build cleanup
- Fixed GoToDialogScannerCoord World-to-Voxel conversion
- Fixed coil target creation logic
- Corrected `sys_platform` detection from "windows" to "win32"
- Fixed saving and loading .mkss files with MEP values (incremented file version to 4)
- Fixed loading of old marker file versions

### DevOps
- Automated nightly builds with proper pre-release flagging
- Improved CI/CD with workflow file for Mac and Windows releases
- Added app.spec for PyInstaller builds on macOS
- Enhanced release automation with previous release cleanup

### Dependencies
- wxPython: Updated to latest version
- GDCM: 3.0.24 → 3.0.24.1
- setuptools-scm: Added for dynamic versioning
- requests: Added for version checking

---

## [3.1.1](https://github.com/invesalius/invesalius3/tree/v3.1.1) - 2017-08-10

### Added
- Lanczos 3D interpolation method.
- Option to user set the interpolation method when reorienting an image.
- Option to user digit the angles used to reorient image.

### Fixed
- Not starting InVesalius when user home has non-ascii chars.
- Read DICOM and other image files with non-ascii chars in its filename.
- Save InVesalius project wih non-ascii chars in its filename.
- Import and export surface with non-ascii chars in its filename.
- Export surface with non-ascii chars in its filename.
- DICOM/Bitmap import dialog was not ShowModal.
- Cut plane wasn't working when reenabled volume raycasting 

## [3.1.0](https://github.com/invesalius/invesalius3/tree/v3.1.0) - 2017-07-04

### Added
- Support to open TIFF, BMP, JPEG and PNG files.
- Support to open NiFTI 1 files.
- Support to open PAR/REC files.
- Region Growing based segmentation (Dynamic, Threshold and Confidence).
- Selection of mask connected components.
- Removal of mask connected components.
- Tool to fill mask holes automatically.
- Tool to fill mask holes interactively.
- Tool to crop mask.
- Support to move slice measure points.
- Menu option to (de)activate the navigation mode.
- Import surface files (STL, PLY, OBJ and VTP) into InVesalius project.
- Surface area information.
- Segmentation menu with the options: Threshold, Manual, Watershed and Region Growing.
- Created a canvas class (CanvasRendererCTX) to draw 2D forms and text over the vtkRenderer.
- Swap image axes.
- Flip image.
- English documentation.

### Changed
- Code restructured to follow Python pattern.
- Code ported to wxPython3.
- Code ported to VTK 6.
- Context-Aware Smoothing ported to Cython.
- Using CanvasRendererCTX to draw slice measures.
- Using CanvasRendererCTX to draw the slice informations.
- Brazilian Portuguese updated to 3.1.0 version.

### Fixed
- Transparency widget from **Surface properties** respects the actual surface transparency.
- Measures, Surfaces, Mask and other data are being removed from memory when closing a project.
- Importation of Koning Breast CT DICOM images.
