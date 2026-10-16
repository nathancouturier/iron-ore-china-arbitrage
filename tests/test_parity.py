"""The JavaScript calculator must agree with the Python engine to 1e-9."""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ironarb import dce, margins, vat, voyage
from ironarb.calculator import calculate

ROOT = Path(__file__).resolve().parents[1]
TOL = 1e-9


def fixtures() -> dict:
    calc = []
    grid = itertools.product([45.0, 101.6, 214.3], [6.2, 7.1], [0.17, 0.13], [20.0, 30.0], [0.06, 0.08, 0.10])
    for i, (cfr, fx, v, port, moist) in enumerate(grid):
        calc.append(
            {
                "cfrUsdDmt": cfr,
                "usdcny": fx,
                "vat": v,
                "portRmbWmt": port,
                "moisture": moist,
                "freightUsdWmt": 5.0 + i * 0.37,
                "usdRatePct": 0.1 + (i % 7) * 0.8,
                "spreadBp": 150.0,
                "financingDays": 20.5 + (i % 3) * 22.6,
                "dce62RmbDmt": cfr * fx * 1.05 + (i % 5) * 7.0,
                "band": 25.0,
            }
        )
    vessels = []
    for nm, speed, tce, fuel in [
        (3530.7, 14.0, 20000.0, 600.0),
        (11136.9, 12.0, 33678.0, 540.5),
        (3571.5, 13.0, 4000.0, 290.0),
    ]:
        vessels.append(
            {
                "ladenNm": nm,
                "ballastNm": nm,
                "ladenSpeedKn": speed,
                "ballastSpeedKn": speed,
                "ladenFuelTDay": 52.0,
                "ballastFuelTDay": 44.0,
                "portFuelTDay": 5.0,
                "loadPortDays": 2.5,
                "dischargePortDays": 170000 / 30000 + 1,
                "cargoT": 170000.0,
                "commission": 0.05,
                "portCostsUsd": 350000.0,
                "tceUsdDay": tce,
                "fuelUsdT": fuel,
            }
        )
    return {
        "calculator": calc,
        "vat_dates": ["2018-04-30", "2018-05-01", "2019-03-31", "2019-04-01", "2026-10-16", "2014-01-02"],
        "voyages": vessels,
        "dce62": [{"price": 700.5, "standardFe": 61.0, "x": 1.5}, {"price": 512.0, "standardFe": 62.0, "x": 1.5}],
        "mill": [{"steel": 3054.0, "ore": 744.5, "coke": 1865.0, "oreCoef": 1.6, "cokeCoef": 0.5, "other": 1080.0}],
        "netback": [
            {"cfr": 101.6, "freight": 9.87, "moisture": 0.08},
            {"cfr": 45.0, "freight": 5.473, "moisture": 0.09},
        ],
    }


def python_results(fx: dict) -> dict:
    out = {"calculator": [calculate(c) for c in fx["calculator"]], "vat": [vat.vat_rate(d) for d in fx["vat_dates"]]}
    out["voyage"] = []
    for v in fx["voyages"]:
        voy = voyage.Voyage(
            name="fixture",
            laden_nm=v["ladenNm"],
            ballast_nm=v["ballastNm"],
            laden_speed_kn=v["ladenSpeedKn"],
            ballast_speed_kn=v["ballastSpeedKn"],
            laden_fuel_t_day=v["ladenFuelTDay"],
            ballast_fuel_t_day=v["ballastFuelTDay"],
            port_fuel_t_day=v["portFuelTDay"],
            load_port_days=v["loadPortDays"],
            discharge_port_days=v["dischargePortDays"],
            cargo_t=v["cargoT"],
            commission=v["commission"],
            port_costs_usd=v["portCostsUsd"],
        )
        out["voyage"].append(
            {
                "days": voy.total_days,
                "freight": voyage.freight_usd_per_t(voy, v["tceUsdDay"], v["fuelUsdT"]),
                "financingDays": voyage.financing_days(voy, 10),
            }
        )
    out["dce62"] = [
        dce.to_62_basis(c["price"], "I2601" if c["standardFe"] == 61.0 else "I2201", c["x"]) for c in fx["dce62"]
    ]
    out["mill"] = [
        margins.mill_margin(c["steel"], c["ore"], c["coke"], c["oreCoef"], c["cokeCoef"], c["other"])
        for c in fx["mill"]
    ]
    out["netback"] = [margins.fob_netback(c["cfr"], c["freight"], c["moisture"]) for c in fx["netback"]]
    return out


def _close(a, b, path=""):
    if isinstance(a, dict):
        assert set(a) == set(b), path
        for k in a:
            _close(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _close(x, y, f"{path}[{i}]")
    else:
        assert abs(float(a) - float(b)) <= TOL, f"{path}: python {a} vs js {b}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_js_engine_matches_python(tmp_path):
    fx = fixtures()
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(fx))
    proc = subprocess.run(
        ["node", str(ROOT / "tests" / "js_parity.mjs"), str(path)], capture_output=True, text=True, check=True
    )
    js = json.loads(proc.stdout)
    py = python_results(fx)
    assert len(py["calculator"]) == 72
    _close(py, js)
