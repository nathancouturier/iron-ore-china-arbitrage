"""Reconcile the model with dated public anchors (section 4 of the study).

Anchors are never used to tune a default parameter. Where an anchor's own
assumptions differ from ours, they are inferred and shown next to the error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ironarb import margins, vat
from ironarb.params import PARAMS
from ironarb.voyage import financing_days

from . import inputs
from .margin_model import Assumptions, build_voyages

ROOT = Path(__file__).resolve().parents[1]
ANCHORS = ROOT / "data" / "anchors"


def _asof(s: pd.Series, d: pd.Timestamp) -> float:
    s = s.dropna()
    return float(s.loc[:d].iloc[-1])


def import_cost(a: Assumptions) -> dict[str, Any]:
    """Ruida Futures estimated import cost (RMB/t) against our landed cost."""
    df = pd.read_csv(ANCHORS / "ruida_reports.csv", parse_dates=["report_date", "data_date"])
    fx = inputs.fx_daily()
    cp = inputs.central_parity_daily()
    rate = inputs.usd_rate_daily()
    voy = build_voyages(a)[a.route]
    days = financing_days(voy, a.extra_days)
    rows = []
    for _, r in df.iterrows():
        d = r["data_date"]
        fx_d = _asof(fx, d)
        cp_t = _asof(cp, r["report_date"])
        v = vat.vat_rate(d)
        fin = margins.financing_usd(r["platts62_usd_dmt"], _asof(rate, d), a.spread_bp, days)
        ours = margins.landed_cost(r["platts62_usd_dmt"], fx_d, v, a.port_rmb_wmt, a.moisture, fin).total_rmb
        ours_cp = margins.landed_cost(r["platts62_usd_dmt"], cp_t, v, a.port_rmb_wmt, a.moisture, fin).total_rmb
        their_base = r["platts62_usd_dmt"] * cp_t * (1 + v)
        rows.append(
            {
                "report_date": r["report_date"].date().isoformat(),
                "data_date": d.date().isoformat(),
                "platts62_usd_dmt": r["platts62_usd_dmt"],
                "ruida_import_cost_rmb_t": r["import_cost_rmb_t"],
                "our_landed_rmb_dmt": ours,
                "error_rmb": ours - r["import_cost_rmb_t"],
                "our_landed_central_parity_rmb_dmt": ours_cp,
                "error_central_parity_rmb": ours_cp - r["import_cost_rmb_t"],
                "usdcny_dexchus": fx_d,
                "usdcny_central_parity_report_day": cp_t,
                "implied_adder_rmb_t": r["import_cost_rmb_t"] - their_base,
                "url": r["url"],
            }
        )
    t = pd.DataFrame(rows)
    adder = float(t["implied_adder_rmb_t"].median())
    t["reconstructed_rmb_t"] = t["platts62_usd_dmt"] * t["usdcny_central_parity_report_day"] * 1.13 + adder
    t["reconstructed_error_rmb"] = t["reconstructed_rmb_t"] - t["ruida_import_cost_rmb_t"]
    return {
        "rows": t,
        "inferred": {
            "fx": "PBoC central parity of the report day",
            "vat": 0.13,
            "median_adder_rmb_t": adder,
            "adder_range": [float(t["implied_adder_rmb_t"].min()), float(t["implied_adder_rmb_t"].max())],
        },
        "max_abs_error_ours": float(t["error_rmb"].abs().max()),
        "max_abs_error_ours_central_parity": float(t["error_central_parity_rmb"].abs().max()),
        "mean_error_ours": float(t["error_rmb"].mean()),
        "max_abs_error_reconstructed": float(t["reconstructed_error_rmb"].abs().max()),
        "tolerance_rmb": 15.0,
    }


def port_price(a: Assumptions) -> dict[str, Any]:
    """Fastmarkets 62% fines fot Qingdao (RMB per wet tonne, VAT and port fees
    included) converted to USD per dry tonne with our conventions."""
    df = pd.read_csv(ANCHORS / "fastmarkets_port.csv", parse_dates=["date"])
    fx = inputs.fx_daily()
    rows = []
    for _, r in df.iterrows():
        d = r["date"]
        fx_d = _asof(fx, d)
        v = vat.vat_rate(d)
        p_dmt = r["port_62_fot_qingdao_rmb_wmt"] / (1 - a.moisture)
        port_dmt = a.port_rmb_wmt / (1 - a.moisture)
        ours = (p_dmt - port_dmt) / (fx_d * (1 + v))
        # port charge (RMB/wmt, our convention) that would close the gap exactly
        implied_port = r["port_62_fot_qingdao_rmb_wmt"] - r["implied_usd_dmt"] * fx_d * (1 + v) * (1 - a.moisture)
        rows.append(
            {
                "date": d.date().isoformat(),
                "fastmarkets_rmb_wmt": r["port_62_fot_qingdao_rmb_wmt"],
                "fastmarkets_implied_usd_dmt": r["implied_usd_dmt"],
                "our_conversion_usd_dmt": ours,
                "error_usd_dmt": ours - r["implied_usd_dmt"],
                "usdcny": fx_d,
                "implied_port_charge_rmb_wmt": implied_port,
                "url": r["url"],
            }
        )
    t = pd.DataFrame(rows)
    return {
        "rows": t,
        "max_abs_error_usd": float(t["error_usd_dmt"].abs().max()),
        "implied_port_range": [
            float(t["implied_port_charge_rmb_wmt"].min()),
            float(t["implied_port_charge_rmb_wmt"].max()),
        ],
    }


def mill_margin() -> dict[str, Any]:
    df = pd.read_csv(ANCHORS / "mill_margin.csv", parse_dates=["date"])
    panel = pd.read_csv(ROOT / "data" / "derived" / "mill_anchor_prices.csv", parse_dates=["date"])
    px = panel.set_index(["contract", "date"])["close"]
    other = PARAMS["mill_other_costs_rebar"]["value"]
    rows = []
    for _, r in df.iterrows():
        d = r["date"]
        rb, i, j = (float(px.get((c, d), float("nan"))) for c in [r["rb_contract"], r["i_contract"], r["j_contract"]])
        if r["publisher"].startswith("SDIC"):
            ours = rb - ((1.6 * i + 0.5 * j) / 0.9 + 900.0)
            formula = "publisher's own formula"
        else:
            ours = margins.mill_margin(rb, i, j, 1.6, 0.5, other)
            formula = f"default (1.6, 0.5, {other:.0f})"
        rows.append(
            {
                "date": d.date().isoformat(),
                "publisher": r["publisher"],
                "contracts": f"{r['rb_contract']}, {r['i_contract']}, {r['j_contract']}",
                "published_rmb_t": r["published_margin_rmb_t"],
                "ours_rmb_t": ours,
                "error_rmb_t": ours - r["published_margin_rmb_t"],
                "our_closes": f"{rb:g}, {i:g}, {j:g}",
                "published_closes": ""
                if pd.isna(r["rb_close"])
                else f"{r['rb_close']:g}, {r['i_close']:g}, {r['j_close']:g}",
                "formula": formula,
                "independent": r["independent"] == "yes",
                "url": r["url"],
            }
        )
    t = pd.DataFrame(rows)
    return {"rows": t, "max_abs_error": float(t["error_rmb_t"].abs().max()), "tolerance_rmb_t": 5.0}


def reconcile_all(a: Assumptions) -> dict[str, Any]:
    return {"import_cost": import_cost(a), "port_price": port_price(a), "mill_margin": mill_margin()}
