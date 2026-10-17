"""Unit tests for the engine, with hand-checked numbers."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from ironarb import dce, margins, stats, units, vat, voyage
from ironarb.curve import eligible, interpolate_constant_maturity, most_active
from ironarb.curve_build import constant_maturity_day
from ironarb.dce_x import reference_window


# Units ------------------------------------------------------------------------
def test_wet_dry_round_trip():
    # 10 USD per wet tonne at 8% moisture: 10 / 0.92 = 10.869565... per dry tonne
    assert units.per_wmt_to_per_dmt(10.0, 0.08) == pytest.approx(10.869565217391305, abs=1e-12)
    assert units.per_dmt_to_per_wmt(10.869565217391305, 0.08) == pytest.approx(10.0, abs=1e-12)
    assert units.dry_tonnes(170_000, 0.08) == pytest.approx(156_400.0)


def test_moisture_bounds():
    with pytest.raises(ValueError):
        units.per_wmt_to_per_dmt(10.0, 1.0)
    with pytest.raises(ValueError):
        units.per_wmt_to_per_dmt(10.0, -0.01)


# VAT schedule -------------------------------------------------------------------
@pytest.mark.parametrize(
    ("day", "rate"),
    [
        ("1994-04-30", 0.17),
        ("1994-05-01", 0.13),
        ("2008-12-31", 0.13),
        ("2009-01-01", 0.17),
        ("2018-04-30", 0.17),
        ("2018-05-01", 0.16),
        ("2019-03-31", 0.16),
        ("2019-04-01", 0.13),
        ("2014-06-15", 0.17),
        ("2026-10-16", 0.13),
    ],
)
def test_vat_boundaries(day, rate):
    assert vat.vat_rate(day) == rate


def test_vat_series_matches_scalar():
    days = pd.to_datetime(["2018-04-30", "2018-05-01", "2019-03-31", "2019-04-01"])
    assert list(vat.vat_series(days)) == [0.17, 0.16, 0.16, 0.13]


# DCE conventions ----------------------------------------------------------------
def test_standard_grade_switch_at_i2205():
    assert dce.standard_fe("I2204") == 62.0
    assert dce.standard_fe("I2205") == 61.0
    assert dce.standard_fe("I1405") == 62.0
    assert dce.standard_fe("I2701") == 61.0


@pytest.mark.parametrize(("avg", "x"), [(599.99, 1.0), (600.0, 1.5), (1200.0, 1.5), (1200.01, 2.0), (450.0, 1.0)])
def test_x_tiers(avg, x):
    assert dce.x_tier(avg) == x


def test_grade_adjustment():
    # 61% contract at 700 with X = 1.5: a 62% cargo is worth 700 + 10 x 1.5 = 715
    assert dce.to_62_basis(700.0, "I2601", 1.5) == pytest.approx(715.0)
    # 62% contract: unchanged
    assert dce.to_62_basis(700.0, "I2201", 1.5) == pytest.approx(700.0)


def test_expiry_is_tenth_trading_day():
    cal = pd.bdate_range("2026-11-01", "2026-12-31")
    exp = dce.expiry_dates(["I2611", "I2612"], cal)
    # November 2026: weekdays 2,3,4,5,6,9,10,11,12,13 -> 13 November
    assert exp["I2611"] == pd.Timestamp("2026-11-13")
    # December 2026: 1,2,3,4,7,8,9,10,11,14 -> 14 December
    assert exp["I2612"] == pd.Timestamp("2026-12-14")


def test_x_reference_window_mapping():
    cal = pd.bdate_range("2020-01-01", "2023-12-31")
    # May 2022 delivery (I2205): September 2021 publication, window March to September 2021
    s, e = reference_window(2022, 5, cal)
    assert (s.year, s.month, e.year, e.month) == (2021, 3, 2021, 9)
    # November 2022 delivery: March 2022 publication, window September 2021 to March 2022
    s, e = reference_window(2022, 11, cal)
    assert (s.year, s.month, e.year, e.month) == (2021, 9, 2022, 3)
    # January 2023 delivery: also the March 2022 publication
    s, e = reference_window(2023, 1, cal)
    assert (s.year, s.month, e.year, e.month) == (2021, 9, 2022, 3)


# Constant maturity --------------------------------------------------------------
def test_interpolation_hand_checked():
    # contracts at 30 and 60 days priced 700 and 690; 45 days is halfway: 695
    r = interpolate_constant_maturity(np.array([30.0, 60.0]), np.array([700.0, 690.0]), ["A", "B"], 45)
    assert r.value == pytest.approx(695.0)
    assert r.method == "interpolated"
    # 40 days: 700 - 10 x 10/30 = 696.666...
    r = interpolate_constant_maturity(np.array([60.0, 30.0]), np.array([690.0, 700.0]), ["B", "A"], 40)
    assert r.value == pytest.approx(696.6666666666666)
    assert (r.near, r.far) == ("A", "B")


def test_flat_and_linear_extrapolation():
    day = pd.DataFrame(
        {"contract": ["I05", "I09"], "dte": [90.0, 210.0], "oi": [5000.0, 4000.0], "price62": [800.0, 760.0]}
    )
    r = constant_maturity_day(day, 45, min_oi=1700, min_share=0, min_days=5, max_extrap_gap=120)
    # slope -40/120 per day; 45 days is 45 days before 90: 800 + 40/120 x 45 = 815
    assert r.method == "extrapolated_linear"
    assert r.value == pytest.approx(815.0)
    r = constant_maturity_day(day, 45, min_oi=1700, min_share=0, min_days=5, max_extrap_gap=30)
    assert r.method == "extrapolated_flat"
    assert r.value == pytest.approx(800.0)


def test_eligibility_filter():
    ok = eligible(np.array([1700, 1699, 50_000]), np.array([20, 20, 4]), min_oi=1700, min_share=0, min_days=5)
    assert list(ok) == [True, False, False]


def test_most_active_uses_previous_day_open_interest():
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 2 + ["2024-01-03"] * 2),
            "contract": ["I2405", "I2409"] * 2,
            "oi": [100, 50, 40, 200],
            "price": [1.0, 2.0, 3.0, 4.0],
        }
    )
    ma = most_active(panel)
    # on 3 January the leader is chosen from 2 January open interest: I2405
    assert ma.loc[ma["date"] == "2024-01-03", "contract"].item() == "I2405"
    assert ma.loc[ma["date"] == "2024-01-03", "price"].item() == 3.0


# Voyage model -------------------------------------------------------------------
def _toy_voyage() -> voyage.Voyage:
    return voyage.Voyage(
        name="toy",
        laden_nm=3600.0,
        ballast_nm=3600.0,
        laden_speed_kn=12.0,
        ballast_speed_kn=12.0,
        laden_fuel_t_day=50.0,
        ballast_fuel_t_day=40.0,
        port_fuel_t_day=5.0,
        load_port_days=2.0,
        discharge_port_days=3.0,
        cargo_t=170_000.0,
        commission=0.05,
        port_costs_usd=300_000.0,
    )


def test_voyage_days_and_freight_hand_checked():
    v = _toy_voyage()
    # 3,600 nm at 12 kn = 300 h = 12.5 days each way; plus 5 port days
    assert v.laden_days == pytest.approx(12.5)
    assert v.total_days == pytest.approx(30.0)
    # fuel: 12.5 x 50 + 12.5 x 40 = 1,125 t at sea; 5 x 5 = 25 t in port
    assert v.sea_fuel_t == pytest.approx(1125.0)
    # freight = (20,000 x 30 + 1,150 x 600 + 300,000) / (170,000 x 0.95)
    expected = (20_000 * 30 + 1150 * 600 + 300_000) / (170_000 * 0.95)
    assert voyage.freight_usd_per_t(v, 20_000, 600) == pytest.approx(expected)
    assert expected == pytest.approx(9.845201238390093)


def test_implied_tce_inverts_freight():
    v = _toy_voyage()
    f = voyage.freight_usd_per_t(v, 23_456.0, 612.0)
    assert voyage.implied_tce(v, f, 612.0) == pytest.approx(23_456.0)


# Margins ------------------------------------------------------------------------
def test_financing_hand_checked():
    # 100 USD at (4.30% + 150 bp) for 36 days: 100 x 0.058 x 36/360 = 0.58
    assert margins.financing_usd(100.0, 4.30, 150.0, 36.0) == pytest.approx(0.58)


def test_landed_cost_hand_checked():
    lc = margins.landed_cost(100.0, 7.0, 0.13, 30.0, 0.08, 0.58)
    # goods 700, VAT 91, port 30/0.92 = 32.6087, financing 0.58 x 7 = 4.06
    assert lc.goods_rmb == pytest.approx(700.0)
    assert lc.vat_rmb == pytest.approx(91.0)
    assert lc.port_rmb == pytest.approx(32.608695652173914)
    assert lc.financing_rmb == pytest.approx(4.06)
    assert lc.total_rmb == pytest.approx(827.6686956521739)
    assert margins.import_margin(850.0, lc.total_rmb) == pytest.approx(22.331304347826086)


def test_window_state_and_netback():
    assert list(margins.window_state([30.0, 0.0, -30.0, 25.0], 25.0)) == [1, 0, -1, 0]
    # 100 USD/dmt CFR minus 9.2 USD/wmt at 8% moisture (10 USD/dmt): 90
    assert margins.fob_netback(100.0, 9.2, 0.08) == pytest.approx(90.0)


def test_mill_margin_hand_checked():
    # 3,054 - 1.6 x 744.5 - 0.5 x 1,865 - 1,080 = -149.7
    assert margins.mill_margin(3054.0, 744.5, 1865.0, 1.6, 0.5, 1080.0) == pytest.approx(-149.7)


# Statistics ---------------------------------------------------------------------
def test_half_life():
    assert stats.half_life(0.5) == pytest.approx(1.0)
    assert stats.half_life(0.8) == pytest.approx(math.log(0.5) / math.log(0.8))
    assert stats.half_life(1.0) == math.inf


def test_ar1_recovers_known_rho():
    rng = np.random.default_rng(0)
    x = np.zeros(5000)
    for t in range(1, len(x)):
        x[t] = 2.0 + 0.7 * x[t - 1] + rng.normal()
    fit = stats.ar1(x)
    assert fit.rho == pytest.approx(0.7, abs=0.03)
    assert fit.const == pytest.approx(2.0, abs=0.15)


def test_mackinnon_values():
    # statsmodels mackinnonp(-2.86154, "c") = 0.05 to about 3 decimals (5% asymptotic critical value)
    assert stats.mackinnon_p(-2.86154) == pytest.approx(0.05, abs=0.002)
    assert stats.mackinnon_p(-3.43035) == pytest.approx(0.01, abs=0.002)
    crit = stats.mackinnon_crit(100)
    assert crit["5%"] == pytest.approx(-2.86154 - 2.8903 / 100 - 4.234 / 1e4 - 40.040 / 1e6)


def test_adf_rejects_for_stationary_and_not_for_random_walk():
    rng = np.random.default_rng(1)
    e = rng.normal(size=600)
    ar = np.zeros(600)
    for t in range(1, 600):
        ar[t] = 0.5 * ar[t - 1] + e[t]
    assert stats.adf(ar).pvalue < 0.01
    rw = np.cumsum(e)
    assert stats.adf(rw).pvalue > 0.10


def test_newey_west_equals_white_with_zero_lags():
    rng = np.random.default_rng(2)
    x = np.column_stack([np.ones(200), rng.normal(size=200)])
    y = x @ np.array([1.0, 2.0]) + rng.normal(size=200)
    fit = stats.ols(y, x)
    xtx_inv = np.linalg.inv(x.T @ x)
    white = np.sqrt(np.diag(xtx_inv @ (x.T * fit.resid**2) @ x @ xtx_inv))
    assert np.allclose(stats.newey_west_se(x, fit.resid, 0), white)
