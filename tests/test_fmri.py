import math

import numpy as np
import vtk

import invesalius.data.fmri as fmri


def test_yeo_networks_definitions():
    # Verify Yeo 7 networks
    assert len(fmri.YEO_7_NETWORKS) == 7
    for i in range(1, 8):
        assert i in fmri.YEO_7_NETWORKS
        net = fmri.YEO_7_NETWORKS[i]
        assert "name" in net
        assert "color" in net
        assert len(net["color"]) == 3
        assert all(0 <= c <= 255 for c in net["color"])

    # Verify Yeo 17 networks
    assert len(fmri.YEO_17_NETWORKS) == 17
    for i in range(1, 18):
        assert i in fmri.YEO_17_NETWORKS
        net = fmri.YEO_17_NETWORKS[i]
        assert "name" in net
        assert "color" in net
        assert len(net["color"]) == 3


def test_generate_synthetic_yeo_parcellation():
    shape = (20, 30, 30)
    parc = fmri.generate_synthetic_yeo_parcellation(shape)
    assert parc.shape == shape
    assert parc.dtype == np.uint8
    unique_labels = set(np.unique(parc))
    assert 0 in unique_labels
    # Ensure cortical networks 1 to 7 are present
    assert len(unique_labels) > 4
    for val in unique_labels:
        assert 0 <= val <= 7


def test_build_categorical_colormap():
    labels = np.array([0, 1, 2, 7])
    cmap_dict = fmri.build_categorical_colormap(labels, fmri.YEO_7_NETWORKS, active_labels={1, 7})
    # Label 0 must be transparent
    assert cmap_dict[0] == (0.0, 0.0, 0.0, 0.0)
    # Active label 1 must be opaque and have correct RGB
    assert cmap_dict[1][3] == 1.0
    r1, g1, b1 = (c / 255.0 for c in fmri.YEO_7_NETWORKS[1]["color"])
    assert math.isclose(cmap_dict[1][0], r1, rel_tol=1e-3)
    assert math.isclose(cmap_dict[1][1], g1, rel_tol=1e-3)
    assert math.isclose(cmap_dict[1][2], b1, rel_tol=1e-3)
    # Disabled label 2 must be transparent
    assert cmap_dict[2] == (0.0, 0.0, 0.0, 0.0)


def test_generate_synthetic_4d_bold():
    shape = (15, 20, 20)
    num_frames = 25
    bold = fmri.generate_synthetic_4d_bold(shape, num_frames=num_frames)
    assert bold.shape == (15, 20, 20, 25)
    assert bold.dtype == np.float32
    assert np.any(bold > 0)


def test_compute_seed_correlation():
    shape = (12, 16, 16)
    num_frames = 40
    np.random.seed(123)
    bold_4d = np.random.randn(*shape, num_frames).astype(np.float32)

    # Inject correlated signal in two voxels
    signal = np.sin(np.linspace(0, 4 * math.pi, num_frames)).astype(np.float32) * 5.0
    bold_4d[6, 8, 8, :] += signal
    bold_4d[6, 10, 10, :] += signal

    seed_coord = (6, 8, 8)
    r_map, thresh_map = fmri.compute_seed_correlation(bold_4d, seed_coord, threshold=0.4)

    assert r_map.shape == shape
    assert thresh_map.shape == shape
    # Seed voxel self-correlation must be ~1.0
    assert math.isclose(r_map[6, 8, 8], 1.0, abs_tol=1e-3)
    # Correlated voxel must have high r
    assert r_map[6, 10, 10] > 0.7
    assert thresh_map[6, 10, 10] > 0.7
    # Distant random voxel must be low or thresholded to 0
    assert thresh_map[0, 0, 0] == 0.0


def test_resample_volume():
    # 3D categorical labels
    orig_3d = np.array([[[1, 2], [3, 0]]], dtype=np.uint8)
    target_shape = (4, 6, 6)
    res_3d = fmri.resample_volume(orig_3d, target_shape, is_categorical=True)
    assert res_3d.shape == target_shape
    assert set(np.unique(res_3d)).issubset({0, 1, 2, 3})

    # 4D continuous data
    orig_4d = np.random.randn(3, 4, 4, 10).astype(np.float32)
    res_4d = fmri.resample_volume(orig_4d, target_shape, is_categorical=False)
    assert res_4d.shape == (4, 6, 6, 10)


def test_generate_synthetic_gradient():
    shape = (16, 20, 20)
    grad = fmri.generate_synthetic_gradient(shape)
    assert grad.shape == shape
    assert grad.dtype == np.float32
    assert np.min(grad) >= -1.0
    assert np.max(grad) <= 1.0
    assert np.any(grad > 0)
    assert np.any(grad < 0)


