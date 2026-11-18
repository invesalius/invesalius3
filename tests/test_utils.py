from invesalius.utils import next_copy_name


def test_next_copy_name_first_copy():
    assert next_copy_name("Mask 1", ["Mask 1"]) == "Mask 1 copy"


def test_next_copy_name_numbered_copies():
    names = ["Mask 1", "Mask 1 copy"]
    assert next_copy_name("Mask 1 copy", names) == "Mask 1 copy#1"

    names.append("Mask 1 copy#1")
    assert next_copy_name("Mask 1 copy#1", names) == "Mask 1 copy#2"


def test_next_copy_name_non_numeric_suffix():
    # Used to raise NameError because the suffix was passed to eval().
    name = "Skull copy#final"
    assert next_copy_name(name, [name]) == "Skull copy#final copy"


def test_next_copy_name_does_not_evaluate_name(tmp_path):
    # Names come from untrusted .inv3 project files and must never be executed.
    marker = tmp_path / "marker"
    name = f"Mask 1 copy#1 and __import__('pathlib').Path({str(marker)!r}).write_text('x')"

    new_name = next_copy_name(name, [name])

    assert not marker.exists()
    assert new_name == f"{name} copy"
