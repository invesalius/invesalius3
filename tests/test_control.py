from unittest.mock import call, patch

import pytest
import wx

import invesalius.constants as const
import invesalius.utils as utils
from invesalius.control import Controller
from invesalius.pubsub import pub as Publisher


@pytest.fixture
def mock_session(mocker):
    mock_session = mocker.patch("invesalius.session.Session")
    mock_instance = mock_session.return_value
    return mock_instance


@pytest.fixture
def mock_publisher(mocker):
    return mocker.patch.object(Publisher, "sendMessage")


@pytest.fixture
def mock_utils(mocker):
    return mocker.patch.object(utils, "debug")


def test_set_bitmap_spacing():
    controller = Controller(None)
    with patch("invesalius.project.Project") as mock_project:
        instance = mock_project.return_value
        controller.SetBitmapSpacing((1.0, 1.0, 1.0))
        assert instance.spacing == (1.0, 1.0, 1.0)


def test_show_dialog_import_directory(mock_session, mocker):
    controller = Controller(None)

    mock_import_dialog = mocker.patch(
        "invesalius.gui.dialogs.ShowImportDirDialog", return_value="/test/dummyPath"
    )
    mock_listdir = mocker.patch("os.listdir", return_value=[])
    mock_start_import_panel = mocker.patch.object(controller, "StartImportPanel")
    mock_import_empty_dialog = mocker.patch("invesalius.gui.dialogs.ImportEmptyDirectory")

    controller.ShowDialogImportDirectory()

    mock_import_dialog.assert_called_once()
    mock_listdir.assert_called_once_with("/test/dummyPath")

    # Verify behavior when directory is empty
    mock_import_empty_dialog.assert_called_once_with(
        "/test/dummyPath"
    )  # Ensure ImportEmptyDirectory is called
    mock_start_import_panel.assert_not_called()
    mock_listdir.return_value = ["file1.dcm", "file2.dcm"]
    controller.ShowDialogImportDirectory()
    mock_start_import_panel.assert_called_once_with("/test/dummyPath")


def test_on_cancel_import(mocker):
    controller = Controller(None)
    mock_pub = mocker.patch.object(Publisher, "sendMessage")

    controller.OnCancelImport()
    mock_pub.assert_called_with("Hide import panel")


@patch.object(Publisher, "sendMessage")
def test_show_dialog_import_other_files(mock_send_message, mock_session, mocker):
    controller = Controller(None)
    mock_session.GetConfig.return_value = const.PROJECT_STATUS_CHANGED
    mock_session.GetState.return_value = ["", "test_project.inv3"]
    mock_session.IsOpen.return_value = True
    mock_save_dialog = mocker.patch("invesalius.gui.dialogs.SaveChangesDialog2", return_value=True)
    mock_save_project = mocker.patch.object(controller, "ShowDialogSaveProject")
    mock_close_project = mocker.patch.object(controller, "CloseProject")
    mock_import_dialog = mocker.patch(
        "invesalius.gui.dialogs.ShowImportOtherFilesDialog", return_value="/dummy/path/file.txt"
    )

    controller.ShowDialogImportOtherFiles(wx.ID_ANY)

    mock_session.GetConfig.assert_any_call("project_status")
    mock_save_dialog.assert_called_once_with("test_project.inv3")
    mock_save_project.assert_called_once()
    mock_close_project.assert_called_once()
    mock_import_dialog.assert_called_once_with(wx.ID_ANY)
    mock_send_message.assert_any_call("Set project name")
    mock_send_message.assert_any_call("Stop Config Recording")
    mock_send_message.assert_any_call("Enable style", style=const.STATE_DEFAULT)
    mock_send_message.assert_any_call("Open other files", filepath="/dummy/path/file.txt")


def test_show_dialog_open_project(mock_session, mocker):
    controller = Controller(None)
    mock_session.GetConfig.return_value = const.PROJECT_STATUS_NEW
    mock_session.GetState.return_value = ["", "test_project.inv3"]
    mock_session.IsOpen.return_value = True
    mock_save_dialog = mocker.patch("invesalius.gui.dialogs.SaveChangesDialog2", return_value=True)
    mock_save_project = mocker.patch.object(controller, "ShowDialogSaveProject")
    mock_close_project = mocker.patch.object(controller, "CloseProject")
    mock_open_dialog = mocker.patch(
        "invesalius.gui.dialogs.ShowOpenProjectDialog", return_value="/dummy/path/project.inv3"
    )
    mock_open_project = mocker.patch.object(controller, "OpenProject")

    controller.ShowDialogOpenProject()

    mock_session.GetConfig.assert_any_call("project_status")
    mock_save_dialog.assert_called_once_with("test_project.inv3")
    mock_save_project.assert_called_once()
    mock_open_dialog.assert_called_once()
    mock_session.IsOpen.assert_called_once()
    mock_close_project.assert_called_once()
    mock_open_project.assert_called_once_with("/dummy/path/project.inv3")


def test_show_dialog_save_project(mock_session, mocker):
    controller = Controller(None)
    mock_project = mocker.patch("invesalius.project.Project")
    mock_project_instance = mock_project.return_value
    mock_project_instance.name = "test_project"
    mock_project_instance.compress = True
    mock_session.GetState.return_value = ["/dummy/path", "test_project.inv3"]
    mock_save_as_dialog = mocker.patch(
        "invesalius.gui.dialogs.ShowSaveAsProjectDialog",
        return_value=("/dummy/path/test_project.inv3", True),
    )
    mock_save_project = mocker.patch.object(controller, "SaveProject")

    controller.ShowDialogSaveProject(saveas=True)

    mock_save_as_dialog.assert_called_once_with("test_project")
    mock_save_project.assert_called_once_with("/dummy/path/test_project.inv3", True)

    controller.ShowDialogSaveProject(saveas=False)

    mock_save_project.assert_called_with(
        "/dummy/path/test_project.inv3", mock_project_instance.compress
    )


