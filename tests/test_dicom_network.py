from invesalius.net.dicom import DicomNet
import pytest

@pytest.mark.skip(reason="Requires a running DICOM server")
def test_c_echo():
    dn = DicomNet(address="127.0.0.1", port=4242,
                  aetitle_call="MYAE", aetitle="ORTHANC")
    assert dn.RunCEcho() is True

@pytest.mark.skip(reason="Requires a running DICOM server")
def test_c_find():
    dn = DicomNet(
        address="127.0.0.1",
        port=4242,
        aetitle_call="MYAE",
        aetitle="ORTHANC"
    )

    results = dn.RunCFind()
    
    assert results is not None
    assert isinstance(results, dict)