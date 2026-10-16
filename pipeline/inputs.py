"""Load cleaned input series for the model stage (daily and monthly).

Forward-fill rules (documented on the method page):
- USD/CNY (FRED DEXCHUS, New York noon rate) on US holidays: carried forward at
  most 5 business days.
- USD reference rate: SOFR from 2 April 2018, effective fed funds before;
  carried forward at most 5 business days.
- Brent and BCI on London or US holidays: carried forward at most 5 business days.
No other gaps are filled; Chinese holidays simply have no Dalian observation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .ingest import eastmoney, fred, safe, sgx, worldbank

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
FFILL_LIMIT = 5
SOFR_START = pd.Timestamp("2018-04-02")


def _daily(s: pd.Series, name: str) -> pd.Series:
    s = s.dropna().sort_index()
    idx = pd.bdate_range(s.index.min(), s.index.max())
    return s.reindex(idx).ffill(limit=FFILL_LIMIT).rename(name)


def fx_daily() -> pd.Series:
    df = fred.read("DEXCHUS").set_index("date")["value"]
    return _daily(df, "usdcny")


def central_parity_daily() -> pd.Series:
    df = safe.read().set_index("date")["usdcny_cp"]
    return _daily(df, "usdcny_cp")


def usd_rate_daily() -> pd.Series:
    sofr = fred.read("SOFR").set_index("date")["value"].dropna()
    dff = fred.read("DFF").set_index("date")["value"].dropna()
    rate = pd.concat([dff[dff.index < SOFR_START], sofr[sofr.index >= SOFR_START]])
    return _daily(rate, "usd_rate_pct")


def brent_daily() -> pd.Series:
    return _daily(fred.read("DCOILBRENTEU").set_index("date")["value"], "brent_usd_bbl")


def bci_daily() -> pd.Series:
    return _daily(eastmoney.read("bci").set_index("date")["value"].astype(float), "bci_pts")


def cfr_monthly() -> pd.DataFrame:
    imf = fred.read("PIORECRUSDM").set_index("date")["value"].rename("cfr62_imf_usd_dmt")
    wb = worldbank.read().set_index("date")["value"].rename("cfr62_wb_usd_dmt")
    return pd.concat([imf, wb], axis=1)


def sgx_fef() -> pd.DataFrame:
    cache = ROOT / "data" / "cache" / "sgx_fef.csv.gz"
    df = sgx.read_fef()
    df.to_csv(cache, index=False)
    return df


def dce_curve() -> pd.DataFrame:
    return pd.read_csv(DERIVED / "dce_iron_ore_curve_daily.csv", parse_dates=["date"]).set_index("date")


def mill_daily() -> pd.DataFrame:
    return pd.read_csv(DERIVED / "futures_mill_daily.csv", parse_dates=["date"]).set_index("date")
