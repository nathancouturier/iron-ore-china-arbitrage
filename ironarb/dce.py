"""Dalian Commodity Exchange iron ore conventions.

- Contract code I + YYMM, 100 t per lot, RMB per tonne on a dry basis
  ("铁矿石采用干基计价"), VAT included.
- Last trading day: the 10th trading day of the delivery month.
- Standard grade: 62% Fe up to contract I2204; 61% Fe from contract I2205
  (DCE announcement of 19 May 2021).
- From I2205, deliveries between 60.0% and 63.5% Fe are priced with a premium or
  discount of X RMB per tonne for each 0.1% Fe step from the 61% standard, with
  X set by price tier: 1.0 below 600 RMB, 1.5 from 600 to 1,200 RMB, 2.0 above
  1,200 RMB. A 62% Fe cargo is therefore worth 10 x X more than the 61% contract
  price; before I2205 no adjustment is needed.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

SWITCH_CONTRACT = (22, 5)  # I2205: first contract on the 61% Fe standard
_CODE = re.compile(r"^([A-Z]+)(\d{2})(\d{2})$")


def parse_code(code: str) -> tuple[str, int, int]:
    """'I2205' -> ('I', 2022, 5)."""
    m = _CODE.match(code.strip().upper())
    if not m:
        raise ValueError(f"bad contract code {code!r}")
    return m.group(1), 2000 + int(m.group(2)), int(m.group(3))


def standard_fe(code: str) -> float:
    """Standard Fe grade (percent) of a DCE iron ore contract."""
    _, year, month = parse_code(code)
    return 61.0 if (year % 100, month) >= SWITCH_CONTRACT else 62.0


def x_tier(avg_settlement_rmb: float) -> float:
    """X (RMB per tonne per 0.1% Fe) for a reference average settlement price."""
    if not np.isfinite(avg_settlement_rmb):
        raise ValueError("reference price must be finite")
    if avg_settlement_rmb < 600.0:
        return 1.0
    if avg_settlement_rmb <= 1200.0:
        return 1.5
    return 2.0


def to_62_basis(price_rmb: float | np.ndarray, code: str, x: float) -> float | np.ndarray:
    """Express a DCE settlement price on a 62% Fe basis.

    For 61% Fe contracts a 62% Fe delivery earns ten 0.1% steps of X:
    price62 = price + 10 x X. Contracts on the 62% standard are unchanged.
    """
    steps = round((62.0 - standard_fe(code)) / 0.1)
    return price_rmb + steps * x


def expiry_dates(contracts: list[str], trading_days: pd.DatetimeIndex) -> dict[str, pd.Timestamp]:
    """Last trading day (10th trading day of the delivery month) per contract.

    ``trading_days`` must cover the delivery months; for future months pass a
    calendar extended with expected trading days.
    """
    td = pd.DatetimeIndex(trading_days).sort_values()
    out: dict[str, pd.Timestamp] = {}
    for c in contracts:
        _, y, m = parse_code(c)
        days = td[(td.year == y) & (td.month == m)]
        if len(days) < 10:
            raise ValueError(f"calendar has fewer than 10 trading days in {y}-{m:02d}")
        out[c] = days[9]
    return out


def extend_calendar(observed: pd.DatetimeIndex, until: pd.Timestamp, holidays: list[str]) -> pd.DatetimeIndex:
    """Observed trading days, then weekdays after the last observation minus
    the given statutory holidays."""
    obs = pd.DatetimeIndex(observed).sort_values()
    future = pd.bdate_range(obs[-1] + pd.Timedelta(days=1), until)
    future = future[~future.isin(pd.DatetimeIndex(holidays))]
    return obs.append(future)
