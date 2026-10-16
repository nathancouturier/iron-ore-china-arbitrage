"""Modeled Capesize freight for C3 (Tubarao to Qingdao) and C5 (West Australia to
Qingdao). Route assessments are paid data, so two transparent estimates are
built from public inputs and scored on dated public anchors:

(a) voyage model: time charter equivalent from the Baltic Capesize Index
    (BCI points to Capesize T/C average USD/day, calibrated on dated public
    pairs by regime) and bunker price from Brent (calibrated on dated public
    Singapore bunker prices, separately before and after IMO 2020), fed through
    ``ironarb.voyage``. Not fitted to route anchors, so every anchor is out of
    sample.
(b) statistical map: route rate = a + b x BCI + c x Brent, fitted by OLS on the
    route anchors; scored by leave-one-out cross-validation.

Every output is labeled "modeled".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ironarb import stats
from ironarb.voyage import freight_usd_per_t

from . import inputs
from .margin_model import Assumptions, build_voyages

ROOT = Path(__file__).resolve().parents[1]
ANCHORS = ROOT / "data" / "anchors"
IMO2020 = pd.Timestamp("2020-01-01")
# BCI to Capesize time charter average, by regime (see the decision log):
# to September 2020 a linear relation with an intercept; from then a fixed ratio
# to the 180,000 dwt 5TC; from 2 January 2026 a fixed ratio to the 182,000 dwt 5TC.
TC_REGIMES = [
    (
        "BCI 2014 basis, linear (to Sep 2020)",
        pd.Timestamp("1999-01-01"),
        pd.Timestamp("2020-09-19"),
        "linear",
        "tc_usd_day",
    ),
    (
        "5TC 180,000 dwt, fixed ratio (Sep 2020 to Dec 2025)",
        pd.Timestamp("2020-09-20"),
        pd.Timestamp("2026-01-01"),
        "ratio",
        "tc_usd_day",
    ),
    (
        "5TC 182,000 dwt, fixed ratio (from Jan 2026)",
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2100-01-01"),
        "ratio",
        "tc182_usd_day",
    ),
]
TC_182_ADJUSTMENT = 3503.0  # Baltic prescribed gap between the 182 and 180 averages


def regime_of(d: pd.Timestamp) -> str:
    for name, a, b, _, _ in TC_REGIMES:
        if a <= d <= b:
            return name
    raise ValueError(d)


@dataclass
class Linear:
    a: float
    b: float
    n: int
    resid_sd: float
    r2: float
    extra: dict[str, Any] = field(default_factory=dict)

    def __call__(self, x):
        return self.a + self.b * np.asarray(x, dtype=float)


def fit_ratio(x: np.ndarray, y: np.ndarray) -> Linear:
    """Least squares through the origin: y = b x."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    b = float((x @ y) / (x @ x))
    resid = y - b * x
    return Linear(0.0, b, len(y), float(np.sqrt((resid**2).sum() / max(len(y) - 1, 1))), float("nan"))


def fit_linear(x: np.ndarray, y: np.ndarray) -> Linear:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    design = np.column_stack([np.ones_like(x), x])
    fit = stats.ols(y, design)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float((fit.resid**2).sum()) / ss_tot if ss_tot > 0 else float("nan")
    return Linear(float(fit.beta[0]), float(fit.beta[1]), len(y), float(np.sqrt(fit.sigma2)), r2)


# Calibration inputs ---------------------------------------------------------------
def load_tc_pairs() -> pd.DataFrame:
    df = pd.read_csv(ANCHORS / "bci_tc_pairs.csv", parse_dates=["date"])
    df["regime"] = df["date"].map(regime_of)
    return df


def load_bunker() -> pd.DataFrame:
    df = pd.read_csv(ANCHORS / "bunker_prices.csv", parse_dates=["date"])
    brent = inputs.brent_daily()
    df["brent_usd_bbl"] = brent.reindex(df["date"]).to_numpy()
    df["era"] = np.where(df["date"] < IMO2020, "HSFO 380 cst (before 2020)", "VLSFO 0.5% S (from 2020)")
    return df


def load_route_anchors() -> pd.DataFrame:
    df = pd.read_csv(ANCHORS / "freight_routes.csv", parse_dates=["date"])
    return df


@dataclass
class Calibration:
    tc: dict[str, Linear]
    bunker: dict[str, Linear]
    tc_pairs: pd.DataFrame
    bunker_points: pd.DataFrame


def calibrate() -> Calibration:
    pairs = load_tc_pairs()
    pairs["tc182_usd_day"] = pairs["tc182_usd_day"].fillna(pairs["tc_usd_day"] + TC_182_ADJUSTMENT)
    tc = {}
    for name, _, _, kind, col in TC_REGIMES:
        g = pairs[pairs["regime"] == name]
        if g.empty:
            continue
        fit = fit_ratio if kind == "ratio" else fit_linear
        tc[name] = fit(g["bci_pts"].to_numpy(), g[col].to_numpy())
        ratio = g[col] / g["bci_pts"]
        tc[name].extra = {
            "kind": kind,
            "tc_basis": "182,000 dwt 5TC" if col == "tc182_usd_day" else "180,000 dwt (4TC/5TC) average",
            "ratio_min": float(ratio.min()),
            "ratio_max": float(ratio.max()),
            "first": str(g["date"].min().date()),
            "last": str(g["date"].max().date()),
        }
    bunk = load_bunker().dropna(subset=["brent_usd_bbl"])
    bunker = {}
    for era, g in bunk.groupby("era"):
        bunker[era] = fit_linear(g["brent_usd_bbl"].to_numpy(), g["price_usd_t"].to_numpy())
    return Calibration(tc, bunker, pairs, bunk)


