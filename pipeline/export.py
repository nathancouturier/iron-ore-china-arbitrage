"""Export stage: compact JSON per site view, CSV downloads and meta.json."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ironarb.params import LOAD_DAYS_NOTE, PARAMS, PORT_COSTS_NOTE, ROUTES, VESSEL
from ironarb.vat import SCHEDULE

from . import geo, history, inputs
from .anchors import TOLERANCE
from .ingest.common import load_manifest

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
SITE = ROOT / "site"
DATA = SITE / "data"
DL = SITE / "downloads"
VERSION = "1.0.0"


def _r(x: Any, d: int = 2) -> Any:
    if x is None:
        return None
    if isinstance(x, (float, np.floating)):
        f = float(x)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, d)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def series(df: pd.DataFrame, col: str, d: int = 2) -> list[list[Any]]:
    """[[iso date, value], ...] with missing values kept as null (gaps stay visible)."""
    idx = [str(i)[:10] for i in df.index]
    return [[i, _r(v, d)] for i, v in zip(idx, df[col].tolist(), strict=True)]


def _write(name: str, obj: Any) -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    (DATA / f"{name}.json").write_text(text, encoding="utf-8")
    return len(text)


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return _r(obj, 4) if isinstance(obj, float) else obj


def _retrieved(prefix: str) -> str | None:
    m = load_manifest()
    stamps = [v["retrieved_at"] for k, v in m.items() if k.startswith(prefix)]
    return max(stamps)[:10] if stamps else None


DOWNLOAD_TEXT = {
    "import_margin_daily.csv": (
        "Import margin, daily",
        "Landed cost of 62% fines (C5 and C3 voyages) and the Dalian 45-day 62% equivalent, with every bridge "
        "component, the margin against the most-active contract, modeled freight with bands and netbacks. "
        "CFR proxy: SGX iron ore futures at a 45-day horizon.",
    ),
    "import_margin_monthly.csv": (
        "Import margin, monthly baseline",
        "Same chain on the IMF 62% Fe CFR China monthly average against the monthly average of the daily Dalian "
        "45-day price, with World Bank CFR for comparison, freight shares and netbacks.",
    ),
    "freight_modeled_daily.csv": (
        "Modeled Capesize freight, daily",
        "C3 and C5 voyage model and regression estimates with 80% error bands, the BCI, Brent, the time charter "
        "and bunker proxies. Modeled series, not published route rates.",
    ),
    "mill_margin_daily.csv": (
        "Steel mill futures margin, daily",
        "Rebar and HRC futures margins (most-active and same-delivery-month contracts) with the ore, coke and "
        "other-cost components.",
    ),
    "dce_iron_ore_curve_daily.csv": (
        "Dalian iron ore curve, daily",
        "Constant-maturity 30, 45, 60 and 90-day prices on a 62% Fe basis with the method and contracts used, "
        "the most-active contract and total open interest.",
    ),
    "dce_x_schedule.csv": (
        "Dalian grade premium X",
        "Fe premium per 0.1% computed from the exchange rule for each half-year window, used to put 61% contracts "
        "on a 62% basis.",
    ),
    "iron_ore_price_long_monthly.csv": (
        "Iron ore price since 1960, monthly",
        "World Bank Pink Sheet iron ore series as published (US cents per dry tonne unit for the annual contracts "
        "to 2005, USD per dry tonne for the spot price from 2006), its regime and basis, the 62% Fe equivalent in "
        "USD per dry tonne and the same in dollars of the latest CPI month (US CPI-U).",
    ),
    "landed_cost_long_monthly.csv": (
        "Delivered cost since 2006, monthly",
        "Landed cost of a 62% Fe cargo in RMB per dry tonne from the World Bank spot price, with every bridge "
        "component and the Dalian 45-day 62% equivalent from 2014.",
    ),
    "china_iron_ore_imports_by_origin_annual.csv": (
        "China iron ore imports by origin since 1992",
        "Annual tonnage (customs weight), value (USD, CIF) and unit value for Australia, Brazil, India, South Africa "
        "and other origins, HS 260111 and 260112, from UN Comtrade via World Bank WITS.",
    ),
    "baltic_indices_monthly.csv": (
        "Baltic indices since 1988, monthly averages",
        "Monthly averages of the Baltic Dry Index (from October 1988) and the Baltic Capesize Index (from April 1999), "
        "index points as published.",
    ),
    "china_iron_ore_imports_monthly.csv": (
        "China iron ore imports, monthly",
        "Iron ores and concentrates, million tonnes, from the China Customs (GACC) English monthly bulletins, "
        "with the table and URL of each month. January and February 2020 were published together; September "
        "and October 2024 and the latest month come from the preliminary release.",
    ),
    "anchors_import_cost.csv": (
        "Validation anchors: Ruida Futures import cost",
        "Dated Ruida Futures daily reports: Platts 62% index, estimated import cost, route freight and BDI, with the URL.",
    ),
    "anchors_port_price.csv": (
        "Validation anchors: Fastmarkets Qingdao port price",
        "Dated Fastmarkets 62% Fe fines port prices in RMB per wet tonne with the implied USD per dry tonne, with the URL.",
    ),
    "anchors_mill_margin.csv": (
        "Validation anchors: broker rebar margins",
        "Dated broker rebar futures margins with the publisher's formula where stated, the contracts and the URL.",
    ),
    "anchors_freight_routes.csv": (
        "Validation anchors: published route rates",
        "Dated C3 and C5 assessments with the assessor, the publication that reported them, the URL and a quote.",
    ),
    "anchors_bci_tc_pairs.csv": (
        "Calibration pairs: BCI and time charter",
        "Dated pairs of BCI points and the Capesize time charter average used to calibrate the TCE proxy.",
    ),
    "anchors_bunker_prices.csv": (
        "Calibration points: bunker prices",
        "Dated Singapore HSFO and VLSFO prices used to map Brent to the bunker price.",
    ),
}


def history_block(a: dict[str, Any]) -> dict[str, Any]:
    """Long view: price since 1960, delivered cost since 2006, imports by origin
    since 1992, Baltic indices since 1988 (monthly averages)."""
    p = pd.read_csv(DERIVED / "iron_ore_price_long_monthly.csv")
    lc = pd.read_csv(DERIVED / "landed_cost_long_monthly.csv")
    o = pd.read_csv(DERIVED / "china_iron_ore_imports_by_origin_annual.csv")
    b = history.baltic_monthly()
    DL.mkdir(parents=True, exist_ok=True)
    b.reset_index().assign(month=lambda x: x["month"].astype(str)).to_csv(
        DL / "baltic_indices_monthly.csv", index=False, float_format="%.1f"
    )
    years = sorted(o["year"].unique().tolist())
    q = o.pivot(index="year", columns="origin", values="qty_mt").reindex(years).fillna(0.0)
    uv = o.pivot(index="year", columns="origin", values="unit_value_usd_t").reindex(years)
    tot = history.imports_total()
    origins = [*history.ORIGINS, "Other"]
    return {
        "summary": a["history"],
        "params": {k: v["value"] for k, v in PARAMS.items()},
        "regimes": [
            {"start": r.start, "end": r.end, "label": r.label, "basis": r.basis, "unit": r.unit, "fe_pct": r.fe_pct}
            for r in history.REGIMES
        ],
        "price": {
            "months": p["month"].tolist(),
            "nominal": [_r(v, 2) for v in p["fe62_usd_dmt"]],
            "real": [_r(v, 2) for v in p["fe62_real_usd_dmt"]],
            "native": [_r(v, 2) for v in p["wb_native"]],
        },
        "landed": {
            "months": lc["month"].tolist(),
            "landed": [_r(v, 1) for v in lc["landed_rmb_dmt"]],
            "dalian": [_r(v, 1) for v in lc["dce62_rmb_dmt"]],
            "cfr": [_r(v, 2) for v in lc["cfr62_usd_dmt"]],
            "usdcny": [_r(v, 4) for v in lc["usdcny"]],
            "vat": [_r(v, 2) for v in lc["vat_rate"]],
        },
        "imports": {
            "years": years,
            "origins": origins,
            "qty_mt": {k: [_r(v, 2) for v in q.get(k, pd.Series(0.0, index=years))] for k in origins},
            "unit_value": {k: [_r(v, 2) for v in uv.get(k, pd.Series(np.nan, index=years))] for k in origins},
            "total_mt": [_r(v, 2) for v in tot["qty_mt"]],
            "unit_value_all": [_r(v, 2) for v in tot["unit_value_usd_t"]],
        },
        "baltic": {
            "months": [str(m) for m in b.index],
            "bdi": [_r(v, 0) for v in b["bdi_pts"]],
            "bci": [_r(v, 0) for v in b["bci_pts"]],
        },
    }


def imports_block(a: dict[str, Any]) -> dict[str, Any]:
    """China Customs imports and the pre-registered imports test (D041 to D043)."""
    imp = pd.read_csv(DERIVED / "china_iron_ore_imports_monthly.csv", dtype={"start": str, "end": str})
    t, x = a["imports_test"], a["imports_test_ex_2021_2022"]
    return {
        "per_rmb_dmt": t["per_rmb_dmt"],
        "nw_lags": t["nw_lags"],
        "rows": t["rows"],
        "rows_ex": x["rows"],
        "exclude_years": x["exclude_years"],
        "points": [[p["month"], _r(p["margin_rmb_dmt"], 1), _r(p["growth_pct"], 2)] for p in t["points"]],
        "series": [
            [r.start, r.end, int(r.months), _r(float(r.imports_mt), 2), "preliminary" in r.table]
            for r in imp.itertuples(index=False)
        ],
        "first": str(imp["start"].min()),
        "last": str(imp["end"].max()),
    }


def episode_events(daily: pd.DataFrame, a: dict[str, Any]) -> list[dict[str, Any]]:
    """Sourced explanations (data/anchors/events.json) for the largest episodes,
    with the margin on the day taken from the daily series. Every computed
    episode must have an entry, so a refresh that moves an episode fails loudly
    instead of showing an unexplained point."""
    events = json.loads((ROOT / "data" / "anchors" / "events.json").read_text())
    by_date = {e["date"]: e for e in events}
    out = []
    for rank, dev in enumerate(a["deviations_daily"], start=1):
        day = str(dev["period"])[:10]
        if day not in by_date:
            raise ValueError(f"episode {day} has no sourced explanation in data/anchors/events.json")
        e = dict(by_date[day])
        e["value"] = _r(float(daily.loc[pd.Timestamp(day), "margin_rmb_dmt"]), 1)
        e["rank"] = rank
        out.append(e)
    return out


def build_meta(a: dict[str, Any], daily: pd.DataFrame, monthly: pd.DataFrame) -> dict[str, Any]:
    status_path = DERIVED / "source_status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    ing = status.get("ingest", {})
    curve = pd.read_csv(DERIVED / "dce_iron_ore_curve_daily.csv", usecols=["date"])
    mill = pd.read_csv(DERIVED / "mill_margin_daily.csv", usecols=["date"])
    sgx = pd.read_csv(DERIVED / "sgx_fef_curve_daily.csv", usecols=["date"])
    baltic = pd.read_csv(DERIVED / "baltic_indices_daily.csv", usecols=["date"])
    cp = pd.read_csv(DERIVED / "usdcny_central_parity_daily.csv", usecols=["date"])
    imports = pd.read_csv(DERIVED / "china_iron_ore_imports_monthly.csv", dtype={"end": str})
    fred = {
        s: pd.read_csv(ROOT / "data" / "raw" / "fred" / f"{s}.csv")
        for s in ["PIORECRUSDM", "DEXCHUS", "DCOILBRENTEU", "SOFR", "DFF", "CPIAUCSL"]
    }

    def last_fred(s: str) -> str:
        df = fred[s]
        df = df[pd.to_numeric(df.iloc[:, 1], errors="coerce").notna()]
        return str(df.iloc[-1, 0])[:10]

    def src(label: str, asof: str, key: str, prefix: str, url: str) -> dict[str, Any]:
        info = ing.get(key, {})
        return {
            "label": label,
            "asof": asof,
            "retrieved": _retrieved(prefix),
            "stale": (not info.get("ok", True)) if info else False,
            "url": url,
        }

    sources = {
        "imf": src(
            "IMF iron ore 62% Fe CFR China (FRED PIORECRUSDM)",
            last_fred("PIORECRUSDM")[:7],
            "fred",
            "fred/PIORECRUSDM",
            "https://fred.stlouisfed.org/series/PIORECRUSDM",
        ),
        "worldbank": src(
            "World Bank Pink Sheet, iron ore",
            str(inputs.cfr_monthly()["cfr62_wb_usd_dmt"].dropna().index[-1])[:7],
            "worldbank",
            "worldbank/",
            "https://www.worldbank.org/en/research/commodity-markets",
        ),
        "dce": src(
            "Dalian Commodity Exchange iron ore, coke, coking coal",
            str(curve["date"].iloc[-1])[:10],
            "sina",
            "dce/",
            "http://www.dce.com.cn/dalianshangpin/xqsj/lssj/index.html",
        ),
        "shfe": src(
            "Shanghai Futures Exchange rebar and hot-rolled coil",
            str(mill["date"].iloc[-1])[:10],
            "shfe",
            "shfe/",
            "https://www.shfe.com.cn/",
        ),
        "sina": src(
            "Sina Finance per-contract futures history",
            str(curve["date"].iloc[-1])[:10],
            "sina",
            "sina/",
            "https://finance.sina.com.cn/futuremarket/",
        ),
        "sgx": src(
            "SGX iron ore futures (FEF) settlements",
            str(sgx["date"].iloc[-1])[:10],
            "sgx",
            "sgx/",
            "https://www.sgx.com/derivatives/products/iron-ore",
        ),
        "baltic": src(
            "Baltic Capesize and Dry indices via East Money",
            str(baltic["date"].iloc[-1])[:10],
            "eastmoney",
            "eastmoney/",
            "https://data.eastmoney.com/cjsj/hyzs_list_EMI00107666.html",
        ),
        "fx": src(
            "USD/CNY noon buying rate (FRED DEXCHUS)",
            last_fred("DEXCHUS"),
            "fred",
            "fred/DEXCHUS",
            "https://fred.stlouisfed.org/series/DEXCHUS",
        ),
        "central_parity": src(
            "PBoC USD/CNY central parity (SAFE)",
            str(cp["date"].iloc[-1])[:10],
            "safe",
            "safe/",
            "https://www.safe.gov.cn/safe/rmbhlzjj/index.html",
        ),
        "wits": src(
            "UN Comtrade via World Bank WITS, China iron ore imports by partner",
            str(
                int(
                    pd.read_csv(DERIVED / "china_iron_ore_imports_by_partner_annual.csv", usecols=["year"])[
                        "year"
                    ].max()
                )
            ),
            "wits",
            "wits/",
            "https://wits.worldbank.org/",
        ),
        "cpi": src(
            "US consumer prices, CPI-U (FRED CPIAUCSL)",
            last_fred("CPIAUCSL")[:7],
            "fred",
            "fred/CPIAUCSL",
            "https://fred.stlouisfed.org/series/CPIAUCSL",
        ),
        "gacc": src(
            "China Customs (GACC) monthly iron ore imports",
            str(imports["end"].max()),
            "gacc",
            "gacc/",
            "http://english.customs.gov.cn/statics/report/monthly.html",
        ),
        "brent": src(
            "Brent crude (FRED DCOILBRENTEU)",
            last_fred("DCOILBRENTEU"),
            "fred",
            "fred/DCOILBRENTEU",
            "https://fred.stlouisfed.org/series/DCOILBRENTEU",
        ),
        "rates": src(
            "SOFR and effective fed funds (FRED)",
            last_fred("SOFR"),
            "fred",
            "fred/SOFR",
            "https://fred.stlouisfed.org/series/SOFR",
        ),
    }
    return {
        "version": VERSION,
        "build_time": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "build_date": datetime.now(UTC).date().isoformat(),
        "ingest_mode": status.get("ingest_mode", "full"),
        "asof": {
            "daily": str(daily.index[-1])[:10],
            "futures": str(curve["date"].iloc[-1])[:10],
            "monthly": str(monthly.index[-1]),
            "fx_observation": last_fred("DEXCHUS"),
        },
        "sources": sources,
    }


def run() -> dict[str, str]:
    a = json.loads((DERIVED / "analysis.json").read_text())
    monthly = pd.read_csv(DERIVED / "import_margin_monthly.csv").set_index("month")
    daily = pd.read_csv(DERIVED / "import_margin_daily.csv", parse_dates=["date"]).set_index("date")
    freight = pd.read_csv(DERIVED / "freight_modeled_daily.csv", parse_dates=["date"]).set_index("date")
    mill = pd.read_csv(DERIVED / "mill_margin_daily.csv", parse_dates=["date"]).set_index("date")
    curve = pd.read_csv(DERIVED / "dce_iron_ore_curve_daily.csv", parse_dates=["date"]).set_index("date")
    meta = build_meta(a, daily, monthly)
    sizes = {"meta": _write("meta", meta)}
    p = PARAMS
    band = p["band_rmb_dmt"]["value"]
    moist = p["moisture"]["value"]

    # Overview ------------------------------------------------------------------
    last = daily.dropna(subset=["margin_rmb_dmt", "c5_model_usd_wmt"]).iloc[-1]
    ld = str(daily.dropna(subset=["margin_rmb_dmt", "c5_model_usd_wmt"]).index[-1])[:10]
    fx = float(last["usdcny"])
    mlast = monthly.dropna(subset=["margin_rmb_dmt"]).iloc[-1]
    mill_last = mill.dropna(subset=["rebar_margin_ma_rmb_t"]).iloc[-1]
    mill_date = str(mill.dropna(subset=["rebar_margin_ma_rmb_t"]).index[-1])[:10]
    c5_dmt = float(last["c5_model_usd_dmt"])
    c3_dmt = float(last["c3_model_usd_dmt"])
    cfr = float(last["cfr62_usd_dmt"])
    bridge = {
        "date": ld,
        "usdcny": _r(fx, 4),
        "vat_rate": _r(float(last["vat_rate"]), 4),
        "cfr_usd_dmt": _r(cfr),
        "fob_australia_usd_dmt": _r(cfr - c5_dmt),
        "fob_brazil_usd_dmt": _r(cfr - c3_dmt),
        "freight_c5_usd_dmt": _r(c5_dmt),
        "freight_c3_usd_dmt": _r(c3_dmt),
        "freight_c5_usd_wmt": _r(float(last["c5_model_usd_wmt"])),
        "freight_c3_usd_wmt": _r(float(last["c3_model_usd_wmt"])),
        "goods_rmb": _r(float(last["goods_rmb_dmt"])),
        "vat_rmb": _r(float(last["vat_rmb_dmt"])),
        "port_rmb": _r(float(last["port_rmb_dmt"])),
        "financing_rmb": _r(float(last["financing_rmb_dmt"])),
        "financing_rmb_c3": _r(
            float(last["landed_c3_rmb_dmt"] - last["landed_c5_rmb_dmt"] + last["financing_rmb_dmt"])
        ),
        "landed_rmb": _r(float(last["landed_rmb_dmt"])),
        "landed_c3_rmb": _r(float(last["landed_c3_rmb_dmt"])),
        "dce62_rmb": _r(float(last["dce62_rmb_dmt"])),
        "dce_ma62_rmb": _r(float(last["dce_ma62_rmb_dmt"])),
        "margin_rmb": _r(float(last["margin_rmb_dmt"])),
        "margin_naive_rmb": _r(float(last["margin_naive_rmb_dmt"])),
        "basis_flag": str(last.get("basis_flag", "")),
        "basis_adj_usd_dmt": _r(float(last.get("basis_adj_usd_dmt", 0.0))),
        "sgx_cm_raw_usd_dmt": _r(float(last["cfr62_usd_dmt"] - last.get("basis_adj_usd_dmt", 0.0))),
        "sgx_contracts": str(last.get("sgx_contracts", "")),
        "fx_observation": meta["asof"]["fx_observation"],
    }
    recent = daily[daily.index >= daily.index[-1] - pd.DateOffset(months=12)]
    overview = {
        "bridge": bridge,
        "band": band,
        "facts": {
            "margin": {
                "value": bridge["margin_rmb"],
                "date": ld,
                "state": int(np.sign(bridge["margin_rmb"]) if abs(bridge["margin_rmb"]) > band else 0),
            },
            "margin_monthly": {
                "value": _r(float(mlast["margin_rmb_dmt"])),
                "month": str(monthly.dropna(subset=["margin_rmb_dmt"]).index[-1]),
            },
            "freight_share": {
                "value": _r(float(last["freight_share_landed_c5"]), 4),
                "date": ld,
                "share_of_cfr": _r(c5_dmt / cfr, 4),
            },
            "rebar_margin": {
                "value": _r(float(mill_last["rebar_margin_ma_rmb_t"]), 1),
                "date": mill_date,
                "contract": str(mill_last["rb_ma_contract"]),
            },
        },
        "recent": series(recent, "margin_rmb_dmt"),
        "share_closed_daily": a["window_daily"]["share_closed"],
        "sgx_basis": a["sgx_basis"]["info"],
        "params": {k: v["value"] for k, v in PARAMS.items()},
        "x_latest": _r(float(curve["dce_i_ma_grade_adj_rmb"].dropna().iloc[-1]), 1),
        "sensitivity": a["daily_sensitivity"],
    }
    sizes["overview"] = _write("overview", _clean(overview))

    # Import window ---------------------------------------------------------------
    dm = daily[
        [
            "margin_rmb_dmt",
            "margin_naive_rmb_dmt",
            "cfr62_usd_dmt",
            "landed_rmb_dmt",
            "dce62_rmb_dmt",
            "dce_ma62_rmb_dmt",
            "usdcny",
        ]
    ]
    mvals = daily["margin_rmb_dmt"].dropna()
    step = band  # bin edges fall on -band and +band, so colors follow the window state exactly
    hist_edges = np.arange(np.floor(mvals.min() / step) * step, np.ceil(mvals.max() / step) * step + step / 2, step)
    counts, _ = np.histogram(mvals, bins=hist_edges)
    window = {
        "daily": {
            "margin": series(dm, "margin_rmb_dmt", 1),
            "naive": series(dm, "margin_naive_rmb_dmt", 1),
        },
        "monthly": {
            "months": list(monthly.index),
            "margin": [_r(v, 1) for v in monthly["margin_rmb_dmt"]],
            "naive": [_r(v, 1) for v in monthly["margin_naive_rmb_dmt"]],
            # average of the daily (forward against forward) margin in the same month
            "daily_avg": [
                _r(v, 1)
                for v in daily["margin_rmb_dmt"]
                .groupby(daily.index.to_period("M").astype(str))
                .mean()
                .reindex(monthly.index)
            ],
        },
        "band": band,
        "stats_daily": {k: v for k, v in a["window_daily"].items() if k != "runs"},
        "stats_monthly": {k: v for k, v in a["window_monthly"].items() if k != "runs"},
        "band_sensitivity": a["band_sensitivity"],
        "band_history": a["band_history"],
        "histogram": {"edges": hist_edges.tolist(), "counts": counts.tolist()},
        "convergence_monthly": a["convergence_monthly"],
        "convergence_daily": a["convergence_daily"],
        "tornado": a["tornado"],
        "maturity": a["maturity_comparison"],
        "ma_dte_mean": _r(float(curve.loc[curve.index >= pd.Timestamp("2014-01-01"), "dce_i_ma_dte_days"].mean()), 0),
        "fx_effect": a["fx_source_effect"],
        "deviations_daily": a["deviations_daily"],
        "deviations_monthly": a["deviations_monthly"],
        "events": episode_events(daily, a),
        "curve_robustness": {k: v for k, v in a["curve_robustness"].items() if k != "daily_open_runs"},
        "imports": imports_block(a),
    }
    sizes["window"] = _write("window", _clean(window))

    # Freight ---------------------------------------------------------------------
    fr = freight[freight.index >= pd.Timestamp("2014-01-01")]
    fw = fr.resample("W-FRI").last()
    routes = json.loads((DERIVED / "routes.json").read_text())
    fm = monthly
    freight_out = {
        "routes": routes,
        "land": geo.land_geojson(),
        "voyages": a["freight"]["voyages"],
        "sensitivity": a["freight"]["sensitivity"],
        "routes_meta": {k: {"label": r["label"], "load": r["load"]} for k, r in ROUTES.items()},
        "port_costs_note": PORT_COSTS_NOTE,
        "load_days_note": LOAD_DAYS_NOTE,
        "primary": a["freight"]["primary"],
        "evaluation": a["freight"]["evaluation"],
        "anchors": a["freight"]["anchors"],
        "tc_calibration": a["freight"]["tc_calibration"],
        "bunker_calibration": a["freight"]["bunker_calibration"],
        "weekly": {
            "c3": series(fw, "c3_model_usd_wmt"),
            "c3_lo": series(fw, "c3_model_usd_wmt_lo"),
            "c3_hi": series(fw, "c3_model_usd_wmt_hi"),
            "c5": series(fw, "c5_model_usd_wmt"),
            "c5_lo": series(fw, "c5_model_usd_wmt_lo"),
            "c5_hi": series(fw, "c5_model_usd_wmt_hi"),
            "c3_alt": series(
                fw, "c3_stat_usd_wmt" if a["freight"]["primary"]["C3"] == "voyage" else "c3_voyage_usd_wmt"
            ),
            "c5_alt": series(
                fw, "c5_stat_usd_wmt" if a["freight"]["primary"]["C5"] == "voyage" else "c5_voyage_usd_wmt"
            ),
            "bci": series(fw, "bci_pts", 0),
            "brent": series(fw, "brent_usd_bbl"),
            "diff": [
                [d, _r(c3 - c5) if (c3 is not None and c5 is not None) else None]
                for (d, c3), (_, c5) in zip(series(fw, "c3_model_usd_wmt"), series(fw, "c5_model_usd_wmt"), strict=True)
            ],
        },
        "monthly": {
            "months": list(fm.index),
            "cfr": [_r(v) for v in fm["cfr62_usd_dmt"]],
            "fob_australia": [_r(v) for v in fm["fob_australia_usd_dmt"]],
            "fob_brazil": [_r(v) for v in fm["fob_brazil_usd_dmt"]],
            "fob_australia_lo": [_r(v) for v in fm["fob_australia_usd_dmt_lo"]],
            "fob_australia_hi": [_r(v) for v in fm["fob_australia_usd_dmt_hi"]],
            "fob_brazil_lo": [_r(v) for v in fm["fob_brazil_usd_dmt_lo"]],
            "fob_brazil_hi": [_r(v) for v in fm["fob_brazil_usd_dmt_hi"]],
            "share_c5": [_r(v, 4) for v in fm["freight_share_cfr_c5"]],
            "share_c3": [_r(v, 4) for v in fm["freight_share_cfr_c3"]],
        },
        "moisture": moist,
        "vessel": {k: v for k, v in VESSEL.items()},
    }
    an = pd.DataFrame(a["freight"]["anchors"])
    an["date"] = an["date"].astype(str).str[:10]
    an["error"] = an["voyage_model"] - an["value_usd_wmt"]
    recent_err = {}
    for route in ["C3", "C5"]:
        r = an[an["route"] == route].dropna(subset=["voyage_model"]).sort_values("date").tail(5)
        recent_err[route] = {
            "n": len(r),
            "first": r["date"].iloc[0],
            "last": r["date"].iloc[-1],
            "mean_error": float(r["error"].mean()),
            "errors": [float(e) for e in r["error"]],
        }
    pv = an.pivot_table(index="date", columns="route", values="value_usd_wmt", aggfunc="first")
    bci_at = an.groupby("date")["bci_pts"].first()
    pv = pv.dropna(subset=["C3", "C5"]).join(bci_at).dropna(subset=["bci_pts"])
    freight_out["recent_error"] = recent_err
    freight_out["published_pairs"] = [
        [float(b), _r(float(c3 - c5), 3), d]
        for d, c3, c5, b in zip(pv.index, pv["C3"], pv["C5"], pv["bci_pts"], strict=True)
    ]
    freight_out["latest_daily"] = {
        "date": ld,
        "cfr_usd_dmt": _r(cfr),
        "share_c5": _r(c5_dmt / cfr, 4),
        "share_c3": _r(c3_dmt / cfr, 4),
        "netback_gap_usd_dmt": _r(c3_dmt - c5_dmt),
    }
    freight_out["anchor_rows"] = len(pd.read_csv(ROOT / "data" / "anchors" / "freight_routes.csv"))
    sizes["freight"] = _write("freight", _clean(freight_out))

    # Mill margin -----------------------------------------------------------------
    mm = mill[mill.index >= pd.Timestamp("2014-01-01")]
    mmm = mm.resample("ME").mean(numeric_only=True)
    mill_out = {
        "daily": {
            "rebar": series(mm, "rebar_margin_ma_rmb_t", 1),
            "hrc": series(mm, "hrc_margin_ma_rmb_t", 1),
            "rebar_sm": series(mm, "rebar_margin_sm_rmb_t", 1),
            "hrc_sm": series(mm, "hrc_margin_sm_rmb_t", 1),
        },
        "monthly": {
            "months": [str(i)[:7] for i in mmm.index],
            "ore": [_r(v, 1) for v in mmm["ore_cost_rmb_t"]],
            "coke": [_r(v, 1) for v in mmm["coke_cost_rmb_t"]],
            "other": [_r(v, 1) for v in mmm["other_cost_rmb_t"]],
            "rebar": [_r(v, 1) for v in mmm["rb_ma_rmb_t"]],
            "margin": [_r(v, 1) for v in mmm["rebar_margin_ma_rmb_t"]],
            "hrc": [_r(v, 1) for v in mmm["hc_ma_rmb_t"]],
            "margin_hrc": [_r(v, 1) for v in mmm["hrc_margin_ma_rmb_t"]],
        },
        "test_rebar": a["mill_test_rebar"],
        "test_hrc": a["mill_test_hrc"],
        "sensitivity": a["mill_sensitivity"],
        "params": {
            k: p[k]
            for k in ["mill_ore_coef", "mill_coke_coef", "mill_other_costs_rebar", "mill_other_costs_hrc_premium"]
        },
        "latest": {
            "date": mill_date,
            "rebar": _r(float(mill_last["rebar_margin_ma_rmb_t"]), 1),
            "hrc": _r(float(mill_last["hrc_margin_ma_rmb_t"]), 1),
            "contracts": {k: str(mill_last[f"{k}_ma_contract"]) for k in ["rb", "hc", "i", "j"]},
        },
    }
    sizes["mill"] = _write("mill", _clean(mill_out))

    # Calculator defaults ------------------------------------------------------------
    calc = {
        "defaults": {
            "date": ld,
            "cfrUsdDmt": _r(cfr, 4),
            "usdcny": _r(fx, 4),
            "vat": bridge["vat_rate"],
            "portRmbWmt": p["port_charges_rmb_wmt"]["value"],
            "moisture": moist,
            "usdRatePct": _r(float(last["usd_rate_pct"]), 3),
            "spreadBp": p["financing_spread_bp"]["value"],
            "dce62RmbDmt": _r(float(last["dce62_rmb_dmt"]), 4),
            "band": band,
        },
        "routes": {
            code: {
                "label": label,
                "freightUsdWmt": _r(float(last[f"{code.lower()}_model_usd_wmt"]), 4),
                "financingDays": _r(
                    float(a["freight"]["voyages"][code]["laden_days"] + p["financing_extra_days"]["value"]), 2
                ),
            }
            for code, label in [("C5", "C5 West Australia"), ("C3", "C3 Tubarao, Brazil")]
        },
        "vat_schedule": [[d.isoformat(), r] for d, r in SCHEDULE],
        "params": p,
    }
    sizes["calculator"] = _write("calculator", _clean(calc))

    # Method and data ---------------------------------------------------------------
    xs = pd.read_csv(DERIVED / "dce_x_schedule.csv")
    checks = json.loads((DERIVED / "cross_checks.json").read_text()) if (DERIVED / "cross_checks.json").exists() else []
    method = {
        "params": p,
        "vessel": VESSEL,
        "x_schedule": xs.to_dict(orient="records"),
        "vat_schedule": [[d.isoformat(), r] for d, r in SCHEDULE],
        "sources": meta["sources"],
        "anchors": a["anchors"],
        "freight_eval": a["freight"]["evaluation"],
        "freight_anchors": a["freight"]["anchors"],
        "tc_calibration": a["freight"]["tc_calibration"],
        "bunker_calibration": a["freight"]["bunker_calibration"],
        "cross_checks": checks,
        "tolerance": TOLERANCE,
        "daily_sensitivity": a["daily_sensitivity"],
        "curve_robustness": {k: v for k, v in a["curve_robustness"].items() if k != "daily_open_runs"},
        "sgx_basis": a["sgx_basis"],
        "cm_methods": curve.groupby(curve.index.year)["cm45_method"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
        .rename(columns={"date": "year"})
        .to_dict(orient="records"),
    }
    sizes["method"] = _write("method", _clean(method))

    # Long view (D050 to D054) ----------------------------------------------------------
    sizes["history"] = _write("history", _clean(history_block(a)))

    # CSV downloads -------------------------------------------------------------------
    DL.mkdir(parents=True, exist_ok=True)
    files = {
        "import_margin_daily.csv": daily,
        "import_margin_monthly.csv": monthly,
        "freight_modeled_daily.csv": freight,
        "mill_margin_daily.csv": mill,
        "dce_iron_ore_curve_daily.csv": curve,
    }
    listing = []
    for name, df in files.items():
        df.to_csv(DL / name, float_format="%.4f")
        listing.append(
            {
                "file": name,
                "title": DOWNLOAD_TEXT[name][0],
                "description": DOWNLOAD_TEXT[name][1],
                "rows": len(df),
                "columns": list(df.columns),
                "first": str(df.index[0])[:10],
                "last": str(df.index[-1])[:10],
                "bytes": (DL / name).stat().st_size,
            }
        )
    for extra, src in [
        ("dce_x_schedule.csv", DERIVED / "dce_x_schedule.csv"),
        ("china_iron_ore_imports_monthly.csv", DERIVED / "china_iron_ore_imports_monthly.csv"),
        ("iron_ore_price_long_monthly.csv", DERIVED / "iron_ore_price_long_monthly.csv"),
        ("landed_cost_long_monthly.csv", DERIVED / "landed_cost_long_monthly.csv"),
        ("china_iron_ore_imports_by_origin_annual.csv", DERIVED / "china_iron_ore_imports_by_origin_annual.csv"),
        ("baltic_indices_monthly.csv", DL / "baltic_indices_monthly.csv"),
        ("anchors_import_cost.csv", ROOT / "data" / "anchors" / "ruida_reports.csv"),
        ("anchors_port_price.csv", ROOT / "data" / "anchors" / "fastmarkets_port.csv"),
        ("anchors_mill_margin.csv", ROOT / "data" / "anchors" / "mill_margin.csv"),
        ("anchors_freight_routes.csv", ROOT / "data" / "anchors" / "freight_routes.csv"),
        ("anchors_bci_tc_pairs.csv", ROOT / "data" / "anchors" / "bci_tc_pairs.csv"),
        ("anchors_bunker_prices.csv", ROOT / "data" / "anchors" / "bunker_prices.csv"),
    ]:
        (DL / extra).write_bytes(src.read_bytes())
        df = pd.read_csv(src)
        listing.append(
            {
                "file": extra,
                "title": DOWNLOAD_TEXT[extra][0],
                "description": DOWNLOAD_TEXT[extra][1],
                "rows": len(df),
                "columns": list(df.columns),
                "first": None,
                "last": None,
                "bytes": src.stat().st_size,
            }
        )
    pdf = DL / "Iron-Ore-China-Import-Arbitrage-Research-Note.pdf"
    sizes["downloads"] = _write(
        "downloads",
        {
            "files": listing,
            "note": pdf.name if pdf.exists() else None,
            "note_bytes": pdf.stat().st_size if pdf.exists() else None,
        },
    )
    return {k: f"{v / 1024:.0f} KB" for k, v in sizes.items()}
