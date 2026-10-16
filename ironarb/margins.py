"""Delivered cost chain and margins.

All RMB amounts are per dry metric tonne (dmt) unless a name says otherwise.

    financing (USD/dmt) = CFR x (USD rate + spread) x days / 360
    landed cost (RMB/dmt) = CFR x USDCNY x (1 + VAT)
                            + port charges per dmt
                            + financing x USDCNY          (no import VAT on financing)
    import margin = Dalian 62% equivalent at the matching maturity - landed cost
    FOB netback (USD/dmt) = CFR - freight per wmt / (1 - moisture)
    mill margin (RMB/t) = steel - a x iron ore - b x coke - other costs
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from .units import per_wmt_to_per_dmt


def _out(x: np.ndarray) -> np.ndarray | float:
    return float(x) if np.ndim(x) == 0 else x


def financing_usd(
    cfr_usd_dmt: ArrayLike, usd_rate_pct: ArrayLike, spread_bp: ArrayLike, days: ArrayLike
) -> np.ndarray | float:
    """Interest on the cargo value over the financing period, actual/360."""
    cfr = np.asarray(cfr_usd_dmt, dtype=float)
    rate = np.asarray(usd_rate_pct, dtype=float) / 100.0 + np.asarray(spread_bp, dtype=float) / 10_000.0
    return _out(cfr * rate * np.asarray(days, dtype=float) / 360.0)


@dataclass(frozen=True)
class LandedCost:
    """Components of the landed cost, RMB per dry tonne."""

    goods_rmb: np.ndarray | float  # CFR converted at USDCNY
    vat_rmb: np.ndarray | float  # import VAT on the CFR value
    port_rmb: np.ndarray | float  # port charges per dmt
    financing_rmb: np.ndarray | float
    total_rmb: np.ndarray | float


def landed_cost(
    cfr_usd_dmt: ArrayLike,
    usdcny: ArrayLike,
    vat: ArrayLike,
    port_rmb_wmt: ArrayLike,
    moisture: ArrayLike,
    financing_usd_dmt: ArrayLike,
) -> LandedCost:
    """Landed cost of 62% Fe fines in RMB per dry tonne, VAT included.

    Port charges are quoted per wet tonne handled and converted to a dry basis
    with ``moisture``. Customs value is approximated by CFR (insurance excluded).
    """
    cfr = np.asarray(cfr_usd_dmt, dtype=float)
    fx = np.asarray(usdcny, dtype=float)
    v = np.asarray(vat, dtype=float)
    goods = cfr * fx
    tax = goods * v
    port = np.asarray(per_wmt_to_per_dmt(port_rmb_wmt, moisture), dtype=float)
    fin = np.asarray(financing_usd_dmt, dtype=float) * fx
    total = goods + tax + port + fin
    return LandedCost(_out(goods), _out(tax), _out(port), _out(fin), _out(total))


def import_margin(dce62_rmb_dmt: ArrayLike, landed_rmb_dmt: ArrayLike) -> np.ndarray | float:
    """Positive when onshore futures pay more than the delivered cost of seaborne ore."""
    return _out(np.asarray(dce62_rmb_dmt, dtype=float) - np.asarray(landed_rmb_dmt, dtype=float))


def window_state(margin: ArrayLike, band: float) -> np.ndarray:
    """+1 open (margin above the band), 0 inside the band, -1 closed below it."""
    m = np.asarray(margin, dtype=float)
    out = np.where(m > band, 1, np.where(m < -band, -1, 0))
    return np.where(np.isnan(m), np.nan, out)


def fob_netback(cfr_usd_dmt: ArrayLike, freight_usd_wmt: ArrayLike, moisture: ArrayLike) -> np.ndarray | float:
    """Index-equivalent FOB netback: CFR minus freight converted to a dry basis."""
    freight_dmt = np.asarray(per_wmt_to_per_dmt(freight_usd_wmt, moisture), dtype=float)
    return _out(np.asarray(cfr_usd_dmt, dtype=float) - freight_dmt)


def mill_margin(
    steel: ArrayLike, ore: ArrayLike, coke: ArrayLike, ore_coef: float, coke_coef: float, other_costs: float
) -> np.ndarray | float:
    """Futures-implied steel margin (Chinese market convention), RMB per tonne of steel."""
    return _out(
        np.asarray(steel, dtype=float)
        - ore_coef * np.asarray(ore, dtype=float)
        - coke_coef * np.asarray(coke, dtype=float)
        - other_costs
    )
