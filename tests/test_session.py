# import json
# import os
# import sys
# from unittest.mock import call, mock_open

# import pytest

# import invesalius.constants as const
# from invesalius import inv_paths
# from invesalius.session import CONFIG_PATH, STATE_PATH, Session

# session = Session()


# def test_set_and_get_config():
#     session.SetConfig("debug", True)
#     assert session.GetConfig("debug") == True


# def test_write_config_file(mocker):
#     mock_file = mock_open()
#     mocker.patch("builtins.open", mock_file)
#     mock_json_dump = mocker.patch("json.dump")
#     session._config = {"debug": True, "language": "en", "file_logging": 1}
#     session.WriteConfigFile()
#     mock_file.assert_called_once_with(CONFIG_PATH, "w")
#     expected_data = {"debug": True, "language": "en", "file_logging": 1}
#     mock_json_dump.assert_called_once_with(expected_data, mock_file(), sort_keys=True, indent=4)


# def test_create_config(mocker):
#     mock_write_config = mocker.patch.object(session, "WriteConfigFile")
#     session.CreateConfig()
#     assert session._config["mode"] == const.MODE_RP
#     assert session._config["project_status"] == const.PROJECT_STATUS_CLOSED
#     assert session._config["debug"] is False
#     assert session._config["debug_efield"] is False
#     assert session._config["language"] == ""
#     assert isinstance(session._config["random_id"], int)
#     assert session._config["surface_interpolation"] == 1
#     assert session._config["rendering"] == 0
#     assert session._config["slice_interpolation"] == 0
#     assert session._config["auto_reload_preview"] is False
#     assert session._config["recent_projects"] == [(str(inv_paths.SAMPLE_DIR), "Cranium.inv3")]
#     assert session._config["last_dicom_folder"] == ""
#     assert session._config["file_logging"] == 0
#     assert session._config["file_logging_level"] == 0
#     assert session._config["append_log_file"] == 0
#     assert session._config["logging_file"] == ""
#     assert session._config["console_logging"] == 0
#     assert session._config["console_logging_level"] == 0
#     mock_write_config.assert_called_once()


# def test_read_state(mocker):
#     test_data = {"dummykey": "dummyValue"}
#     mock_file = mock_open(read_data=json.dumps(test_data))
#     mocker.patch("builtins.open", mock_file)
#     mocker.patch("json.load", return_value=test_data)
#     mocker.patch("os.path.exists", return_value=True)
#     success = session._ReadState()
#     session._state = test_data
#     assert session.GetState("dummykey") == "dummyValue"
#     assert success is True


# def test_create_state(mocker):
#     mock_state_json = mock_open()
#     mocker.patch("builtins.open", mock_state_json)
#     mock_json_dump = mocker.patch("json.dump")
#     session.CreateState()
#     mock_state_json.assert_called_once_with(STATE_PATH, "w")
#     mock_json_dump.assert_called_once_with({}, mock_state_json(), sort_keys=True, indent=4)


# def test_set_and_get_state(mocker):
#     mock_file = mock_open()
#     mocker.patch("builtins.open", mock_file)
#     mock_json = mocker.patch("json.dump")
#     session.SetState("test_key", "test_value")
#     mock_file.assert_called_once_with(STATE_PATH, "w")
#     mock_json.assert_called_once_with(session._state, mock_file(), sort_keys=True, indent=4)
#     assert session.GetState("test_key") == "test_value"


# def test_delete_state_file(mocker):
#     mocker.patch("os.path.exists", return_value=True)
#     mock_remove = mocker.patch("os.remove")
#     session.DeleteStateFile()
#     mock_remove.assert_called_once_with(STATE_PATH)


# def test_delete_state_file_not_exist(mocker):
#     mocker.patch("os.path.exists", return_value=False)
#     mock_remove = mocker.patch("os.remove")
#     session.DeleteStateFile()
#     mock_remove.assert_not_called()


# def test_close_project(mocker):
#     mock_set_state = mocker.patch.object(session, "SetState")
#     mock_set_config = mocker.patch.object(session, "SetConfig")
#     session.CloseProject()
#     mock_set_state.assert_called_once_with("project_path", None)
#     mock_set_config.assert_called_once_with("project_status", const.PROJECT_STATUS_CLOSED)


# def test_save_project(mocker):
#     """Ensure SaveProject sets the project state and updates the config."""
#     mock_set_state = mocker.patch.object(session, "SetState")
#     mock_set_config = mocker.patch.object(session, "SetConfig")
#     mocker.patch.object(
#         session, "GetConfig", return_value=[["/dummy/path", "dummy.inv"]]
#     )  # Ensures its not None
#     project_path = ("path", "project.inv")
#     session.SaveProject(project_path)
#     mock_set_state.assert_called_once_with("project_path", project_path)
#     mock_set_config.assert_has_calls(
#         [
#             call("recent_projects", mocker.ANY),  # Ensures recent projects were updated
#             call("project_status", const.PROJECT_STATUS_OPENED),
#         ],
#         any_order=True,
#     )
#     assert mock_set_config.call_count == 2


# def test_change_project(mocker):
#     mock_set_config = mocker.patch.object(session, "SetConfig")
#     session.ChangeProject()
#     mock_set_config.assert_called_once_with("project_status", const.PROJECT_STATUS_CHANGED)


# def test_create_project(mocker):
#     mock_set_state = mocker.patch.object(session, "SetState")
#     mock_set_config = mocker.patch.object(session, "SetConfig")
#     session.CreateProject("new_project.inv")
#     mock_set_state.assert_called_once()
#     mock_set_config.assert_called_once_with("project_status", const.PROJECT_STATUS_NEW)


# def test_open_project(mocker):
#     mock_set_state = mocker.patch.object(session, "SetState")
#     mock_set_config = mocker.patch.object(session, "SetConfig")
#     mocker.patch.object(session, "GetConfig", return_value=[["/existing/path", "existing.inv"]])
#     project_path = "/path/dummy.inv"
#     session.OpenProject(project_path)
#     mock_set_state.assert_called_once_with("project_path", ("/path", "dummy.inv"))

#     mock_set_config.assert_has_calls(
#         [
#             call("recent_projects", mocker.ANY),
#             call("project_status", const.PROJECT_STATUS_OPENED),  # Ensures project was opened
#         ],
#         any_order=True,
#     )

#     assert mock_set_config.call_count == 2


# def test_read_state_with_corrupted_json(mocker):
#     mocker.patch("os.path.exists", return_value=True)
#     mock_file = mock_open(read_data="corrupted data")
#     mocker.patch("builtins.open", mock_file)
#     mocker.patch("json.load", side_effect=json.JSONDecodeError("Expecting value", "", 0))
#     mock_delete = mocker.patch.object(session, "DeleteStateFile")
#     success = session._ReadState()
#     assert success is False
#     mock_delete.assert_called_once()
