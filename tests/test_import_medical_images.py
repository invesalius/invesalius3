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
        controller.ImportMedicalImages("/images/sub-01.t1.nii.gz")

        mock_read.assert_called_once_with("/images/sub-01.t1.nii.gz")
        mock_create_proj.assert_called_once_with("sub-01.t1", "matrix", "filename")
        mock_load_proj.assert_called_once()
        mock_pub.assert_called_once_with("Enable state project", state=True)


def test_import_medical_images_backslash_path(controller):
    """Importing a path with backslashes on any OS should parse extension and base name correctly."""
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


def test_no_gui_failed_import_exits_with_error(capsys):
    """In --no-gui mode, a failed import should print an error and exit with code 1 instead of continuing to export."""
    from app import use_cmd_optargs

    args = MagicMock()
    args.dicom_dir = "/path/to/corrupt_or_empty"
    args.no_gui = True
    args.save = False
    args.cranioplasty = False
    args.export_project = "out.hdf5"
    args.export = False
    args.export_to_all = False

    with (
        patch("invesalius.pubsub.pub.sendMessage"),
        patch("invesalius.session.Session.IsOpen", return_value=False),
        pytest.raises(SystemExit) as exc_info,
    ):
        use_cmd_optargs(args)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Failed to import medical images" in captured.out


def test_check_for_export_without_loaded_project(capsys):
    """check_for_export should not attempt export if no project or matrix is loaded."""
    from app import check_for_export

    args = MagicMock()
    args.export = "out.stl"
    args.threshold = "100,500"
    args.export_to_all = False
    args.export_project = False
    args.no_gui = True

    with (
        patch("invesalius.session.Session.IsOpen", return_value=False),
        patch("invesalius.data.slice_.Slice.matrix", None),
        pytest.raises(SystemExit) as exc_info,
    ):
        check_for_export(args)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Export cancelled" in captured.out


def test_export_project_to_hdf5_without_matrix():
    """export_project_to_hdf5 should raise ValueError if Slice matrix is None, avoiding corrupt file creation."""
    from invesalius.project import Project

    prj = Project()
    with (
        patch("invesalius.data.slice_.Slice.matrix", None),
        pytest.raises(ValueError, match="No image data to export"),
    ):
        prj.export_project_to_hdf5("test.hdf5")