@pytest.mark.parametrize(
    "project_status, get_state_side_effect, save_dialog_return, debug_msg, expected_publisher_calls",
    [
        (
            const.PROJECT_STATUS_CLOSED,
            None,
            None,
            None,
            [],
        ),  # Already closed -> return -1, nothing happens
        (
            const.PROJECT_STATUS_NEW,
            AttributeError,
            None,
            "Project doesn't exist",
            [call("Stop Config Recording")],
        ),  # No project -> log msg, stop config
        (
            const.PROJECT_STATUS_CHANGED,
            None,
            -1,
            "Cancel",
            [],
        ),  # Unsaved changes, user cancels -> nothing happens
        (
            const.PROJECT_STATUS_CHANGED,
            None,
            0,
            "Close without changes",
            [  # Unsaved changes, user discards -> close project
                call("Enable state project", state=False),
                call("Set project name"),
                call("Stop Config Recording"),
            ],
        ),
        (
            const.PROJECT_STATUS_CHANGED,
            None,
            1,
            "Save changes and close",
            [  # Unsaved changes, user saves and closes -> save & close project
                call("Enable state project", state=False),
                call("Set project name"),
                call("Stop Config Recording"),
            ],
        ),
    ],
)
def test_show_dialog_close_project(
    mock_session,
    mock_publisher,
    mock_utils,
    mocker,
    project_status,
    get_state_side_effect,
    save_dialog_return,
    debug_msg,
    expected_publisher_calls,
):
    controller = Controller(None)
    mock_publisher.reset_mock()
    mock_session.reset_mock()

    mock_session.GetConfig.return_value = project_status
    mock_session.GetState.side_effect = (
        get_state_side_effect if get_state_side_effect else lambda key: ["", "test_project.inv3"]
    )
    mock_save_dialog = mocker.patch(
        "invesalius.gui.dialogs.SaveChangesDialog", return_value=save_dialog_return
    )
    mock_save_project = mocker.patch.object(controller, "ShowDialogSaveProject")
    mock_close_project = mocker.patch.object(controller, "CloseProject")

    result = controller.ShowDialogCloseProject()

    if project_status == const.PROJECT_STATUS_CLOSED:
        assert result == -1
        mock_publisher.assert_not_called()

    if get_state_side_effect is AttributeError:
        mock_utils.assert_called_once_with(debug_msg)
        mock_publisher.assert_called_once_with("Stop Config Recording")
        mock_close_project.assert_not_called()
        assert result is None

    if save_dialog_return is not None:
        mock_save_dialog.assert_called_once_with("test_project.inv3", controller.frame)

        if save_dialog_return == -1:
            mock_utils.assert_called_once_with(debug_msg)
            mock_close_project.assert_not_called()
            assert result is None

        if save_dialog_return == 0:
            mock_utils.assert_called_once_with(debug_msg)
            mock_close_project.assert_called_once()
            assert result is None

        if save_dialog_return == 1:
            mock_utils.assert_called_once_with(debug_msg)
            mock_save_project.assert_called_once()
            mock_close_project.assert_called_once()
            assert result is None

    if expected_publisher_calls:
        mock_publisher.assert_has_calls(expected_publisher_calls, any_order=True)
        assert mock_publisher.call_count == len(expected_publisher_calls)
    else:
        mock_publisher.assert_not_called()


@pytest.mark.parametrize(
    "file_exists, project_status, save_dialog_return, session_is_open",
    [
        (True, const.PROJECT_STATUS_NEW, 1, True),  # New project, user chooses to save
        (True, const.PROJECT_STATUS_CHANGED, 0, True),  # Changed project, user discards changes
        (True, const.PROJECT_STATUS_CHANGED, -1, False),  # Changed project, user cancels
        (False, None, None, None),  # Filepath does not exist
    ],
)
def test_on_open_recent_project(
    mock_session, mocker, file_exists, project_status, save_dialog_return, session_is_open
):
    controller = Controller(None)
    mock_session.reset_mock()
    filepath = "/dummy/path/project.inv3"

    mocker.patch("os.path.exists", return_value=file_exists)
    mock_session.GetConfig.return_value = project_status
    mock_session.GetState.return_value = ["", "test_project.inv3"]
    mock_session.IsOpen.return_value = session_is_open
    mock_save_dialog = mocker.patch(
        "invesalius.gui.dialogs.SaveChangesDialog2", return_value=save_dialog_return
    )
    mock_inexistent_path = mocker.patch("invesalius.gui.dialogs.InexistentPath")
    mock_close_project = mocker.patch.object(controller, "CloseProject")
    mock_open_project = mocker.patch.object(controller, "OpenProject")
    mock_save_project = mocker.patch.object(controller, "ShowDialogSaveProject")

    controller.OnOpenRecentProject(filepath)

    if file_exists:
        mock_session.GetConfig.assert_called_once_with("project_status")

        if save_dialog_return is not None:
            mock_save_dialog.assert_called_once_with("test_project.inv3")

        if session_is_open:
            mock_close_project.assert_called_once()  # Close project if it's already open
        else:
            mock_close_project.assert_not_called()

        if save_dialog_return == 1:
            mock_save_project.assert_called_once()  # Project should be saved if user confirms

        mock_open_project.assert_called_once_with(
            filepath
        )  # Project should always be opened if file exists
    else:
        mock_inexistent_path.assert_called_once_with(filepath)  # Error dialog should appear
