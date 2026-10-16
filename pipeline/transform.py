"""Transform raw exchange files into clean daily panels and series.

Outputs (single-sided lots, RMB per tonne):
- futures panel: every contract-day for I, J, JM (DCE), RB, HC (SHFE)
- iron ore curve: constant-maturity prices on a 62% Fe basis, most-active contract
- most-active and same-month series for the mill margin
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ironarb import dce as dce_rules
from ironarb.curve import most_active
from ironarb.curve_build import constant_maturity_series
from ironarb.dce_x import x_by_contract, x_table
from ironarb.params import value

from .ingest import dce, eastmoney, gacc, safe, sgx, shfe, sina

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
DERIVED = ROOT / "data" / "derived"
DCE_LAST_OFFICIAL = pd.Timestamp("2024-12-31")
SINGLE_SIDED_FROM = pd.Timestamp("2020-01-01")
# Statutory holidays fixed by law that fall after the data end (used only to
# estimate expiries of contracts that have not expired yet).
SGX_MONTHS_AHEAD = 4  # current month plus the next four contract months
FUTURE_HOLIDAYS = ["2027-01-01", "2027-05-01", "2027-10-01"]
FIRST_DATE = pd.Timestamp("2013-10-18")  # first day of DCE iron ore trading


def _sina_single_sided(df: pd.DataFrame) -> pd.DataFrame:
    df = df.astype({"volume": float, "oi": float, "settle": float, "close": float})
    pre = df["date"] < SINGLE_SIDED_FROM
    df.loc[pre, "volume"] = df.loc[pre, "volume"] / 2.0
    df.loc[pre, "oi"] = df.loc[pre, "oi"] / 2.0
    df["settle"] = df["settle"].where(df["settle"] > 0)
    return df


def has_dce_history() -> bool:
    return (dce.DIR / "index.json").exists()


def futures_panel() -> pd.DataFrame:
    """Merge official exchange files with Sina, normalized to single-sided lots."""
    frames = []
    # DCE: official annual files to 2024 (when cached), Sina from 2025.
    if has_dce_history():
        off = dce.read_panel(("I", "J", "JM"))
        off = off.astype({"volume": float, "oi": float, "settle": float, "close": float})
        off = off.assign(volume=off["volume"] / 2.0, oi=off["oi"] / 2.0, source="dce_official")
        frames.append(off[["product", "contract", "date", "settle", "close", "volume", "oi", "source"]])
    sn = _sina_single_sided(sina.read_all(("I", "J", "JM", "RB", "HC")))
    dce_recent = sn[sn["product"].isin(["I", "J", "JM"]) & (sn["date"] > DCE_LAST_OFFICIAL)]
    frames.append(dce_recent.assign(source="sina"))
    # SHFE: official daily files where cached, Sina for days not covered.
    sh = shfe.read_panel()
    if not sh.empty:
        sh = sh.astype({"volume": float, "oi": float, "settle": float, "close": float})
        pre = sh["date"] < SINGLE_SIDED_FROM
        sh.loc[pre, "volume"] = sh.loc[pre, "volume"] / 2.0
        sh.loc[pre, "oi"] = sh.loc[pre, "oi"] / 2.0
        sh["source"] = "shfe_official"
        frames.append(sh[["product", "contract", "date", "settle", "close", "volume", "oi", "source"]])
        covered = set(sh["date"].unique())
    else:
        covered = set()
    sn_shfe = sn[sn["product"].isin(["RB", "HC"]) & ~sn["date"].isin(covered)]
    frames.append(sn_shfe.assign(source="sina"))
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.drop_duplicates(["contract", "date"], keep="first")
    return panel.sort_values(["product", "date", "contract"]).reset_index(drop=True)


def trading_calendar(panel: pd.DataFrame, until: pd.Timestamp) -> pd.DatetimeIndex:
    observed = pd.DatetimeIndex(np.sort(panel.loc[panel["product"] == "I", "date"].unique()))
    return dce_rules.extend_calendar(observed, until, FUTURE_HOLIDAYS)


def add_expiry(panel: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    exp = dce_rules.expiry_dates(sorted(panel["contract"].unique()), calendar)
    out = panel.copy()
    out["expiry"] = out["contract"].map(exp)
    out["dte"] = (out["expiry"] - out["date"]).dt.days
    return out[out["dte"] >= 0]


def x_schedule(iron: pd.DataFrame) -> dict[str, float]:
    """X (RMB per 0.1% Fe) for each 61% Fe contract (see ``ironarb.dce_x``).

    Values that cannot be recomputed from the available history (incremental
    refresh) are taken from the committed table ``dce_x_by_contract.csv``."""
    xmap = x_by_contract(iron)
    snap = DERIVED / "dce_x_by_contract.csv"
    if snap.exists():
        old = pd.read_csv(snap).set_index("contract")["x_rmb_per_0_1pct"].to_dict()
        for k, v in old.items():
            xmap.setdefault(k, float(v))
    return xmap


def iron_ore_curve(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily constant-maturity curve (62% basis) and most-active contract."""
    iron = panel[panel["product"] == "I"].copy()
    cal = trading_calendar(panel, iron["date"].max() + pd.Timedelta(days=500))
    iron = add_expiry(iron, cal)
    xmap = x_schedule(iron)
    iron["x"] = iron["contract"].map(xmap).fillna(0.0)
    iron["std_fe"] = iron["contract"].map(dce_rules.standard_fe)
    iron["grade_adj"] = np.where(iron["std_fe"] == 61.0, 10.0 * iron["x"], 0.0)
    iron["price"] = iron["settle"].fillna(iron["close"])
    iron["price62"] = iron["price"] + iron["grade_adj"]
    targets = [30, 45, 60, 90]
    cm = constant_maturity_series(
        iron,
        targets,
        min_oi=value("cm_min_oi_lots"),
        min_share=0.0,
        min_days=value("cm_min_days"),
        max_extrap_gap=value("cm_max_extrapolation_days"),
    )
    wide = cm.pivot(index="date", columns="target_days", values="value")
    wide.columns = [f"dce_i_cm{int(t)}_rmb_dmt" for t in wide.columns]
    # Robustness variant (not the default): contracts in their delivery month
    # excluded, so the curve never leans on an expiring contract (decision log D032).
    in_delivery_month = iron["date"].dt.to_period("M") >= iron["expiry"].dt.to_period("M")
    cmx = constant_maturity_series(
        iron[~in_delivery_month],
        [45],
        min_oi=value("cm_min_oi_lots"),
        min_share=0.0,
        min_days=value("cm_min_days"),
        max_extrap_gap=value("cm_max_extrapolation_days"),
    )
    wide["dce_i_cm45_exdm_rmb_dmt"] = cmx.set_index("date")["value"]
    meth = cm.pivot(index="date", columns="target_days", values="method")
    meth.columns = [f"cm{int(t)}_method" for t in meth.columns]
    c45 = cm[cm["target_days"] == 45].set_index("date")[["near", "far", "near_days", "far_days"]]
    c45.columns = ["cm45_near", "cm45_far", "cm45_near_days", "cm45_far_days"]
    ma = most_active(iron[["date", "contract", "oi", "price", "price62", "dte", "grade_adj", "volume"]])
    ma = ma.set_index("date").rename(
        columns={
            "contract": "dce_i_ma_contract",
            "price": "dce_i_ma_rmb_dmt",
            "price62": "dce_i_ma62_rmb_dmt",
            "dte": "dce_i_ma_dte_days",
            "grade_adj": "dce_i_ma_grade_adj_rmb",
            "oi": "dce_i_ma_oi_lots",
            "volume": "dce_i_ma_volume_lots",
        }
    )
    curve = wide.join(meth).join(c45).join(ma, how="left")
    curve["dce_i_total_oi_lots"] = iron.groupby("date")["oi"].sum()
    curve.index.name = "date"
    return curve.reset_index(), iron


