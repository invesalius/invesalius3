#!/usr/bin/env python

# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

"""
surface_texture.py
==================
Surface texture generation for InVesalius3.

This module ports the medical_triangle_texture algorithm (by Thiago Franco
de Moraes) into InVesalius, using the Rust implementation in invesalius_rs.

The algorithm:
1. Takes an existing 3D surface mesh (from marching cubes)
2. For each triangle, shoots rays along surface normals into the CT/MRI volume
3. Samples volume HU values at multiple depths (multi-slice raycasting)
4. Maps HU values to RGB colors via Window/Level + Color Lookup Table
5. Packs all triangle textures into a 2D atlas image
6. Assigns UV coordinates to mesh vertices

Reference:
    Moraes et al. (2016). Isosurface rendering of medical images improved
    by automatic texture mapping. Computer Methods in Biomechanics and
    Biomedical Engineering: Imaging & Visualization.
    https://doi.org/10.1080/21681163.2016.1254069
"""

import logging
import os
import plistlib

import numpy as np
import vtk
from skimage.io import imsave
from vtk.util import numpy_support

from invesalius.pubsub import pub as Publisher

# Import the Rust texture generation module
try:
    import invesalius_rs
    import invesalius_rs._native as _native

    HAS_NATIVE = True
except ImportError:
    try:
        import _native

        HAS_NATIVE = True
    except ImportError:
        HAS_NATIVE = False
        logging.warning("invesalius_rs._native not found. Surface texture generation unavailable.")

logger = logging.getLogger(__name__)

# Default parameters matching Thiago's reference dataset (0543.txt)
DEFAULT_WW = 500
DEFAULT_WL = 100
DEFAULT_TEXTURE_DIM = 5000
DEFAULT_NSLICES = 10

# Path to InVesalius color presets
PRESETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "presets",
    "raycasting",
    "color_list",
)
DEFAULT_CLUT = os.path.join(PRESETS_DIR, "HotMetal.plist")


def load_clut(clut_path=None, config=None, ww=None, wl=None):
    """
    Load a Color Lookup Table from a .plist file or a 16-bit CLUT config dict.

    Parameters
    ----------
    clut_path : str, optional
        Path to .plist CLUT file. Defaults to HotMetal.plist.
    config : dict, optional
        The raycasting preset dictionary. If this contains 16-bit curves,
        they will be used instead of the CLUT file.
    ww : int, optional
        Window width (required for 16-bit CLUT interpolation to 8-bit).
    wl : int, optional
        Window level (required for 16-bit CLUT interpolation to 8-bit).

    Returns
    -------
    clut : numpy.ndarray, shape (256, 3), dtype uint8
        RGB color lookup table.
    """
    if config and "16bitClutColors" in config and "16bitClutCurves" in config:
        import vtk

        color_transfer = vtk.vtkColorTransferFunction()
        curve_table = config["16bitClutCurves"]
        color_table = config["16bitClutColors"]

        for i, element in enumerate(curve_table):
            for j, lopacity in enumerate(element):
                try:
                    gray_level = lopacity["x"]
                    r = color_table[i][j]["red"]
                    g = color_table[i][j]["green"]
                    b = color_table[i][j]["blue"]
                    color_transfer.AddRGBPoint(gray_level, r, g, b)
                except (IndexError, KeyError):
                    continue

        # Resample to 256 colors based on WW/WL
        if ww is not None and wl is not None:
            wl_min = wl - ww / 2.0
        else:
            # Fallback range if WW/WL not provided
            wl_min, ww = -1000, 2000

        clut = np.zeros((256, 3), dtype="uint8")
        for i in range(256):
            val = wl_min + (i / 255.0) * ww
            rgb = color_transfer.GetColor(val)
            clut[i] = [int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)]
        return clut

    if clut_path is None:
        clut_path = DEFAULT_CLUT

    if not os.path.exists(clut_path):
        # Fallback: grayscale CLUT
        logger.warning(f"CLUT file not found: {clut_path}. Using grayscale.")
        clut = np.zeros((256, 3), dtype="uint8")
        for i in range(256):
            clut[i] = [i, i, i]
        return clut

    with open(clut_path, "rb") as fp:
        p = plistlib.load(fp)
    clut = np.array(list(zip(p["Red"], p["Green"], p["Blue"])), dtype="uint8")
    return clut


