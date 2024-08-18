from typing import Iterable

import numpy as np

def floodfill(
    data: np.ndarray,
    i: int,
    j: int,
    k: int,
    v: int,
    fill: int,
    out: np.ndarray | None,
) -> np.ndarray | None: ...
def floodfill_threshold(
    data: np.ndarray,
    seeds: list[Iterable[int]],
    t0: int,
    t1: int,
    fill: int,
    strct: np.ndarray,
    out: np.ndarray | None,
) -> np.ndarray | None: ...
def floodfill_auto_threshold(
    data: np.ndarray, seeds: list[Iterable[int]], p: float, fill: int, out: np.ndarray | None
) -> np.ndarray | None: ...
def fill_holes_automatically(
    mask: np.ndarray, labels: np.ndarray, nlabels: int, max_size: int
) -> bool: ...
