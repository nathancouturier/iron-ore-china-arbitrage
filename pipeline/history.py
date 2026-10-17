"""Long history (decision log D050 to D054).

- The seaborne iron ore price since January 1960 (World Bank Pink Sheet), on one
  axis as a 62% Fe equivalent in USD per dry tonne, nominal and in today's
  dollars (US CPI-U).
- The delivered cost of a 62% cargo in RMB per dry tonne since January 2006,
  when the World Bank series becomes a spot price CFR China.
- China's iron ore imports by origin since 1992 (UN Comtrade via WITS).
- The Baltic Dry Index since October 1988 and the Capesize index since April 1999.

The import margin itself starts with the Dalian futures (October 2013).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ironarb import margins, vat
from ironarb.voyage import financing_days

from . import inputs
from .ingest import fred
from .margin_model import Assumptions, build_voyages

DERIVED = inputs.DERIVED


@dataclass(frozen=True)
class Regime:
    start: str
    end: str | None
    label: str
    basis: str  # contract_fob_brazil or spot_cfr_china
    unit: str
    fe_pct: float | None  # Fe grade of a spot quote; None for per-Fe-unit contract prices


# From the Description sheet of the World Bank monthly workbook (CMO-Historical-Data-Monthly.xlsx)
REGIMES = (
    Regime(
        "1960-01",
        "1986-12",
        "Annual contract, Itabira (Vale), FOB Tubarão",
        "contract_fob_brazil",
        "US cents/dmtu",
        None,
    ),
    Regime(
        "1987-01",
        "2005-12",
        "Annual contract, Carajás sinter feed (Vale), FOB Ponta da Madeira",
        "contract_fob_brazil",
        "US cents/dmtu",
        None,
    ),
    Regime("2006-01", "2008-11", "Spot 63.5% Fe fines, CFR China", "spot_cfr_china", "USD/dmt", 63.5),
    Regime("2008-12", None, "Spot 62% Fe fines, CFR China", "spot_cfr_china", "USD/dmt", 62.0),
)
FE_REF = 62.0


def regime_of(month: pd.Period) -> Regime:
    for r in REGIMES:
        if month >= pd.Period(r.start, "M") and (r.end is None or month <= pd.Period(r.end, "M")):
            return r
    raise ValueError(f"no World Bank iron ore regime for {month}")


def to_62_equivalent(value: float, r: Regime) -> float:
    """USD per dry tonne at 62% Fe. Contract prices are per Fe unit (1% Fe in a
    dry tonne), so a 62% tonne is 62 units; spot quotes at another grade scale
    pro rata to the Fe content."""
    if r.fe_pct is None:
        return value * FE_REF / 100.0
    return value * FE_REF / r.fe_pct


def long_price() -> pd.DataFrame:
    """Monthly World Bank iron ore price since 1960 with its regime, the 62% Fe
    equivalent and the same in dollars of the latest CPI month."""
    wb = inputs.cfr_monthly()["cfr62_wb_usd_dmt"].dropna()
    wb.index = wb.index.to_period("M")
    cpi = fred.read("CPIAUCSL").set_index("date")["value"].dropna()
    cpi.index = cpi.index.to_period("M")
    rows = []
    for m, v in wb.items():
        r = regime_of(m)
        rows.append(
            {
                "month": m,
                "wb_native": float(v),
                "wb_unit": r.unit,
                "regime": r.label,
                "basis": r.basis,
                "fe62_usd_dmt": to_62_equivalent(float(v), r),
            }
        )
    df = pd.DataFrame(rows).set_index("month")
    df["cpi_u"] = cpi.reindex(df.index)
    base = cpi.index.max()
    df["fe62_real_usd_dmt"] = df["fe62_usd_dmt"] * float(cpi.loc[base]) / df["cpi_u"]
    df.attrs["cpi_base"] = str(base)
    return df


def long_landed(a: Assumptions | None = None, start: str = "2006-01") -> pd.DataFrame:
    """Delivered cost of a 62% cargo (C5 voyage) in RMB per dry tonne, monthly,
    from the World Bank spot series, with the dated VAT schedule and today's port
    and financing assumptions; the Dalian 45-day price from 2014 alongside."""
    a = a or Assumptions()
    p = long_price()
    p = p[(p.index >= pd.Period(start, "M")) & (p["basis"] == "spot_cfr_china")]
    fx = inputs.fx_daily()
    rate = inputs.usd_rate_daily()
    fx_m = fx.groupby(fx.index.to_period("M")).mean()
    rate_m = rate.groupby(rate.index.to_period("M")).mean()
    df = pd.DataFrame({"cfr62_usd_dmt": p["fe62_usd_dmt"], "usdcny": fx_m, "usd_rate_pct": rate_m}).dropna()
    days = financing_days(build_voyages(a)[a.route], a.extra_days)
    df["vat_rate"] = vat.vat_series(df.index.to_timestamp())
    fin = margins.financing_usd(df["cfr62_usd_dmt"], df["usd_rate_pct"], a.spread_bp, days)
    lc = margins.landed_cost(df["cfr62_usd_dmt"], df["usdcny"], df["vat_rate"], a.port_rmb_wmt, a.moisture, fin)
    df["goods_rmb_dmt"] = lc.goods_rmb
    df["vat_rmb_dmt"] = lc.vat_rmb
    df["port_rmb_dmt"] = lc.port_rmb
    df["financing_rmb_dmt"] = lc.financing_rmb
    df["landed_rmb_dmt"] = lc.total_rmb
    curve = inputs.dce_curve()[f"dce_i_cm{a.cm_target}_rmb_dmt"].dropna()
    dce_m = curve.groupby(curve.index.to_period("M")).mean()
    df["dce62_rmb_dmt"] = dce_m.reindex(df.index)
    df.index.name = "month"
    return df


ORIGINS = ("Australia", "Brazil", "India", "South Africa")


def imports_by_origin() -> pd.DataFrame:
    """Annual China imports of iron ore (HS 260111 and 260112) by origin group:
    million tonnes (customs weight), USD million (CIF) and the unit value in USD
    per tonne. Partners without a reported quantity are left out of tonnage and
    unit value and counted in ``value_without_qty_musd``."""
    d = pd.read_csv(DERIVED / "china_iron_ore_imports_by_partner_annual.csv", dtype={"hs": str})
    d["origin"] = np.where(d["partner"].isin(ORIGINS), d["partner"], "Other")
    has_q = d["qty_t"].notna()
    g = d.groupby(["year", "origin"])
    out = pd.DataFrame(
        {
            "qty_mt": g["qty_t"].sum(min_count=1) / 1e6,
            "value_musd": g["value_kusd"].sum() / 1e3,
            "value_with_qty_musd": d[has_q].groupby(["year", "origin"])["value_kusd"].sum() / 1e3,
        }
    )
    out["value_without_qty_musd"] = out["value_musd"] - out["value_with_qty_musd"].fillna(0.0)
    out["unit_value_usd_t"] = out["value_with_qty_musd"] * 1e6 / (out["qty_mt"] * 1e6)
    return out.drop(columns="value_with_qty_musd").reset_index()


def imports_total() -> pd.DataFrame:
    """Annual totals over every partner, with the share of each origin group."""
    o = imports_by_origin()
    t = o.groupby("year")[["qty_mt", "value_musd"]].sum()
    t["unit_value_usd_t"] = t["value_musd"] / t["qty_mt"]
    # an origin absent from a year's partner list reported no imports that year
    shares = o.pivot(index="year", columns="origin", values="qty_mt").fillna(0.0).div(t["qty_mt"], axis=0)
    shares.columns = [f"share_{c.lower().replace(' ', '_')}" for c in shares.columns]
    return t.join(shares)


def baltic_monthly() -> pd.DataFrame:
    b = inputs.baltic_daily()
    m = b.groupby(b.index.to_period("M")).mean()
    m.index.name = "month"
    return m


def summary(price: pd.DataFrame, landed: pd.DataFrame, imp: pd.DataFrame, baltic: pd.DataFrame) -> dict:
    """Headline numbers for the long view, all computed here so the site and
    the note quote the same figures."""
    real = price["fe62_real_usd_dmt"]
    yearly = real.groupby(real.index.year).mean()
    pre = yearly.loc[1960:2003]
    peak_m = price["fe62_usd_dmt"].idxmax()
    peak_real_m = real.idxmax()
    tot = imports_total()
    first, last = tot.index.min(), tot.index.max()
    decade = tot["qty_mt"].groupby((tot.index // 10) * 10).mean()
    la = landed["landed_rmb_dmt"]
    bm = baltic["bci_pts"].dropna()
    return {
        "cpi_base": price.attrs.get("cpi_base"),
        "price_first_month": str(price.index.min()),
        "price_last_month": str(price.index.max()),
        "real_mean_1960_2003": float(pre.mean()),
        "real_min_year": int(yearly.idxmin()),
        "real_min_year_value": float(yearly.min()),
        "real_last_12m_mean": float(real.iloc[-12:].mean()),
        "nominal_peak_month": str(peak_m),
        "nominal_peak": float(price.loc[peak_m, "fe62_usd_dmt"]),
        "real_peak_month": str(peak_real_m),
        "real_peak": float(real.loc[peak_real_m]),
        "imports_first_year": int(first),
        "imports_last_year": int(last),
        "imports_first_mt": float(tot.loc[first, "qty_mt"]),
        "imports_last_mt": float(tot.loc[last, "qty_mt"]),
        "imports_decade_mean_mt": {str(k): float(v) for k, v in decade.items()},
        "share_australia_first": float(tot.loc[first, "share_australia"]),
        "share_australia_last": float(tot.loc[last, "share_australia"]),
        "share_brazil_first": float(tot.loc[first, "share_brazil"]),
        "share_brazil_last": float(tot.loc[last, "share_brazil"]),
        "share_india_peak_year": int(tot["share_india"].idxmax()),
        "share_india_peak": float(tot["share_india"].max()),
        "share_india_last": float(tot.loc[last, "share_india"]),
        "landed_first_month": str(la.index.min()),
        "landed_peak_month": str(la.idxmax()),
        "landed_peak": float(la.max()),
        "landed_last_month": str(la.index.max()),
        "landed_last": float(la.iloc[-1]),
        "bci_peak_month": str(bm.idxmax()),
        "bci_peak": float(bm.max()),
    }
