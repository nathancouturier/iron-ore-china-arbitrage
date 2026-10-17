"""Section 4 anchors as tests. They run on committed data (FRED raw files,
derived snapshots and the anchor CSVs), so CI needs no exchange downloads.

Tolerances are documented here and on the Method page; no default parameter is
tuned to meet them.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline import anchors, freight_model, inputs
from pipeline.margin_model import Assumptions


@pytest.fixture(scope="module")
def assumptions() -> Assumptions:
    return Assumptions()


@pytest.fixture(scope="module")
def freight_eval():
    cal = freight_model.calibrate()
    daily = freight_model.voyage_model_daily(cal)
    return cal, freight_model.evaluate(cal, daily)


def test_bci_published_lows_and_highs():
    bci = inputs.baltic_daily()["bci_pts"]
    assert bci.loc["2016-01-29"] == 211  # Splash247: 211 on 29 January 2016, then a record low
    assert bci.loc["2016-02-02"] == 217  # same article: BCI 217
    assert bci.loc["2026-07-03"] == 4100  # Hellenic Shipping News, week 27 2026


def test_bci_to_5tc_fixed_ratio_is_stable(freight_eval):
    cal, _ = freight_eval
    r = cal.tc["5TC 180,000 dwt, fixed ratio (Sep 2020 to Dec 2025)"]
    assert r.b == pytest.approx(8.293, abs=0.002)
    assert r.extra["ratio_max"] - r.extra["ratio_min"] < 0.01
    r26 = cal.tc["5TC 182,000 dwt, fixed ratio (from Jan 2026)"]
    assert r26.b == pytest.approx(9.07, abs=0.002)


def test_week27_2026_5tc_reproduced(freight_eval):
    cal, _ = freight_eval
    # BCI 4,100 on 3 July 2026 with C5TC(180) 33,678: 182 basis = 9.0694 x 4,100, minus 3,503
    tc182 = cal.tc["5TC 182,000 dwt, fixed ratio (from Jan 2026)"](4100.0)
    assert tc182 - freight_model.TC_182_ADJUSTMENT == pytest.approx(33678, abs=60)


def test_bunker_maps_have_expected_shape(freight_eval):
    cal, _ = freight_eval
    hsfo = cal.bunker["HSFO 380 cst (before 2020)"]
    vlsfo = cal.bunker["VLSFO 0.5% S (from 2020)"]
    # fuel oil per tonne is roughly 6 to 8 times Brent per barrel; VLSFO above HSFO
    assert 5.5 < hsfo.b < 8.0
    assert 6.5 < vlsfo.b < 9.0
    assert vlsfo(80.0) > hsfo(80.0)


@pytest.mark.parametrize(("route", "max_rmse"), list(anchors.TOLERANCE["freight_rmse_usd_t"].items()))
def test_freight_models_out_of_sample(freight_eval, route, max_rmse):
    """Tolerance: RMSE under 3.0 USD/t for C3 and 1.5 for C5 (about 10% of typical rates)."""
    _, ev = freight_eval
    assert ev[route]["voyage"]["n"] >= 15
    assert ev[route]["voyage"]["rmse"] < max_rmse
    assert ev[route]["stat_loo"]["rmse"] < max_rmse


def test_freight_seed_anchors(freight_eval):
    _, ev = freight_eval
    rows = ev["rows"].set_index(["date", "route"])
    # Splash247: C3 5.473 on 2 February 2016 (BCI 217)
    assert rows.loc[(pd.Timestamp("2016-02-02"), "C3"), "voyage_model"] == pytest.approx(5.473, abs=1.5)
    # Week 27 2026: C3 30.11, C5 12.25
    assert rows.loc[(pd.Timestamp("2026-07-03"), "C3"), "voyage_model"] == pytest.approx(30.11, abs=4.0)
    assert rows.loc[(pd.Timestamp("2026-07-03"), "C5"), "voyage_model"] == pytest.approx(12.25, abs=2.0)


def test_ruida_import_cost_within_15_rmb(assumptions):
    """Our landed cost reconciles with Ruida's estimate within 15 RMB/t once the
    FX source matches theirs (PBoC central parity of the report day)."""
    r = anchors.import_cost(assumptions)
    assert len(r["rows"]) == 8
    assert r["max_abs_error_ours_central_parity"] < anchors.TOLERANCE["import_cost_rmb_t"]
    assert r["max_abs_error_reconstructed"] < 5.0
    # their adder sits in the range of published port charges (23 to 40 RMB/t)
    lo, hi = r["inferred"]["adder_range"]
    assert 23.0 <= lo and hi <= 40.0


def test_fastmarkets_port_price_conversion(assumptions):
    r = anchors.port_price(assumptions)
    assert r["max_abs_error_usd"] < anchors.TOLERANCE["port_price_usd_dmt"]
    lo, hi = r["implied_port_range"]
    assert 20.0 <= lo and hi <= 45.0


def test_broker_mill_margins():
    r = anchors.mill_margin()
    rows = r["rows"]
    sdic = rows[rows["independent"]]
    assert abs(sdic["error_rmb_t"]).max() < 1.0  # SDIC Essence Futures, 1 June 2022: 211.4
    assert r["max_abs_error"] < anchors.TOLERANCE["mill_margin_rmb_t"]  # Everbright Futures 2026 dailies
    # closing prices printed in the broker reports equal ours
    eb = rows[~rows["independent"]]
    assert (eb["our_closes"] == eb["published_closes"]).all()
