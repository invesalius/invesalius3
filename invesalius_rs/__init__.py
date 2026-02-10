"""
invesalius_rs
==============

Safe Python interface for optional Rust-accelerated routines.

If Rust native module is unavailable, InVesalius must not crash.
Instead, functions raise clear runtime errors when used.
"""

from __future__ import annotations

import warnings


# --------------------------------------------------
# Try loading native Rust extension
# --------------------------------------------------
_native = None
_NATIVE_AVAILABLE = False

try:
    from invesalius_rs import _native  # type: ignore
    _NATIVE_AVAILABLE = True
except Exception as exc:
    warnings.warn(
        (
            "Rust native backend not available. "
            "InVesalius will run in Python-only mode.\n"
            f"Reason: {exc}"
        ),
        RuntimeWarning,
    )


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def native_available() -> bool:
    return _NATIVE_AVAILABLE


def _native_required(func_name: str):
    raise RuntimeError(
        f"Rust native backend required for `{func_name}`, "
        "but it is not available on this system."
    )


# --------------------------------------------------
# Floodfill API
# --------------------------------------------------
def floodfill_threshold(data, seeds, t0, t1, fill, strct=None, out=None):
    if not _NATIVE_AVAILABLE:
        _native_required("floodfill_threshold")

    return _native.floodfill_threshold(
        data, seeds, t0, t1, fill, strct, out
    )


def floodfill_threshold_inplace(data, seeds, t0, t1, fill, strct=None):
    if not _NATIVE_AVAILABLE:
        _native_required("floodfill_threshold_inplace")

    return _native.floodfill_threshold_inplace(
        data, seeds, t0, t1, fill, strct
    )


# --------------------------------------------------
# Mask / 3D operations (EXPECTED BY GUI)
# --------------------------------------------------
def mask_cut(*args, **kwargs):
    """
    Cut mask using 3D geometry.

    Rust-only operation.
    """
    if not _NATIVE_AVAILABLE:
        _native_required("mask_cut")

    return _native.mask_cut(*args, **kwargs)


def fill_holes_automatically(*args, **kwargs):
    if not _NATIVE_AVAILABLE:
        _native_required("fill_holes_automatically")

    return _native.fill_holes_automatically(*args, **kwargs)

