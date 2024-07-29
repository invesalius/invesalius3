# Changelog

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
