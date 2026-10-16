"""Sina Finance futures daily history, one request per contract.

Endpoint (the one used by akshare ``futures_zh_daily_sina``):
``https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_X=/InnerFuturesNewService.getDailyKLine?symbol=I2601``
Fields: d (date), o, h, l, c (close), v (volume, lots), p (open interest, lots),
s (settlement price). Prices in RMB per tonne. Sina keeps per-contract history
for contracts expiring from about May 2018; older contracts return null.
"""

from __future__ import annotations

import json
import time
from datetime import date

import pandas as pd

from .common import RAW, FetchError, http, register_many, write_bytes

URL = "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_X=/InnerFuturesNewService.getDailyKLine"
DIR = RAW / "sina"
FIRST_CONTRACT = {"I": (2019, 5), "J": (2019, 5), "JM": (2019, 5), "RB": (2019, 5), "HC": (2019, 5)}
CONTINUOUS = ["I0", "J0", "JM0", "RB0", "HC0"]


def contract_codes(product: str, start: tuple[int, int], today: date, ahead: int = 13) -> list[str]:
    """All monthly contract codes from ``start`` to ``ahead`` months after today."""
    y, m = start
    end_y, end_m = today.year + (today.month + ahead - 1) // 12, (today.month + ahead - 1) % 12 + 1
    codes = []
    while (y, m) <= (end_y, end_m):
        codes.append(f"{product}{y % 100:02d}{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return codes


def parse(text: str) -> list[dict]:
    payload = text.split("=(", 1)[1].rsplit(");", 1)[0]
    data = json.loads(payload)
    return data or []


def is_final(code: str, today: date) -> bool:
    """A contract whose delivery month ended more than 40 days ago will not change."""
    yy, mm = int(code[-4:-2]), int(code[-2:])
    y = 2000 + yy
    end_of_month = date(y + (mm == 12), mm % 12 + 1, 1)
    return (today - end_of_month).days > 40


def fetch_contracts(codes: list[str], today: date, pause: float = 0.4) -> dict[str, str]:
    status: dict[str, str] = {}
    entries = []
    for code in codes:
        path = DIR / f"{code}.json"
        if path.exists() and is_final(code, today) and code[-1] != "0":
            status[code] = "cached"
            continue
        try:
            r = http(URL, params={"symbol": code, "type": "2021_04_12"}, timeout=45)
            rows = parse(r.text)
        except (FetchError, ValueError, IndexError) as exc:
            status[code] = f"error: {exc}"
            continue
        if not rows:
            status[code] = "empty"
            time.sleep(pause)
            continue
        write_bytes(path, json.dumps(rows, separators=(",", ":")).encode())
        entries.append((path, f"{URL}?symbol={code}", None))
        status[code] = f"ok {len(rows)} rows"
        time.sleep(pause)
    if entries:
        register_many(entries)
    return status


def read_all(products: tuple[str, ...] = ("I", "J", "JM", "RB", "HC")) -> pd.DataFrame:
    """Long panel: product, contract, date, close, settle, volume, oi (cached files)."""
    frames = []
    for path in sorted(DIR.glob("*.json")):
        code = path.stem
        product = code.rstrip("0123456789")
        if product not in products or (code.endswith("0") and len(code) <= 3):
            continue
        if not code[len(product) :].isdigit() or len(code) - len(product) != 4:
            continue
        rows = json.loads(path.read_text())
        df = pd.DataFrame(rows)
        df = df.rename(columns={"d": "date", "c": "close", "s": "settle", "v": "volume", "p": "oi"})
        df["product"] = product
        df["contract"] = code
        frames.append(df[["product", "contract", "date", "close", "settle", "volume", "oi"]])
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    for c in ["close", "settle", "volume", "oi"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def read_continuous(code: str) -> pd.DataFrame:
    rows = json.loads((DIR / f"{code}.json").read_text())
    df = pd.DataFrame(rows).rename(columns={"d": "date", "c": "close", "s": "settle", "v": "volume", "p": "oi"})
    df["date"] = pd.to_datetime(df["date"])
    for c in ["close", "settle", "volume", "oi"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["date", "close", "settle", "volume", "oi"]]


def run(today: date | None = None, full: bool = True) -> dict[str, str]:
    """``full`` fetches every contract from May 2019; otherwise contracts whose
    delivery month is within the last 14 months or later."""
    today = today or date.today()
    codes: list[str] = []
    recent = (today.year - (1 if today.month > 2 else 2), (today.month - 2 - 1) % 12 + 1)
    for product, start in FIRST_CONTRACT.items():
        codes += contract_codes(product, start if full else max(start, recent), today)
    codes += CONTINUOUS
    status = fetch_contracts(codes, today)
    n_ok = sum(1 for v in status.values() if v.startswith("ok") or v == "cached")
    n_err = sum(1 for v in status.values() if v.startswith("error"))
    return {
        "sina": f"{n_ok} contracts available, {n_err} errors",
        **{k: v for k, v in status.items() if v.startswith("error")},
    }
