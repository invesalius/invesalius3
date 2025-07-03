import os

from invesalius.reader import dicom_reader


def test_dicom_loading():
    # Path to the directory containing DICOM files
    dicom_dir = os.path.join(os.path.dirname(__file__), "data")
    patients = dicom_reader.GetDicomGroups(dicom_dir, recursive=True)
    groups = patients[0].GetGroups()
    group = groups[0]
    expected_key = ("CT 0051 - InVesalius Sample", "000001", "000002", "AXIAL", 0)
    assert (
        group.key == expected_key
    ), f"Group key {group.key} does not match expected {expected_key}"
    slices = list(group.GetList())
    assert len(slices) == 108, f"Expected 108 slices, got {len(slices)}"
    dicom = slices[0]
    assert (
        dicom.patient.name == "CT 0051 - InVesalius Sample"
    ), f"Expected patient name 'CT 0051 - InVesalius Sample', got '{dicom.patient.name}'"
    spacing = dicom.image.spacing
    assert spacing == [
        0.4785156,
        0.4785156,
        2.0,
    ], f"Expected spacing [0.4785156, 0.4785156, 2.0], got {spacing}"
    size = dicom.image.size
    assert size == (512, 512), f"Expected size (512, 512), got {size}"
    assert (
        dicom.image.orientation_label == "AXIAL"
    ), f"Expected orientation label 'AXIAL', got '{dicom.image.orientation_label}'"
    assert os.path.exists(dicom.image.file)
