"""Unit conversions between wet and dry metric tonnes.

Iron ore is priced per dry metric tonne (dmt): the CFR benchmark and the Dalian
futures are both dry-basis prices. Physical cargo, freight and port handling are
measured on the actual (wet) weight. With moisture ``m`` (fraction of wet
weight), one wet tonne holds ``1 - m`` dry tonnes, so a cost per wet tonne equals
``cost / (1 - m)`` per dry tonne.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


def _check_moisture(moisture: ArrayLike) -> None:
    m = np.asarray(moisture, dtype=float)
    if np.any((m < 0) | (m >= 1)):
        raise ValueError("moisture must be a fraction in [0, 1)")


def per_wmt_to_per_dmt(value_per_wmt: ArrayLike, moisture: ArrayLike) -> np.ndarray | float:
    """Convert a cost or price per wet tonne to the same amount per dry tonne."""
    _check_moisture(moisture)
    out = np.asarray(value_per_wmt, dtype=float) / (1.0 - np.asarray(moisture, dtype=float))
    return float(out) if np.ndim(out) == 0 else out


def per_dmt_to_per_wmt(value_per_dmt: ArrayLike, moisture: ArrayLike) -> np.ndarray | float:
    """Convert a price per dry tonne to the same amount per wet tonne."""
    _check_moisture(moisture)
    out = np.asarray(value_per_dmt, dtype=float) * (1.0 - np.asarray(moisture, dtype=float))
    return float(out) if np.ndim(out) == 0 else out


def dry_tonnes(wet_tonnes: ArrayLike, moisture: ArrayLike) -> np.ndarray | float:
    """Dry weight contained in a wet weight."""
    _check_moisture(moisture)
    out = np.asarray(wet_tonnes, dtype=float) * (1.0 - np.asarray(moisture, dtype=float))
    return float(out) if np.ndim(out) == 0 else out
