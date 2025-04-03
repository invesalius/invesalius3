import pytest
import wx

import invesalius.constants as const
from invesalius.gui.import_bitmap_panel import InnerPanel


@pytest.fixture(scope="module")
def wx_app():
    app = wx.App(False)
    yield app  # Provide the app instance to tests
    app.Destroy()  # Cleanup after all tests in the module


@pytest.fixture
def frame(wx_app):
    frame = wx.Frame(None)
    yield frame
    frame.Destroy()


@pytest.fixture
def panel(frame):
    panel = InnerPanel(frame)
    yield panel
    panel.Destroy()


@pytest.fixture
def text_panel(panel):
    yield panel.text_panel


@pytest.fixture
def image_panel(panel):
    yield panel.image_panel


def test_panel_initialization(panel):
    """
    Test that the panel is initialized correctly with expected attributes and default states.
    """
    # Check Attribute Existence
    assert hasattr(panel, "btn_ok"), "Panel should have an 'OK' button (btn_ok)."
    assert hasattr(panel, "btn_cancel"), "Panel should have a 'Cancel' button (btn_cancel)."
    assert hasattr(
        panel, "combo_interval"
    ), "Panel should have a combo box for interval selection (combo_interval)."

    # Check Attribute Types
    assert isinstance(panel.btn_ok, wx.Button), "'btn_ok' should be a wx.Button."
    assert isinstance(panel.btn_cancel, wx.Button), "'btn_cancel' should be a wx.Button."
    assert isinstance(
        panel.combo_interval, wx.ComboBox
    ), "'combo_interval' should be a wx.ComboBox."

    # Check Initial States
    assert (
        panel.combo_interval.GetSelection() == 0
    ), "Default selection of 'combo_interval' should be index 0."
    assert (
        panel.combo_interval.GetStringSelection() == const.IMPORT_INTERVAL[0]
    ), f"Default string selection of 'combo_interval' should be '{const.IMPORT_INTERVAL[0]}'."
    assert panel.btn_ok.GetLabel() == "Import", "Label of 'btn_ok' should be 'OK'."
    assert panel.btn_cancel.GetLabel() == "Cancel", "Label of 'btn_cancel' should be 'Cancel'."


def test_text_panel_population(text_panel, mocker):
    test_data = [
        ["/path/to/img1.bmp", "Bitmap", "512x512", 512, 512, "1.0 mm"],
        ["/path/to/img2.png", "PNG", "1024x1024", 1024, 1024, "2.0 mm"],
    ]
    pub_mock = mocker.patch("invesalius.pubsub.pub.Publisher.sendMessage")
    bind_mock = mocker.patch.object(text_panel.tree, "Bind")

    text_panel.Populate(test_data)
    tree = text_panel.tree
    root = tree.GetRootItem()

    assert tree.GetChildrenCount(root) == len(
        test_data
    ), "Tree should create one item per data entry"

    # Verify first item's data
    first_child = tree.GetFirstChild(root)[0]
    assert tree.GetItemText(first_child) == test_data[0][0], "Path column mismatch"
    assert tree.GetItemText(first_child, 1) == test_data[0][2], "Dimensions column mismatch"
    assert tree.GetItemText(first_child, 2) == test_data[0][5], "Interval column mismatch"

    # Verify event bindings
    bind_mock.assert_any_call(wx.EVT_TREE_ITEM_ACTIVATED, text_panel.OnActivate)
    bind_mock.assert_any_call(wx.EVT_TREE_SEL_CHANGED, text_panel.OnSelChanged)

    # Verify PubSub message
    pub_mock.assert_called_once_with("Load bitmap into import panel", data=test_data)


def test_button_events(panel, mocker):
    pub_mock = mocker.patch("invesalius.pubsub.pub.Publisher.sendMessage")
    dialog_mock = mocker.patch("invesalius.gui.dialogs.ImportBitmapParameters")
    # --- Test OK Button ---
    ok_event = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, panel.btn_ok.GetId())
    panel.btn_ok.GetEventHandler().ProcessEvent(ok_event)
    dialog_mock.assert_called_once()
    dialog_instance = dialog_mock.return_value
    dialog_instance.SetInterval.assert_called_with(panel.combo_interval.GetSelection())

    # --- Test Cancel Button ---
    cancel_event = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, panel.btn_cancel.GetId())
    panel.btn_cancel.GetEventHandler().ProcessEvent(cancel_event)

    pub_mock.assert_any_call("Cancel DICOM load")


