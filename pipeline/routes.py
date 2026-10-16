"""Sea routes for the C3 and C5 voyages from the ``searoute`` package.

searoute (Halili, MIT license) finds the shortest path on a maritime network
derived from Eurostat's MARNET. Distances are checked in the tests against
published port-to-port distances. Output: ``data/derived/routes.json`` with the
distance of each leg in nautical miles and a simplified geometry for the map.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "derived" / "routes.json"

PORTS = {
    "port_hedland": {"name": "Port Hedland", "lonlat": [118.58, -20.31]},
    "dampier": {"name": "Dampier", "lonlat": [116.71, -20.64]},
    "tubarao": {"name": "Tubarao", "lonlat": [-40.24, -20.29]},
    "qingdao": {"name": "Qingdao", "lonlat": [120.32, 36.05]},
}
LEGS = [("port_hedland", "qingdao"), ("dampier", "qingdao"), ("tubarao", "qingdao")]


def _load_searoute():
    try:
        import searoute  # noqa: PLC0415
    except ImportError:  # local fallback: pure-Python source cached under data/cache/vendor
        import sys  # noqa: PLC0415

        sys.path.insert(0, str(ROOT / "data" / "cache" / "vendor"))
        import searoute  # noqa: PLC0415
    return searoute


def compute() -> dict:
    sr = _load_searoute()
    legs = {}
    for a, b in LEGS:
        r = sr.searoute(PORTS[a]["lonlat"], PORTS[b]["lonlat"], units="naut", restrictions=["northwest"])
        coords = [[round(x, 3), round(y, 3)] for x, y in r.geometry["coordinates"]]
        legs[f"{a}-{b}"] = {"from": a, "to": b, "nm": round(float(r.properties["length"]), 1), "coords": coords}
    return {"ports": PORTS, "legs": legs, "method": "searoute shortest path, restrictions: northwest passage"}


def run() -> dict[str, str]:
    data = compute()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return {k: f"{v['nm']} nm" for k, v in data["legs"].items()}


def distances() -> dict[str, float]:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    return {k: v["nm"] for k, v in data["legs"].items()}
