"""Shanghai Futures Exchange official daily quotes, one JSON file per trading day.

Endpoint: ``https://www.shfe.com.cn/data/tradedata/future/dailydata/kx{YYYYMMDD}.dat``
(the source used by akshare ``get_shfe_daily``). Non-trading days return HTTP 404
and are remembered in ``nontrading.json`` so they are not requested again.
Only rebar (rb) and hot-rolled coil (hc) rows are kept in the parsed panel;
the raw daily file is cached gzip-compressed.
"""

from __future__ import annotations

import gzip
import json
import time
from datetime import date, timedelta

import pandas as pd

from .common import RAW, FetchError, http, register_many, write_bytes

URL = "https://www.shfe.com.cn/data/tradedata/future/dailydata/kx{d}.dat"
DIR = RAW / "shfe"
NONTRADING = DIR / "nontrading.json"
PRODUCTS = ("rb", "hc")


def _nontrading() -> set[str]:
    return set(json.loads(NONTRADING.read_text())) if NONTRADING.exists() else set()


def path_for(d: date):
    return DIR / str(d.year) / f"kx{d:%Y%m%d}.dat.gz"


def fetch_range(start: date, end: date, pause: float = 0.35, max_requests: int | None = None) -> dict[str, int]:
    """Fetch every weekday in [start, end] not already cached; resumable."""
    skip = _nontrading()
    entries = []
    counts = {"fetched": 0, "cached": 0, "nontrading": 0, "errors": 0}
    d = start
    n_req = 0
    while d <= end:
        key = f"{d:%Y%m%d}"
        if d.weekday() >= 5 or key in skip:
            d += timedelta(days=1)
            continue
        p = path_for(d)
        if p.exists():
            counts["cached"] += 1
            d += timedelta(days=1)
            continue
        if max_requests is not None and n_req >= max_requests:
            break
        n_req += 1
        try:
            r = http(URL.format(d=key), timeout=45, ok_statuses=(200,))
            payload = r.content
            json.loads(payload)
            write_bytes(p, gzip.compress(payload))
            entries.append((p, URL.format(d=key), None))
            counts["fetched"] += 1
        except FetchError as exc:
            if "HTTP 404" in str(exc):
                skip.add(key)
                counts["nontrading"] += 1
            else:
                counts["errors"] += 1
        except ValueError:
            counts["errors"] += 1
        if len(entries) >= 100:
            register_many(entries)
            entries = []
            NONTRADING.write_text(json.dumps(sorted(skip)))
        time.sleep(pause)
        d += timedelta(days=1)
    if entries:
        register_many(entries)
    DIR.mkdir(parents=True, exist_ok=True)
    NONTRADING.write_text(json.dumps(sorted(skip)))
    return counts


def read_panel() -> pd.DataFrame:
    """Long panel of rb and hc contracts: product, contract, date, close, settle, volume, oi."""
    rows = []
    for p in sorted(DIR.glob("*/kx*.dat.gz")):
        day = p.name[2:10]
        data = json.loads(gzip.decompress(p.read_bytes()))
        for r in data.get("o_curinstrument", []):
            pid = str(r.get("PRODUCTID", "")).strip().split("_")[0]
            month = str(r.get("DELIVERYMONTH", "")).strip()
            if pid not in PRODUCTS or not month.isdigit():
                continue
            rows.append(
                {
                    "product": pid.upper(),
                    "contract": pid.upper() + month,
                    "date": day,
                    "close": r.get("CLOSEPRICE"),
                    "settle": r.get("SETTLEMENTPRICE"),
                    "volume": r.get("VOLUME"),
                    "oi": r.get("OPENINTEREST"),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    for c in ["close", "settle", "volume", "oi"]:
        df[c] = pd.to_numeric(df[c].replace("", None), errors="coerce")
    return df


def run(start: date = date(2013, 10, 18), end: date | None = None, full: bool = True) -> dict[str, str]:
    """``full`` fetches every trading day from ``start``; otherwise the last 45 days."""
    end = end or date.today()
    if not full:
        start = max(start, end - timedelta(days=45))
    counts = fetch_range(start, end)
    return {"shfe": ", ".join(f"{k} {v}" for k, v in counts.items())}
