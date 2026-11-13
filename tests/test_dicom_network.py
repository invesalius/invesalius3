import pytest

from invesalius.net.dicom import DicomNet


@pytest.mark.skip(reason="Requires a running DICOM server")
def test_c_echo():
    dn = DicomNet(address="127.0.0.1", port=4242, aetitle_call="INVESALIUS", aetitle="ORTHANC")
    assert dn.RunCEcho() is True


@pytest.mark.skip(reason="Requires a running DICOM server")
def test_c_find():
    dn = DicomNet(address="127.0.0.1", port=4242, aetitle_call="INVESALIUS", aetitle="ORTHANC")

    results = dn.RunCFind()

    assert results is not None
    assert isinstance(results, dict)


@pytest.mark.skip(reason="Requires a running DICOM server")
def test_c_get():
    dn = DicomNet(address="127.0.0.1", port=4242, aetitle_call="INVESALIUS", aetitle="ORTHANC")
    # Manually added data to the orthanc server...
    results = dn.RunCGet(
        "IMAGE",
        "1422",
        "1.2.840.113704.1.111.3452.1134393493.8",
        "1.2.840.113704.1.111.4564.1134393955.20",
        "1.2.840.113704.1.111.3896.1134394062.5263",
    )


@pytest.mark.skip(reason="Requires a running DICOM server")
def test_c_move():
    dn = DicomNet(address="127.0.0.1", port=4242, aetitle_call="INVESALIUS", aetitle="ORTHANC")
    # Manually added data to the orthanc server...
    results = dn.RunCMove(
        "IMAGE",
        "1422",
        "1.2.840.113704.1.111.3452.1134393493.8",
        "1.2.840.113704.1.111.4564.1134393955.20",
        "1.2.840.113704.1.111.3896.1134394062.5263",
    )


def test_select_event():
    from invesalius.gui.network.text_panel import SelectEvent, myEVT_SELECT_PATIENT

    evt = SelectEvent(myEVT_SELECT_PATIENT, 100)
    evt.SetSelectedID("patient_001")
    evt.SetItemData({"name": "Test Patient"})

    assert evt.GetSelectID() == "patient_001"
    assert evt.GetItemData() == {"name": "Test Patient"}


def test_network_gui_imports():
    """Verify that network GUI modules and progress dialog can be imported without NameError."""
    import invesalius.gui.network.dicom_server_panel as dsp
    import invesalius.gui.network.nodes_panel as np
    import invesalius.gui.network.text_panel as tp
    import invesalius.net.dialog as nd

    assert hasattr(tp, "SelectEvent")
    assert hasattr(tp, "TextPanel")
    assert hasattr(tp, "dcm")
    assert hasattr(dsp, "DicomServerPanel")
    assert hasattr(np, "NodesPanel")
    assert hasattr(nd, "SurfaceProgressWindow")
