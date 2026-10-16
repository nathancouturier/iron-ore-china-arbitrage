"""SGX daily futures settlement files, used for the daily 62% Fe CFR proxy.

Endpoint: ``https://links.sgx.com/1.0.0/derivatives-daily/{file_id}/FUTURE.zip``
(the archive behind the SGX "historical daily data" page, also used by akshare
``futures_settlement_price_sgx``). Each archive holds one trading day of
settlement prices for every SGX future; ids are sequential by trading day.
Only the iron ore rows (commodity code FEF: SGX iron ore CFR China 62% Fe fines
index futures, USD per dry metric tonne) are kept in the parsed panel.
"""

from __future__ import annotations

import io
import json
import time
import zipfile

import pandas as pd

from .common import RAW, FetchError, http, register_many, write_bytes

URL = "https://links.sgx.com/1.0.0/derivatives-daily/{id}/FUTURE.zip"
DIR = RAW / "sgx"
FIRST_ID = 4790  # 2015-12-29, so the series starts with January 2016 complete
INDEX = DIR / "index.json"


def _parse(blob: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = z.namelist()[0]
        text = z.read(name).decode("utf-8", errors="replace")
    sep = "\t" if "\t" in text.splitlines()[0] else ","
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip()
    # Archives published before 2018 are tab-separated .txt files whose prices
    # carry two implied decimals (3958 means 39.58); later .csv files are plain.
    df.attrs["price_scale"] = 0.01 if name.lower().endswith(".txt") else 1.0
    return df


def _index() -> dict[str, str]:
    return json.loads(INDEX.read_text()) if INDEX.exists() else {}


def fetch_ids(first: int, last: int | None = None, pause: float = 0.3, max_misses: int = 12) -> dict[str, int]:
    """Download archives from ``first`` until ``last`` or until ``max_misses``
    consecutive ids are missing (the newest id not yet published)."""
    index = _index()
    entries = []
    counts = {"fetched": 0, "cached": 0, "missing": 0}
    misses = 0
    i = first
    while last is None or i <= last:
        path = DIR / "zip" / f"{i}.zip"
        if path.exists():
            counts["cached"] += 1
            i += 1
            continue
        try:
            blob = http(URL.format(id=i), timeout=60).content
            df = _parse(blob)
            day = df["DATE"].iloc[0]
        except (FetchError, zipfile.BadZipFile, KeyError, IndexError, ValueError):
            counts["missing"] += 1
            misses += 1
            if misses >= max_misses:
                break
            i += 1
            time.sleep(pause)
            continue
        misses = 0
        write_bytes(path, blob)
        index[str(i)] = day
        entries.append((path, URL.format(id=i), None))
        counts["fetched"] += 1
        if len(entries) >= 100:
            register_many(entries)
            entries = []
            INDEX.write_text(json.dumps(index))
        i += 1
        time.sleep(pause)
    if entries:
        register_many(entries)
    DIR.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(index))
    return counts


def read_fef() -> pd.DataFrame:
    """Panel of FEF settlements: date, contract month (YYYY-MM), settle, volume, oi."""
    rows = []
    for path in sorted((DIR / "zip").glob("*.zip"), key=lambda p: int(p.stem)):
        df = _parse(path.read_bytes())
        scale = df.attrs["price_scale"]
        df = df[df["COM"] == "FEF"]
        if df.empty:
            continue
        for _, r in df.iterrows():
            rows.append(
                {
                    "date": r["DATE"],
                    "month": f"{int(r['COM_YY']):04d}-{int(r['COM_MM']):02d}",
                    "settle": float(r["SETTLE"]) * scale if r["SETTLE"] not in ("", None) else None,
                    "volume": r.get("VOLUME"),
                    "oi": r.get("OINT"),
                    "file_id": int(path.stem),
                }
            )
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"], format="%Y%m%d")
    for c in ["settle", "volume", "oi"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["settle"] = out["settle"].where(out["settle"] > 0)  # 0 marks a missing settlement
    return out.drop_duplicates(["date", "month"], keep="last").sort_values(["date", "month"])


def run() -> dict[str, str]:
    index = _index()
    start = max([int(k) for k in index] + [FIRST_ID - 1]) + 1 if index else FIRST_ID
    counts = fetch_ids(start)
    return {"sgx": ", ".join(f"{k} {v}" for k, v in counts.items())}
