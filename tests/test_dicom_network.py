from invesalius.net.dicom import DicomNet
import pytest

@pytest.mark.skip(reason="Requires a running DICOM server")
def test_c_echo():
    dn = DicomNet(address="127.0.0.1", port=4242,
                  aetitle_call="INVESALIUS", aetitle="ORTHANC")
    assert dn.RunCEcho() is True

@pytest.mark.skip(reason="Requires a running DICOM server")
def test_c_find():
    dn = DicomNet(
        address="127.0.0.1",
        port=4242,
        aetitle_call="INVESALIUS",
        aetitle="ORTHANC"
    )

    results = dn.RunCFind()
    
    assert results is not None
    assert isinstance(results, dict)

@pytest.mark.skip(reason="Requires a running DICOM server")
def test_c_get():
    dn = DicomNet(
        address="127.0.0.1",
        port=4242,
        aetitle_call="INVESALIUS",
        aetitle="ORTHANC"
    )
    results = dn.RunCGet('IMAGE', '1422', '1.2.840.113704.1.111.3452.1134393493.8', '1.2.840.113704.1.111.4564.1134393955.20', '1.2.840.113704.1.111.3896.1134394062.5263')

test_c_get()