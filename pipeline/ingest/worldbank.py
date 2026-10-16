"""World Bank Commodity Price Data (Pink Sheet), monthly historical workbook.

The workbook link is read from the World Bank commodity markets page each time,
because the file URL changes with every monthly release. Data are published
under CC BY 4.0.
"""

from __future__ import annotations

import re

import pandas as pd

from .common import RAW, http, register, write_bytes

PAGE = "https://www.worldbank.org/en/research/commodity-markets"
PATH = RAW / "worldbank" / "CMO-Historical-Data-Monthly.xlsx"


def find_link() -> str:
    html = http(PAGE, timeout=60).text
    links = re.findall(r'href="([^"]+CMO-Historical-Data-Monthly\.xlsx)"', html)
    if not links:
        raise ValueError("monthly workbook link not found on commodity markets page")
    link = links[0]
    return link if link.startswith("http") else "https://www.worldbank.org" + link


def fetch() -> pd.DataFrame:
    url = find_link()
    r = http(url, timeout=120)
    write_bytes(PATH, r.content)
    register(PATH, url, note="World Bank Pink Sheet monthly prices, CC BY 4.0")
    return read()


def read() -> pd.DataFrame:
    """Return monthly iron ore price (USD/dmt) from the 'Monthly Prices' sheet."""
    raw = pd.read_excel(PATH, sheet_name="Monthly Prices", header=None)
    labels = [[str(v) for v in raw.iloc[i].tolist()] for i in range(10)]
    header_row = next(i for i, row in enumerate(labels) if any("Iron ore" in v for v in row))
    names = [v.strip() for v in labels[header_row]]
    col = next(j for j, n in enumerate(names) if n.lower().startswith("iron ore"))
    units = str(raw.iloc[header_row + 1, col]).strip()
    body = raw.iloc[header_row + 2 :, [0, col]].copy()
    body.columns = ["period", "value"]
    body = body[body["period"].astype(str).str.match(r"^\d{4}M\d{2}$")]
    body["date"] = pd.to_datetime(body["period"].str.replace("M", "-") + "-01")
    body["value"] = pd.to_numeric(body["value"], errors="coerce")
    body.attrs["units"] = units
    body.attrs["label"] = names[col]
    return body[["date", "value"]].reset_index(drop=True)


def run() -> dict[str, str]:
    try:
        df = fetch()
        return {"pinksheet": f"ok {len(df)} rows to {df['date'].max().date()}"}
    except Exception as exc:
        return {"pinksheet": f"stale: {exc}"}
