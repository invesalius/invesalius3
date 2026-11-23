"""Coordinate conversion round-trip between world and InVesalius space."""

import numpy as np
import pytest

try:
    import invesalius_rs  # noqa: F401
except ImportError:
    pytest.skip("invesalius_rs is not built in this checkout", allow_module_level=True)

from invesalius.data import imagedata_utils


class _FakeSlice:
    def __init__(self, affine, matrix):
        self.affine = affine
        self.matrix = matrix
        self.spacing = (1.0, 2.0, 3.0)


def test_world_to_invesalius_is_the_inverse_of_invesalius_to_world(monkeypatch):
    # A translation makes a wrong matrix order visible.
    affine = np.eye(4)
    affine[:3, 3] = (10.0, 20.0, 30.0)
    fake = _FakeSlice(affine, np.zeros((20, 24, 16)))
    monkeypatch.setattr(imagedata_utils.sl, "Slice", lambda: fake)

    position = np.array([12.5, -4.0, 7.0])
    orientation = np.array([10.0, 20.0, 30.0])

    world_position, world_orientation = imagedata_utils.convert_invesalius_to_world(
        position, orientation
    )
    back_position, back_orientation = imagedata_utils.convert_world_to_invesalius(
        world_position, world_orientation
    )

    np.testing.assert_allclose(back_position, position)
    np.testing.assert_allclose(back_orientation, orientation, atol=1e-6)


def test_world_conversion_needs_a_project_affine(monkeypatch):
    fake = _FakeSlice(None, np.zeros((20, 24, 16)))
    monkeypatch.setattr(imagedata_utils.sl, "Slice", lambda: fake)
    assert imagedata_utils.convert_world_to_invesalius([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]) == (
        None,
        None,
    )


def test_world_conversion_needs_a_loaded_matrix(monkeypatch):
    fake = _FakeSlice(np.eye(4), None)
    monkeypatch.setattr(imagedata_utils.sl, "Slice", lambda: fake)
    assert imagedata_utils.convert_world_to_invesalius([0.0, 0.0, 0.0], [0.0, 0.0, 0.0]) == (
        None,
        None,
    )
