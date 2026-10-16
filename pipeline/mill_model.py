"""Futures-implied steel mill margins and the pre-registered test.

Rebar margin = RB - 1.6 x I - 0.5 x J - other costs (RMB per tonne of steel),
HRC margin = HC - 1.6 x I - 0.5 x J - (other costs + HRC premium), on day-session
closing prices. Two versions:
- most active: each product's most-active contract (previous day's open interest)
- same month: January or May contracts of all four products (see transform)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ironarb import margins, stats
from ironarb.params import PARAMS

from . import inputs


def mill_margins(
    ore_coef: float | None = None,
    coke_coef: float | None = None,
    other_rebar: float | None = None,
    hrc_premium: float | None = None,
) -> pd.DataFrame:
    ore_coef = PARAMS["mill_ore_coef"]["value"] if ore_coef is None else ore_coef
    coke_coef = PARAMS["mill_coke_coef"]["value"] if coke_coef is None else coke_coef
    other = PARAMS["mill_other_costs_rebar"]["value"] if other_rebar is None else other_rebar
    prem = PARAMS["mill_other_costs_hrc_premium"]["value"] if hrc_premium is None else hrc_premium
    f = inputs.mill_daily()
    out = pd.DataFrame(index=f.index)
    out["rb_ma_rmb_t"] = f["rb_ma_close"]
    out["hc_ma_rmb_t"] = f["hc_ma_close"]
    out["i_ma_rmb_t"] = f["i_ma_close"]
    out["j_ma_rmb_t"] = f["j_ma_close"]
    out["ore_cost_rmb_t"] = ore_coef * f["i_ma_close"]
    out["coke_cost_rmb_t"] = coke_coef * f["j_ma_close"]
    out["other_cost_rmb_t"] = other
    out["rebar_margin_ma_rmb_t"] = margins.mill_margin(
        f["rb_ma_close"], f["i_ma_close"], f["j_ma_close"], ore_coef, coke_coef, other
    )
    out["hrc_margin_ma_rmb_t"] = margins.mill_margin(
        f["hc_ma_close"], f["i_ma_close"], f["j_ma_close"], ore_coef, coke_coef, other + prem
    )
    out["rebar_margin_sm_rmb_t"] = margins.mill_margin(
        f["rb_sm_close"], f["i_sm_close"], f["j_sm_close"], ore_coef, coke_coef, other
    )
    out["hrc_margin_sm_rmb_t"] = margins.mill_margin(
        f["hc_sm_close"], f["i_sm_close"], f["j_sm_close"], ore_coef, coke_coef, other + prem
    )
    out["sm_month"] = f["sm_month"]
    for c in ["rb_ma_contract", "hc_ma_contract", "i_ma_contract", "j_ma_contract"]:
        out[c] = f[c]
    return out


def bottom_decile_signal(margin: pd.Series, window: int = 756, q: float = 0.10) -> pd.Series:
    """True when the margin is below the q-quantile of the previous ``window`` days."""
    thr = margin.shift(1).rolling(window, min_periods=window).quantile(q)
    sig = margin < thr
    return sig.where(thr.notna())


def forward_log_change(price: pd.Series, h: int) -> pd.Series:
    lp = np.log(price)
    return lp.shift(-h) - lp


def decile_test(margin: pd.Series, ore: pd.Series, horizons: tuple[int, ...] = (21, 42, 63)) -> pd.DataFrame:
    """Pre-registered test: forward Dalian ore change after bottom-decile margins."""
    df = pd.concat([margin.rename("m"), ore.rename("ore")], axis=1).dropna()
    df["sig"] = bottom_decile_signal(df["m"])
    rows = []
    for h in horizons:
        d = df.copy()
        d["fwd"] = forward_log_change(d["ore"], h) * 100.0
        d = d.dropna(subset=["sig", "fwd"])
        flag = d["sig"].astype(bool).to_numpy()
        y = d["fwd"].to_numpy()
        bb = stats.block_bootstrap_diff(y, flag, block=63, n_boot=2000)
        x = np.column_stack([np.ones(len(y)), flag.astype(float)])
        fit = stats.ols(y, x)
        nw = stats.newey_west_se(x, fit.resid, h)
        rows.append(
            {
                "horizon_days": h,
                "n_obs": len(y),
                "n_signal_days": int(flag.sum()),
                "mean_fwd_signal_pct": float(y[flag].mean()),
                "mean_fwd_other_pct": float(y[~flag].mean()),
                "effect_pct": bb["diff"],
                "ci_lo_pct": bb["lo"],
                "ci_hi_pct": bb["hi"],
                "nw_t": float(fit.beta[1] / nw[1]),
                "sample_start": d.index.min().date().isoformat(),
                "sample_end": d.index.max().date().isoformat(),
            }
        )
    return pd.DataFrame(rows)
