"""Long history: World Bank price regimes, the 62% Fe equivalent and the
UN Comtrade (WITS) parser (decision log D050 to D053)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from pipeline import history
from pipeline.ingest import wits


@pytest.mark.parametrize(
    ("month", "basis", "fe"),
    [
        ("1960-01", "contract_fob_brazil", None),
        ("1986-12", "contract_fob_brazil", None),
        ("1987-01", "contract_fob_brazil", None),
        ("2005-12", "contract_fob_brazil", None),
        ("2006-01", "spot_cfr_china", 63.5),
        ("2008-11", "spot_cfr_china", 63.5),
        ("2008-12", "spot_cfr_china", 62.0),
        ("2026-09", "spot_cfr_china", 62.0),
    ],
)
def test_regimes(month, basis, fe):
    r = history.regime_of(pd.Period(month, "M"))
    assert r.basis == basis
    assert r.fe_pct == fe


def test_itabira_to_carajas():
    assert "Itabira" in history.regime_of(pd.Period("1986-12", "M")).label
    assert "Carajás" in history.regime_of(pd.Period("1987-01", "M")).label


def test_62_equivalent():
    contract = history.regime_of(pd.Period("2005-06", "M"))
    # 65 US cents per Fe unit, 62 units in a 62% dry tonne
    assert math.isclose(history.to_62_equivalent(65.0, contract), 40.3)
    spot635 = history.regime_of(pd.Period("2007-06", "M"))
    assert math.isclose(history.to_62_equivalent(127.0, spot635), 124.0)
    spot62 = history.regime_of(pd.Period("2020-06", "M"))
    assert history.to_62_equivalent(101.5, spot62) == 101.5


def test_no_regime_before_1960():
    with pytest.raises(ValueError):
        history.regime_of(pd.Period("1959-12", "M"))


# Cells split by tags and a partner without a quantity, as on the WITS pages
PAGE = (
    "<table><tr><td>China</td><td>Import</td><td>260111</td><td>Non-agglomerated iron ores</td><td>2005</td>"
    "<td>World</td><td>15,954,914.10</td><td>251,605,000,000</td><td>Kg</td></tr>"
    "<tr><td>China</td><td>Import</td><td>260111</td><td>Non-agglomerated iron ores</td><td>2005</td>"
    "<td>Australia</td><td>6,075,560.53</td><td>111,192,000,000</td><td>Kg</td></tr>"
    "<tr><td>China</td><td>Import</td><td>260111</td><td>Non-agglomerated iron ores</td><td>2005</td>"
    "<td>Korea, Dem. Rep.</td><td>67,148.40</td><td></td><td></td></tr>"
    "<tr><td>China</td><td>Import</td><td>260111</td><td>Non-agglomerated iron ores</td><td>2005</td>"
    "<td>Brazil</td><td>3,218,536.75</td><td>47,524,400,000</td><td>Kg</td></tr></table>"
)


def test_wits_parse():
    df = wits.parse(PAGE, "260111")
    assert list(df["partner"]) == ["World", "Australia", "Korea, Dem. Rep.", "Brazil"]
    assert df.loc[df["partner"] == "Australia", "qty_kg"].iloc[0] == 111_192_000_000
    assert df.loc[df["partner"] == "Brazil", "value_kusd"].iloc[0] == 3_218_536.75
    assert pd.isna(df.loc[df["partner"] == "Korea, Dem. Rep.", "qty_kg"].iloc[0])
    assert set(df["year"]) == {2005}
