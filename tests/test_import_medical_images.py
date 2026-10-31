from unittest.mock import MagicMock, patch

import pytest

from invesalius.control import Controller


@pytest.fixture
def controller():
    ctrl = object.__new__(Controller)
    return ctrl


def test_import_directory_no_extension_no_dicom(controller):
    """Importing a non-DICOM folder without extension should return cleanly without IndexError."""
    with patch("invesalius.reader.dicom_reader.GetDicomGroups", return_value=[]):
        # Should not raise IndexError
        controller.ImportMedicalImages("/path/to/dicom_folder")


def test_import_medical_images_multi_dot_nii(controller):
    """Importing a NIfTI file with multiple dots should extract the correct filetype and project name."""
    mock_group = MagicMock()
    with (
        patch("invesalius.reader.dicom_reader.GetDicomGroups", return_value=[]),
        patch("invesalius.reader.others_reader.ReadOthers", return_value=mock_group) as mock_read,
        patch.object(controller, "OpenOtherFiles", return_value=("matrix", "filename")),
        patch.object(controller, "CreateOtherProject") as mock_create_proj,
        patch.object(controller, "LoadProject") as mock_load_proj,
        patch("invesalius.pubsub.pub.sendMessage") as mock_pub,
    ):
        controller.ImportMedicalImages("/data/scans/patient.01.scan.nii")

        mock_read.assert_called_once_with("/data/scans/patient.01.scan.nii")
        mock_create_proj.assert_called_once_with("patient.01.scan", "matrix", "filename")
        mock_load_proj.assert_called_once()
        mock_pub.assert_called_once_with("Enable state project", state=True)


def test_import_medical_images_nii_gz(controller):
    """Importing a compressed NIfTI (.nii.gz) file should parse extension and base name correctly."""
    mock_group = MagicMock()
    with (
        patch("invesalius.reader.dicom_reader.GetDicomGroups", return_value=[]),
        patch("invesalius.reader.others_reader.ReadOthers", return_value=mock_group) as mock_read,
        patch.object(controller, "OpenOtherFiles", return_value=("matrix", "filename")),
        patch.object(controller, "CreateOtherProject") as mock_create_proj,
        patch.object(controller, "LoadProject") as mock_load_proj,
        patch("invesalius.pubsub.pub.sendMessage") as mock_pub,
    ):
        controller.ImportMedicalImages("C:\\images\\sub-01.t1.nii.gz")

        mock_read.assert_called_once_with("C:\\images\\sub-01.t1.nii.gz")
        mock_create_proj.assert_called_once_with("sub-01.t1", "matrix", "filename")
        mock_load_proj.assert_called_once()
        mock_pub.assert_called_once_with("Enable state project", state=True)


def test_import_medical_images_read_others_fails(controller):
    """If ReadOthers returns False or None, LoadProject should not be invoked."""
    with (
        patch("invesalius.reader.dicom_reader.GetDicomGroups", return_value=[]),
        patch("invesalius.reader.others_reader.ReadOthers", return_value=False) as mock_read,
        patch.object(controller, "OpenOtherFiles") as mock_open_other,
        patch.object(controller, "CreateOtherProject") as mock_create_proj,
        patch.object(controller, "LoadProject") as mock_load_proj,
    ):
        controller.ImportMedicalImages("/data/scans/corrupt.nii")

        mock_read.assert_called_once_with("/data/scans/corrupt.nii")
        mock_open_other.assert_not_called()
        mock_create_proj.assert_not_called()
        mock_load_proj.assert_not_called()
