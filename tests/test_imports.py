"""China Customs import parsing and the imports test windows (D041, D042)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from pipeline.analysis import import_growth, window_sum
from pipeline.ingest import gacc

# Minimal markup in the shape of the GACC English tables (cells split across tags as on the site)
T14 = (
    "<table><tr><td>（14）Major Import Commodities in Quantity and Value,1-2. 2020</td></tr>"
    "<tr><td>Commodity</td><td>QuantityUnit</td><td>1 to 2</td></tr>"
    "<tr><td><span>Iron</span> ores and concentrates</td><td>10000T</td><td>17,684</td><td>16,054,802</td></tr></table>"
)
P6 = (
    "<table><tr><td>(6) China's Major Imports by Quantity and Value, September 2024 (in USD)</td></tr>"
    "<tr><td>&nbsp;Iron ore and concentrates</td><td>10,000 Tons</td><td>10,413.2&nbsp;</td><td>9,941.7</td></tr></table>"
)
INDEX = (
    "<tr><td>（14）Major Import Commodities in Quantity and Value</td><td>"
    "<a\n href=http://x/a.html>\n Jan.</a><span>Feb.</span><a href=http://x/c.html> Mar.</a></td></tr>"
)


def test_parse_table14_combined_months():
    (year, first, last), q = gacc.parse_table14(T14)
    assert (year, first, last) == (2020, 1, 2)
    assert q == 17684.0


def test_parse_preliminary6():
    (year, first, last), q = gacc.parse_preliminary6(P6)
    assert (year, first, last) == (2024, 9, 9)
    assert q == 10413.2


def test_month_links_skip_unpublished():
    links = gacc.month_links(INDEX, "Major Import Commodities in Quantity and Value")
    assert links == {1: "http://x/a.html", 3: "http://x/c.html"}


def _imports() -> pd.DataFrame:
    rows = [("2019-01", "2019-01", 90.0), ("2019-02", "2019-02", 80.0), ("2019-03", "2019-03", 85.0)]
    rows += [("2020-01", "2020-02", 180.0), ("2020-03", "2020-03", 95.0)]
    return pd.DataFrame(rows, columns=["start", "end", "imports_mt"])


def test_window_sum_never_splits_a_combined_period():
    cover = [
        (frozenset(pd.period_range(s, e, freq="M")), v)
        for s, e, v in _imports()[["start", "end", "imports_mt"]].itertuples(index=False)
    ]
    p = pd.Period
    assert window_sum(cover, [p("2020-01", "M"), p("2020-02", "M")]) == 180.0
    assert math.isnan(window_sum(cover, [p("2020-02", "M"), p("2020-03", "M")]))
    assert math.isnan(window_sum(cover, [p("2019-12", "M")]))


def test_import_growth_year_on_year():
    months = pd.PeriodIndex(["2019-12", "2020-01", "2020-02"], freq="M")
    g2 = import_growth(_imports(), months, 2)
    # Dec 2019 signal: Jan+Feb 2020 (180) against Jan+Feb 2019 (170)
    assert np.isclose(g2[pd.Period("2019-12", "M")], 100 * np.log(180 / 170))
    # Jan 2020 signal: Feb+Mar 2020 straddles the combined period
    assert np.isnan(g2[pd.Period("2020-01", "M")])
    g1 = import_growth(_imports(), months, 1)
    assert np.isclose(g1[pd.Period("2020-02", "M")], 100 * np.log(95 / 85))
