"""Futures curve tools: constant-maturity interpolation and most-active selection.

A seaborne cargo priced today arrives in China two to six weeks later, so the
onshore price it competes with is the Dalian price for that maturity, not the
price of whichever contract happens to be most traded.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CMResult:
    """Constant-maturity price for one day."""

    value: float
    method: str  # "interpolated", "exact", "extrapolated_flat" or "none"
    near: str | None
    far: str | None
    near_days: float | None
    far_days: float | None


def interpolate_constant_maturity(
    days_to_expiry: np.ndarray,
    prices: np.ndarray,
    contracts: list[str],
    target_days: float,
    allow_flat_extrapolation: bool = True,
) -> CMResult:
    """Linear interpolation of price on calendar days to expiry.

    ``days_to_expiry``, ``prices`` and ``contracts`` describe the eligible
    contracts on one day (already filtered for liquidity). When the target lies
    before the first eligible expiry or after the last, the nearest contract's
    price is used and the result is flagged ``extrapolated_flat``.
    """
    d = np.asarray(days_to_expiry, dtype=float)
    p = np.asarray(prices, dtype=float)
    ok = np.isfinite(d) & np.isfinite(p)
    d, p = d[ok], p[ok]
    names = [c for c, k in zip(contracts, ok, strict=True) if k]
    if len(d) == 0:
        return CMResult(float("nan"), "none", None, None, None, None)
    order = np.argsort(d)
    d, p = d[order], p[order]
    names = [names[i] for i in order]
    if np.any(d == target_days):
        i = int(np.flatnonzero(d == target_days)[0])
        return CMResult(float(p[i]), "exact", names[i], names[i], float(d[i]), float(d[i]))
    if target_days < d[0] or target_days > d[-1]:
        if not allow_flat_extrapolation:
            return CMResult(float("nan"), "none", None, None, None, None)
        i = 0 if target_days < d[0] else len(d) - 1
        return CMResult(float(p[i]), "extrapolated_flat", names[i], names[i], float(d[i]), float(d[i]))
    j = int(np.searchsorted(d, target_days))
    i = j - 1
    w = (target_days - d[i]) / (d[j] - d[i])
    value = (1.0 - w) * p[i] + w * p[j]
    return CMResult(float(value), "interpolated", names[i], names[j], float(d[i]), float(d[j]))


def eligible(
    oi: np.ndarray,
    days_to_expiry: np.ndarray,
    min_oi: float,
    min_share: float,
    min_days: float,
) -> np.ndarray:
    """Liquidity filter: open interest at least ``min_oi`` lots and at least
    ``min_share`` of the day's total, and more than ``min_days`` calendar days
    before expiry (contracts in their final days converge to delivery value and
    trade thinly)."""
    oi = np.asarray(oi, dtype=float)
    total = np.nansum(oi)
    share = oi / total if total > 0 else np.zeros_like(oi)
    return (oi >= min_oi) & (share >= min_share) & (np.asarray(days_to_expiry, dtype=float) > min_days)


def most_active(panel: pd.DataFrame, by: str = "oi") -> pd.DataFrame:
    """Most-active contract per day, chosen on the previous trading day's open
    interest (so the choice uses only information available at the open).

    ``panel`` columns: date, contract, ``by``, plus any price columns. Returns
    one row per date with the chosen contract and its same-day values.
    """
    p = panel.sort_values(["date", "contract"])
    dates = np.sort(p["date"].unique())
    prev = pd.Series(dates[:-1], index=dates[1:])
    leader = p.loc[p.groupby("date")[by].idxmax(), ["date", "contract"]].set_index("date")["contract"]
    choice = prev.map(leader)
    pick = pd.DataFrame({"date": choice.index, "contract": choice.values})
    out = pick.merge(p, on=["date", "contract"], how="left")
    # If yesterday's leader no longer trades today (it expired), use today's leader.
    gone = out[by].isna()
    if gone.any():
        same_day = p.loc[p.groupby("date")[by].idxmax()].set_index("date")
        repl = same_day.loc[out.loc[gone, "date"]].reset_index()
        out = pd.concat([out[~gone], repl[out.columns]], ignore_index=True)
    return out.sort_values("date").reset_index(drop=True)
