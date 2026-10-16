"""China import value-added tax on iron ore as a dated schedule.

- 17% until 30 April 2018.
- 16% from 1 May 2018 (Caishui [2018] No. 32, 财税〔2018〕32号).
- 13% from 1 April 2019 (MOF, STA and GACC Announcement [2019] No. 39,
  财政部 税务总局 海关总署公告2019年第39号).

Import duty on iron ore (HS 2601) is zero, so VAT is the only tax wedge between
the CFR price and the tax-inclusive onshore price.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

# (first day in force, rate)
SCHEDULE: tuple[tuple[date, float], ...] = (
    (date(1994, 1, 1), 0.17),
    (date(2018, 5, 1), 0.16),
    (date(2019, 4, 1), 0.13),
)


def vat_rate(day: date | pd.Timestamp | str) -> float:
    """Import VAT rate in force on ``day``."""
    d = pd.Timestamp(day).date()
    if d < SCHEDULE[0][0]:
        raise ValueError(f"no VAT schedule before {SCHEDULE[0][0]}")
    rate = SCHEDULE[0][1]
    for start, r in SCHEDULE:
        if d >= start:
            rate = r
    return rate


def vat_series(days: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """Vectorised ``vat_rate`` for a sequence of dates."""
    idx = pd.DatetimeIndex(pd.to_datetime(days))
    out = np.full(len(idx), SCHEDULE[0][1])
    for start, r in SCHEDULE[1:]:
        out[idx >= pd.Timestamp(start)] = r
    return out
