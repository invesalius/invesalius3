from invesalius.reader.dicom import Parser


def make_parser(tag, value):
    parser = Parser()
    parser.data_image = {str(0x0008): {str(tag): value}}
    return parser


def test_acquisition_time_with_fraction_of_second():
    # DICOM TM values usually carry a fraction: HHMMSS.FFFFFF
    parser = make_parser(0x0032, "143512.000000")
    assert parser.GetAcquisitionTime() == "14:35:12"


def test_image_time_with_fraction_of_second():
    parser = make_parser(0x0033, "093005.5")
    assert parser.GetImageTime() == "09:30:05"


def test_acquisition_time_without_fraction():
    parser = make_parser(0x0032, "143512")
    assert parser.GetAcquisitionTime() == "14:35:12"


def test_acquisition_date_formats():
    assert make_parser(0x0022, "20200315").GetAcquisitionDate() == "15/03/2020"
    assert make_parser(0x0022, "2020.03.15").GetAcquisitionDate() == "15/03/2020"
    assert make_parser(0x0022, "15.03.2020").GetAcquisitionDate() == "15/03/2020"
    assert make_parser(0x0022, "15/03/2020").GetAcquisitionDate() == "15/03/2020"


def test_acquisition_date_invalid():
    assert make_parser(0x0022, "not a date").GetAcquisitionDate() == ""
