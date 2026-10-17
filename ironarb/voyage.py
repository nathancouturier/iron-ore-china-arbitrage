"""Capesize voyage model: from a time charter equivalent to a freight rate.

A shipowner quoting a voyage rate must earn the time charter equivalent (TCE)
over the whole round voyage, ballast leg included, and recover bunker fuel and
port costs, net of commissions. Hence

    freight (USD per wet tonne of cargo)
        = (TCE x total voyage days + bunker cost + port costs)
          / (cargo tonnes x (1 - commission))

Freight is paid on the bill-of-lading (wet) weight of the cargo.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import ArrayLike


@dataclass(frozen=True)
class Voyage:
    """Round voyage definition. Distances in nautical miles, speeds in knots,
    consumption in tonnes of fuel per day, cargo in metric tonnes."""

    name: str
    laden_nm: float
    ballast_nm: float
    laden_speed_kn: float
    ballast_speed_kn: float
    laden_fuel_t_day: float
    ballast_fuel_t_day: float
    port_fuel_t_day: float
    load_port_days: float
    discharge_port_days: float
    cargo_t: float
    commission: float
    port_costs_usd: float

    @property
    def laden_days(self) -> float:
        return self.laden_nm / (24.0 * self.laden_speed_kn)

    @property
    def ballast_days(self) -> float:
        return self.ballast_nm / (24.0 * self.ballast_speed_kn)

    @property
    def port_days(self) -> float:
        return self.load_port_days + self.discharge_port_days

    @property
    def total_days(self) -> float:
        return self.laden_days + self.ballast_days + self.port_days

    @property
    def sea_fuel_t(self) -> float:
        return self.laden_days * self.laden_fuel_t_day + self.ballast_days * self.ballast_fuel_t_day

    @property
    def port_fuel_t(self) -> float:
        return self.port_days * self.port_fuel_t_day

    def with_(self, **changes: float) -> Voyage:
        return replace(self, **changes)


def freight_usd_per_t(
    voyage: Voyage, tce_usd_day: ArrayLike, fuel_usd_t: ArrayLike, port_fuel_usd_t: ArrayLike | None = None
) -> np.ndarray | float:
    """Voyage freight in USD per (wet) tonne of cargo.

    ``fuel_usd_t`` prices the fuel burnt at sea; ``port_fuel_usd_t`` the fuel
    burnt in port (defaults to the same price).
    """
    tce = np.asarray(tce_usd_day, dtype=float)
    fuel = np.asarray(fuel_usd_t, dtype=float)
    pfuel = fuel if port_fuel_usd_t is None else np.asarray(port_fuel_usd_t, dtype=float)
    bunker = voyage.sea_fuel_t * fuel + voyage.port_fuel_t * pfuel
    gross = tce * voyage.total_days + bunker + voyage.port_costs_usd
    out = gross / (voyage.cargo_t * (1.0 - voyage.commission))
    return float(out) if np.ndim(out) == 0 else out


def implied_tce(
    voyage: Voyage, freight_usd_t: ArrayLike, fuel_usd_t: ArrayLike, port_fuel_usd_t: ArrayLike | None = None
) -> np.ndarray | float:
    """Inverse of :func:`freight_usd_per_t`: TCE in USD/day implied by a freight rate."""
    f = np.asarray(freight_usd_t, dtype=float)
    fuel = np.asarray(fuel_usd_t, dtype=float)
    pfuel = fuel if port_fuel_usd_t is None else np.asarray(port_fuel_usd_t, dtype=float)
    bunker = voyage.sea_fuel_t * fuel + voyage.port_fuel_t * pfuel
    out = (f * voyage.cargo_t * (1.0 - voyage.commission) - bunker - voyage.port_costs_usd) / voyage.total_days
    return float(out) if np.ndim(out) == 0 else out


def financing_days(voyage: Voyage, extra_days: float) -> float:
    """Days of cargo financing: laden passage plus discharge plus a fixed buffer
    for loading, documents and payment terms."""
    return voyage.laden_days + extra_days