def apply_wwwl_and_clut(image_hf, ww, wl, clut):
    """
    Convert raw HU multi-slice image to RGB using WW/WL + CLUT.

    Parameters
    ----------
    image_hf : numpy.ndarray, shape (nslices, H, W), dtype int16
        Raw HU values from generate_tcoords_hf.
    ww : int
        Window width.
    wl : int
        Window level.
    clut : numpy.ndarray, shape (256, 3), dtype uint8
        Color lookup table.

    Returns
    -------
    image_rgb : numpy.ndarray, shape (H, W, 3), dtype uint8
        RGB texture atlas.
    """
    # Take max intensity projection across all slices
    # Ignore NULL_VALUE (-32768) sentinel
    image_max = np.where(image_hf == -32768, -32768, image_hf).max(axis=0).astype("float64")

    # Apply Window/Level mapping
    wl_f = float(wl)
    ww_f = float(ww)
    min_val = wl_f - 0.5 - (ww_f - 1.0) / 2.0
    max_val = wl_f - 0.5 + (ww_f - 1.0) / 2.0

    gv = np.where(
        image_max <= min_val,
        0.0,
        np.where(
            image_max >= max_val, 255.0, ((image_max - (wl_f - 0.5)) / (ww_f - 1.0) + 0.5) * 255.0
        ),
    )

    # Map through CLUT
    gv_idx = np.clip(gv.astype("int32"), 0, 255)
    image_rgb = clut[gv_idx].astype("uint8")

    return image_rgb


def polydata_to_numpy(polydata):
    """
    Convert VTK PolyData to numpy arrays.

    Parameters
    ----------
    polydata : vtk.vtkPolyData
        Input mesh.

    Returns
    -------
    vertices : numpy.ndarray, shape (N, 3), dtype float64
    normals : numpy.ndarray, shape (N, 3), dtype float64
    faces : numpy.ndarray, shape (M, 3), dtype int32
    """
    # Ensure normals are computed
    if polydata.GetPointData().GetNormals() is None:
        normal_filter = vtk.vtkPolyDataNormals()
        normal_filter.SetInputData(polydata)
        normal_filter.ComputePointNormalsOn()
        normal_filter.Update()
        polydata = normal_filter.GetOutput()

    vertices = numpy_support.vtk_to_numpy(polydata.GetPoints().GetData()).astype("float64")

    normals = numpy_support.vtk_to_numpy(polydata.GetPointData().GetNormals()).astype("float64")

    faces_vtk = numpy_support.vtk_to_numpy(polydata.GetPolys().GetData())
    faces_vtk = faces_vtk.reshape(-1, 4)
    faces = faces_vtk[:, 1:].astype("int32")

    return vertices, normals, faces


def apply_texture_to_actor(actor, polydata, tcoords, image_rgb):
    """
    Apply UV texture coordinates and texture image to a VTK actor.

    Parameters
    ----------
    actor : vtk.vtkActor
        The surface actor to texture.
    polydata : vtk.vtkPolyData
        The surface mesh polydata.
    tcoords : numpy.ndarray, shape (M, 6), dtype float64
        Per-face UV coordinates from generate_tcoords_hf.
    image_rgb : numpy.ndarray, shape (H, W, 3), dtype uint8
        RGB texture atlas image.
    """
    n_faces = tcoords.shape[0]
    n_verts = polydata.GetNumberOfPoints()

    # Build per-vertex UV from per-face UV
    # Each face has 3 UV pairs (u0,v0, u1,v1, u2,v2)
    # We use face centroid UV mapped to each vertex
    uv_per_vertex = np.zeros((n_verts, 2), dtype="float64")
    uv_count = np.zeros(n_verts, dtype="int32")

    faces_vtk = numpy_support.vtk_to_numpy(polydata.GetPolys().GetData())
    faces_vtk = faces_vtk.reshape(-1, 4)
    faces = faces_vtk[:, 1:]

    for i in range(n_faces):
        v0, v1, v2 = faces[i]
        # Average UV for each vertex in this face
        uv_per_vertex[v0] += [tcoords[i, 0], tcoords[i, 1]]
        uv_per_vertex[v1] += [tcoords[i, 2], tcoords[i, 3]]
        uv_per_vertex[v2] += [tcoords[i, 4], tcoords[i, 5]]
        uv_count[v0] += 1
        uv_count[v1] += 1
        uv_count[v2] += 1

    # Average overlapping UVs
    mask = uv_count > 0
    uv_per_vertex[mask] /= uv_count[mask, np.newaxis]

    # Apply UV coordinates to polydata
    vtk_tcoords = numpy_support.numpy_to_vtk(uv_per_vertex.astype("float32"), deep=True)
    vtk_tcoords.SetNumberOfComponents(2)
    vtk_tcoords.SetName("TextureCoordinates")
    polydata.GetPointData().SetTCoords(vtk_tcoords)

    # Create VTK texture from RGB image
    h, w = image_rgb.shape[:2]
    img_flat = image_rgb[::-1, :, :].flatten()  # flip Y for VTK

    img_import = vtk.vtkImageImport()
    img_import.CopyImportVoidPointer(img_flat, img_flat.nbytes)
    img_import.SetDataScalarTypeToUnsignedChar()
    img_import.SetNumberOfScalarComponents(3)
    img_import.SetDataExtent(0, w - 1, 0, h - 1, 0, 0)
    img_import.SetWholeExtent(0, w - 1, 0, h - 1, 0, 0)
    img_import.Update()

    texture = vtk.vtkTexture()
    texture.SetInputConnection(img_import.GetOutputPort())
    texture.InterpolateOn()

    actor.SetTexture(texture)
    actor.GetMapper().SetInputData(polydata)
    actor.GetMapper().ScalarVisibilityOff()

    logger.info("Texture applied to actor successfully.")


