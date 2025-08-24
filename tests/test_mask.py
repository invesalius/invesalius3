import numpy as np
from invesalius.data.slice_ import Slice
from invesalius.project import Project
from unittest.mock import patch

def test_create_new_mask() -> None:
    slc: Slice = Slice()
    shape: tuple[int, int, int] = (5, 5, 5)
    with patch("numpy.histogram", return_value=(np.array([0]), np.array([0, 1]))):
        slc.matrix = np.ones(shape, dtype=np.int16)
    slc.spacing = (1.0, 1.0, 1.0)

    mask_name: str = "DummyName"
    mask_colour: tuple[float, float, float] = (0.5, 0.5, 0.5)
    mask_opacity: float = 0.7
    threshold_range: tuple[int, int] = (100, 200)
    edition_threshold_range: tuple[int, int] = (110, 190)

    mask = slc.create_new_mask(
        name=mask_name,
        colour=mask_colour,
        opacity=mask_opacity,
        threshold_range=threshold_range,
        edition_threshold_range=edition_threshold_range,
        add_to_project=False,
        show=False,
    )

    expected_shape: tuple[int, ...] = tuple(dim + 1 for dim in shape)
    assert mask.name == mask_name
    assert mask.colour == mask_colour
    assert mask.opacity == mask_opacity
    assert mask.threshold_range == threshold_range
    assert mask.edition_threshold_range == edition_threshold_range
    assert mask.matrix.shape == expected_shape
    assert mask.spacing == slc.spacing

def test_project_add_and_remove_mask() -> None:
    slc: Slice = Slice()
    shape: tuple[int, int, int] = (5, 5, 5)
    with patch("numpy.histogram", return_value=(np.array([0]), np.array([0, 1]))):
        slc.matrix = np.ones(shape, dtype=np.int16)
    slc.spacing = (1.0, 1.0, 1.0)

    mask = slc.create_new_mask(name="ProjectMask", add_to_project=False, show=False)
    project: Project = Project()
    mask_index: int = project.AddMask(mask)
    assert mask_index in project.mask_dict
    assert project.mask_dict[mask_index] == mask

    project.RemoveMask(mask_index)
    assert mask_index not in project.mask_dict

def test_set_mask_name() -> None:
    slc: Slice = Slice()
    with patch("numpy.histogram", return_value=(np.array([0]), np.array([0, 1]))):
        slc.matrix = np.ones((5, 5, 5), dtype=np.int16)
    slc.spacing = (1.0, 1.0, 1.0)
    mask = slc.create_new_mask(name="OldName", add_to_project=True, show=False)
    mask_index: int = mask.index

    new_name: str = "NewName"
    slc.SetMaskName(mask_index, new_name)
    proj: Project = Project()
    assert proj.mask_dict[mask_index].name == new_name
