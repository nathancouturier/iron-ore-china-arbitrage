"""China iron ore imports by month from the General Administration of Customs
(GACC), English statistics pages.

Source: table (14) "Major Import Commodities in Quantity and Value" of the
monthly bulletin, row "Iron ores and concentrates", quantity in 10,000 tonnes.
Index pages list one link per month: ``/statics/report/monthly{year}.html`` for
past years and ``/statics/report/monthly.html`` for the current year (January
2018 is the earliest year with an English index page). A month with no table
(14) on the English site falls back to table (6) of the preliminary release
(``preliminary{year}.html``), flagged ``preliminary``. A table that covers two
months (January and February 2020 were published together) is kept as one
two-month value and never split.
"""

from __future__ import annotations

import html
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd

from .common import RAW, http, register, write_bytes

BASE = "http://english.customs.gov.cn"
DIR = RAW / "gacc"
FIRST_YEAR = 2018
MONTHS = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


def _index_url(kind: str, year: int, today: date) -> str:
    return f"{BASE}/statics/report/{kind}.html" if year == today.year else f"{BASE}/statics/report/{kind}{year}.html"


def _text(raw: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", "|", raw)).replace("\xa0", " ")
    return re.sub(r"\s*\|[\s|]*", "|", re.sub(r"[ \t\r\n]+", " ", t))


def month_links(index_html: str, table: str) -> dict[int, str]:
    """Month number to table URL for the index row whose title contains ``table``."""
    for row in re.findall(r"<tr>(.*?)</tr>", index_html, re.S):
        if table in row:
            links = re.findall(r"<a\s+href=([^\s>]+)\s*>\s*([A-Za-z]{3})[a-z]*\.?\s*</a>", row)
            return {MONTHS[m]: u for u, m in links if m in MONTHS}
    return {}


def parse_table14(raw: str) -> tuple[tuple[int, int, int], float]:
    """Return ((year, first month, last month), quantity in 10,000 t)."""
    t = _text(raw)
    m = re.search(r"Quantity and Value\s*,\s*(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*\.\s*(\d{4})", t)
    if not m:
        raise ValueError("table (14) title not found")
    first = int(m.group(1))
    last = int(m.group(2) or m.group(1))
    q = re.search(r"\|\s*Iron[\s|]+ores[\s|]+and[\s|]+concentrates\s*\|\s*10000T\s*\|\s*([\d,]+(?:\.\d+)?)\s*\|", t)
    if not q:
        raise ValueError("iron ore row not found")
    return (int(m.group(3)), first, last), float(q.group(1).replace(",", ""))


def parse_preliminary6(raw: str) -> tuple[tuple[int, int, int], float]:
    """Preliminary release table (6), USD version: same quantity unit (10,000 t)."""
    t = _text(raw)
    m = re.search(r"Major Imports by Quantity and Value,\s*([A-Z][a-z]+)(?:\s*-\s*([A-Z][a-z]+))?\s+(\d{4})", t)
    names = [g[:3] for g in (m.groups()[:2] if m else ()) if g]
    if not m or not names or any(n not in MONTHS for n in names):
        raise ValueError("table (6) title not found")
    q = re.search(
        r"\|\s*Iron[\s|]+ores?[\s|]+and[\s|]+concentrates\s*\|\s*10,000 Tons\s*\|\s*([\d,]+(?:\.\d+)?)\s*\|", t
    )
    if not q:
        raise ValueError("iron ore row not found")
    return (int(m.group(3)), MONTHS[names[0]], MONTHS[names[-1]]), float(q.group(1).replace(",", ""))


def year_totals() -> dict[int, float]:
    """Full-year imports (Mt) from the January to December column of each
    December table (14), for the cross-check against the sum of the months."""
    out = {}
    for path in sorted(DIR.glob("t14_*-12.html")):
        t = _text(path.read_text(encoding="utf-8", errors="replace"))
        m = re.search(
            r"\|\s*Iron[\s|]+ores[\s|]+and[\s|]+concentrates\s*\|\s*10000T\s*\|\s*[\d,]+\s*\|\s*[\d,]+\s*\|\s*([\d,]+)\s*\|",
            t,
        )
        if m:
            out[int(path.name[4:8])] = float(m.group(1).replace(",", "")) / 100.0
    return out


def _get(url: str, path: Path, refresh: bool, note: str) -> str:
    if refresh or not path.exists():
        r = http(url, timeout=60)
        write_bytes(path, r.content)
        register(path, url, note=note)
        time.sleep(1.0)
    return path.read_text(encoding="utf-8", errors="replace")


def fetch(today: date, first_year: int = FIRST_YEAR) -> int:
    """Download index pages and monthly tables; past months are cached."""
    errors = 0
    for year in range(first_year, today.year + 1):
        recent = year >= today.year - 1
        idx = _get(
            _index_url("monthly", year, today), DIR / f"index_{year}.html", recent, "GACC monthly bulletin index"
        )
        links = month_links(idx, "Major Import Commodities in Quantity and Value")
        missing = [mo for mo in range(1, 13) if mo not in links and (year < today.year or mo < today.month)]
        for mo, url in links.items():
            try:
                _get(url, DIR / f"t14_{year}-{mo:02d}.html", False, "GACC table (14), major import commodities")
            except Exception:
                errors += 1
        if missing:
            pidx = _get(
                _index_url("preliminary", year, today),
                DIR / f"prelim_index_{year}.html",
                recent,
                "GACC preliminary index",
            )
            plinks = month_links(pidx, "Major Imports by Quantity and Value (in USD)")
            for mo in missing:
                if mo in plinks:
                    try:
                        _get(plinks[mo], DIR / f"p6_{year}-{mo:02d}.html", False, "GACC preliminary table (6)")
                    except Exception:
                        errors += 1
    return errors


def _url_of(path: Path) -> str:
    from .common import load_manifest  # noqa: PLC0415

    rel = path.resolve().relative_to(RAW).as_posix()
    return load_manifest().get(rel, {}).get("source_url", "")


def read() -> pd.DataFrame:
    """One row per published period: first and last month covered, quantity in Mt."""
    rows = []
    if not DIR.exists():
        raise FileNotFoundError(DIR)
    for path in sorted(DIR.glob("t14_*.html")):
        (y, m1, m2), q = parse_table14(path.read_text(encoding="utf-8", errors="replace"))
        rows.append((y, m1, m2, q, "GACC table (14)", _url_of(path)))
    for path in sorted(DIR.glob("p6_*.html")):
        (y, m1, m2), q = parse_preliminary6(path.read_text(encoding="utf-8", errors="replace"))
        rows.append((y, m1, m2, q, "GACC preliminary table (6)", _url_of(path)))
    df = pd.DataFrame(rows, columns=["year", "first_month", "last_month", "imports_10kt", "table", "url"])
    df["start"] = pd.to_datetime(dict(year=df["year"], month=df["first_month"], day=1)).dt.strftime("%Y-%m")
    df["end"] = pd.to_datetime(dict(year=df["year"], month=df["last_month"], day=1)).dt.strftime("%Y-%m")
    df["months"] = df["last_month"] - df["first_month"] + 1
    df["imports_mt"] = df["imports_10kt"] / 100.0
    # a final table (14) wins over a preliminary value for the same period
    df["rank"] = (df["table"] != "GACC table (14)").astype(int)
    df = df.sort_values(["start", "rank"]).drop_duplicates(["start", "end"]).drop(columns="rank")
    return df[["start", "end", "months", "imports_mt", "table", "url"]].reset_index(drop=True)


def run(full: bool = False, today: date | None = None) -> dict[str, str]:
    """Full: every year from 2018. Incremental: the current and previous year;
    older months come from the committed derived snapshot."""
    today = today or date.today()
    try:
        note = f"{fetch(today, FIRST_YEAR if full else today.year - 1)} errors"
    except Exception as exc:  # keep the cached tables
        note = f"index failed: {exc}"
    try:
        df = read()
    except Exception as exc:
        return {"gacc_imports": f"stale: {exc}"}
    return {"gacc_imports": f"ok {len(df)} periods to {df['end'].max()}, {note}"}