class SurfaceTexture:
    """
    Surface texture generator for InVesalius3.

    Generates a texture atlas from CT/MRI volume data and applies it
    to an existing surface mesh using multi-slice surface raycasting.

    Parameters
    ----------
    surface_index : int
        Index of the surface in Project().surface_dict.
    ww : int
        Window width for HU mapping (default 500).
    wl : int
        Window level for HU mapping (default 100).
    texture_dim : int
        Texture atlas size in pixels (default 5000).
    nslices : int
        Number of raycasting slices (default 10).
    clut_path : str, optional
        Path to .plist CLUT file.
    """

    def __init__(
        self,
        surface_index,
        ww=DEFAULT_WW,
        wl=DEFAULT_WL,
        texture_dim=DEFAULT_TEXTURE_DIM,
        nslices=DEFAULT_NSLICES,
        clut_path=None,
    ):
        self.surface_index = surface_index
        self.ww = ww
        self.wl = wl
        self.texture_dim = texture_dim
        self.nslices = nslices
        self.clut_path = clut_path

        # Results
        self.tcoords = None
        self.image_hf = None
        self.tnormals = None
        self.image_rgb = None

    def get_numpy_mesh(self):
        """
        Extract mesh data from InVesalius Project surface.

        Returns
        -------
        vertices : numpy.ndarray (N, 3) float64
        normals : numpy.ndarray (N, 3) float64
        faces : numpy.ndarray (M, 3) int32
        polydata : vtk.vtkPolyData
        """
        import invesalius.project as prj

        proj = prj.Project()

        if self.surface_index not in proj.surface_dict:
            raise ValueError(f"Surface index {self.surface_index} not found in project.")

        surface = proj.surface_dict[self.surface_index]
        polydata = surface.polydata

        if polydata is None:
            raise ValueError(f"Surface {self.surface_index} has no polydata.")

        vertices, normals, faces = polydata_to_numpy(polydata)

        logger.info(f"Mesh loaded: {len(vertices)} vertices, {len(faces)} faces")
        return vertices, normals, faces, polydata

    def get_volume_data(self):
        """
        Get CT/MRI volume and spacing from InVesalius Slice singleton.

        Returns
        -------
        matrix : numpy.ndarray (Z, Y, X) int16
        spacing : numpy.ndarray [sx, sy, sz] float64
        """
        from invesalius.data.slice_ import Slice

        sl = Slice()
        matrix = sl.matrix

        if matrix is None:
            raise ValueError("No volume data loaded in InVesalius.")

        spacing = np.array(sl.spacing, dtype="float64")

        logger.info(f"Volume loaded: shape={matrix.shape}, spacing={spacing}")
        return matrix, spacing

    def generate(self):
        """
        Generate texture atlas from volume data.

        Returns
        -------
        image_rgb : numpy.ndarray (H, W, 3) uint8
            RGB texture atlas.
        tcoords : numpy.ndarray (M, 6) float64
            Per-face UV coordinates.
        tnormals : numpy.ndarray (H, W, 3) uint8
            Normal map atlas.
        """
        if not HAS_NATIVE:
            raise RuntimeError(
                "invesalius_rs._native module not available. Please rebuild invesalius_rs."
            )

        Publisher.sendMessage("Update status text in GUI", label="Loading mesh and volume data...")

        # ── Load mesh ────────────────────────────────────────────────────
        vertices, normals, faces, polydata = self.get_numpy_mesh()

        # ── Load volume ──────────────────────────────────────────────────
        matrix, spacing = self.get_volume_data()

        # ── Load CLUT ────────────────────────────────────────────────────
        clut = load_clut(self.clut_path)

        # ── Y-axis alignment ─────────────────────────────────────────────
        # InVesalius PLY meshes export with negative Y axis.
        # Shift Y to start from 0 so raycasting hits the volume correctly.
        y_min = vertices[:, 1].min()
        if y_min < 0:
            vertices[:, 1] -= y_min
            logger.info(f"Y-axis shifted by {-y_min:.2f} mm for alignment.")

        Publisher.sendMessage(
            "Update status text in GUI",
            label="Generating surface texture (this may take a few minutes)...",
        )

        logger.info(
            f"Starting texture generation: "
            f"faces={len(faces)}, dim={self.texture_dim}, "
            f"nslices={self.nslices}, ww={self.ww}, wl={self.wl}"
        )

        # ── Run Rust texture engine ──────────────────────────────────────
        self.tcoords, self.image_hf, self.tnormals = _native.generate_tcoords_hf(
            vertices.astype("float64"),
            normals.astype("float64"),
            faces.astype("int32"),
            matrix,
            spacing,
            self.ww,
            self.wl,
            clut,
            self.texture_dim,
            self.nslices,
        )

        logger.info(
            f"Texture generated: "
            f"image_shape={self.image_hf.shape}, "
            f"nonzero={np.count_nonzero(self.image_hf != -32768)}"
        )

        # ── Convert HU → RGB ─────────────────────────────────────────────
        Publisher.sendMessage("Update status text in GUI", label="Applying color mapping...")

        self.image_rgb = apply_wwwl_and_clut(self.image_hf, self.ww, self.wl, clut)

        Publisher.sendMessage("Update status text in GUI", label="Texture generation complete.")

        logger.info("Texture generation complete.")
        return self.image_rgb, self.tcoords, self.tnormals

    def apply_to_actor(self, actor):
        """
        Apply generated texture to a VTK actor.

        Parameters
        ----------
        actor : vtk.vtkActor
            The surface actor to texture.
        """
        if self.tcoords is None or self.image_rgb is None:
            raise RuntimeError("Texture not generated yet. Call generate() first.")

        _, _, _, polydata = self.get_numpy_mesh()
        apply_texture_to_actor(actor, polydata, self.tcoords, self.image_rgb)

    def save_texture(self, filepath):
        """
        Save the RGB texture atlas as a PNG file.

        Parameters
        ----------
        filepath : str
            Output path for texture PNG.
        """
        if self.image_rgb is None:
            raise RuntimeError("Texture not generated yet. Call generate() first.")

        imsave(filepath, self.image_rgb)
        logger.info(f"Texture saved to: {filepath}")

    def save_normal_map(self, filepath):
        """
        Save the normal map atlas as a PNG file.

        Parameters
        ----------
        filepath : str
            Output path for normal map PNG.
        """
        if self.tnormals is None:
            raise RuntimeError("Texture not generated yet. Call generate() first.")

        imsave(filepath, self.tnormals)
        logger.info(f"Normal map saved to: {filepath}")


