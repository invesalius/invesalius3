"""Regression tests for image registration and its conflicting toolbar actions.

Run with ``xvfb-run -a python -m pytest tests/test_image_registration.py`` on Linux.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import wx


@pytest.fixture(scope="module")
def wx_app():
    app = wx.App.Get() or wx.App(False)
    yield app


@pytest.fixture
def registration_ui(wx_app):
    # Import after wx.App exists: these modules also create GUI resources.
    import invesalius.constants as const
    from invesalius.gui.frame import ObjectToolBar, SliceToolBar
    from invesalius.gui.task_navigator import ImagePage
    from invesalius.pubsub import pub as Publisher
    from invesalius.style import StyleStateManager

    parent = wx.Frame(None)
    object_toolbar = ObjectToolBar(parent)
    slice_toolbar = SliceToolBar(parent)
    image = Mock()
    image.IsImageFiducialSet.return_value = False
    image.GetImageFiducialForUI.return_value = 0
    image.AreImageFiducialsSet.return_value = False
    page = ImagePage(parent, SimpleNamespace(image=image))

    # Use the real style stack without constructing VTK viewers or tracker hardware.
    styles = StyleStateManager()

    def enable_style(style):
        styles.AddState(style)

    def disable_style(style):
        styles.RemoveState(style)

    Publisher.subscribe(enable_style, "Enable style")
    Publisher.subscribe(disable_style, "Disable style")
    Publisher.sendMessage("Enable state project", state=True)

    yield SimpleNamespace(
        page=page,
        image=image,
        object_toolbar=object_toolbar,
        slice_toolbar=slice_toolbar,
        toolbars=(object_toolbar, slice_toolbar),
        styles=styles,
        const=const,
        publisher=Publisher,
    )

    for owner in (page, object_toolbar, slice_toolbar):
        Publisher.unsubscribe_owner(owner)
    Publisher.unsubscribe(enable_style, "Enable style")
    Publisher.unsubscribe(disable_style, "Disable style")
    parent.Destroy()
    wx_app.ProcessPendingEvents()


def click_registration(page, active):
    """Dispatch the same event as a click on Start/Stop Registration."""
    button = page.start_button
    button.SetValue(active)
    event = wx.CommandEvent(wx.EVT_TOGGLEBUTTON.typeId, button.GetId())
    button.GetEventHandler().ProcessEvent(event)


def assert_tools_enabled(ui, enabled):
    for toolbar in ui.toolbars:
        for tool in toolbar.enable_items:
            assert toolbar.GetToolEnabled(tool) == enabled, f"Unexpected state for tool {tool}"


def test_start_registration_disables_conflicting_tools(registration_ui):
    ui = registration_ui
    assert_tools_enabled(ui, True)

    click_registration(ui.page, True)

    assert_tools_enabled(ui, False)
    assert ui.styles.GetActualState() == ui.const.STATE_REGISTRATION
    assert ui.page.start_button.GetLabel() == "Stop Registration"
    assert all(button.IsEnabled() for button in ui.page.btns_set_fiducial)


def test_registration_shows_persistent_notice(registration_ui):
    page = registration_ui.page
    assert not page.registration_notice.IsShown()

    click_registration(page, True)

    assert page.registration_notice.IsShown()
    assert "disabled" in page.registration_notice.GetLabel().lower()

    click_registration(page, False)

    assert not page.registration_notice.IsShown()


def test_registration_notice_fits_without_resizing_the_page(registration_ui):
    page = registration_ui.page
    minimum_size = page.GetSizer().GetMinSize()

    click_registration(page, True)

    assert page.GetSizer().GetMinSize() == minimum_size


@pytest.mark.parametrize(
    "toolbar_name,tool_name",
    [
        ("object_toolbar", "STATE_WL"),
        ("slice_toolbar", "SLICE_STATE_SCROLL"),
        ("slice_toolbar", "SLICE_STATE_CROSS"),
    ],
)
def test_start_clears_previous_tool_and_style(registration_ui, toolbar_name, tool_name):
    ui = registration_ui
    toolbar = getattr(ui, toolbar_name)
    tool = getattr(ui.const, tool_name)
    toolbar.ToggleTool(tool, True)
    ui.publisher.sendMessage("Enable style", style=tool)

    click_registration(ui.page, True)
    click_registration(ui.page, False)

    assert not toolbar.GetToolToggled(tool)
    assert ui.styles.GetActualState() == ui.const.STATE_DEFAULT


@pytest.mark.parametrize("stop_action", ["button", "message", "fiducials", "reset"])
def test_registration_exit_restores_tools(registration_ui, stop_action):
    ui = registration_ui
    click_registration(ui.page, True)

    if stop_action == "button":
        click_registration(ui.page, False)
    elif stop_action == "message":
        ui.publisher.sendMessage("Stop image registration")
    elif stop_action == "fiducials":
        ui.image.AreImageFiducialsSet.return_value = True
        ui.page.SetImageFiducial("LE", (1, 2, 3))
    else:
        ui.publisher.sendMessage("Reset image fiducials")

    assert_tools_enabled(ui, True)
    assert ui.styles.GetActualState() == ui.const.STATE_DEFAULT
    assert not ui.page.start_button.GetValue()
    assert ui.page.start_button.GetLabel() == "Start Registration"
    assert all(not button.IsEnabled() for button in ui.page.btns_set_fiducial)


def test_project_updates_do_not_unlock_registration(registration_ui):
    ui = registration_ui
    click_registration(ui.page, True)

    ui.publisher.sendMessage("Enable state project", state=True)

    assert_tools_enabled(ui, False)
    assert ui.styles.GetActualState() == ui.const.STATE_REGISTRATION


@pytest.mark.parametrize("close_topic", ["Enable state project", "Close project data"])
def test_project_close_clears_registration_without_enabling_tools(registration_ui, close_topic):
    ui = registration_ui
    click_registration(ui.page, True)

    args = {"state": False} if close_topic == "Enable state project" else {}
    ui.publisher.sendMessage(close_topic, **args)
    ui.publisher.sendMessage("Stop image registration")

    assert_tools_enabled(ui, False)
    assert not ui.page.start_button.GetValue()
    assert ui.styles.GetActualState() == ui.const.STATE_DEFAULT

    ui.publisher.sendMessage("Enable state project", state=True)

    assert_tools_enabled(ui, True)


def test_programmatic_slice_toggle_cannot_override_registration(registration_ui):
    ui = registration_ui
    click_registration(ui.page, True)

    ui.publisher.sendMessage("Toggle toolbar button", id=ui.const.SLICE_STATE_SCROLL)

    assert not ui.slice_toolbar.GetToolToggled(ui.const.SLICE_STATE_SCROLL)
    assert ui.styles.GetActualState() == ui.const.STATE_REGISTRATION


@pytest.mark.parametrize(
    "toolbar_name,tool_name",
    [
        ("object_toolbar", "STATE_PAN"),
        ("slice_toolbar", "SLICE_STATE_SCROLL"),
        ("slice_toolbar", "SLICE_STATE_CROSS"),
    ],
)
def test_pending_toolbar_click_cannot_override_registration(
    registration_ui, toolbar_name, tool_name
):
    ui = registration_ui
    toolbar = getattr(ui, toolbar_name)
    tool = getattr(ui.const, tool_name)
    click_registration(ui.page, True)

    # A click queued before registration can arrive after the button is disabled.
    toolbar.ToggleTool(tool, True)
    event = wx.CommandEvent(wx.EVT_TOOL.typeId, tool)
    toolbar.GetEventHandler().ProcessEvent(event)

    assert not toolbar.GetToolToggled(tool)
    click_registration(ui.page, False)
    assert ui.styles.GetActualState() == ui.const.STATE_DEFAULT


def test_stopping_inactive_registration_preserves_other_modes(registration_ui):
    ui = registration_ui
    ui.publisher.sendMessage("Enable style", style=ui.const.STATE_MASK_3D_EDIT)

    ui.publisher.sendMessage("Stop image registration")

    assert ui.styles.GetActualState() == ui.const.STATE_MASK_3D_EDIT


@pytest.mark.parametrize("handler_name", ["_ToggleLinearMeasure", "_ToggleAngularMeasure"])
def test_measurement_shortcuts_cannot_override_registration(registration_ui, handler_name):
    ui = registration_ui
    click_registration(ui.page, True)

    getattr(ui.object_toolbar, handler_name)()
    click_registration(ui.page, False)

    assert ui.styles.GetActualState() == ui.const.STATE_DEFAULT
    assert all(
        not ui.object_toolbar.GetToolToggled(tool) for tool in ui.object_toolbar.enable_items
    )
