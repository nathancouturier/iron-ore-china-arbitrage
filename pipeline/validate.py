"""Validation stage: schema and unit checks plus cross-source comparisons.

Writes ``data/cache/cross_checks.json`` (rendered into ``data/AUDIT.md``) and
raises if a hard check fails.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .ingest import dce, eastmoney, fred, gacc, safe, sgx, shfe, sina, worldbank

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "derived" / "cross_checks.json"


class ValidationError(RuntimeError):
    pass


def _agreement(a: pd.DataFrame, b: pd.DataFrame, label_a: str, label_b: str, by_year: bool = True) -> list[dict]:
    m = a.merge(b, on=["product", "contract", "date"], suffixes=("_a", "_b"))
    m = m[(m["volume_a"] > 0) & m["settle_b"].notna() & (m["settle_b"] > 0)]
    m["year"] = m["date"].dt.year
    rows = []
    for (prod, yr), g in m.groupby(["product", "year"]):
        rows.append(
            {
                "product": prod,
                "year": int(yr),
                "rows": len(g),
                "settle_identical": round(float((g["settle_a"] - g["settle_b"]).abs().lt(1e-9).mean()), 4),
                "close_identical": round(float((g["close_a"] - g["close_b"]).abs().lt(1e-9).mean()), 4),
                f"oi_ratio_{label_b}_to_{label_a}": round(
                    float((g["oi_b"] / g["oi_a"].replace(0, np.nan)).median()), 3
                ),
            }
        )
    return rows


def checks() -> list[dict]:
    out: list[dict] = []
    # 1. DCE official vs Sina
    off = dce.read_panel(("I", "J", "JM"))
    sn = sina.read_all(("I", "J", "JM"))
    rows = _agreement(off, sn, "dce", "sina")
    out.append(
        {
            "title": "DCE official files against Sina (I, J, JM), liquid contract-days",
            "text": (
                "Share of contract-days with identical settlement and close, by product and year, and the median "
                "ratio of Sina to DCE open interest. DCE annual files report double-sided open interest; Sina "
                "switches to single-sided from 2020 (ratio 0.5). Sina stores missing settlements as 0 (most of "
                "February to July 2020), hence the lower 2020 settlement agreement. Pipeline: DCE files to "
                "2024-12-31, Sina from 2025-01-01."
            ),
            "table": rows,
        }
    )
    # 2. SHFE official vs Sina
    sh = shfe.read_panel()
    if not sh.empty:
        rows = _agreement(sh, sina.read_all(("RB", "HC")), "shfe", "sina")
        out.append(
            {
                "title": "SHFE official daily files against Sina (RB, HC), liquid contract-days",
                "text": (
                    "Same comparison for rebar and hot-rolled coil. SHFE files report open interest as published at "
                    "the time: double-sided to 31 December 2019, single-sided from 2 January 2020 (total rebar open "
                    "interest falls from 3.58 million to 1.75 million lots overnight); the pipeline halves pre-2020 values."
                ),
                "table": rows,
            }
        )
    # 3. SGX final settlement vs IMF and World Bank
    fef = sgx.read_fef().dropna(subset=["settle"])
    fef["dm"] = fef["date"].dt.strftime("%Y-%m")
    own = fef[fef["month"] == fef["dm"]].sort_values("date")
    final = own.groupby("month").tail(1).set_index("month")["settle"]
    imf = fred.read("PIORECRUSDM").assign(m=lambda d: d["date"].dt.strftime("%Y-%m")).set_index("m")["value"]
    wb = worldbank.read().assign(m=lambda d: d["date"].dt.strftime("%Y-%m")).set_index("m")["value"]
    cmp = pd.DataFrame({"sgx": final, "imf": imf, "wb": wb}).dropna()
    cmp["year"] = cmp.index.str[:4].astype(int)
    tab = []
    for yr, g in cmp.groupby("year"):
        tab.append(
            {
                "year": int(yr),
                "months": len(g),
                "sgx_minus_imf_mean": round(float((g["sgx"] - g["imf"]).mean()), 2),
                "sgx_minus_wb_mean": round(float((g["sgx"] - g["wb"]).mean()), 2),
                "imf_minus_wb_mean": round(float((g["imf"] - g["wb"]).mean()), 2),
                "imf_minus_wb_max_abs": round(float((g["imf"] - g["wb"]).abs().max()), 2),
            }
        )
    out.append(
        {
            "title": "Monthly 62% CFR: SGX final settlement, IMF (FRED) and World Bank Pink Sheet",
            "text": (
                "USD per dry tonne. SGX iron ore futures settle on the monthly average of the index: TSI 62% Fe "
                "for contract months to December 2025, Platts IODEX (61% Fe basis from 2 January 2026) from "
                "January 2026, so the 2026 rows measure the 62/61 basis spread."
            ),
            "table": tab,
        }
    )
    # 4. FX: noon buying rate vs central parity
    fx = fred.read("DEXCHUS").dropna().set_index("date")["value"]
    cp = safe.read().set_index("date")["usdcny_cp"]
    j = pd.concat([fx.rename("dexchus"), cp], axis=1).dropna()
    j["diff"] = j["dexchus"] - j["usdcny_cp"]
    tab = [
        {
            "year": int(y),
            "days": len(g),
            "mean_diff": round(float(g["diff"].mean()), 4),
            "max_abs_diff": round(float(g["diff"].abs().max()), 4),
        }
        for y, g in j.groupby(j.index.year)
    ]
    out.append(
        {
            "title": "USD/CNY: FRED DEXCHUS (New York noon) against the PBoC central parity",
            "text": "CNY per USD; DEXCHUS minus central parity on common days.",
            "table": tab,
        }
    )
    # 5. BCI spot checks against published values
    bci = eastmoney.read("bci").set_index("date")["value"]
    spots = [
        ("2016-01-29", 211, "Splash247: BCI 211 on 29 January 2016, then a record low"),
        ("2026-07-03", 4100, "Hellenic Shipping News week 27 2026: BCI 4,100"),
    ]
    tab = [
        {"date": d, "published": v, "east_money": int(bci.get(pd.Timestamp(d), -9999)), "source": s}
        for d, v, s in spots
    ]
    for r in tab:
        if r["published"] != r["east_money"]:
            raise ValidationError(f"BCI spot check failed: {r}")
    out.append(
        {"title": "BCI spot checks", "text": "East Money BCI against index values quoted in the press.", "table": tab}
    )
    out.append(gacc_check())
    return out


GACC_TITLE = "China Customs imports: sum of the monthly bulletins against the year total"


def gacc_check(previous: dict | None = None) -> dict:
    """Months as first published (derived series) against the January to
    December total of each cached December bulletin; years whose December
    bulletin is not cached keep their row from ``previous``."""
    imp = pd.read_csv(ROOT / "data" / "derived" / "china_iron_ore_imports_monthly.csv", dtype={"start": str})
    rows = {r["year"]: r for r in (previous or {}).get("table", [])}
    for y, total in gacc.year_totals().items():
        s = float(imp.loc[imp["start"].str[:4] == str(y), "imports_mt"].sum())
        diff = 100.0 * (s / total - 1.0)
        if abs(diff) > 1.0:
            raise ValidationError(f"China Customs {y}: months sum to {s:.2f} Mt against a year total of {total:.2f}")
        rows[y] = {
            "year": y,
            "monthly_sum_mt": round(s, 2),
            "year_total_mt": round(total, 2),
            "diff_pct": round(diff, 3),
        }
    if not rows:
        raise FileNotFoundError("no December bulletin cached")
    return {
        "title": GACC_TITLE,
        "text": (
            "Iron ores and concentrates, million tonnes. Monthly figures as first published (September and October "
            "2024 from the preliminary release) against the January to December total in each December bulletin, "
            "which carries later revisions."
        ),
        "table": [rows[y] for y in sorted(rows)],
    }


# Derived files in long form, keyed by more than the date
LONG_FORM_KEYS = {
    "sgx_fef_curve_daily.csv": ["date", "months_ahead"],
    "mill_anchor_prices.csv": ["date", "contract"],
}


def schema_checks() -> None:
    """Hard checks on derived files: one row per key (the date, or the date and
    contract for long-form files)."""
    derived = ROOT / "data" / "derived"
    for path in derived.glob("*.csv"):
        df = pd.read_csv(path)
        if "date" not in df.columns:
            continue
        key = LONG_FORM_KEYS.get(path.name, ["date"])
        if df.duplicated(subset=key).any():
            raise ValidationError(f"{path.name}: duplicate rows for key {key}")
    imports = derived / "china_iron_ore_imports_monthly.csv"
    if imports.exists():
        df = pd.read_csv(imports, dtype={"start": str, "end": str})
        months = [str(m) for s, e in zip(df["start"], df["end"], strict=True) for m in pd.period_range(s, e, freq="M")]
        if len(months) != len(set(months)):
            raise ValidationError(f"{imports.name}: overlapping periods")
        if (df["imports_mt"] <= 0).any():
            raise ValidationError(f"{imports.name}: non-positive imports")


def run() -> dict[str, str]:
    """Cross-source checks need the raw exchange files, which only a full
    rebuild has; otherwise the committed results are kept and only the schema
    checks run."""
    schema_checks()
    try:
        res = checks()
    except (FileNotFoundError, ValueError, KeyError, ImportError) as exc:
        prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
        old = next((c for c in prev if c["title"] == GACC_TITLE), None)
        try:
            g = gacc_check(old)
        except (FileNotFoundError, KeyError):
            return {"validate": f"cross-checks kept from last full rebuild ({type(exc).__name__})"}
        res = [c for c in prev if c["title"] != GACC_TITLE] + [g]
        OUT.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
        return {
            "validate": f"cross-checks kept from last full rebuild ({type(exc).__name__}); China Customs check updated"
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    return {"validate": f"{len(res)} cross-checks written"}