def generate_surface_texture(
    surface_index,
    ww=DEFAULT_WW,
    wl=DEFAULT_WL,
    texture_dim=DEFAULT_TEXTURE_DIM,
    nslices=DEFAULT_NSLICES,
    clut_path=None,
):
    """
    Convenience function — generate and apply texture to a surface.

    Parameters
    ----------
    surface_index : int
        Index of the surface in Project().surface_dict.
    ww : int
        Window width (default 500).
    wl : int
        Window level (default 100).
    texture_dim : int
        Texture atlas size in pixels (default 5000).
    nslices : int
        Number of raycasting slices (default 10).
    clut_path : str, optional
        Path to .plist CLUT file.

    Returns
    -------
    st : SurfaceTexture
        The SurfaceTexture object with generated results.
    """
    st = SurfaceTexture(
        surface_index=surface_index,
        ww=ww,
        wl=wl,
        texture_dim=texture_dim,
        nslices=nslices,
        clut_path=clut_path,
    )
    st.generate()
    return st


def get_opacity_curve_from_preset(config, ww=None, wl=None):
    """
    Extract the full VR opacity transfer function from a preset.

    For advanced 16-bit presets, collects all (HU, opacity) points from
    every opacity curve. For simple 8-bit presets, creates a linear ramp
    from WW/WL bounds.

    Parameters
    ----------
    config : dict
        The raycasting preset dictionary (project.raycasting_preset).
    ww : float, optional
        Window width (used for simple presets).
    wl : float, optional
        Window level (used for simple presets).

    Returns
    -------
    numpy.ndarray
        Nx2 float64 array where column 0 = HU value, column 1 = opacity.
        Sorted by HU ascending.
    """
    points = []

    if config.get("advancedCLUT"):
        for curve in config.get("16bitClutCurves", []):
            for point in curve:
                points.append((float(point["x"]), float(point["y"])))
    else:
        # Simple preset: linear ramp from window bounds
        if ww is None:
            ww = config.get("ww", DEFAULT_WW)
        if wl is None:
            wl = config.get("wl", DEFAULT_WL)
        half_ww = float(ww) / 2.0
        points.append((float(wl) - half_ww, 0.0))
        points.append((float(wl) + half_ww, 1.0))

    if not points:
        # Fallback: fully opaque everywhere
        points = [(-1024.0, 0.0), (3071.0, 1.0)]

    # Sort by HU value and deduplicate
    points.sort(key=lambda p: p[0])
    return np.array(points, dtype="float64")


