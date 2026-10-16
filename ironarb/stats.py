"""Small, dependency-free statistics used by the analysis (numpy only).

- Ordinary least squares with classical and Newey-West (Bartlett) standard errors.
- AR(1) fit, half-life and a recursive residual bootstrap for its interval.
- Augmented Dickey-Fuller test with constant: lag order by AIC, MacKinnon (1994)
  approximate p-values and MacKinnon (2010) finite-sample critical values. The
  response-surface coefficients are copied from statsmodels 0.14.4
  (statsmodels/tsa/adfvalues.py, BSD-3-Clause licence).
- Moving block bootstrap for a difference in means between two regimes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# MacKinnon (1994) p-value coefficients, regression with constant ("c"), N = 1.
_TAU_STAR_C = -1.61
_TAU_MIN_C = -18.83
_TAU_MAX_C = 2.74
_TAU_C_SMALLP = (2.1659, 1.4412, 3.8269 * 1e-2)
_TAU_C_LARGEP = (1.7339, 9.3202 * 1e-1, -1.2745 * 1e-1, -1.0368 * 1e-2)
# MacKinnon (2010) critical values, constant, N = 1: b0 + b1/T + b2/T^2 + b3/T^3.
_TAU_C_2010 = {
    "1%": (-3.43035, -6.5393, -16.786, -79.433),
    "5%": (-2.86154, -2.8903, -4.234, -40.040),
    "10%": (-2.56677, -1.5384, -2.809, 0.0),
}


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass
class OLS:
    beta: np.ndarray
    resid: np.ndarray
    se: np.ndarray
    sigma2: float
    nobs: int
    llf: float


def ols(y: np.ndarray, x: np.ndarray) -> OLS:
    """OLS of ``y`` on the columns of ``x`` (include a constant column yourself)."""
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    n, k = x.shape
    sigma2 = float(resid @ resid / (n - k))
    xtx_inv = np.linalg.inv(x.T @ x)
    se = np.sqrt(np.diag(xtx_inv) * sigma2)
    ssr = float(resid @ resid)
    llf = -n / 2.0 * (math.log(2 * math.pi) + math.log(ssr / n) + 1.0)
    return OLS(beta, resid, se, sigma2, n, llf)


def newey_west_se(x: np.ndarray, resid: np.ndarray, lags: int) -> np.ndarray:
    """Heteroskedasticity and autocorrelation consistent standard errors with a
    Bartlett kernel of ``lags`` lags (Newey and West 1987), no small-sample
    correction."""
    x = np.asarray(x, dtype=float)
    u = np.asarray(resid, dtype=float)[:, None] * x
    s = u.T @ u
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1.0)
        g = u[lag:].T @ u[:-lag]
        s += w * (g + g.T)
    xtx_inv = np.linalg.inv(x.T @ x)
    cov = xtx_inv @ s @ xtx_inv
    return np.sqrt(np.diag(cov))


@dataclass
class AR1:
    const: float
    rho: float
    rho_se: float
    half_life: float  # periods; inf if rho >= 1, nan if rho <= 0
    resid: np.ndarray
    nobs: int


def half_life(rho: float) -> float:
    """Periods for a deviation to halve under AR(1) persistence ``rho``."""
    if rho >= 1.0:
        return math.inf
    if rho <= 0.0:
        return float("nan")
    return math.log(0.5) / math.log(rho)


def ar1(x: np.ndarray) -> AR1:
    """Fit x_t = c + rho x_{t-1} + e_t by OLS."""
    x = np.asarray(x, dtype=float)
    y, lag = x[1:], x[:-1]
    design = np.column_stack([np.ones_like(lag), lag])
    fit = ols(y, design)
    rho = float(fit.beta[1])
    return AR1(float(fit.beta[0]), rho, float(fit.se[1]), half_life(rho), fit.resid, fit.nobs)


def ar1_bootstrap(x: np.ndarray, n_boot: int = 2000, seed: int = 7) -> dict[str, float]:
    """Recursive residual bootstrap of the AR(1) half-life.

    Simulates series of the same length from the fitted model with resampled
    residuals, starting at the observed first value, and re-estimates rho.
    Returns percentile bounds for rho and the half-life, and the share of draws
    with rho >= 1 (no mean reversion)."""
    x = np.asarray(x, dtype=float)
    fit = ar1(x)
    rng = np.random.default_rng(seed)
    resid = fit.resid - fit.resid.mean()
    n = len(x)
    rhos = np.empty(n_boot)
    for b in range(n_boot):
        e = rng.choice(resid, size=n - 1, replace=True)
        sim = np.empty(n)
        sim[0] = x[0]
        for t in range(1, n):
            sim[t] = fit.const + fit.rho * sim[t - 1] + e[t - 1]
        rhos[b] = ar1(sim).rho
    hl = np.array([half_life(r) for r in rhos])
    finite = hl[np.isfinite(hl)]
    return {
        "rho_lo": float(np.percentile(rhos, 2.5)),
        "rho_hi": float(np.percentile(rhos, 97.5)),
        "half_life_lo": float(np.percentile(hl[~np.isnan(hl)], 2.5)),
        "half_life_hi": float(np.percentile(hl[~np.isnan(hl)], 97.5)),
        "half_life_median": float(np.median(finite)) if len(finite) else math.inf,
        "share_nonstationary": float(np.mean(rhos >= 1.0)),
        "n_boot": n_boot,
    }


def mackinnon_p(tau: float) -> float:
    """MacKinnon (1994) approximate p-value for the ADF statistic, constant case."""
    if tau > _TAU_MAX_C:
        return 1.0
    if tau < _TAU_MIN_C:
        return 0.0
    coef = _TAU_C_SMALLP if tau <= _TAU_STAR_C else _TAU_C_LARGEP
    z = sum(c * tau**i for i, c in enumerate(coef))
    return norm_cdf(z)


def mackinnon_crit(nobs: int) -> dict[str, float]:
    """MacKinnon (2010) finite-sample critical values, constant case."""
    t = float(nobs)
    return {k: b[0] + b[1] / t + b[2] / t**2 + b[3] / t**3 for k, b in _TAU_C_2010.items()}


@dataclass
class ADF:
    stat: float
    pvalue: float
    lags: int
    nobs: int
    crit: dict[str, float]


def adf(x: np.ndarray, maxlag: int | None = None) -> ADF:
    """Augmented Dickey-Fuller test with a constant; lag order chosen by AIC on
    a common sample, as in statsmodels ``adfuller(autolag="AIC")``."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if maxlag is None:
        maxlag = math.ceil(12.0 * (n / 100.0) ** 0.25)
        maxlag = min(n // 2 - 2, maxlag)
    dx = np.diff(x)

    def design(lags: int, start: int) -> tuple[np.ndarray, np.ndarray]:
        # rows t = start .. n-2 index dx[t]; regress dx[t] on x[t], dx[t-1..t-lags]
        rows = range(start, n - 1)
        y = np.array([dx[t] for t in rows])
        cols = [np.ones(len(y)), np.array([x[t] for t in rows])]
        for i in range(1, lags + 1):
            cols.append(np.array([dx[t - i] for t in rows]))
        return y, np.column_stack(cols)

    best_aic, best_lag = math.inf, 0
    for lags in range(maxlag + 1):
        y, xx = design(lags, maxlag)
        fit = ols(y, xx)
        aic = -2.0 * fit.llf + 2.0 * xx.shape[1]
        if aic < best_aic:
            best_aic, best_lag = aic, lags
    y, xx = design(best_lag, best_lag)
    fit = ols(y, xx)
    stat = float(fit.beta[1] / fit.se[1])
    return ADF(stat, mackinnon_p(stat), best_lag, fit.nobs, mackinnon_crit(fit.nobs))


def block_bootstrap_diff(
    y: np.ndarray, flag: np.ndarray, block: int, n_boot: int = 2000, seed: int = 11
) -> dict[str, float]:
    """Difference in means of ``y`` between flagged and unflagged observations,
    with a moving block bootstrap interval that resamples (y, flag) pairs in
    blocks of ``block`` consecutive observations to respect overlap and serial
    correlation."""
    y = np.asarray(y, dtype=float)
    f = np.asarray(flag, dtype=bool)
    ok = np.isfinite(y)
    y, f = y[ok], f[ok]
    n = len(y)
    est = float(y[f].mean() - y[~f].mean())
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block)
    draws = []
    for _ in range(n_boot):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        yb, fb = y[idx], f[idx]
        if fb.sum() == 0 or (~fb).sum() == 0:
            continue
        draws.append(yb[fb].mean() - yb[~fb].mean())
    d = np.array(draws)
    return {
        "diff": est,
        "lo": float(np.percentile(d, 2.5)),
        "hi": float(np.percentile(d, 97.5)),
        "n_flag": int(f.sum()),
        "n": int(n),
        "n_boot_valid": len(d),
    }
