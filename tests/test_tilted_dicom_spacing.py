import math
from unittest.mock import MagicMock

import numpy as np
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from invesalius.reader import dicom_reader
from invesalius.reader.dicom_grouper import DicomGroup


def _create_mock_slice(position, orientation_label="AXIAL", patient_orientation=None, number=1):
    mock_dicom = MagicMock()
    mock_dicom.image.position = list(position)
    mock_dicom.image.orientation_label = orientation_label
    mock_dicom.acquisition.patient_orientation = patient_orientation
    mock_dicom.image.number = number
    mock_dicom.image.type = ["ORIGINAL", "PRIMARY"]
    mock_dicom.image.number_of_frames = 1
    return mock_dicom


def test_tilted_series_slice_spacing():
    """Verify that tilted / oblique slice series compute the true 3D Euclidean spacing
    without being compressed by a factor of cos(tilt)."""
    true_spacing = 2.0

    # Note: 45-degree tilt is classified as OBLIQUE by GDCM, which is handled
    # separately in OpenDicomGroup (see issue #1074). We test tilts [0, 10, 20, 30]
    # under AXIAL and [60] under CORONAL.
    for tilt in [0, 10, 20, 30, 60]:
        t = math.radians(tilt)
        row = (1.0, 0.0, 0.0)
        col = (0.0, math.cos(t), math.sin(t))
        normal = (
            row[1] * col[2] - row[2] * col[1],
            row[2] * col[0] - row[0] * col[2],
            row[0] * col[1] - row[1] * col[0],
        )
        norm_len = math.sqrt(sum(v * v for v in normal))
        unit_normal = (normal[0] / norm_len, normal[1] / norm_len, normal[2] / norm_len)
        iop = [*row, *col]
        label = "AXIAL" if tilt < 45 else "CORONAL"

        group = DicomGroup()
        for i in range(10):
            pos = [float(v * true_spacing * i) for v in unit_normal]
            dcm = _create_mock_slice(
                position=pos,
                orientation_label=label,
                patient_orientation=iop,
                number=i + 1,
            )
            group.AddSlice(dcm)

        group.UpdateZSpacing()
        assert group.zspacing == pytest.approx(true_spacing, rel=1e-5), (
            f"Failed at tilt {tilt} deg: expected {true_spacing}, got {group.zspacing}"
        )


def test_gantry_tilted_ct_table_travel():
    """Verify that for gantry-tilted CT with table movement along Z,
    the Euclidean distance between consecutive slices equals delta-Z."""
    table_feed_z = 2.5
    tilt = 15.0
    t = math.radians(tilt)
    row = (1.0, 0.0, 0.0)
    col = (0.0, math.cos(t), math.sin(t))
    iop = [*row, *col]

    group = DicomGroup()
    for i in range(15):
        # Table advances strictly in Z
        pos = [0.0, 0.0, float(i * table_feed_z)]
        dcm = _create_mock_slice(
            position=pos,
            orientation_label="AXIAL",
            patient_orientation=iop,
            number=i + 1,
        )
        group.AddSlice(dcm)

    group.UpdateZSpacing()
    assert group.zspacing == pytest.approx(table_feed_z, rel=1e-6)


def test_coronal_and_sagittal_spacing():
    """Verify standard coronal and sagittal series compute correct slice spacing."""
    # Coronal: advances along Y
    coronal_group = DicomGroup()
    coronal_iop = [1.0, 0.0, 0.0, 0.0, 0.0, -1.0]
    for i in range(8):
        pos = [0.0, float(i * 1.5), 0.0]
        dcm = _create_mock_slice(
            position=pos,
            orientation_label="CORONAL",
            patient_orientation=coronal_iop,
            number=i + 1,
        )
        coronal_group.AddSlice(dcm)
    coronal_group.UpdateZSpacing()
    assert coronal_group.zspacing == pytest.approx(1.5, rel=1e-6)

    # Sagittal: advances along X
    sagittal_group = DicomGroup()
    sagittal_iop = [0.0, 1.0, 0.0, 0.0, 0.0, -1.0]
    for i in range(8):
        pos = [float(i * 3.0), 0.0, 0.0]
        dcm = _create_mock_slice(
            position=pos,
            orientation_label="SAGITTAL",
            patient_orientation=sagittal_iop,
            number=i + 1,
        )
        sagittal_group.AddSlice(dcm)
    sagittal_group.UpdateZSpacing()
    assert sagittal_group.zspacing == pytest.approx(3.0, rel=1e-6)


def test_jumbled_instance_numbers_sorted_by_spatial_projection():
    """Verify that slices with non-monotonic instance numbers are spatially
    sorted along the slice normal so consecutive pairs yield the correct spacing."""
    group = DicomGroup()
    spacing = 2.0
    iop = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]  # standard axial

    # Add slices in reverse or jumbled order, decoupling spatial index from InstanceNumber
    jumbled_indices = [5, 2, 8, 1, 0, 9, 3, 7, 4, 6]
    for n, idx in enumerate(jumbled_indices):
        pos = [0.0, 0.0, float(idx * spacing)]
        dcm = _create_mock_slice(
            position=pos,
            orientation_label="AXIAL",
            patient_orientation=iop,
            number=n + 1,
        )
        group.AddSlice(dcm)

    group.UpdateZSpacing()
    assert group.zspacing == pytest.approx(spacing, rel=1e-6)


def test_single_slice_defaults_to_one():
    """Verify single slice group defaults to zspacing = 1."""
    group = DicomGroup()
    dcm = _create_mock_slice(position=[0.0, 0.0, 10.0], orientation_label="AXIAL", number=1)
    group.AddSlice(dcm)
    group.UpdateZSpacing()
    assert group.zspacing == 1


def test_real_reader_tilted_dicom_spacing(tmp_path):
    """Verify end-to-end DICOM reading with pydicom synthetic series exercising
    Acquisition.SetParser and d.acquisition.patient_orientation."""
    tilt_rad = math.radians(30.0)
    true_spacing = 2.0
    row = [1.0, 0.0, 0.0]
    col = [0.0, math.cos(tilt_rad), math.sin(tilt_rad)]
    normal = [0.0, -math.sin(tilt_rad), math.cos(tilt_rad)]

    series_uid = generate_uid()
    study_uid = generate_uid()

    for idx in range(5):
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = MRImageStorage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        filename = str(tmp_path / f"slice_{idx}.dcm")
        ds = FileDataset(filename, {}, file_meta=file_meta, preamble=b"\0" * 128)
        ds.PatientName = "Test^Patient"
        ds.PatientID = "12345"
        ds.StudyInstanceUID = study_uid
        ds.StudyID = "1"
        ds.SeriesInstanceUID = series_uid
        ds.SeriesNumber = 1
        ds.SOPClassUID = MRImageStorage
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.Modality = "MR"
        ds.InstanceNumber = idx + 1
        ds.ImageOrientationPatient = [float(x) for x in row + col]
        pos = [float(idx * true_spacing * n) for n in normal]
        ds.ImagePositionPatient = pos
        ds.PixelSpacing = [1.0, 1.0]
        ds.Rows = 16
        ds.Columns = 16
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.PixelData = np.zeros((16, 16), dtype=np.uint16).tobytes()
        ds.save_as(filename, write_like_original=False)

    patients = dicom_reader.GetDicomGroups(str(tmp_path))
    assert len(patients) > 0
    groups = patients[0].GetGroups()
    assert len(groups) > 0
    assert groups[0].zspacing == pytest.approx(true_spacing, rel=1e-3)