def test_keyboard_delete_event(text_panel, mocker):
    pub_mock = mocker.patch("invesalius.pubsub.pub.Publisher.sendMessage")
    mock_bitmap_data = mocker.MagicMock()
    mock_bitmap_instance = mock_bitmap_data.return_value

    mock_bitmap_instance.GetIndexByPath.return_value = 0
    mock_bitmap_instance.GetData.return_value = [object()]  # Simulate existing data

    mocker.patch("invesalius.reader.bitmap_reader.BitmapData", new=mock_bitmap_data)

    test_data = [
        ["/path/to/image1.bmp", "Bitmap", "512x512", 512, 512, "1.0 mm", "Sample Title", 0, 0, {}]
    ]

    text_panel.Populate(test_data)
    # Select the first item
    root = text_panel.tree.GetRootItem()
    item = text_panel.tree.GetFirstChild(root)[0]
    text_panel.tree.SelectItem(item)
    # Simulate DELETE key press
    event = wx.KeyEvent(wx.EVT_CHAR_HOOK.typeId)
    event.SetKeyCode(wx.WXK_DELETE)
    text_panel.GetEventHandler().ProcessEvent(event)
    mock_bitmap_instance.RemoveFileByPath.assert_called_once_with(test_data[0][0])
    pub_mock.assert_any_call("Set bitmap in preview panel", pos=0)

    assert text_panel.tree.GetChildrenCount(root) == 0, "Tree should be empty after deletion"


def test_interval_selection(panel):
    """
    Test that all interval options in const.IMPORT_INTERVAL are correctly reflected
    in the combo_interval widget and behave as expected.
    """
    # Validate that combo box contains all expected intervals
    assert panel.combo_interval.GetCount() == len(
        const.IMPORT_INTERVAL
    ), "Combo box should contain the same number of intervals as const.IMPORT_INTERVAL."
    assert panel.combo_interval.GetSelection() == 0, "Default selection should be index 0."
    assert (
        panel.combo_interval.GetStringSelection() == const.IMPORT_INTERVAL[0]
    ), "Default selected value should match the first item in const.IMPORT_INTERVAL. ie 'Keep all slices'"
    for idx, interval in enumerate(const.IMPORT_INTERVAL):
        panel.combo_interval.SetSelection(idx)
        assert panel.combo_interval.GetStringSelection() == interval, (
            f"Combo box selection mismatch at index {idx}: "
            f"expected '{interval}', got '{panel.combo_interval.GetStringSelection()}'."
        )


def test_ok_button_sets_interval(panel, mocker):
    """
    Test that clicking OK button passes the selected interval to ImportBitmapParameters dialog.
    """
    mock_dialog = mocker.patch("invesalius.gui.dialogs.ImportBitmapParameters")

    # Select a non-default interval
    test_index = 2
    panel.combo_interval.SetSelection(test_index)

    # Trigger OK button click
    ok_event = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, panel.btn_ok.GetId())
    panel.btn_ok.GetEventHandler().ProcessEvent(ok_event)

    # Verify dialog received correct interval
    mock_dialog.return_value.SetInterval.assert_called_once_with(test_index)


def test_non_delete_key_ignored(text_panel):
    """
    Test that non-DELETE keys don't trigger deletion.
    """
    initial_item_count = text_panel.tree.GetChildrenCount(text_panel.tree.GetRootItem())

    # Simulate SPACE key press
    event = wx.KeyEvent(wx.EVT_CHAR_HOOK.typeId)
    event.SetKeyCode(wx.WXK_SPACE)
    text_panel.GetEventHandler().ProcessEvent(event)

    assert (
        text_panel.tree.GetChildrenCount(text_panel.tree.GetRootItem()) == initial_item_count
    ), "Non-DELETE keys should not trigger deletion"
