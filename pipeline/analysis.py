"""Section 5 analyses on the import margin (pre-registered in the decision log)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from ironarb import stats

from .margin_model import Assumptions, monthly_margin


def window_stats(margin: pd.Series, band: float) -> dict[str, Any]:
    """Shares above, inside and below the band, and run lengths of each state."""
    m = margin.dropna()
    state = np.where(m > band, 1, np.where(m < -band, -1, 0))
    runs = []
    start = 0
    for i in range(1, len(state) + 1):
        if i == len(state) or state[i] != state[start]:
            runs.append(
                {"state": int(state[start]), "start": m.index[start], "end": m.index[i - 1], "length": i - start}
            )
            start = i
    runs_df = pd.DataFrame(runs)

    def mean_len(s: int) -> float:
        r = runs_df[runs_df["state"] == s]
        return float(r["length"].mean()) if len(r) else 0.0

    return {
        "n": len(m),
        "share_open": float(np.mean(state == 1)),
        "share_inside": float(np.mean(state == 0)),
        "share_closed": float(np.mean(state == -1)),
        "n_open_runs": int((runs_df["state"] == 1).sum()),
        "mean_open_run": mean_len(1),
        "n_inside_runs": int((runs_df["state"] == 0).sum()),
        "mean_inside_run": mean_len(0),
        "mean_closed_run": mean_len(-1),
        "mean": float(m.mean()),
        "median": float(m.median()),
        "sd": float(m.std()),
        "p05": float(m.quantile(0.05)),
        "p25": float(m.quantile(0.25)),
        "p75": float(m.quantile(0.75)),
        "p95": float(m.quantile(0.95)),
        "min": float(m.min()),
        "min_at": str(m.idxmin()),
        "max": float(m.max()),
        "max_at": str(m.idxmax()),
        "runs": runs_df,
    }


def largest_deviations(margin: pd.Series, k: int = 3, min_gap: int = 6) -> pd.DataFrame:
    """The k largest absolute deviations from the sample mean, at least
    ``min_gap`` periods apart (one point per episode)."""
    m = margin.dropna()
    dev = (m - m.mean()).abs().sort_values(ascending=False)
    picked: list[Any] = []
    pos = {idx: i for i, idx in enumerate(m.index)}
    for idx in dev.index:
        if all(abs(pos[idx] - pos[p]) >= min_gap for p in picked):
            picked.append(idx)
        if len(picked) == k:
            break
    return pd.DataFrame(
        {
            "period": [str(p) for p in picked],
            "margin": [float(m[p]) for p in picked],
            "deviation": [float(m[p] - m.mean()) for p in picked],
        }
    )


def convergence(margin: pd.Series, n_boot: int = 2000) -> dict[str, Any]:
    x = margin.dropna().to_numpy()
    fit = stats.ar1(x)
    boot = stats.ar1_bootstrap(x, n_boot=n_boot)
    a = stats.adf(x)
    return {
        "n": len(x),
        "rho": fit.rho,
        "rho_se": fit.rho_se,
        "long_run_mean": fit.const / (1 - fit.rho) if fit.rho < 1 else float("nan"),
        "half_life": fit.half_life,
        **{f"boot_{k}": v for k, v in boot.items()},
        "adf_stat": a.stat,
        "adf_p": a.pvalue,
        "adf_lags": a.lags,
        "adf_nobs": a.nobs,
        "adf_crit_5pct": a.crit["5%"],
        "adf_crit_1pct": a.crit["1%"],
    }


def tornado(base: Assumptions | None = None, period: str | None = None) -> pd.DataFrame:
    """Change in the distance of the monthly import margin from the open-window
    threshold (margin minus band; latest month, or ``period``) when one
    assumption moves to its low and high values, all else at defaults. For
    every assumption except the band this equals the change in the margin."""
    base = base or Assumptions()
    ref = monthly_margin(base)
    p = ref.index[-1] if period is None else pd.Period(period, "M")
    m0 = float(ref.loc[p, "margin_rmb_dmt"]) - base.band
    cases = [
        ("Port charges (20 / 40 RMB/wmt)", {"port_rmb_wmt": 20.0}, {"port_rmb_wmt": 40.0}),
        ("Moisture for port charges (6% / 10%)", {"moisture": 0.06}, {"moisture": 0.10}),
        ("Financing spread (50 / 300 bp)", {"spread_bp": 50.0}, {"spread_bp": 300.0}),
        ("Maturity target (30 / 90 days)", {"cm_target": 30}, {"cm_target": 90}),
        ("FX source (PBoC central parity)", {"fx_source": "central_parity"}, None),
        ("Route financing (Brazil, C3)", {"route": "C3"}, None),
        ("No-arbitrage band (15 / 35 RMB/dmt)", {"band": 15.0}, {"band": 35.0}),
    ]
    rows = []
    for label, lo, hi in cases:
        a_lo = replace(base, **lo)
        v_lo = float(monthly_margin(a_lo).loc[p, "margin_rmb_dmt"]) - a_lo.band
        v_hi = float("nan")
        if hi is not None:  # a single alternative has one bar, not a low and a high
            a_hi = replace(base, **hi)
            v_hi = float(monthly_margin(a_hi).loc[p, "margin_rmb_dmt"]) - a_hi.band
        rows.append({"assumption": label, "low": v_lo - m0, "high": v_hi - m0})
    out = pd.DataFrame(rows)
    out.attrs["base_distance"] = m0
    out.attrs["period"] = str(p)
    out["span"] = out[["low", "high"]].abs().max(axis=1)
    return out.sort_values("span", ascending=False).reset_index(drop=True)


def _coverage(imports: pd.DataFrame) -> list[tuple[frozenset[pd.Period], float]]:
    return [
        (frozenset(pd.period_range(s, e, freq="M")), float(v))
        for s, e, v in zip(imports["start"], imports["end"], imports["imports_mt"], strict=True)
    ]


def window_sum(cover: list[tuple[frozenset[pd.Period], float]], months: list[pd.Period]) -> float:
    """Imports over exactly ``months``. NaN when a month is missing or when a
    published period (January and February 2020 together) straddles the edge."""
    need = set(months)
    total, got = 0.0, set()
    for cov, v in cover:
        if cov & need:
            if not cov <= need:
                return float("nan")
            total += v
            got |= cov
    return total if got == need else float("nan")


def import_growth(imports: pd.DataFrame, months: pd.PeriodIndex, h: int) -> pd.Series:
    """Year-on-year log growth (percent) of imports over months t+1..t+h."""
    cover = _coverage(imports)
    out = {}
    for t in months:
        fwd = window_sum(cover, [t + k for k in range(1, h + 1)])
        base = window_sum(cover, [t + k - 12 for k in range(1, h + 1)])
        out[t] = 100.0 * (np.log(fwd) - np.log(base)) if fwd > 0 and base > 0 else np.nan
    return pd.Series(out, dtype=float)


def imports_test(
    margin: pd.Series,
    imports: pd.DataFrame,
    horizons: tuple[int, ...] = (1, 2, 3),
    per: float = 50.0,
    lags: int = 12,
    exclude_years: tuple[int, ...] = (),
) -> dict[str, Any]:
    """Pre-registered test (D042): does a higher monthly import margin precede
    faster year-on-year import growth over the next one to three months? OLS
    slope per ``per`` RMB/dmt, Newey-West standard errors with ``lags`` lags.
    ``exclude_years`` drops signal months in those years (exploratory check, D043)."""
    m = margin.dropna()
    m.index = pd.PeriodIndex(m.index, freq="M")
    rows, points = [], None
    for h in horizons:
        y = import_growth(imports, m.index, h)
        d = pd.concat([m.rename("x"), y.rename("y")], axis=1).dropna()
        d = d[~d.index.year.isin(exclude_years)]
        x = np.column_stack([np.ones(len(d)), d["x"].to_numpy()])
        fit = stats.ols(d["y"].to_numpy(), x)
        se = stats.newey_west_se(x, fit.resid, lags)
        b, s = float(fit.beta[1]), float(se[1])
        rows.append(
            {
                "horizon_months": h,
                "n_obs": len(d),
                "effect_pp": b * per,
                "ci_lo_pp": (b - 1.96 * s) * per,
                "ci_hi_pp": (b + 1.96 * s) * per,
                "nw_t": b / s,
                "intercept_pp": float(fit.beta[0]),
                "mean_growth_pct": float(d["y"].mean()),
                "sample_start": str(d.index.min()),
                "sample_end": str(d.index.max()),
            }
        )
        if h == max(horizons):
            points = pd.DataFrame(
                {"month": d.index.astype(str), "margin_rmb_dmt": d["x"].to_numpy(), "growth_pct": d["y"].to_numpy()}
            )
    return {
        "per_rmb_dmt": per,
        "nw_lags": lags,
        "exclude_years": list(exclude_years),
        "rows": pd.DataFrame(rows),
        "points": points,
    }
