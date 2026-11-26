from invesalius.utils import format_date, format_time


def test_format_date_yyyymmdd():
    result = format_date("20200201")
    assert result == "01/02/2020"


def test_format_date_dd_mm_yyyy():
    result = format_date("01/02/2020")
    assert result == "01/02/2020"


def test_format_date_dd_dot_mm_dot_yyyy():
    result = format_date("01.02.2020")
    assert result == "01/02/2020"


def test_format_date_yyyy_dot_mm_dot_dd():
    result = format_date("2020.02.01")
    assert result == "01/02/2020"


def test_format_date_invalid():
    result = format_date("not-a-date")
    assert result == ""


def test_format_time_hhmmss():
    result = format_time("202000")
    assert result == "20:20:00"


def test_format_time_colon_separated():
    result = format_time("20:20:00")
    assert result == "20:20:00"


def test_format_time_dot_separated():
    result = format_time("20.20.00")
    assert result == "20:20:00"


def test_format_time_with_decimal_seconds():
    result = format_time("20:20:00.5")
    assert result == "20:20:00"


def test_format_time_float_seconds():
    result = format_time("202000.5")
    assert result == "08:06:40"
