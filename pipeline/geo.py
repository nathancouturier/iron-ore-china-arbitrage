"""Land outline for the route map from Natural Earth (public domain) via the
world-atlas 2.0.2 TopoJSON package (ISC licence), decoded to GeoJSON here."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "vendor" / "world-atlas-2.0.2" / "land-110m.json"


def _decode_arcs(topo: dict) -> list[list[list[float]]]:
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append([round(x * sx + tx, 2), round(y * sy + ty, 2)])
        arcs.append(pts)
    return arcs


def _ring(indices: list[int], arcs: list[list[list[float]]]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in indices:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        out.extend(a if not out else a[1:])
    return out


def land_geojson(bbox: tuple[float, float, float, float] = (-75.0, -50.0, 160.0, 55.0)) -> dict:
    """Land polygons that intersect ``bbox`` (lon_min, lat_min, lon_max, lat_max)."""
    topo = json.loads(SRC.read_text())
    arcs = _decode_arcs(topo)
    geom = topo["objects"]["land"]["geometries"]
    polys = []
    for g in geom:
        parts = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        for poly in parts:
            rings = [_ring(r, arcs) for r in poly]
            xs = [p[0] for p in rings[0]]
            ys = [p[1] for p in rings[0]]
            # keep a polygon only if one of its points lies in the box (a bounding-box
            # overlap test would keep antimeridian islands such as Fiji, whose rings
            # run from -180 to 180 and draw a line across the map)
            if not any(bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3] for x, y in rings[0]):
                continue
            if (max(xs) - min(xs)) * (max(ys) - min(ys)) < 0.5:
                continue  # drop tiny islands to keep the file small
            polys.append(rings)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "land"},
                "geometry": {"type": "MultiPolygon", "coordinates": polys},
            }
        ],
    }
