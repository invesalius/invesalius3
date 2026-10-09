import queue
import threading
from types import SimpleNamespace

import numpy as np
import pytest

import invesalius.constants as const
import invesalius.data.coregistration as coregistration

TARGET_A = [40.0, 30.0, 20.0, 0.0, 0.0, 0.0]
TARGET_B = [-30.0, -50.0, 60.0, 0.0, 0.0, 0.0]


class FakeTracker:
    """Still tracker that changes the navigation target and stops the loop at given reads."""

    def __init__(self, navigation, event, target_changes, stop_at):
        self.navigation = navigation
        self.event = event
        self.target_changes = target_changes
        self.stop_at = stop_at
        self.reads = 0

    def GetCoordinates(self):
        self.reads += 1
        if self.reads in self.target_changes:
            self.navigation.target = self.target_changes[self.reads]
        if self.reads == self.stop_at:
            self.event.set()
        return np.zeros((3, 6)), [True, True, True]


def navigate(monkeypatch, target_changes):
    """Run the coregistration loop for 300 reads and return the coil positions."""
    monkeypatch.setattr(coregistration, "sleep", lambda seconds: None)

    eye = np.identity(4)
    event = threading.Event()
    navigation = SimpleNamespace(target=TARGET_A, main_coil="coil", e_field_revision=0)
    tracker = FakeTracker(navigation, event, target_changes, stop_at=300)
    thread = coregistration.CoordinateCorregistrate(
        ref_mode_id=0,
        tracker=SimpleNamespace(TrackerCoordinates=tracker),
        coreg_data=[eye, None],
        obj_datas={"coil": (2, eye, eye, eye, eye, eye, eye)},
        view_tracts=False,
        queues=[queue.Queue() for _ in range(4)],
        event=event,
        sle=0,
        tracker_id=const.DEBUGTRACKAPPROACH,
        target=navigation.target,
        icp=SimpleNamespace(use_icp=False, m_icp=None),
        e_field_loaded=False,
        navigation=navigation,
    )
    thread.run()

    positions = []
    while not thread.coord_queue.empty():
        coords, _, _ = thread.coord_queue.get()
        positions.append(coords["coil"][:3])
    return positions


def test_coil_follows_target_changed_during_navigation(monkeypatch) -> None:
    positions = navigate(monkeypatch, {150: TARGET_B})

    assert positions[148] == pytest.approx([40.0, -30.0, 20.0], abs=0.5)
    assert positions[-1] == pytest.approx([-30.0, 50.0, 60.0], abs=0.5)
    assert TARGET_B == [-30.0, -50.0, 60.0, 0.0, 0.0, 0.0]


def test_coil_stays_at_target_after_unset(monkeypatch) -> None:
    positions = navigate(monkeypatch, {150: None})

    assert positions[-1] == pytest.approx([40.0, -30.0, 20.0], abs=0.5)
