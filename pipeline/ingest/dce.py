"""Dalian Commodity Exchange annual historical quote files (official).

The files are downloaded by ``scripts/dce_history.mjs`` (headless Chromium,
because the DCE site answers plain HTTP clients with a JavaScript challenge)
from the DCE historical data page
http://www.dce.com.cn/dalianshangpin/xqsj/lssj/index.html.
Formats differ by year (zipped GBK CSV for 2013 to 2016, xlsx or csv-named xlsx
for 2017 to 2023, legacy xls for 2024) but columns are the same:
合约 contract, 日期 date, 收盘价 close, 结算价 settlement, 成交量 volume (lots),
持仓量 open interest (lots). Prices are RMB per tonne.
"""

from __future__ import annotations

import io
import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd

from .common import RAW, ROOT, register_many

DIR = RAW / "dce" / "annual"
PAGE = "http://www.dce.com.cn/dalianshangpin/xqsj/lssj/index.html"
COLS = {
    "合约": "contract",
    "日期": "date",
    "收盘价": "close",
    "结算价": "settle",
    "成交量": "volume",
    "持仓量": "oi",
}


def download() -> str:
    """Run the Playwright downloader; returns a status string."""
    cmd = ["node", str(ROOT / "scripts" / "dce_history.mjs"), str(DIR)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False)
    if proc.returncode != 0:
        return f"stale: downloader exit {proc.returncode}: {proc.stderr.strip()[:200]}"
    index = json.loads((DIR / "index.json").read_text())
    new = [it for it in index if not it.get("cached")]
    register_many([(Path(it["path"]).resolve(), "http://www.dce.com.cn" + it["url"], {"page": PAGE}) for it in new])
    return f"ok {len(index)} files ({len(new)} new)"


def _read_one(path: Path) -> pd.DataFrame:
    if path.suffix == ".zip":
        z = zipfile.ZipFile(path)
        raw = z.read(z.namelist()[0])
        df = pd.read_csv(io.BytesIO(raw), encoding="gbk")
    elif path.suffix == ".xls":
        df = pd.read_excel(path, engine="xlrd")
    else:  # xlsx, including the 2017 file published with a .csv name
        df = pd.read_excel(path, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.rename(columns=COLS)
    missing = [c for c in COLS.values() if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    df = df[list(COLS.values())].copy()
    df["contract"] = df["contract"].astype(str).str.strip().str.upper()
    df["date"] = pd.to_datetime(df["date"].astype(str).str.slice(0, 8), format="%Y%m%d")
    for c in ["close", "settle", "volume", "oi"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["source_file"] = path.name
    return df


def read_panel(products: tuple[str, ...] = ("I", "J", "JM")) -> pd.DataFrame:
    """Long panel of all contracts for the requested products, deduplicated."""
    index = json.loads((DIR / "index.json").read_text())
    frames = []
    for it in index:
        product = it["variety"].upper()
        if product not in products:
            continue
        df = _read_one(Path(it["path"]))
        df = df[df["contract"].str.fullmatch(product + r"\d{4}")]
        df.insert(0, "product", product)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(["contract", "date"], keep="last")
    return out.sort_values(["product", "date", "contract"]).reset_index(drop=True)


def run() -> dict[str, str]:
    return {"dce_annual": download()}