def get_isovalues_from_preset(config):
    """
    Extract HU isosurface thresholds from a Volume Rendering preset.

    For advanced 16-bit presets, finds the first HU value where opacity
    exceeds a significance threshold (0.1). This captures all visible
    anatomy including thin ribs, rather than only the densest bone.
    For multi-curve presets, uses the highest such threshold to avoid
    boxy skin envelopes.
    For simple 8-bit presets, uses the WW/WL midpoint.

    Parameters
    ----------
    config : dict
        The raycasting preset dictionary (project.raycasting_preset).

    Returns
    -------
    list of float
        HU isovalues where opacity first becomes significant.
    """
    isovalues = []
    if config.get("advancedCLUT"):
        for curve in config.get("16bitClutCurves", []):
            # Find the first point where opacity exceeds 0.1
            for i, point in enumerate(curve):
                if point["y"] > 0.1:
                    if i > 0:
                        prev = curve[i - 1]
                        dy = point["y"] - prev["y"]
                        if abs(dy) > 1e-9:
                            # Interpolate where opacity crosses 0.1
                            t = (0.1 - prev["y"]) / dy
                            isovalue = prev["x"] + t * (point["x"] - prev["x"])
                        else:
                            isovalue = point["x"]
                    else:
                        isovalue = point["x"]
                    isovalues.append(isovalue)
                    break
        # For multi-curve presets (e.g. Skin+Bone), use only the highest
        # threshold to avoid capturing the skin envelope
        if len(isovalues) > 1:
            isovalues = [max(isovalues)]
    else:
        # For simple presets, use the window midpoint (WL) as isovalue
        wl = config.get("wl", DEFAULT_WL)
        isovalues.append(float(wl))
    return isovalues


