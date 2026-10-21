import json
from pathlib import Path
from struct import unpack
from types import SimpleNamespace

import numpy as np
import pytest

import invesalius.data.slice_ as slice_module
import invesalius.project as project_module
from invesalius.data import eeg_montage, imagedata_utils
from invesalius.data.bases import ras_to_head_matrix
from invesalius.data.eeg_electrode import EEGElectrode


@pytest.fixture
def montage(monkeypatch):
    image = SimpleNamespace(matrix=np.zeros((2, 3, 4)), spacing=(1.0, 1.0, 1.0))
    project = SimpleNamespace(
        name="Test MRI",
        active_image_version="original",
        image_fiducials=np.array([[-80, 0, 0], [80, 0, 0], [0, 100, 0]], dtype=float),
    )
    monkeypatch.setattr(slice_module, "Slice", lambda: image)
    monkeypatch.setattr(project_module, "Project", lambda: project)
    monkeypatch.setattr(
        imagedata_utils,
        "convert_invesalius_to_world",
        lambda position, orientation: (
            np.asarray(position, dtype=float) + [10, 20, 30],
            orientation,
        ),
    )
    electrodes = [EEGElectrode([1, 2, 3], "Pz"), EEGElectrode([4, 5, 6], "Cz")]
    return electrodes, project


@pytest.mark.parametrize("export_format", ["BIDS", "HPTS", "SFP", "ELC", "FIF"])
def test_exports_write_all_files_and_registration_metadata(montage, tmp_path, export_format):
    electrodes, _project = montage
    paths = [Path(path) for path in eeg_montage.export_montage(electrodes, tmp_path, export_format)]
    assert paths == eeg_montage.get_export_paths(tmp_path, export_format)
    assert all(path.stat().st_size > 0 for path in paths)
    metadata = json.loads(paths[-1].read_text())
    assert metadata["ExportFormat"] == export_format
    assert metadata["ElectrodeRegistrations"][0]["ElectrodeUUID"] == electrodes[0].electrode_uuid
    assert metadata["ImageToScannerRAS"]["Matrix"] == [
        [1, 0, 0, 10],
        [0, 1, 0, 20],
        [0, 0, 1, 30],
        [0, 0, 0, 1],
    ]
    if export_format == "BIDS":
        assert paths[0].read_text().splitlines() == [
            "name\tx\ty\tz",
            "Cz\t14.0\t25.0\t36.0",
            "Pz\t11.0\t22.0\t33.0",
        ]
    elif export_format == "HPTS":
        assert "eeg Cz 14.00 25.00 36.00" in paths[0].read_text()
    elif export_format == "SFP":
        assert "Cz 14.000000 25.000000 36.000000" in paths[0].read_text()
    elif export_format == "ELC":
        assert "NumberPositions= 5" in paths[0].read_text()
        assert paths[0].read_text().splitlines()[-2:] == ["Cz", "Pz"]
    else:
        data = paths[0].read_bytes()
        dig_points = []
        channel_names = None
        offset = 0
        while offset < len(data):
            kind, _data_type, size, next_tag = unpack(">4i", data[offset : offset + 16])
            value = data[offset + 16 : offset + 16 + size]
            if kind == 213:
                dig_points.append(unpack(">ii3f", value))
            if kind == 3507:
                channel_names = value.decode("latin1")
            offset += 16 + size
            if next_tag == -1:
                break
        assert channel_names == "Cz:Pz"
        assert len(dig_points) == 5
        assert dig_points[3][:2] == (3, 1)
        # Translation is removed by the fiducial-defined head frame; output is meters.
        assert dig_points[3][2:] == pytest.approx([0.004, 0.005, 0.006])
        assert metadata["ExportedCoordinateUnits"] == "m"
        assert metadata["MNETransformFile"]["File"] == paths[1].name


def test_validation_failure_preserves_existing_export_files(montage, tmp_path):
    electrodes, project = montage
    paths = eeg_montage.get_export_paths(tmp_path, "FIF")
    for path in paths:
        path.write_text("previous export")
    project.image_fiducials[:] = np.nan
    with pytest.raises(ValueError, match="requires NAS"):
        eeg_montage.export_montage(electrodes, tmp_path, "FIF")
    assert all(path.read_text() == "previous export" for path in paths)
    assert sorted(tmp_path.iterdir()) == sorted(paths)


def test_duplicate_labels_and_missing_mri_are_rejected(montage, monkeypatch, tmp_path):
    electrodes, _project = montage
    electrodes[1].label = electrodes[0].label
    with pytest.raises(ValueError, match="Duplicate"):
        eeg_montage.export_montage(electrodes, tmp_path, "BIDS")
    electrodes[1].label = "Cz"
    monkeypatch.setattr(
        imagedata_utils, "convert_invesalius_to_world", lambda *args: ((None,) * 3, (None,) * 3)
    )
    with pytest.raises(ValueError, match="MRI world"):
        eeg_montage.export_montage(electrodes, tmp_path, "BIDS")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "fiducials",
    [
        [[0, 1, 0], [0, 0, 0], [0, 0, 0]],
        [[0, 0, 0], [-1, 0, 0], [1, 0, 0]],
        [[0, float("inf"), 0], [-1, 0, 0], [1, 0, 0]],
    ],
)
def test_head_frame_rejects_degenerate_fiducials(fiducials):
    with pytest.raises(ValueError):
        ras_to_head_matrix(*fiducials)
