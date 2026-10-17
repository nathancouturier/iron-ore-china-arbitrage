"""PBoC USD/CNY central parity (人民币汇率中间价) from the State Administration of
Foreign Exchange (SAFE) query page.

Endpoint: POST ``https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do`` with
``startDate`` and ``endDate``. The page lists the daily central parity in RMB per
100 units of foreign currency; the USD column is divided by 100 here.
"""

from __future__ import annotations

import re
import time
from datetime import date

import pandas as pd

from .common import RAW, http, register, write_bytes

URL = "https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do"
DIR = RAW / "safe"


def fetch_year(year: int, today: date) -> None:
    start = f"{year}-01-01"
    end = f"{year}-12-31" if year < today.year else today.isoformat()
    r = http(URL, method="POST", data={"startDate": start, "endDate": end, "queryYN": "true"}, timeout=90)
    path = DIR / f"central_parity_{year}.html"
    write_bytes(path, r.content)
    register(path, URL, params={"startDate": start, "endDate": end}, note="PBoC central parity via SAFE")


def parse(html: str) -> pd.DataFrame:
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", html))
    rows = re.findall(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|[\s|]*?([\d.]+)\s*\|", text)
    df = pd.DataFrame(rows, columns=["date", "usd_per100"])
    df["date"] = pd.to_datetime(df["date"])
    df["usdcny_cp"] = pd.to_numeric(df["usd_per100"]) / 100.0
    return df[["date", "usdcny_cp"]]


def read() -> pd.DataFrame:
    frames = [parse(p.read_text(encoding="utf-8", errors="replace")) for p in sorted(DIR.glob("*.html"))]
    df = pd.concat(frames).drop_duplicates("date").sort_values("date")
    return df.reset_index(drop=True)


def run(first_year: int = 2013, today: date | None = None) -> dict[str, str]:
    today = today or date.today()
    errors = 0
    for y in range(first_year, today.year + 1):
        path = DIR / f"central_parity_{y}.html"
        if path.exists() and y < today.year - 1:
            continue
        try:
            fetch_year(y, today)
        except Exception:
            errors += 1
        time.sleep(1.0)
    try:
        df = read()
        return {"safe_central_parity": f"ok {len(df)} rows to {df['date'].max().date()}, {errors} errors"}
    except Exception as exc:
        return {"safe_central_parity": f"stale: {exc}"}