def tce_proxy(bci: pd.Series, cal: Calibration) -> pd.Series:
    out = pd.Series(np.nan, index=bci.index)
    for name, a, b, _, _ in TC_REGIMES:
        m = (bci.index >= a) & (bci.index <= b)
        key = name if name in cal.tc else _nearest_regime(name, cal)
        out[m] = cal.tc[key](bci[m])
    return out.rename("tce_proxy_usd_day")


def _nearest_regime(name: str, cal: Calibration) -> str:
    order = [r[0] for r in TC_REGIMES]  # nearest calibrated regime
    i = order.index(name)
    for j in sorted(range(len(order)), key=lambda k: abs(k - i)):
        if order[j] in cal.tc:
            return order[j]
    raise KeyError(name)


def bunker_proxy(brent: pd.Series, cal: Calibration) -> pd.Series:
    out = pd.Series(np.nan, index=brent.index)
    pre = brent.index < IMO2020
    out[pre] = cal.bunker["HSFO 380 cst (before 2020)"](brent[pre])
    out[~pre] = cal.bunker["VLSFO 0.5% S (from 2020)"](brent[~pre])
    return out.rename("bunker_proxy_usd_t")


def voyage_model_daily(cal: Calibration, a: Assumptions | None = None) -> pd.DataFrame:
    a = a or Assumptions()
    voy = build_voyages(a)
    bci = inputs.bci_daily()
    brent = inputs.brent_daily()
    idx = bci.index.intersection(brent.index)
    # holidays are bridged by the carry-forward in inputs, but no modeled day
    # goes past the last published BCI
    last_bci = inputs.baltic_daily()["bci_pts"].dropna().index.max()
    idx = idx[(idx >= pd.Timestamp("2014-01-01")) & (idx <= last_bci)]
    df = pd.DataFrame({"bci_pts": bci.reindex(idx), "brent_usd_bbl": brent.reindex(idx)})
    df["tce_proxy_usd_day"] = tce_proxy(df["bci_pts"], cal)
    df["bunker_proxy_usd_t"] = bunker_proxy(df["brent_usd_bbl"], cal)
    for code, v in voy.items():
        df[f"{code.lower()}_voyage_usd_wmt"] = freight_usd_per_t(v, df["tce_proxy_usd_day"], df["bunker_proxy_usd_t"])
    return df


# Scoring --------------------------------------------------------------------------
def score(errors: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    e = np.asarray(errors, dtype=float)
    act = np.asarray(actual, dtype=float)
    rel = e / act
    return {
        "n": len(e),
        "mae": float(np.mean(np.abs(e))),
        "rmse": float(np.sqrt(np.mean(e**2))),
        "bias": float(np.mean(e)),
        "mape": float(np.mean(np.abs(rel))),
        "rel_q10": float(np.quantile(rel, 0.10)) if len(rel) >= 5 else float("nan"),
        "rel_q90": float(np.quantile(rel, 0.90)) if len(rel) >= 5 else float("nan"),
    }


def evaluate(cal: Calibration, daily: pd.DataFrame) -> dict[str, Any]:
    anchors = load_route_anchors()
    out: dict[str, Any] = {"rows": []}
    for route in ["C3", "C5"]:
        an = anchors[anchors["route"] == route].copy()
        # inputs on the anchor date (or the last business day before it)
        feats = daily[["bci_pts", "brent_usd_bbl", f"{route.lower()}_voyage_usd_wmt"]]
        joined = pd.merge_asof(an.sort_values("date"), feats.reset_index().rename(columns={"index": "date"}), on="date")
        joined = joined.dropna(subset=["bci_pts", "brent_usd_bbl"])
        y = joined["value_usd_wmt"].to_numpy()
        voy = joined[f"{route.lower()}_voyage_usd_wmt"].to_numpy()
        # (b) leave-one-out OLS on BCI and Brent
        xmat = np.column_stack([np.ones(len(y)), joined["bci_pts"], joined["brent_usd_bbl"]])
        loo = np.empty(len(y))
        for i in range(len(y)):
            keep = np.arange(len(y)) != i
            beta = stats.ols(y[keep], xmat[keep]).beta
            loo[i] = xmat[i] @ beta
        full = stats.ols(y, xmat)
        joined["voyage_model"] = voy
        joined["stat_model_loo"] = loo
        out[route] = {
            "voyage": score(voy - y, y),
            "stat_loo": score(loo - y, y),
            "stat_coef": {"const": float(full.beta[0]), "bci": float(full.beta[1]), "brent": float(full.beta[2])},
        }
        out["rows"].append(joined.assign(route=route))
    out["rows"] = pd.concat(out["rows"], ignore_index=True)
    return out


def modeled_series(cal: Calibration, ev: dict[str, Any], daily: pd.DataFrame) -> pd.DataFrame:
    """Daily modeled C3 and C5 (both estimates) with 80% error bands from the
    out-of-sample relative errors (10th and 90th percentiles)."""
    out = daily.copy()
    for route in ["C3", "C5"]:
        k = route.lower()
        coef = ev[route]["stat_coef"]
        out[f"{k}_stat_usd_wmt"] = coef["const"] + coef["bci"] * out["bci_pts"] + coef["brent"] * out["brent_usd_bbl"]
        for model, col in [("voyage", f"{k}_voyage_usd_wmt"), ("stat_loo", f"{k}_stat_usd_wmt")]:
            s = ev[route][model]
            # model = actual x (1 + rel)  =>  actual = model / (1 + rel)
            out[f"{col}_lo"] = out[col] / (1.0 + s["rel_q90"])
            out[f"{col}_hi"] = out[col] / (1.0 + s["rel_q10"])
    return out
