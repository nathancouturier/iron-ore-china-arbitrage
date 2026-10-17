"""China iron ore imports by partner, annual, from UN Comtrade via the World
Bank's WITS pages.

One page per year and HS 6-digit product lists every partner with the trade
value (USD thousand, CIF) and the quantity (kg, customs weight):
``/trade/comtrade/en/country/CHN/year/{year}/tradeflow/Imports/partner/ALL/product/{hs}``.
Products: 260111 (non-agglomerated iron ores and concentrates) and 260112
(agglomerated, mainly pellets). China reports to Comtrade from 1992.
"""

from __future__ import annotations

import html
import re
import time
from datetime import date

import pandas as pd

from .common import RAW, http, load_manifest, register, write_bytes

BASE = "https://wits.worldbank.org/trade/comtrade/en/country/CHN/year/{year}/tradeflow/Imports/partner/ALL/product/{hs}"
DIR = RAW / "wits"
PRODUCTS = ("260111", "260112")
FIRST_YEAR = 1992


def _text(raw: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", "|", raw)).replace("\xa0", " ")
    return re.sub(r"\s*\|[\s|]*", "|", re.sub(r"[ \t\r\n]+", " ", t))


def _num(s: str) -> float | None:
    s = s.replace(",", "").strip()
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def parse(raw: str, hs: str) -> pd.DataFrame:
    """Rows of (year, partner, value_kusd, qty_kg); quantity is missing when not reported."""
    rows = []
    for part in _text(raw).split(f"|China|Import|{hs}|")[1:]:
        f = part.split("|")
        if len(f) < 4 or not re.fullmatch(r"\d{4}", f[1]):
            continue
        value = _num(f[3])
        qty = _num(f[4]) if len(f) > 5 and f[5] == "Kg" else None
        if value is None:
            continue
        rows.append({"year": int(f[1]), "partner": f[2].strip(), "hs": hs, "value_kusd": value, "qty_kg": qty})
    return pd.DataFrame(rows, columns=["year", "partner", "hs", "value_kusd", "qty_kg"])


def fetch(today: date, first_year: int = FIRST_YEAR) -> int:
    """Download one page per year and product; years before last year are cached."""
    errors = 0
    for year in range(first_year, today.year):
        for hs in PRODUCTS:
            path = DIR / f"chn_{hs}_{year}.html"
            if path.exists() and year < today.year - 2:
                continue
            url = BASE.format(year=year, hs=hs)
            try:
                r = http(url, timeout=60)
                if f"|China|Import|{hs}|" not in _text(r.text):
                    continue  # year not yet reported
                write_bytes(path, r.content)
                register(path, url, note=f"UN Comtrade via WITS, China imports HS {hs}")
            except Exception:
                errors += 1
            time.sleep(1.0)
    return errors


def read() -> pd.DataFrame:
    if not DIR.exists():
        raise FileNotFoundError(DIR)
    manifest = load_manifest()
    frames = []
    for path in sorted(DIR.glob("chn_*.html")):
        hs = path.name.split("_")[1]
        df = parse(path.read_text(encoding="utf-8", errors="replace"), hs)
        rel = path.resolve().relative_to(RAW).as_posix()
        df["url"] = manifest.get(rel, {}).get("source_url", "")
        frames.append(df)
    if not frames:
        raise FileNotFoundError("no WITS pages cached")
    return pd.concat(frames, ignore_index=True)


def run(full: bool = False, today: date | None = None) -> dict[str, str]:
    """Full: every year from 1992. Incremental: the last three reported years;
    older years come from the committed derived snapshot."""
    today = today or date.today()
    try:
        note = f"{fetch(today, FIRST_YEAR if full else today.year - 3)} errors"
    except Exception as exc:  # keep the cached pages
        note = f"fetch failed: {exc}"
    try:
        df = read()
    except Exception as exc:
        return {"wits_imports": f"stale: {exc}"}
    return {"wits_imports": f"ok {df['year'].nunique()} years to {df['year'].max()}, {note}"}
