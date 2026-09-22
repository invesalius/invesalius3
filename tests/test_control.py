from types import SimpleNamespace
from unittest.mock import Mock, patch

import invesalius.control as control


def test_load_project_publishes_integer_scroll_positions():
    """wx.ScrollBar requires integer thumb positions."""

    fake_project = SimpleNamespace(
        threshold_range=(0, 4095),
        threshold_modes={"Bone": (1250, 4095)},
        window=4095.0,
        level=1024.0,
        spacing=(1.0, 1.0, 2.0),
        mask_dict={},
        surface_dict={},
        measurement_dict={},
        name="probe",
        modality="MRI",
        matrix_shape=(161, 338, 61),
        export_project_to_nifti=Mock(),
    )
    fake_slice = SimpleNamespace(spacing=None, affine=None, current_mask=None)
    controller = control.Controller.__new__(control.Controller)
    controller.LoadImagedataInfo = Mock()

    with (
        patch.object(control, "_", lambda text: text, create=True),
        patch.object(control.prj, "Project", return_value=fake_project),
        patch.object(control.sl, "Slice", return_value=fake_slice),
        patch.object(control.Publisher, "sendMessage") as send_message,
    ):
        controller.LoadProject()

    positions = {
        call.args[0][1]: call.kwargs["index"]
        for call in send_message.call_args_list
        if call.args
        and isinstance(call.args[0], tuple)
        and call.args[0][0] == "Set scroll position"
    }
    assert positions == {"AXIAL": 80, "SAGITAL": 169, "CORONAL": 30}
    assert all(isinstance(index, int) for index in positions.values())
