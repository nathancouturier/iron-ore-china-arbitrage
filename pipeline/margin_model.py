"""Import margin: delivered cost of seaborne 62% fines against Dalian.

Monthly baseline: IMF 62% Fe CFR China monthly average (FRED PIORECRUSDM)
against the monthly average of the daily 45-day constant-maturity Dalian price.
Daily series: SGX prompt-month iron ore futures settlement as the CFR proxy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ironarb import margins, vat
from ironarb.params import PARAMS, ROUTES, VESSEL
from ironarb.voyage import Voyage, financing_days

from . import inputs, routes


@dataclass
class Assumptions:
    """One full set of assumptions; defaults from ``ironarb.params``."""

    port_rmb_wmt: float = PARAMS["port_charges_rmb_wmt"]["value"]
    moisture: float = PARAMS["moisture"]["value"]
    spread_bp: float = PARAMS["financing_spread_bp"]["value"]
    extra_days: float = PARAMS["financing_extra_days"]["value"]
    cm_target: int = PARAMS["cm_target_days"]["value"]
    band: float = PARAMS["band_rmb_dmt"]["value"]
    fx_source: str = "dexchus"  # or "central_parity"
    route: str = "C5"
    vessel: dict[str, float] = field(default_factory=lambda: {k: v["value"] for k, v in VESSEL.items()})
    port_costs_usd: dict[str, float] = field(default_factory=dict)


def build_voyages(a: Assumptions) -> dict[str, Voyage]:
    dist = routes.distances()
    v = a.vessel
    out = {}
    for code, r in ROUTES.items():
        nm = dist[f"{r['load']}-qingdao"]
        out[code] = Voyage(
            name=code,
            laden_nm=nm,
            ballast_nm=nm,
            laden_speed_kn=v["laden_speed_kn"],
            ballast_speed_kn=v["ballast_speed_kn"],
            laden_fuel_t_day=v["laden_fuel_t_day"],
            ballast_fuel_t_day=v["ballast_fuel_t_day"],
            port_fuel_t_day=v["port_fuel_t_day"],
            load_port_days=r["load_days"],
            discharge_port_days=v["discharge_days"],
            cargo_t=v["cargo_t"],
            commission=v["commission"],
            port_costs_usd=a.port_costs_usd.get(code, r.get("port_costs_usd", 0.0)),
        )
    return out


def _monthly_mean(s: pd.Series) -> pd.Series:
    return s.groupby(s.index.to_period("M")).mean()


def monthly_inputs() -> pd.DataFrame:
    cfr = inputs.cfr_monthly()
    cfr.index = cfr.index.to_period("M")
    curve = inputs.dce_curve()
    cols = [c for c in curve.columns if c.startswith("dce_i_cm") or c in ("dce_i_ma62_rmb_dmt", "dce_i_ma_rmb_dmt")]
    dce_m = curve[cols].groupby(curve.index.to_period("M")).mean()
    dce_m["dce_trading_days"] = curve.groupby(curve.index.to_period("M")).size()
    fx = _monthly_mean(inputs.fx_daily())
    cp = _monthly_mean(inputs.central_parity_daily())
    rate = _monthly_mean(inputs.usd_rate_daily())
    df = cfr.join(dce_m, how="outer").join(fx).join(cp).join(rate)
    df.index.name = "month"
    return df


def compute_margin(df: pd.DataFrame, cfr_col: str, a: Assumptions, voyages: dict[str, Voyage]) -> pd.DataFrame:
    """Landed cost and margins for a frame indexed by month (Period) or date."""
    out = pd.DataFrame(index=df.index)
    dates = df.index.to_timestamp() if isinstance(df.index, pd.PeriodIndex) else df.index
    out["cfr62_usd_dmt"] = df[cfr_col]
    fx = df["usdcny"] if a.fx_source == "dexchus" else df["usdcny_cp"]
    out["usdcny"] = fx
    out["vat_rate"] = vat.vat_series(dates)
    out["usd_rate_pct"] = df["usd_rate_pct"]
    cm_col = f"dce_i_cm{a.cm_target}_rmb_dmt"
    out["dce62_rmb_dmt"] = df[cm_col]
    out["dce_ma62_rmb_dmt"] = df["dce_i_ma62_rmb_dmt"]
    for code, v in voyages.items():
        days = financing_days(v, a.extra_days)
        fin = margins.financing_usd(out["cfr62_usd_dmt"], out["usd_rate_pct"], a.spread_bp, days)
        lc = margins.landed_cost(out["cfr62_usd_dmt"], fx, out["vat_rate"], a.port_rmb_wmt, a.moisture, fin)
        k = code.lower()
        out[f"financing_days_{k}"] = days
        out[f"financing_{k}_usd_dmt"] = fin
        out[f"landed_{k}_rmb_dmt"] = lc.total_rmb
        if code == a.route:
            out["goods_rmb_dmt"] = lc.goods_rmb
            out["vat_rmb_dmt"] = lc.vat_rmb
            out["port_rmb_dmt"] = lc.port_rmb
            out["financing_rmb_dmt"] = lc.financing_rmb
            out["landed_rmb_dmt"] = lc.total_rmb
    out["margin_rmb_dmt"] = margins.import_margin(out["dce62_rmb_dmt"], out["landed_rmb_dmt"])
    out["margin_naive_rmb_dmt"] = margins.import_margin(out["dce_ma62_rmb_dmt"], out["landed_rmb_dmt"])
    out["window_state"] = margins.window_state(out["margin_rmb_dmt"], a.band)
    return out


def monthly_margin(a: Assumptions | None = None, start: str = "2014-01") -> pd.DataFrame:
    a = a or Assumptions()
    df = monthly_inputs()
    df = df[df.index >= pd.Period(start, "M")]
    df = df.dropna(subset=["cfr62_imf_usd_dmt", f"dce_i_cm{a.cm_target}_rmb_dmt"])
    res = compute_margin(df, "cfr62_imf_usd_dmt", a, build_voyages(a))
    res["cfr62_wb_usd_dmt"] = df["cfr62_wb_usd_dmt"]
    res["dce_trading_days"] = df["dce_trading_days"]
    return res


# Daily CFR proxy ----------------------------------------------------------------
@dataclass
class SgxProxy:
    daily: pd.DataFrame
    basis: pd.DataFrame
    info: dict[str, Any] = field(default_factory=dict)


IODEX_61_FROM = pd.Period("2026-01", "M")


def sgx_prompt(prompt: pd.DataFrame, cfr_m: pd.DataFrame) -> SgxProxy:
    """Prompt-month (current calendar month) SGX settlement as a daily 62% CFR proxy.

    Contracts for months before January 2026 settle on a 62% Fe index. From
    January 2026 they settle on Platts IODEX, which is on a 61% Fe basis; those
    settlements are lifted to a 62% basis by the measured monthly spread between
    the IMF 62% monthly average and the contract's final settlement; months the
    IMF has not yet published use the mean of the measured 2026 spreads.
    """
    p = prompt.dropna(subset=["sgx_prompt_usd_dmt"]).copy().set_index("date").sort_index()
    p["dmonth"] = p.index.to_period("M")
    finals = p.groupby("dmonth")["sgx_prompt_usd_dmt"].last()
    complete = p.groupby("dmonth").apply(
        lambda g: g.index.max() >= g.index.max().to_period("M").end_time.normalize() - pd.offsets.BDay(1)
    )
    bench = cfr_m["cfr62_imf_usd_dmt"]
    basis = pd.DataFrame({"sgx_final_usd_dmt": finals, "bench62_usd_dmt": bench}).dropna(subset=["sgx_final_usd_dmt"])
    basis["month_complete"] = complete
    basis["spread_usd_dmt"] = (basis["bench62_usd_dmt"] - basis["sgx_final_usd_dmt"]).where(basis["month_complete"])
    basis["iodex61"] = basis.index >= IODEX_61_FROM
    measured = basis.loc[basis["iodex61"], "spread_usd_dmt"].dropna()
    mean_spread = float(measured.mean()) if len(measured) else float("nan")
    adj = pd.Series(0.0, index=p.index)
    flag = pd.Series("62_basis", index=p.index)
    for m, grp in p.groupby("dmonth"):
        if m < IODEX_61_FROM:
            continue
        sp = basis["spread_usd_dmt"].get(m, np.nan)
        if np.isnan(sp):
            sp = mean_spread
            flag.loc[grp.index] = "61_basis_lifted_mean_spread"
        else:
            flag.loc[grp.index] = "61_basis_lifted_same_month_spread"
        adj.loc[grp.index] = sp
    daily = pd.DataFrame(
        {
            "sgx_prompt_usd_dmt": p["sgx_prompt_usd_dmt"],
            "sgx_contract_month": p["contract_month"],
            "basis_adj_usd_dmt": adj,
            "cfr62_sgx_usd_dmt": p["sgx_prompt_usd_dmt"] + adj,
            "basis_flag": flag,
        }
    )
    pre = basis.loc[~basis["iodex61"]].dropna()
    info = {
        "pre2026_final_vs_bench_mean": float((pre["sgx_final_usd_dmt"] - pre["bench62_usd_dmt"]).mean()),
        "pre2026_final_vs_bench_sd": float((pre["sgx_final_usd_dmt"] - pre["bench62_usd_dmt"]).std()),
        "spread_2026_mean": float(measured.mean()) if len(measured) else float("nan"),
        "spread_2026_months": len(measured),
        "spread_2026_min": float(measured.min()) if len(measured) else float("nan"),
        "spread_2026_max": float(measured.max()) if len(measured) else float("nan"),
    }
    return SgxProxy(daily, basis, info)


def daily_inputs() -> pd.DataFrame:
    curve = inputs.dce_curve()
    cfr_m = inputs.cfr_monthly()
    cfr_m.index = cfr_m.index.to_period("M")
    proxy = sgx_prompt(inputs.sgx_prompt(), cfr_m)
    df = curve[
        [c for c in curve.columns if c.startswith("dce_i_cm") and c.endswith("rmb_dmt")] + ["dce_i_ma62_rmb_dmt"]
    ]
    df = df.join(proxy.daily, how="inner")
    df = df.join(inputs.fx_daily()).join(inputs.central_parity_daily()).join(inputs.usd_rate_daily())
    df.attrs["sgx_info"] = proxy.info
    df.attrs["sgx_basis"] = proxy.basis
    return df


def daily_margin(a: Assumptions | None = None) -> pd.DataFrame:
    a = a or Assumptions()
    df = daily_inputs()
    df = df.dropna(subset=["cfr62_sgx_usd_dmt", f"dce_i_cm{a.cm_target}_rmb_dmt", "usdcny", "usd_rate_pct"])
    res = compute_margin(df, "cfr62_sgx_usd_dmt", a, build_voyages(a))
    res["basis_flag"] = df["basis_flag"]
    res.attrs = df.attrs
    return res