def test_build_continuous_colormap():
    data = np.linspace(-2.0, 5.0, 100).reshape((5, 5, 4))
    vol, color_dict, zero_val = fmri.build_continuous_colormap(
        data, colormap_name="hot", min_thresh=1.0, two_sided=False
    )
    assert vol.shape == (5, 5, 4)
    assert vol.dtype == np.uint8
    assert zero_val in color_dict
    assert color_dict[zero_val] == (0.0, 0.0, 0.0, 0.0)
    # Values above threshold must have non-zero alpha
    max_uint8 = int(np.max(vol))
    assert color_dict[max_uint8][3] == 1.0


def test_fmri_overlay_manager():
    mgr = fmri.FMRIOverlayManager()
    shape = (16, 24, 24)

    # 1. Parcellation Modality
    mgr.generate_demo_data(fmri.MODALITY_PARCELLATION, shape)
    assert mgr.modality == fmri.MODALITY_PARCELLATION
    assert mgr.cluster_volume.shape == shape
    assert not mgr.is_4d
    assert len(mgr.color_dict) > 1

    # Toggle network off
    mgr.toggle_network(1, False)
    assert 1 not in mgr.active_networks
    assert mgr.color_dict[1] == (0.0, 0.0, 0.0, 0.0)

    # 2. Beta & 4D BOLD Modality
    mgr.generate_demo_data(fmri.MODALITY_BETA_BOLD, shape)
    assert mgr.is_4d
    assert mgr.num_timeframes == 30
    assert mgr.current_timeframe == 0
    mgr.set_timeframe(5)
    assert mgr.current_timeframe == 5
    assert mgr.cluster_volume.shape == shape

    # Thresholding
    mgr.set_threshold(min_thresh=0.5)
    assert mgr.min_threshold == 0.5

    # 3. Seed FC Modality
    mgr.generate_demo_data(fmri.MODALITY_SEED_FC, shape)
    assert mgr.modality == fmri.MODALITY_SEED_FC
    mgr.set_seed_coord(8, 12, 12)
    assert mgr.seed_coord == (8, 12, 12)
    assert mgr.cluster_volume.shape == shape

    # 4. Gradient Modality
    mgr.generate_demo_data(fmri.MODALITY_GRADIENT, shape)
    assert mgr.modality == fmri.MODALITY_GRADIENT
    assert mgr.cluster_volume.shape == shape


def test_map_overlay_to_surface():
    sphere = vtk.vtkSphereSource()
    sphere.SetRadius(10.0)
    sphere.Update()
    polydata = sphere.GetOutput()
    num_pts = polydata.GetNumberOfPoints()

    shape = (20, 20, 20)
    overlay = np.ones(shape, dtype=np.uint8)
    color_dict = {
        0: (0.0, 0.0, 0.0, 0.0),
        1: (1.0, 0.0, 0.0, 1.0),
    }

    colors = fmri.map_overlay_to_surface(
        polydata, overlay, color_dict, spacing=(1.0, 1.0, 1.0)
    )
    assert colors.GetNumberOfTuples() == num_pts
    assert colors.GetNumberOfComponents() == 4


def test_slice_overlay_integration():
    from invesalius.data.slice_ import Slice

    slic = Slice()
    vol_shape = (16, 24, 24)
    rng = np.random.RandomState(42)
    slic.matrix = rng.randint(20, 500, size=vol_shape, dtype=np.int16)
    slic.spacing = (1.0, 1.0, 1.0)
    slic.window_width = 200
    slic.window_level = 100

    mgr = fmri.FMRIOverlayManager()

    for mod in fmri.MODALITY_CHOICES:
        mgr.generate_demo_data(mod, vol_shape)
        slic.aux_matrices["color_overlay"] = mgr.cluster_volume
        slic.aux_matrices_colours["color_overlay"] = mgr.color_dict
        slic.to_show_aux = "color_overlay"

        for ori in ["AXIAL", "CORONAL", "SAGITAL"]:
            img = slic.GetSlices(orientation=ori, slice_number=8, number_slices=1)
            assert img is not None
            assert img.GetNumberOfScalarComponents() >= 3

    slic.to_show_aux = ""


def test_task_fmrisupport_gui_integration():
    import wx

    import invesalius.gui.task_fmrisupport as task_fmri

    app = wx.App.Get()
    if app is None:
        app = wx.App(False)

    frame = wx.Frame(None, -1, "Test fMRI")
    panel = task_fmri.TaskPanel(frame)
    inner = panel.GetChildren()[0]

    for mod in fmri.MODALITY_CHOICES:
        inner.combo_modality.SetStringSelection(mod)
        inner.OnSelectModality(None)
        assert inner.manager.modality == mod

        inner.OnLoadDemo(None)
        assert inner.manager.cluster_volume is not None

    # Test timeframe change
    if inner.manager.is_4d:
        inner.slider_timeframe.SetValue(1)
        inner.OnTimeframeChange(None)
        assert inner.manager.current_timeframe == 1

    # Test threshold change
    inner.slider_threshold.SetValue(20)
    inner.OnThresholdChange(None)

    # Test seed setting
    inner.OnSetSeedFromCrosshair(None)

    # Test clearing overlay
    inner.OnClearOverlay(None)
    assert inner.slc.to_show_aux == ""

    frame.Destroy()

