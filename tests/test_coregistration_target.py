import queue
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

import invesalius.constants as const
from invesalius.data.coregistration import CoordinateCorregistrate

TARGET_A = [40.0, 30.0, 20.0, 0.0, 0.0, 0.0]
TARGET_B = [-30.0, -50.0, 60.0, 0.0, 0.0, 0.0]


class StillTracker:
    def GetCoordinates(self):
        return np.zeros((3, 6)), [True, True, True]


@pytest.fixture
def navigation():
    return SimpleNamespace(target=list(TARGET_A), main_coil="coil", e_field_revision=0)


@pytest.fixture
def thread(navigation):
    eye = np.identity(4)
    coreg = CoordinateCorregistrate(
        ref_mode_id=0,
        tracker=SimpleNamespace(TrackerCoordinates=StillTracker()),
        coreg_data=[eye, None],
        obj_datas={"coil": (2, eye, eye, eye, eye, eye, eye)},
        view_tracts=False,
        queues=[queue.Queue(maxsize=1) for _ in range(4)],
        event=threading.Event(),
        sle=0.001,
        tracker_id=const.DEBUGTRACKAPPROACH,
        target=navigation.target,
        icp=SimpleNamespace(use_icp=False, m_icp=None),
        e_field_loaded=False,
        navigation=navigation,
    )
    coreg.daemon = True
    yield coreg
    coreg.event.set()
    if coreg.is_alive():
        coreg.join(timeout=2)


def wait_for_coil(thread, expected, timeout=10):
    """Read coil coordinates until the coil is at the expected position."""
    position = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            coords, _, _ = thread.coord_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        position = np.array(coords["coil"][:3])
        if np.allclose(position, expected, atol=0.5):
            return
    pytest.fail(f"coil stopped at {position}, expected {expected}")


def test_coil_follows_target_changed_during_navigation(thread, navigation):
    thread.start()
    wait_for_coil(thread, [40.0, -30.0, 20.0])

    navigation.target = list(TARGET_B)
    wait_for_coil(thread, [-30.0, 50.0, 60.0])


def test_coil_stays_at_target_after_unset(thread, navigation):
    thread.start()
    wait_for_coil(thread, [40.0, -30.0, 20.0])

    navigation.target = None
    for _ in range(20):
        thread.coord_queue.get(timeout=2)
    wait_for_coil(thread, [40.0, -30.0, 20.0])


def test_navigation_target_is_not_modified(thread, navigation):
    thread._set_target(navigation.target)
    assert navigation.target == TARGET_A
