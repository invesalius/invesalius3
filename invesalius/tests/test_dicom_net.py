import unittest
from unittest.mock import MagicMock
from invesalius.net.dicom import DicomNet, gdcm


class TestDicomNet(unittest.TestCase):

    def test_set_host(self):
        dicom_net = DicomNet()
        dicom_net.set_host('127.0.0.1')
        self.assertEqual(dicom_net.address, '127.0.0.1')

    def test_set_port(self):
        dicom_net = DicomNet()
        dicom_net.set_port(1234)
        self.assertEqual(dicom_net.port, 1234)

    def test_set_aetitle_call(self):
        dicom_net = DicomNet()
        dicom_net.set_aetitle_call('my_call_ae')
        self.assertEqual(dicom_net.aetitle_call, 'my_call_ae')

    def test_set_aetitle(self):
        dicom_net = DicomNet()
        dicom_net.set_aetitle('my_ae')
        self.assertEqual(dicom_net.aetitle, 'my_ae')

    def test_set_search_word(self):
        dicom_net = DicomNet()
        dicom_net.set_search_word('my_word')
        self.assertEqual(dicom_net.search_word, 'my_word')

    def test_set_search_type(self):
        dicom_net = DicomNet()
        dicom_net.set_search_type('study')
        self.assertEqual(dicom_net.search_type, 'study')
        dicom_net.set_search_type('patient')
        self.assertEqual(dicom_net.search_type, 'patient')

    def test_get_value_from_dicom(self):
        # Create a mock object for the `gdcm.DataSet` class
        ret_mock = MagicMock(spec=gdcm.DataSet)

        # Define a function to mock the behavior of `GetValue` method
        def get_value_mock():
            return {
                (0x0010, 0x0010): "John Doe",
                (0x0010, 0x1010): "30",
                (0x0010, 0x0040): "M",
                (0x0008, 0x1030): "CT scan",
            }.get(tag, "")

        def get_data_element_mock(tag):
            elem_mock = MagicMock(spec=gdcm.DataElement)
            elem_mock.GetValue.return_value = get_value_mock()
            return elem_mock

        ret_mock.GetDataElement.side_effect = get_data_element_mock

        tag = (0x0010, 0x0010)
        obj = DicomNet()
        value = obj.get_value_from_dicom(ret_mock, tag)
        self.assertEqual(value, "John Doe")

        tag = (0x0010, 0x1000)
        value = obj.get_value_from_dicom(ret_mock, tag)
        self.assertEqual(value, "")

        # Test with (0x0008,0x103E) tag
        tag = (0x0008, 0x103E)
        value = obj.get_value_from_dicom(ret_mock, tag)
        self.assertEqual(value, "")


if __name__ == '__main__':
    unittest.main()