def most_active_prices(panel: pd.DataFrame, product: str) -> pd.DataFrame:
    sub = panel[panel["product"] == product][["date", "contract", "oi", "settle", "close"]].copy()
    sub["price"] = sub["close"]
    ma = most_active(sub)
    return ma[["date", "contract", "price", "settle"]].rename(
        columns={
            "contract": f"{product.lower()}_ma_contract",
            "price": f"{product.lower()}_ma_close",
            "settle": f"{product.lower()}_ma_settle",
        }
    )


def same_month_prices(panel: pd.DataFrame) -> pd.DataFrame:
    """Same delivery month for RB, HC, I and J, using the January and May
    contracts (the delivery months that are liquid on all four). On each day the
    month is the one of the two with the larger iron ore open interest on the
    previous trading day."""
    sub = panel[panel["product"].isin(["RB", "HC", "I", "J"])].copy()
    sub["ym"] = sub["contract"].str[-4:]
    sub = sub[sub["ym"].str[-2:].isin(["01", "05"])]
    iron = sub[sub["product"] == "I"][["date", "ym", "oi"]]
    dates = np.sort(iron["date"].unique())
    leader = iron.loc[iron.groupby("date")["oi"].idxmax()].set_index("date")["ym"]
    prev = pd.Series(leader.reindex(dates).shift(1).values, index=dates).dropna()
    rows = pd.DataFrame({"date": prev.index, "ym": prev.values})
    wide = sub.pivot_table(index=["date", "ym"], columns="product", values="close").reset_index()
    out = rows.merge(wide, on=["date", "ym"], how="left")
    out = out.rename(
        columns={"RB": "rb_sm_close", "HC": "hc_sm_close", "I": "i_sm_close", "J": "j_sm_close", "ym": "sm_month"}
    )
    return out


