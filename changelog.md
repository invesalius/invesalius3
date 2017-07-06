# Changelog

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