def generate_surface_from_volume(imagedata, isovalues):
    """
    Generate an isosurface mesh from volume data using VR-derived thresholds.

    Uses vtkFlyingEdges3D for fast parallel isosurface extraction at each
    opacity-derived HU threshold, then merges multi-curve surfaces.

    Parameters
    ----------
    imagedata : vtkImageData
        The volume image data.
    isovalues : list of float
        HU isovalues from get_isovalues_from_preset().

    Returns
    -------
    vtkPolyData
        The generated surface mesh with computed normals.
    """
    from vtkmodules.vtkFiltersCore import (
        vtkAppendPolyData,
        vtkCleanPolyData,
        vtkPolyDataNormals,
        vtkQuadricDecimation,
        vtkSmoothPolyDataFilter,
    )

    try:
        from vtkmodules.vtkFiltersCore import vtkFlyingEdges3D

        ContourClass = vtkFlyingEdges3D
    except ImportError:
        from vtkmodules.vtkFiltersCore import vtkContourFilter

        ContourClass = vtkContourFilter

    if len(isovalues) == 1:
        contour = ContourClass()
        contour.SetInputData(imagedata)
        contour.SetValue(0, isovalues[0])
        contour.Update()
        polydata = contour.GetOutput()
    else:
        appender = vtkAppendPolyData()
        for iso in isovalues:
            contour = ContourClass()
            contour.SetInputData(imagedata)
            contour.SetValue(0, iso)
            contour.Update()
            appender.AddInputData(contour.GetOutput())
        appender.Update()
        polydata = appender.GetOutput()

    # Clean duplicate points
    cleaner = vtkCleanPolyData()
    cleaner.SetInputData(polydata)
    cleaner.Update()

    # Light smoothing to reduce staircase artifacts while preserving detail
    smoother = vtkSmoothPolyDataFilter()
    smoother.SetInputData(cleaner.GetOutput())
    smoother.SetNumberOfIterations(50)
    smoother.SetRelaxationFactor(0.1)
    smoother.FeatureEdgeSmoothingOff()
    smoother.BoundarySmoothingOn()
    smoother.Update()

    # Gentle decimation to reduce polygon count (keep 70% of triangles)
    decimator = vtkQuadricDecimation()
    decimator.SetInputData(smoother.GetOutput())
    decimator.SetTargetReduction(0.3)
    decimator.Update()

    # Recompute normals for proper shading after smoothing/decimation
    normals_filter = vtkPolyDataNormals()
    normals_filter.SetInputData(decimator.GetOutput())
    normals_filter.SetFeatureAngle(80)
    normals_filter.AutoOrientNormalsOn()
    normals_filter.Update()

    return normals_filter.GetOutput()


def _export_textured_surface_worker(format, filename):
    import logging

    from invesalius.i18n import tr as _
    from invesalius.pubsub import pub as Publisher

    try:
        _export_textured_surface_worker_inner(format, filename)
    except Exception as e:
        logger = logging.getLogger("invesalius")
        logger.error(f"Error in export worker: {e}", exc_info=True)
        Publisher.sendMessage(
            "Update texture export progress", progress=100, status=_("Error during export")
        )


