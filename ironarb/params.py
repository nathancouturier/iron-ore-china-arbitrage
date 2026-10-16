"""Default parameters with sources. This module is the single source of truth:
``pipeline/export.py`` writes it to ``site/data/params.json`` for the calculator.
"""

from __future__ import annotations

from typing import Any

PARAMS: dict[str, Any] = {
    "moisture": {
        "value": 0.08,
        "sensitivity": [0.06, 0.10],
        "unit": "fraction of wet weight",
        "source": "Fastmarkets iron ore methodology (January 2026): moisture base 8% for 62%/61% Fe fines fot Qingdao",
    },
    "port_charges_rmb_wmt": {
        "value": 30.0,
        "sensitivity": [20.0, 40.0],
        "unit": "RMB per wet tonne",
        "source": "Set with Ruida Futures import-cost estimates (implied 30 to 35) and Fastmarkets port-to-seaborne conversions (implied 31 to 40) in view; Mysteel uses 23, Huatai Futures 35",
    },
    "financing_spread_bp": {
        "value": 150.0,
        "sensitivity": [50.0, 300.0],
        "unit": "basis points over the USD reference rate",
        "source": "Assumed trade finance spread over SOFR (effective fed funds before April 2018); sensitivity 50 to 300 bp",
    },
    "financing_extra_days": {
        "value": 10.0,
        "unit": "days added to the laden voyage",
        "source": "Assumed time for discharge, customs clearance and payment after arrival",
    },
    "cm_target_days": {
        "value": 45,
        "alternatives": [30, 60, 90],
        "unit": "calendar days to expiry",
        "source": "Cargo priced today arrives in roughly 2 to 6 weeks",
    },
    "cm_min_oi_lots": {
        "value": 1700,
        "unit": "lots (single-sided), 100 t each",
        "source": "One Capesize cargo (170,000 t) of open interest",
    },
    "cm_min_days": {"value": 5, "unit": "calendar days", "source": "Exclude contracts in their final days"},
    "cm_max_extrapolation_days": {
        "value": 120,
        "unit": "calendar days",
        "source": "Linear extrapolation before the first eligible expiry is allowed up to this distance",
    },
    "band_rmb_dmt": {
        "value": 25.0,
        "sensitivity": [15.0, 35.0],
        "unit": "RMB per dry tonne",
        "source": "DCE delivery fee 0.5 + storage 0.3/day x 30 days + ship outbound fee cap 12 = 21.5 RMB/t (27.5 at the pre-2021 storage fee of 0.5/day)",
    },
    "mill_ore_coef": {"value": 1.6, "unit": "t ore per t steel", "source": "Chinese broker convention"},
    "mill_coke_coef": {"value": 0.5, "unit": "t coke per t steel", "source": "Chinese broker convention"},
    "mill_other_costs_rebar": {
        "value": 1080.0,
        "sensitivity": [950.0, 1250.0],
        "unit": "RMB per tonne",
        "source": "Constant implied by Everbright Futures' 2026 daily rebar margins; published range 950 to 1,250",
    },
    "mill_other_costs_hrc_premium": {
        "value": 150.0,
        "unit": "RMB per tonne over rebar",
        "source": "Industrial Futures (2024): 1,200 rebar and 1,350 HRC",
    },
    "insurance_rate": {
        "value": 0.0,
        "alternative": 0.003,
        "unit": "fraction of CFR",
        "source": "CFR approximates the customs value; China Customs deems insurance at 0.3% of goods plus freight when unknown",
    },
}


# Voyage definitions. Distances (nautical miles) come from the searoute package
# (pipeline/routes.py). Vessel figures: the eco point of the Baltic standard
# Capesize table (Circular 21/24: 12 knots on 36 t laden, 29 t ballast), which
# reproduces the Platts round-voyage durations (West Australia under 40 days,
# Brazil about 90 days); the full-speed description (BCI182: 14 knots on 52 t
# laden, 44 t ballast) is the sensitivity.
VESSEL: dict[str, Any] = {
    "laden_speed_kn": {
        "value": 12.0,
        "alt": 14.0,
        "source": "Baltic Circular 21/24 eco table; 14 kn in the BCI182 description",
    },
    "ballast_speed_kn": {
        "value": 12.0,
        "alt": 14.0,
        "source": "Baltic Circular 21/24 eco table; 14 kn in the BCI182 description",
    },
    "laden_fuel_t_day": {
        "value": 36.0,
        "alt": 52.0,
        "source": "Baltic Circular 21/24 eco table; 52 t in the BCI182 description",
    },
    "ballast_fuel_t_day": {
        "value": 29.0,
        "alt": 44.0,
        "source": "Baltic Circular 21/24 eco table; 44 t in the BCI182 description",
    },
    "port_fuel_t_day": {"value": 5.0, "source": "Assumption: auxiliary consumption in port"},
    "cargo_t": {"value": 170_000.0, "source": "Baltic C3 (Circular 44/24) and C5: 170,000 mt 10% MOLOO"},
    "commission": {"value": 0.05, "source": "Baltic voyage routes: 5% total commission"},
    "discharge_days": {
        "value": 170_000 / 30_000 + 1.0,
        "source": "30,000 mt per day SHINC discharge plus 24 h turn time (Baltic C3 and C5)",
    },
}
ROUTES: dict[str, dict[str, Any]] = {
    "C5": {
        "label": "West Australia (Port Hedland) to Qingdao",
        "load": "port_hedland",
        "load_days": 2.5,
        "port_costs_usd": 250_000.0,
    },
    "C3": {"label": "Tubarao to Qingdao", "load": "tubarao", "load_days": 3.0, "port_costs_usd": 250_000.0},
}
PORT_COSTS_NOTE = (
    "No public port disbursement figure was found for Port Hedland, Tubarao or Qingdao; 250,000 USD per round "
    "voyage (load plus discharge) is an explicit assumption, sensitivity 50% to 150% (about 1.5 USD per tonne)."
)
LOAD_DAYS_NOTE = (
    "Load port time: Baltic 'scale load' with 6 h turn time; 2.5 days at Port Hedland and 3 days at Tubarao assumed."
)


def value(name: str) -> Any:
    return PARAMS[name]["value"]