def merge_snapshot(new: pd.DataFrame, path: Path, recompute_from: pd.Timestamp | None) -> pd.DataFrame:
    """Keep committed rows before ``recompute_from`` and replace the rest with
    freshly computed rows. ``recompute_from=None`` replaces everything."""
    if recompute_from is None or not path.exists():
        return new
    old = pd.read_csv(path, parse_dates=["date"])
    keep = old[old["date"] < recompute_from]
    fresh = new[new["date"] >= recompute_from]
    return pd.concat([keep, fresh], ignore_index=True).sort_values("date").reset_index(drop=True)


def recompute_start(panel: pd.DataFrame) -> pd.Timestamp | None:
    """Full history when the DCE annual files are cached; otherwise only dates
    for which every listed contract is in the refreshed set (about 12 months)."""
    if has_dce_history():
        return None
    first = panel.loc[panel["product"] == "I", "date"].min()
    return first + pd.DateOffset(months=13)


def mill_anchor_prices(panel: pd.DataFrame) -> None:
    """Closing prices of the contracts quoted by the broker anchors, kept as a
    small committed extract so the anchor tests run without raw files."""
    path = DERIVED / "mill_anchor_prices.csv"
    an = pd.read_csv(ROOT / "data" / "anchors" / "mill_margin.csv", parse_dates=["date"])
    keys = {
        (c, d)
        for _, r in an.iterrows()
        for c in (r["rb_contract"], r["i_contract"], r["j_contract"])
        for d in [r["date"]]
    }
    sub = panel[[(c, d) in keys for c, d in zip(panel["contract"], panel["date"], strict=True)]]
    sub = sub[["date", "contract", "close", "settle", "source"]].sort_values(["date", "contract"])
    if len(sub) == len(keys) or not path.exists():
        sub.to_csv(path, index=False)


def futures_series(panel: pd.DataFrame, cutoff: pd.Timestamp | None) -> dict[str, str]:
    mill_anchor_prices(panel)
    curve, iron = iron_ore_curve(panel)
    iron.to_csv(CACHE / "iron_ore_contracts.csv.gz", index=False)
    curve = merge_snapshot(curve, DERIVED / "dce_iron_ore_curve_daily.csv", cutoff)
    curve.to_csv(DERIVED / "dce_iron_ore_curve_daily.csv", index=False, float_format="%.4f")
    xt = pd.DataFrame(sorted(x_schedule(iron).items()), columns=["contract", "x_rmb_per_0_1pct"])
    xt.to_csv(DERIVED / "dce_x_by_contract.csv", index=False)
    if has_dce_history():
        x_table(iron).to_csv(DERIVED / "dce_x_schedule.csv", index=False)
    mill = None
    for p in ["RB", "HC", "I", "J", "JM"]:
        ma = most_active_prices(panel, p)
        mill = ma if mill is None else mill.merge(ma, on="date", how="outer")
    mill = mill.merge(same_month_prices(panel), on="date", how="left")
    mill = mill[mill["date"] >= FIRST_DATE]
    mill = merge_snapshot(mill.sort_values("date"), DERIVED / "futures_mill_daily.csv", cutoff)
    mill.to_csv(DERIVED / "futures_mill_daily.csv", index=False, float_format="%.4f")
    return {
        "curve_days": str(len(curve)),
        "curve_range": f"{curve['date'].min().date()} to {curve['date'].max().date()}",
        "mode": "full" if cutoff is None else f"incremental from {cutoff.date()}",
    }


