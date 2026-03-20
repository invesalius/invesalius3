from invesalius.net.dicom import DicomNet


def test_c_echo():
    dn = DicomNet(address="127.0.0.1", port=4242,
                  aetitle_call="MYAE", aetitle="ORTHANC")
    assert dn.RunCEcho() is True
