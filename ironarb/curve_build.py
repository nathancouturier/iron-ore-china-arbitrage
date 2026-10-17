"""Daily constant-maturity and most-active series from a contract panel."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .curve import CMResult, eligible, interpolate_constant_maturity


def linear_extrapolate(d: np.ndarray, p: np.ndarray, target: float, max_gap: float) -> float | None:
    """Extrapolate before the first eligible expiry along the slope of the two
    nearest eligible contracts, if the target is within ``max_gap`` days of the
    first expiry; otherwise return None."""
    if len(d) < 2 or d[0] - target > max_gap:
        return None
    slope = (p[1] - p[0]) / (d[1] - d[0])
    return float(p[0] + slope * (target - d[0]))


def constant_maturity_day(
    day: pd.DataFrame,
    target: float,
    min_oi: float,
    min_share: float,
    min_days: float,
    max_extrap_gap: float,
    price_col: str = "price62",
) -> CMResult:
    """Constant-maturity price on one day from that day's contracts.

    ``day`` columns: contract, dte (calendar days to expiry), oi, and ``price_col``.
    """
    mask = eligible(day["oi"].to_numpy(), day["dte"].to_numpy(), min_oi, min_share, min_days)
    sub = day[mask].sort_values("dte")
    d = sub["dte"].to_numpy(dtype=float)
    p = sub[price_col].to_numpy(dtype=float)
    names = sub["contract"].tolist()
    if len(d) == 0:
        return CMResult(float("nan"), "none", None, None, None, None)
    if target < d[0]:
        v = linear_extrapolate(d, p, target, max_extrap_gap)
        if v is not None:
            return CMResult(v, "extrapolated_linear", names[0], names[1], float(d[0]), float(d[1]))
    return interpolate_constant_maturity(d, p, names, target, allow_flat_extrapolation=True)


def constant_maturity_series(
    panel: pd.DataFrame,
    targets: list[float],
    min_oi: float,
    min_share: float,
    min_days: float,
    max_extrap_gap: float,
    price_col: str = "price62",
) -> pd.DataFrame:
    """One row per date and target with value, method and contracts used."""
    rows = []
    for date, day in panel.groupby("date", sort=True):
        for t in targets:
            r = constant_maturity_day(day, t, min_oi, min_share, min_days, max_extrap_gap, price_col)
            rows.append(
                {
                    "date": date,
                    "target_days": t,
                    "value": r.value,
                    "method": r.method,
                    "near": r.near,
                    "far": r.far,
                    "near_days": r.near_days,
                    "far_days": r.far_days,
                }
            )
    return pd.DataFrame(rows)
