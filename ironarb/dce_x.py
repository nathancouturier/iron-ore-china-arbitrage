"""X, the DCE iron ore Fe premium/discount per 0.1% Fe, by delivery month.

Rule (DCE iron ore futures business rules, annex 1, section 4.2, as amended to
2026; first applied to contract I2205):

- Published on the last trading day of March: arithmetic average of the daily
  settlement price of the nearest delivery-month contract from the 11th trading
  day of September of the previous year to the 10th trading day of March. In
  force from the first trading day of October to the last trading day of the
  following March.
- Published on the last trading day of September: the same average from the
  11th trading day of March to the 10th trading day of September. In force from
  the first trading day of April of the following year to the last trading day
  of September of that year.
- X = 1.0 if the average is below 600 RMB/t, 1.5 from 600 to 1,200, 2.0 above.

A contract's deliveries take place in its delivery month, so the X that applies
to contract I{YYMM} is the X in force in that month.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .dce import parse_code, standard_fe, x_tier


def _nth_trading_day(cal: pd.DatetimeIndex, year: int, month: int, n: int) -> pd.Timestamp:
    days = cal[(cal.year == year) & (cal.month == month)]
    return days[n - 1]


def reference_window(
    delivery_year: int, delivery_month: int, cal: pd.DatetimeIndex
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Averaging window that sets X for deliveries in the given month."""
    y, m = delivery_year, delivery_month
    if m >= 10:  # October to December of year Y: March-Y publication
        start = _nth_trading_day(cal, y - 1, 9, 11)
        end = _nth_trading_day(cal, y, 3, 10)
    elif m <= 3:  # January to March of year Y: March-(Y-1) publication
        start = _nth_trading_day(cal, y - 2, 9, 11)
        end = _nth_trading_day(cal, y - 1, 3, 10)
    else:  # April to September of year Y: September-(Y-1) publication
        start = _nth_trading_day(cal, y - 1, 3, 11)
        end = _nth_trading_day(cal, y - 1, 9, 10)
    return start, end


def front_settlement(iron: pd.DataFrame) -> pd.Series:
    """Daily settlement of the nearest delivery-month contract (smallest days to expiry)."""
    live = iron[iron["dte"] >= 0].dropna(subset=["settle"])
    idx = live.groupby("date")["dte"].idxmin()
    return live.loc[idx].set_index("date")["settle"].sort_index()


def x_by_contract(iron: pd.DataFrame) -> dict[str, float]:
    """X for every 61% Fe contract in ``iron`` (columns: date, contract, settle, dte)."""
    cal = pd.DatetimeIndex(np.sort(iron["date"].unique()))
    front = front_settlement(iron)
    out: dict[str, float] = {}
    for code in sorted(iron["contract"].unique()):
        if standard_fe(code) != 61.0:
            continue
        _, y, m = parse_code(code)
        try:
            start, end = reference_window(y, m, cal)
        except IndexError:
            continue  # window not yet observed
        if end > cal[-1]:
            continue
        avg = float(front.loc[start:end].mean())
        out[code] = x_tier(avg)
    return out


def x_table(iron: pd.DataFrame) -> pd.DataFrame:
    """Readable table of each published X: window, average, X and delivery months."""
    cal = pd.DatetimeIndex(np.sort(iron["date"].unique()))
    front = front_settlement(iron)
    rows = []
    for year in range(2021, cal[-1].year + 1):
        for pub_month, (s_y, s_m, e_y, e_m), first, last in [
            (3, (year - 1, 9, year, 3), f"{year}-10", f"{year + 1}-03"),
            (9, (year, 3, year, 9), f"{year + 1}-04", f"{year + 1}-09"),
        ]:
            try:
                start = _nth_trading_day(cal, s_y, s_m, 11)
                end = _nth_trading_day(cal, e_y, e_m, 10)
            except IndexError:
                continue
            if end > cal[-1]:
                continue
            avg = float(front.loc[start:end].mean())
            if first < "2022-04":
                continue  # I2205 is the first 61% contract
            rows.append(
                {
                    "published": f"{year}-{pub_month:02d} (last trading day)",
                    "window_start": start.date().isoformat(),
                    "window_end": end.date().isoformat(),
                    "avg_front_settle_rmb": round(avg, 2),
                    "x_rmb_per_0_1pct": x_tier(avg),
                    "applies_to_delivery_months": f"{first} to {last}",
                    "adjustment_62_vs_61_rmb": 10 * x_tier(avg),
                }
            )
    return pd.DataFrame(rows)
