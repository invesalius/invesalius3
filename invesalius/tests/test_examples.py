# tests/test_example.py
# this file was created for the demonstration of the working workflow for automated testing of PRs.
def test_always_pass():
    assert True


def test_math():
    assert 2 + 2 == 5


def test_string():
    assert "Hello".upper() == "HELLO"


def test_list():
    sample_list = [1, 2, 3]
    assert len(sample_list) == 3
