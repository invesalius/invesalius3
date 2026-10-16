from unittest.mock import patch

import pytest

from invesalius.data.viewer_navigation import NavigationView


@pytest.fixture
def mock_navigation_view():
    """Create a minimal NavigationView instance with mocked attributes."""
    nav = object.__new__(NavigationView)
    nav.Id_list = [1, 2, 3]
    nav.Idmax = 2
    nav.efield_coords = None
    nav.e_field_norms_to_save = [1.0, 2.0, 3.0]
    nav.coil_position_Trot = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    nav.coil_position = [10.0, 20.0, 30.0]
    nav.plot_no_connection = True
    nav.e_field_col1_to_save = [0.1, 0.2]
    nav.e_field_col2_to_save = [0.3, 0.4]
    nav.e_field_col3_to_save = [0.5, 0.6]
    nav.max_efield_array = [0.1, 0.2, 0.3]
    nav.target_radius_list = []
    nav.focal_factor_members = 1.0
    nav.efield_threshold = 50.0
    nav.efield_ROISize = 10.0
    nav.mtms_coord = [0.0, 0.0, 0.0]
    nav.diperdt = 1.0
    nav.ci = 0.5
    nav.co = 0.5
    nav.path_meshes = "/path/meshes"
    nav.meshes_file = "mesh.stl"
    nav.cortex_file = "cortex.stl"
    nav.coil_model = "coil.stl"
    return nav


def test_save_efield_target_data_none_coords(mock_navigation_view):
    # Test SaveEfieldTargetData when efield_coords is None and plot_efield_vectors is True
    mock_navigation_view.efield_coords = None
    mock_navigation_view.SaveEfieldTargetData(
        target_list_index=0,
        position=[1, 2, 3],
        orientation=[0, 0, 0],
        plot_efield_vectors=True,
    )
    assert len(mock_navigation_view.target_radius_list) == 1
    # efield_coords_position (index 3) should be None
    assert mock_navigation_view.target_radius_list[0][3] is None
    # efield_coords (index 4) should be None
    assert mock_navigation_view.target_radius_list[0][4] is None

    # Test SaveEfieldTargetData when efield_coords is None and plot_efield_vectors is False
    mock_navigation_view.SaveEfieldTargetData(
        target_list_index=1,
        position=[1, 2, 3],
        orientation=[0, 0, 0],
        plot_efield_vectors=False,
    )
    assert len(mock_navigation_view.target_radius_list) == 2
    # efield_coords_position (index 5) should be None
    assert mock_navigation_view.target_radius_list[1][5] is None
    # efield_coords (index 6) should be None
    assert mock_navigation_view.target_radius_list[1][6] is None


def test_save_efield_target_data_with_coords(mock_navigation_view):
    mock_navigation_view.efield_coords = [10.0, 20.0, 30.0, 1.0, 2.0, 3.0]
    with patch(
        "invesalius.data.imagedata_utils.convert_invesalius_to_world",
        return_value=((100.0, 200.0, 300.0), (1.0, 2.0, 3.0)),
    ):
        mock_navigation_view.SaveEfieldTargetData(
            target_list_index=0,
            position=[1, 2, 3],
            orientation=[0, 0, 0],
            plot_efield_vectors=True,
        )
    assert len(mock_navigation_view.target_radius_list) == 1
    assert mock_navigation_view.target_radius_list[0][3] == [
        [100.0, 200.0, 300.0],
        [1.0, 2.0, 3.0],
    ]


def test_save_efield_data_none_coords(mock_navigation_view, tmp_path):
    mock_navigation_view.efield_coords = None
    output_file = tmp_path / "efield_data.csv"

    # plot_efield_vectors=True
    mock_navigation_view.SaveEfieldData(
        marker_id="target_1",
        filename=str(output_file),
        plot_efield_vectors=True,
    )
    assert output_file.exists()

    # plot_efield_vectors=False
    output_file_2 = tmp_path / "efield_data_2.csv"
    mock_navigation_view.SaveEfieldData(
        marker_id="target_2",
        filename=str(output_file_2),
        plot_efield_vectors=False,
    )
    assert output_file_2.exists()
