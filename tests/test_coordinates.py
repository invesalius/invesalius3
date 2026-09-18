"""Tests for invesalius/data/coordinates.py.

The cases here are about the "no tracker selected" state, which is the DEFAULT
state: const.DEFAULT_TRACKER is const.SELECT, which is 0. GetCoordinatesForThread()
used to leave `marker_visibilities` unbound on that path and raise
UnboundLocalError from its own return statement, killing the ReceiveCoordinates
polling thread on its first iteration (#1472).

The second test is the one that matters for the shape of the fix. Returning
(None, None) also stops the UnboundLocalError, but TrackerCoordinates.SetCoordinates()
stores the visibilities *before* its `coord is None` guard, so a None would replace
the list set in __init__ and reach every consumer through GetCoordinates(). Those
consumers index and unpack it, so the crash would come back as a TypeError further
from its cause. Asserting the round trip, rather than just the return value, is what
pins that.
"""

from typing import List, Optional, Tuple

import numpy as np
import pytest
import wx

import invesalius.constants as const
import invesalius.data.coordinates as dco

if not wx.GetApp():
    app = wx.App(False)


def test_get_coordinates_for_thread_without_tracker_does_not_raise() -> None:
    # const.SELECT is the value tracker_id holds before a device is chosen, and
    # DEFAULT_TRACKER is SELECT, so this is the state the app starts in.
    coord, marker_visibilities = dco.GetCoordinatesForThread(
        None, const.SELECT, const.DEFAULT_REF_MODE
    )

    assert coord is None
    assert marker_visibilities == [False, False, False]


def test_no_tracker_visibilities_stay_usable_by_consumers() -> None:
    """The visibilities must remain a sequence of bools, not None.

    SetCoordinates() assigns them before returning early on `coord is None`, so
    whatever GetCoordinatesForThread() produced is what GetCoordinates() hands out.
    """
    _, marker_visibilities = dco.GetCoordinatesForThread(
        None, const.SELECT, const.DEFAULT_REF_MODE
    )

    tracker_coordinates = dco.TrackerCoordinates()
    tracker_coordinates.SetCoordinates(None, marker_visibilities)
    coord, visibilities = tracker_coordinates.GetCoordinates()

    assert coord is None

    # The two shapes every consumer uses. navigation/tracker.py and
    # data/viewer_volume.py unpack; navigation/navigation.py indexes and slices.
    probe_visible, head_visible, *coils_visible = visibilities
    assert probe_visible is False
    assert head_visible is False
    assert any(coils_visible) is False
    assert visibilities[0] is False
    assert any(visibilities[2:]) is False


def test_get_coordinates_for_thread_with_tracker_is_unchanged(mocker) -> None:
    """The selected-tracker path must still return exactly what the device gave."""
    expected_coord = np.array([[1.0, 2.0, 3.0, 0.0, 0.0, 0.0]])
    expected_visibilities = [True, True, False]
    mocker.patch.object(
        dco,
        "DebugCoordRandom",
        return_value=(expected_coord, expected_visibilities),
    )

    coord, marker_visibilities = dco.GetCoordinatesForThread(
        None, const.DEBUGTRACKRANDOM, const.DEFAULT_REF_MODE
    )

    assert np.array_equal(coord, expected_coord)
    assert marker_visibilities == expected_visibilities
