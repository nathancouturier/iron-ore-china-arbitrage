"""Model stage: margins, freight, analysis. Writes derived CSVs and
``data/derived/analysis.json`` (every number the site and the note quote)."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ironarb.params import PARAMS, ROUTES, VESSEL
from ironarb.voyage import financing_days

from . import analysis, anchors, freight_model, inputs, mill_model
from .margin_model import Assumptions, build_voyages, daily_margin, monthly_margin

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"


def _clean(obj: Any) -> Any:
    """JSON-safe: NaN and inf to None, numpy and pandas scalars to Python."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (pd.Timestamp, pd.Period)):
        return str(obj.date() if isinstance(obj, pd.Timestamp) else obj)
    if isinstance(obj, pd.DataFrame):
        return _clean(obj.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return _clean(obj.to_dict())
    return obj


def daily_sensitivity(d: pd.DataFrame, a: Assumptions, info: dict[str, Any]) -> dict[str, Any]:
    """Latest daily margin under other values of the 2026 61%-to-62% basis lift,
    and the moves in CFR or Dalian that would change the window state."""
    last = d.dropna(subset=["margin_rmb_dmt"]).iloc[-1]
    days = financing_days(build_voyages(a)[a.route], a.extra_days)
    # RMB of landed cost per USD/dmt of CFR: goods with VAT plus financing
    slope = float(last["usdcny"] * (1 + last["vat_rate"]))
    slope += float(last["usdcny"] * (last["usd_rate_pct"] + a.spread_bp / 100) / 100 * days / 360)
    margin = float(last["margin_rmb_dmt"])
    lift = float(last.get("basis_adj_usd_dmt", 0.0))

    def at(lift_usd: float) -> dict[str, Any]:
        mg = margin - (lift_usd - lift) * slope
        return {"lift_usd_dmt": lift_usd, "margin_rmb_dmt": mg, "state": int(np.sign(mg)) if abs(mg) > a.band else 0}

    return {
        "date": str(d.dropna(subset=["margin_rmb_dmt"]).index[-1].date()),
        "margin_rmb_dmt": margin,
        "slope_rmb_per_usd": slope,
        "lift": at(lift),
        "no_lift": at(0.0),
        "lift_min": at(info["spread_2026_min"]),
        "lift_max": at(info["spread_2026_max"]),
        "lift_world_bank": at(info["spread_2026_wb_mean"]),
        # CFR change (USD/dmt) that brings the margin to the band edge (-band) and to the open threshold (+band)
        "cfr_change_to_band_usd": (margin + a.band) / slope if margin < -a.band else 0.0,
        "cfr_change_to_open_usd": (margin - a.band) / slope,
        "dalian_change_to_open_rmb": a.band - margin,
    }


def run() -> dict[str, str]:
    a = Assumptions()
    out: dict[str, Any] = {"params": PARAMS}

    # Freight (needed for netbacks and the freight share)
    cal = freight_model.calibrate()
    fdaily = freight_model.voyage_model_daily(cal, a)
    ev = freight_model.evaluate(cal, fdaily)
    freight = freight_model.modeled_series(cal, ev, fdaily)
    # Primary series: the voyage model (not fitted to route anchors; see decision log D030).
    primary = {"C3": "voyage", "C5": "voyage"}
    for route in ["C3", "C5"]:
        k = route.lower()
        col = f"{k}_voyage_usd_wmt" if primary[route] == "voyage" else f"{k}_stat_usd_wmt"
        freight[f"{k}_model_usd_wmt"] = freight[col]
        freight[f"{k}_model_usd_wmt_lo"] = freight[f"{col}_lo"]
        freight[f"{k}_model_usd_wmt_hi"] = freight[f"{col}_hi"]
    freight.index.name = "date"
    freight.reset_index().to_csv(DERIVED / "freight_modeled_daily.csv", index=False, float_format="%.4f")

    # Sensitivity of the voyage model: full-speed vessel description and port costs
    a_fast = replace(a, vessel={k: v.get("alt", v["value"]) for k, v in VESSEL.items()})
    fast = freight_model.voyage_model_daily(cal, a_fast)
    ev_fast = freight_model.evaluate(cal, fast)
    last_day = fdaily.index[-1]
    port_sens = {}
    for share in (0.5, 1.5):
        a_pc = replace(a, port_costs_usd={k: r["port_costs_usd"] * share for k, r in ROUTES.items()})
        port_sens[str(share)] = freight_model.voyage_model_daily(cal, a_pc).loc[
            last_day, ["c3_voyage_usd_wmt", "c5_voyage_usd_wmt"]
        ]
    diff = (freight["c3_model_usd_wmt"] - freight["c5_model_usd_wmt"]).dropna()
    bci = freight["bci_pts"].reindex(diff.index)
    fit = freight_model.fit_linear(bci.to_numpy(), diff.to_numpy())
    freight_sens = {
        "date": str(last_day.date()),
        "base": fdaily.loc[last_day, ["c3_voyage_usd_wmt", "c5_voyage_usd_wmt"]],
        "speed_14kn": {
            "latest": fast.loc[last_day, ["c3_voyage_usd_wmt", "c5_voyage_usd_wmt"]],
            "evaluation": {r: ev_fast[r]["voyage"] for r in ["C3", "C5"]},
            "total_days": {k: v.total_days for k, v in build_voyages(a_fast).items()},
        },
        "port_costs": port_sens,
        "c3_minus_c5_vs_bci": {
            "a": fit.a,
            "b": fit.b,
            "r2": fit.r2,
            "corr": float(np.corrcoef(bci, diff)[0, 1]),
            "n": fit.n,
            "mean": float(diff.mean()),
            "min": float(diff.min()),
            "max": float(diff.max()),
        },
    }
    out["freight"] = {
        "primary": primary,
        "evaluation": {r: ev[r] for r in ["C3", "C5"]},
        "anchors": ev["rows"],
        "tc_calibration": {k: asdict(v) for k, v in cal.tc.items()},
        "bunker_calibration": {k: asdict(v) for k, v in cal.bunker.items()},
        "sensitivity": freight_sens,
        "voyages": {
            k: {**asdict(v), "laden_days": v.laden_days, "total_days": v.total_days}
            for k, v in build_voyages(a).items()
        },
    }

    # Import margin, monthly baseline and daily
    m = monthly_margin(a)
    fm = freight[[c for c in freight.columns if "_model_usd_wmt" in c]].copy()
    fm_m = fm.groupby(fm.index.to_period("M")).mean()
    m = m.join(fm_m)
    moist = a.moisture
    for k in ["c3", "c5"]:
        origin = "brazil" if k == "c3" else "australia"
        m[f"{k}_model_usd_dmt"] = m[f"{k}_model_usd_wmt"] / (1 - moist)
        m[f"fob_{origin}_usd_dmt"] = m["cfr62_usd_dmt"] - m[f"{k}_model_usd_dmt"]
        # netback band from the freight band (high freight gives the low netback)
        m[f"fob_{origin}_usd_dmt_lo"] = m["cfr62_usd_dmt"] - m[f"{k}_model_usd_wmt_hi"] / (1 - moist)
        m[f"fob_{origin}_usd_dmt_hi"] = m["cfr62_usd_dmt"] - m[f"{k}_model_usd_wmt_lo"] / (1 - moist)
    m["freight_share_cfr_c5"] = m["c5_model_usd_dmt"] / m["cfr62_usd_dmt"]
    m["freight_share_cfr_c3"] = m["c3_model_usd_dmt"] / m["cfr62_usd_dmt"]
    m["freight_share_landed_c5"] = m["c5_model_usd_dmt"] * m["usdcny"] * (1 + m["vat_rate"]) / m["landed_rmb_dmt"]
    m.index = m.index.astype(str)
    m.index.name = "month"
    m.reset_index().to_csv(DERIVED / "import_margin_monthly.csv", index=False, float_format="%.4f")

    d = daily_margin(a)
    out["sgx_basis"] = {
        "info": d.attrs["sgx_info"],
        "months": d.attrs["sgx_basis"]
        .reset_index()
        .assign(cmonth=lambda x: x["index"].astype(str))
        .drop(columns="index"),
    }
    d = d.join(fm, how="left")
    for k in ["c3", "c5"]:
        d[f"{k}_model_usd_dmt"] = d[f"{k}_model_usd_wmt"] / (1 - moist)
    d["fob_australia_usd_dmt"] = d["cfr62_usd_dmt"] - d["c5_model_usd_dmt"]
    d["fob_brazil_usd_dmt"] = d["cfr62_usd_dmt"] - d["c3_model_usd_dmt"]
    d["freight_share_landed_c5"] = d["c5_model_usd_dmt"] * d["usdcny"] * (1 + d["vat_rate"]) / d["landed_rmb_dmt"]
    # robustness: Dalian curve without contracts in their delivery month (decision log D032)
    curve = inputs.dce_curve()
    d["margin_exdm_rmb_dmt"] = curve["dce_i_cm45_exdm_rmb_dmt"].reindex(d.index) - d["landed_rmb_dmt"]
    d.index.name = "date"
    d.drop(columns=[c for c in d.columns if c.startswith("financing_days")]).reset_index().to_csv(
        DERIVED / "import_margin_daily.csv", index=False, float_format="%.4f"
    )

    # Sensitivity of the latest daily margin to the 2026 basis lift, and break-evens
    out["daily_sensitivity"] = daily_sensitivity(d, a, out["sgx_basis"]["info"])

    # Analysis on the margin
    out["window_monthly"] = analysis.window_stats(m["margin_rmb_dmt"], a.band)
    out["window_daily"] = analysis.window_stats(d["margin_rmb_dmt"], a.band)
    for key in ["window_monthly", "window_daily"]:
        out[key]["runs"] = out[key]["runs"].astype({"start": str, "end": str})
    out["band_sensitivity"] = {
        str(b): {k: v for k, v in analysis.window_stats(d["margin_rmb_dmt"], b).items() if k.startswith("share")}
        for b in [15.0, 25.0, 35.0]
    }
    out["deviations_monthly"] = analysis.largest_deviations(m["margin_rmb_dmt"])
    out["deviations_daily"] = analysis.largest_deviations(d["margin_rmb_dmt"], min_gap=120)
    exdm_m = curve["dce_i_cm45_exdm_rmb_dmt"].groupby(curve.index.to_period("M")).mean()
    exdm_m.index = exdm_m.index.astype(str)
    m_exdm = (exdm_m.reindex(m.index) - m["landed_rmb_dmt"]).dropna()
    rob_d = analysis.window_stats(d["margin_exdm_rmb_dmt"].dropna(), a.band)
    rob_m = analysis.window_stats(m_exdm, a.band)
    out["curve_robustness"] = {
        "variant": "Dalian 45-day curve with contracts in their delivery month excluded",
        "daily": {k: v for k, v in rob_d.items() if k != "runs"},
        "monthly": {k: v for k, v in rob_m.items() if k != "runs"},
        "daily_mean_diff": float((d["margin_exdm_rmb_dmt"] - d["margin_rmb_dmt"]).mean()),
        "monthly_mean_diff": float((m_exdm - m["margin_rmb_dmt"].reindex(m_exdm.index)).mean()),
        "daily_open_runs": rob_d["runs"][rob_d["runs"]["state"] == 1].astype({"start": str, "end": str}),
    }
    out["convergence_monthly"] = analysis.convergence(m["margin_rmb_dmt"])
    out["convergence_daily"] = analysis.convergence(d["margin_rmb_dmt"])
    t = analysis.tornado(a)
    out["tornado"] = {"period": t.attrs["period"], "base_distance": t.attrs["base_distance"], "rows": t}
    out["maturity_comparison"] = {
        str(tgt): float(monthly_margin(replace(a, cm_target=tgt))["margin_rmb_dmt"].mean()) for tgt in [30, 45, 60, 90]
    }
    out["maturity_comparison"]["most_active"] = float(m["margin_naive_rmb_dmt"].mean())
    out["fx_source_effect"] = {
        "monthly_mean_diff_central_parity_minus_dexchus": float(
            (
                monthly_margin(replace(a, fx_source="central_parity"))["margin_rmb_dmt"]
                - monthly_margin(a)["margin_rmb_dmt"]
            ).mean()
        )
    }

    # Mill margins and the pre-registered test
    mm = mill_model.mill_margins()
    mm = mm[mm.index >= pd.Timestamp("2013-10-18")]
    mm.index.name = "date"
    mm.reset_index().to_csv(DERIVED / "mill_margin_daily.csv", index=False, float_format="%.4f")
    ore = inputs.dce_curve()["dce_i_cm45_rmb_dmt"]
    out["mill_test_rebar"] = mill_model.decile_test(mm["rebar_margin_ma_rmb_t"], ore)
    out["mill_test_hrc"] = mill_model.decile_test(mm["hrc_margin_ma_rmb_t"], ore)
    out["mill_sensitivity"] = {
        str(c): float(mill_model.mill_margins(other_rebar=c)["rebar_margin_ma_rmb_t"].dropna().iloc[-1])
        for c in [950.0, 1080.0, 1250.0]
    }

    # Validation anchors
    out["anchors"] = anchors.reconcile_all(a)

    (DERIVED / "analysis.json").write_text(json.dumps(_clean(out), indent=1) + "\n", encoding="utf-8")
    return {"model": "analysis.json and derived series written"}