def _export_textured_surface_worker_inner(format, filename):
    import wx

    from invesalius import inv_paths
    from invesalius.i18n import tr as _
    from invesalius.project import Project

    Publisher.sendMessage(
        "Update texture export progress",
        progress=5,
        status=_("Reading volume rendering preset..."),
    )

    project = Project()

    # Get Volume instance (without creating a new one)
    app = wx.GetApp()
    if app and hasattr(app, "control"):
        vol = app.control.volume
    else:
        from invesalius.data.volume import Volume

        vol = Volume()

    if not vol or not vol.exist:
        Publisher.sendMessage(
            "Update texture export progress",
            progress=100,
            status=_("Error: Volume Rendering is not active"),
        )
        return

    config = project.raycasting_preset
    if not config:
        Publisher.sendMessage(
            "Update texture export progress",
            progress=100,
            status=_("Error: No raycasting preset loaded"),
        )
        return

    ww = vol.ww if vol.ww is not None else DEFAULT_WW
    wl = vol.wl if vol.wl is not None else DEFAULT_WL

    Publisher.sendMessage(
        "Update texture export progress",
        progress=10,
        status=_("Extracting isosurface thresholds from VR preset..."),
    )

    # Step 1: Extract isovalues from opacity curves
    isovalues = get_isovalues_from_preset(config)
    if not isovalues:
        Publisher.sendMessage(
            "Update texture export progress",
            progress=100,
            status=_("Error: Could not extract thresholds from preset"),
        )
        return

    # Step 1b: Extract full opacity transfer function for raycaster
    opacity_curve = get_opacity_curve_from_preset(config, ww=ww, wl=wl)

    logger.info(f"Extracted isovalues from VR preset: {isovalues}")
    logger.info(f"Opacity curve: {opacity_curve.shape[0]} points")

    Publisher.sendMessage(
        "Update texture export progress",
        progress=15,
        status=_("Generating surface from volume rendering..."),
    )

    # Step 2: Generate isosurface from volume data
    imagedata = vol.image
    if imagedata is None:
        Publisher.sendMessage(
            "Update texture export progress",
            progress=100,
            status=_("Error: Volume image data not available"),
        )
        return

    polydata = generate_surface_from_volume(imagedata, isovalues)
    n_points = polydata.GetNumberOfPoints()
    n_cells = polydata.GetNumberOfCells()

    if n_points == 0 or n_cells == 0:
        Publisher.sendMessage(
            "Update texture export progress",
            progress=100,
            status=_("Error: No surface generated (try different VR preset)"),
        )
        return

    logger.info(f"Auto-generated surface: {n_points} vertices, {n_cells} faces")

    Publisher.sendMessage(
        "Update texture export progress",
        progress=25,
        status=_("Preparing mesh data..."),
    )

    # Step 3: Convert to numpy arrays
    vertices, normals, faces = polydata_to_numpy(polydata)

    # Step 4: Load volume matrix and spacing
    from invesalius.data.slice_ import Slice

    sl = Slice()
    matrix = sl.matrix
    if matrix is None:
        Publisher.sendMessage(
            "Update texture export progress",
            progress=100,
            status=_("Error: No volume data loaded"),
        )
        return

    spacing = np.array(sl.spacing, dtype="float64")

    Publisher.sendMessage(
        "Update texture export progress",
        progress=30,
        status=_("Reading color lookup table..."),
    )

    # Step 5: Load CLUT
    clut_name = config.get("CLUT", "No CLUT") if config else "No CLUT"
    clut_path = None
    if clut_name != "No CLUT":
        clut_path = os.path.join(
            inv_paths.RAYCASTING_PRESETS_DIRECTORY, "color_list", clut_name + ".plist"
        )
    clut = load_clut(clut_path)

    texture_dim = DEFAULT_TEXTURE_DIM

    # Step 6: Y-axis alignment
    # Shift vertices to positive Y-space for matrix coordinate mapping.
    # NOTE: Do NOT flip Y-normals — the auto-generated mesh from vtkPolyDataNormals
    # already has correctly-oriented outward normals. This is just a translation.
    aligned_vertices = vertices.copy()
    y_min = aligned_vertices[:, 1].min()
    if y_min < 0:
        aligned_vertices[:, 1] -= y_min

    Publisher.sendMessage(
        "Update texture export progress",
        progress=35,
        status=_("Generating texture (this may take a few minutes)..."),
    )

    # Step 7: Call Rust raycaster with VR opacity transfer function
    try:
        tcoords, image_rgb, tnormals = invesalius_rs.generate_surface_texture(
            aligned_vertices.astype("float64"),
            normals.astype("float64"),
            faces.astype("int32"),
            matrix,
            spacing,
            int(ww),
            int(wl),
            clut,
            opacity_curve,
            texture_dim,
        )
    except Exception as e:
        logger.error(f"Error calling rust generate_surface_texture: {e}")
        Publisher.sendMessage(
            "Update texture export progress",
            progress=100,
            status=_("Error generating texture"),
        )
        return

    Publisher.sendMessage(
        "Update texture export progress", progress=80, status=_("Saving files...")
    )

    # Step 8: Save texture PNG
    base_dir = os.path.dirname(filename)
    base_name = os.path.basename(filename)
    name_without_ext = os.path.splitext(base_name)[0]

    safe_name = name_without_ext.replace(" ", "_").replace("-", "_")
    texture_filename = safe_name + "_texture.png"
    texture_filepath = os.path.join(base_dir, texture_filename)

    try:
        imsave(texture_filepath, image_rgb)
    except Exception as e:
        logger.error(f"Error saving texture PNG: {e}")
        Publisher.sendMessage(
            "Update texture export progress",
            progress=100,
            status=_("Error saving texture PNG"),
        )
        return

    Publisher.sendMessage(
        "Update texture export progress", progress=90, status=_("Writing 3D format...")
    )

    # Step 9: Write OBJ or VRML
    try:
        if format == "OBJ":
            mtl_filename = name_without_ext + ".mtl"
            mtl_filepath = os.path.join(base_dir, mtl_filename)

            with open(mtl_filepath, "w") as f:
                f.write("newmtl material_0\n")
                f.write("Ka 1.000000 1.000000 1.000000\n")
                f.write("Kd 1.000000 1.000000 1.000000\n")
                f.write("Ks 0.000000 0.000000 0.000000\n")
                f.write(f"map_Kd {texture_filename}\n")

            with open(filename, "w") as f:
                f.write(f"mtllib {mtl_filename}\n")
                for v in vertices:
                    f.write(f"v {v[0]:.6f} {-v[1]:.6f} {v[2]:.6f}\n")
                for vn in normals:
                    f.write(f"vn {vn[0]:.6f} {-vn[1]:.6f} {vn[2]:.6f}\n")

                for i in range(len(faces)):
                    vt1 = (tcoords[i, 0], tcoords[i, 1])
                    vt2 = (tcoords[i, 2], tcoords[i, 3])
                    vt3 = (tcoords[i, 4], tcoords[i, 5])
                    f.write(f"vt {vt1[0]:.6f} {vt1[1]:.6f}\n")
                    f.write(f"vt {vt2[0]:.6f} {vt2[1]:.6f}\n")
                    f.write(f"vt {vt3[0]:.6f} {vt3[1]:.6f}\n")

                f.write("usemtl material_0\n")

                vt_idx = 1
                for i in range(len(faces)):
                    v1 = faces[i, 0] + 1
                    v2 = faces[i, 1] + 1
                    v3 = faces[i, 2] + 1
                    f.write(f"f {v1}/{vt_idx}/{v1} {v2}/{vt_idx + 1}/{v2} {v3}/{vt_idx + 2}/{v3}\n")
                    vt_idx += 3

        elif format == "VRML":
            with open(filename, "w") as f:
                f.write("#VRML V2.0 utf8\n")
                f.write("Shape {\n")
                f.write("  appearance Appearance {\n")
                f.write("    material Material {\n")
                f.write("      diffuseColor 1.0 1.0 1.0\n")
                f.write("    }\n")
                f.write("    texture ImageTexture {\n")
                f.write(f'      url [ "{texture_filename}" ]\n')
                f.write("    }\n")
                f.write("  }\n")
                f.write("  geometry IndexedFaceSet {\n")
                f.write("    coord Coordinate {\n")
                f.write("      point [\n")
                for i, v in enumerate(vertices):
                    sep = "," if i < len(vertices) - 1 else ""
                    f.write(f"        {v[0]:.6f} {-v[1]:.6f} {v[2]:.6f}{sep}\n")
                f.write("      ]\n")
                f.write("    }\n")

                f.write("    coordIndex [\n")
                for i, face in enumerate(faces):
                    sep = "," if i < len(faces) - 1 else ""
                    f.write(f"      {face[0]}, {face[1]}, {face[2]}, -1{sep}\n")
                f.write("    ]\n")

                f.write("    texCoord TextureCoordinate {\n")
                f.write("      point [\n")
                for i in range(len(faces)):
                    sep = "," if i < len(faces) - 1 else ""
                    f.write(f"        {tcoords[i, 0]:.6f} {tcoords[i, 1]:.6f},\n")
                    f.write(f"        {tcoords[i, 2]:.6f} {tcoords[i, 3]:.6f},\n")
                    f.write(f"        {tcoords[i, 4]:.6f} {tcoords[i, 5]:.6f}{sep}\n")
                f.write("      ]\n")
                f.write("    }\n")

                f.write("    texCoordIndex [\n")
                vt_idx = 0
                for i in range(len(faces)):
                    sep = "," if i < len(faces) - 1 else ""
                    f.write(f"      {vt_idx}, {vt_idx + 1}, {vt_idx + 2}, -1{sep}\n")
                    vt_idx += 3
                f.write("    ]\n")

                f.write("    solid FALSE\n")
                f.write("  }\n")
                f.write("}\n")
    except Exception as e:
        logger.error(f"Error writing 3D format {format}: {e}")
        Publisher.sendMessage(
            "Update texture export progress",
            progress=100,
            status=_("Error writing 3D file"),
        )
        return

    Publisher.sendMessage(
        "Update texture export progress", progress=100, status=_("Export complete")
    )


def _start_export_textured_surface(format, filename, parent):
    import os
    import threading

    import wx

    from invesalius.gui.dialog_export_texture import ExportTextureProgressDialog
    from invesalius.i18n import tr as _

    # Show progress dialog immediately
    dlg = ExportTextureProgressDialog(parent)

    def _launch_worker():
        """Start the background thread after the dialog is fully visible."""
        thread = threading.Thread(target=_export_textured_surface_worker, args=(format, filename))
        thread.daemon = True
        thread.start()

    # Delay thread start by 100ms so the dialog is fully rendered first
    wx.CallLater(100, _launch_worker)

    # Block until the export finishes (dialog EndModal's itself)
    dlg.ShowModal()
    export_success = dlg._export_success
    dlg.Destroy()

    # Show success or error dialog
    if export_success:
        base_name = os.path.basename(filename)
        msg_dlg = wx.MessageDialog(
            parent,
            _("File saved successfully!\n\n") + base_name,
            _("Export Complete"),
            wx.OK | wx.ICON_INFORMATION,
        )
        msg_dlg.ShowModal()
        msg_dlg.Destroy()


Publisher.subscribe(_start_export_textured_surface, "Export textured surface")
