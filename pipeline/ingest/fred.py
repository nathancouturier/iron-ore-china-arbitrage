"""FRED series (Federal Reserve Bank of St. Louis), downloaded as CSV.

Series and original publishers:
- PIORECRUSDM: Global price of Iron Ore, USD per dry metric tonne, monthly,
  from the IMF Primary Commodity Price System (62% Fe fines CFR China basis).
- DEXCHUS: China / U.S. foreign exchange rate, CNY per USD, daily noon buying
  rates in New York (Federal Reserve H.10).
- DCOILBRENTEU: Brent crude, USD per barrel, daily (U.S. EIA).
- SOFR: Secured Overnight Financing Rate, percent, daily (New York Fed), from
  2 April 2018.
- DFF: Effective federal funds rate, percent, daily (Federal Reserve).
"""

from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

from .common import RAW, http, register, write_bytes

SERIES = {
    "PIORECRUSDM": "Global price of Iron Ore (IMF), USD/dmt, monthly",
    "DEXCHUS": "China / U.S. FX rate, CNY per USD, daily noon buying rate (H.10)",
    "DCOILBRENTEU": "Brent crude oil spot, USD/bbl, daily (EIA)",
    "SOFR": "Secured Overnight Financing Rate, percent, daily (NY Fed)",
    "DFF": "Effective federal funds rate, percent, daily (Federal Reserve)",
}
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def fetch(series_id: str) -> pd.DataFrame:
    # FRED rejects browser-like user agents sent from non-browser clients, so the
    # request identifies itself with the plain requests user agent.
    plain = {"User-Agent": requests.utils.default_user_agent()}
    r = http(URL, params={"id": series_id}, headers=plain, timeout=90)
    df = pd.read_csv(StringIO(r.text))
    if df.shape[1] != 2 or len(df) < 10:
        raise ValueError(f"unexpected FRED payload for {series_id}: {df.shape}")
    path = RAW / "fred" / f"{series_id}.csv"
    write_bytes(path, r.content)
    register(path, f"{URL}?id={series_id}", note=SERIES[series_id])
    return read(series_id)


def read(series_id: str) -> pd.DataFrame:
    """Read a cached FRED CSV into a (date, value) frame; '.' and blanks are missing."""
    df = pd.read_csv(RAW / "fred" / f"{series_id}.csv")
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def run() -> dict[str, str]:
    status = {}
    for sid in SERIES:
        try:
            df = fetch(sid)
            status[sid] = f"ok {len(df)} rows to {df['date'].max().date()}"
        except Exception as exc:  # keep last good file
            status[sid] = f"stale: {exc}"
    return status
