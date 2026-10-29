# -*- coding: UTF-8 -*-
import struct
from pathlib import Path

import pytest

from invesalius.data.eeg import EEGElectrode, EEGMontage


def read_fiff_tags(path: Path):
    """Read all sequential FIFF tags following the standard 4-byte padded format."""
    tags = []
    with path.open("rb") as stream:
        while True:
            header = stream.read(16)
            if not header or len(header) < 16:
                break
            kind, data_type, size, next_pos = struct.unpack(">4i", header)
            data = stream.read(size)
            assert len(data) == size, f"Premature EOF reading tag kind {kind}"
            pad = (4 - size % 4) % 4
            if pad:
                stream.seek(pad, 1)
            tags.append((kind, data_type, size, next_pos, data))
    return tags


def test_eeg_electrode_validation():
    electrode = EEGElectrode(position=[1.0, 2.0, 3.0], label="Cz")
    assert electrode.label == "Cz"
    assert electrode.position == [1.0, 2.0, 3.0]
    assert electrode.size == 2.0
    assert electrode.visible is True

    data_dict = electrode.to_dict()
    assert data_dict["label"] == "Cz"

    with pytest.raises(ValueError, match="nonempty label"):
        EEGElectrode(position=[0.0, 0.0, 0.0], label="")

    with pytest.raises(ValueError, match="finite numbers"):
        EEGElectrode(position=[0.0, float("nan"), 0.0], label="Fz")

    with pytest.raises(ValueError, match="positive and finite"):
        EEGElectrode(position=[0.0, 0.0, 0.0], label="Fz", size=-1.0)

    with pytest.raises(ValueError, match="between 0 and 1"):
        EEGElectrode(position=[0.0, 0.0, 0.0], label="Fz", colour=[1.5, 0.0, 0.0])


def test_write_fiff_padding(tmp_path: Path):
    fiff_file = tmp_path / "test_padding.fif"
    # Create tags with various payload lengths: 1, 2, 3, 4, 5, 6, 7, 8 bytes
    test_payloads = [
        (3507, 10, b"1"),
        (3507, 10, b"12"),
        (3507, 10, b"123"),
        (3507, 10, b"1234"),
        (3507, 10, b"12345"),
        (3507, 10, b"123456"),
        (3507, 10, b"1234567"),
        (3507, 10, b"12345678"),
        (105, 3, struct.pack(">i", 107)),
    ]

    EEGMontage._write_fiff(fiff_file, test_payloads)

    # Standard FIFF tags: 3 headers (100, 101, 106) + test_payloads + 1 footer (108)
    tags = read_fiff_tags(fiff_file)
    expected_count = 3 + len(test_payloads) + 1
    assert len(tags) == expected_count

    # Verify standard initial header tags
    assert tags[0][0] == 100  # FILE_ID
    assert tags[1][0] == 101  # DIR_POINTER
    assert tags[2][0] == 106  # FREE_LIST

    # Verify each custom tag payload was preserved and offset alignment was maintained
    for idx, (expected_kind, expected_dtype, expected_data) in enumerate(test_payloads):
        actual_kind, actual_dtype, actual_size, _actual_next, actual_data = tags[3 + idx]
        assert actual_kind == expected_kind
        assert actual_dtype == expected_dtype
        assert actual_size == len(expected_data)
        assert actual_data == expected_data

    # Verify trailing NOP tag
    assert tags[-1][0] == 108
    assert tags[-1][2] == 0
    assert tags[-1][3] == -1


def test_export_fif_montage(tmp_path: Path):
    dig_path = tmp_path / "test-dig.fif"
    trans_path = tmp_path / "test-trans.fif"

    # Channel names 'E1:E2' has length 5 bytes in tag 3507
    electrodes = [("E1", (10.0, 20.0, 30.0)), ("E2", (15.0, 25.0, 35.0))]
    metadata = {
        "AnatomicalLandmarksScannerRAS_mm": {
            "NAS": [0.0, 90.0, -10.0],
            "LPA": [-75.0, -15.0, -10.0],
            "RPA": [75.0, -15.0, -10.0],
        }
    }

    EEGMontage._export_fif(dig_path, trans_path, electrodes, metadata)

    assert dig_path.exists()
    assert trans_path.exists()

    # Read back dig file and ensure all tags match without corruption
    dig_tags = read_fiff_tags(dig_path)
    kinds = [t[0] for t in dig_tags]
    assert 104 in kinds  # FIFF_BLOCK_START
    assert 3506 in kinds  # FIFF_COORD_TRANS
    assert 213 in kinds  # FIFF_DIG_POINT
    assert 3507 in kinds  # FIFF_DIG_STRING (channel names)
    assert 105 in kinds  # FIFF_BLOCK_END
    assert 108 in kinds  # FIFF_NOP

    # Confirm the 3507 payload contains 'E1:E2'
    string_tag = next(t for t in dig_tags if t[0] == 3507)
    assert string_tag[4] == b"E1:E2"

    # Confirm trans tags
    trans_tags = read_fiff_tags(trans_path)
    trans_kinds = [t[0] for t in trans_tags]
    assert 222 in trans_kinds  # FIFF_COORD_TRANS
    assert 108 in trans_kinds  # FIFF_NOP


def test_get_export_paths(tmp_path: Path):
    fif_paths = EEGMontage.get_export_paths(str(tmp_path), "FIF", "montage")
    assert len(fif_paths) == 3
    assert fif_paths[0].name == "montage-dig.fif"
    assert fif_paths[1].name == "montage-trans.fif"
    assert fif_paths[2].name == "montage-dig_registration.json"

    bids_paths = EEGMontage.get_export_paths(str(tmp_path), "BIDS", "sub-01_electrodes.tsv")
    assert len(bids_paths) == 3
    assert bids_paths[0].name == "sub-01_electrodes.tsv"
    assert bids_paths[1].name == "sub-01_coordsystem.json"
    assert bids_paths[2].name == "sub-01_registration.json"

    with pytest.raises(ValueError, match="Unsupported EEG montage export format"):
        EEGMontage.get_export_paths(str(tmp_path), "UNKNOWN")