def sgx_series() -> dict[str, str]:
    """Daily SGX iron ore settlements for the current month and the next four
    contract months (long form), merged with the committed snapshot. The daily
    CFR proxy is built from these in ``pipeline.margin_model``."""
    path = DERIVED / "sgx_fef_curve_daily.csv"
    if not (sgx.DIR / "zip").exists():
        return {"sgx": "no raw files; snapshot kept"}
    f = sgx.read_fef().dropna(subset=["settle"])
    ahead = pd.PeriodIndex(f["month"], freq="M") - pd.PeriodIndex(f["date"].dt.strftime("%Y-%m"), freq="M")
    f["months_ahead"] = [x.n for x in ahead]
    f = f[f["months_ahead"].between(0, SGX_MONTHS_AHEAD)]
    # settlements only: volume and open interest are not used and not republished
    cols = ["date", "contract_month", "months_ahead", "settle_usd_dmt", "file_id"]
    curve = f.rename(columns={"month": "contract_month", "settle": "settle_usd_dmt"})[cols]
    cutoff = None if f["date"].min() <= pd.Timestamp("2016-01-05") else f["date"].min()
    curve = merge_snapshot(curve.sort_values(["date", "months_ahead"]), path, cutoff)[cols]
    curve = curve.sort_values(["date", "months_ahead"]).reset_index(drop=True)
    curve.to_csv(path, index=False)
    return {"sgx": f"{curve['date'].nunique()} days to {curve['date'].max().date()}"}


def baltic_series() -> dict[str, str]:
    path = DERIVED / "baltic_indices_daily.csv"
    try:
        bci = eastmoney.read("bci").rename(columns={"value": "bci_pts"})
        bdi = eastmoney.read("bdi").rename(columns={"value": "bdi_pts"})
    except FileNotFoundError:
        return {"baltic": "no raw files; snapshot kept"}
    df = bdi.merge(bci, on="date", how="outer").sort_values("date")
    df = df[df["date"] >= pd.Timestamp("2008-01-01")]
    df.to_csv(path, index=False)
    return {"baltic": f"{len(df)} days to {df['date'].max().date()}"}


def central_parity_series() -> dict[str, str]:
    path = DERIVED / "usdcny_central_parity_daily.csv"
    try:
        cp = safe.read()
    except (FileNotFoundError, ValueError):
        return {"central_parity": "no raw files; snapshot kept"}
    cutoff = None if cp["date"].min() <= pd.Timestamp("2013-01-31") else cp["date"].min()
    cp = merge_snapshot(cp, path, cutoff)
    cp.to_csv(path, index=False, float_format="%.4f")
    return {"central_parity": f"{len(cp)} days to {cp['date'].max().date()}"}


def imports_series() -> dict[str, str]:
    """China Customs monthly iron ore imports. Newly parsed periods replace the
    snapshot (a final table replaces a preliminary value); older periods are kept."""
    path = DERIVED / "china_iron_ore_imports_monthly.csv"
    try:
        new = gacc.read()
    except (FileNotFoundError, ValueError):
        return {"imports": "no raw files; snapshot kept"}
    if path.exists():
        old = pd.read_csv(path, dtype={"start": str, "end": str})
        covered = {m for s, e in zip(new["start"], new["end"], strict=True) for m in _months(s, e)}
        keep = old[[not (set(_months(s, e)) & covered) for s, e in zip(old["start"], old["end"], strict=True)]]
        new = pd.concat([keep, new]).sort_values("start")
    new.to_csv(path, index=False, float_format="%.3f")
    return {"imports": f"{len(new)} periods to {new['end'].max()}"}


def _months(start: str, end: str) -> list[str]:
    return [str(p) for p in pd.period_range(start, end, freq="M")]


def run() -> dict[str, str]:
    CACHE.mkdir(parents=True, exist_ok=True)
    DERIVED.mkdir(parents=True, exist_ok=True)
    panel = futures_panel()
    panel.to_csv(CACHE / "futures_panel.csv.gz", index=False)
    status = futures_series(panel, recompute_start(panel))
    status.update(sgx_series())
    status.update(baltic_series())
    status.update(central_parity_series())
    status.update(imports_series())
    return status
