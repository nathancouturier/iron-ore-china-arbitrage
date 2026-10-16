"""Baltic Capesize Index (BCI) and Baltic Dry Index (BDI), daily, from East Money.

Endpoint (the one used by akshare ``macro_shipping_bci`` and ``macro_shipping_bdi``):
``https://datacenter-web.eastmoney.com/api/data/v1/get`` with report
RPT_INDUSTRY_INDEX and indicator EMI00107666 (BCI) or EMI00107664 (BDI).
Values are index points as published by the Baltic Exchange.
"""

from __future__ import annotations

import json
import time

import pandas as pd

from .common import RAW, http, register, write_bytes

URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
INDICATORS = {"bci": "EMI00107666", "bdi": "EMI00107664"}


def fetch(name: str, pause: float = 0.5) -> pd.DataFrame:
    ind = INDICATORS[name]
    params = {
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
        "pageSize": "500",
        "pageNumber": "1",
        "reportName": "RPT_INDUSTRY_INDEX",
        "columns": "REPORT_DATE,INDICATOR_VALUE",
        "filter": f'(INDICATOR_ID="{ind}")',
        "source": "WEB",
        "client": "WEB",
    }
    first = http(URL, params=params, timeout=60).json()
    pages = int(first["result"]["pages"])
    rows = list(first["result"]["data"])
    for page in range(2, pages + 1):
        params["pageNumber"] = str(page)
        rows += http(URL, params=params, timeout=60).json()["result"]["data"]
        time.sleep(pause)
    path = RAW / "eastmoney" / f"{name}.json"
    write_bytes(path, json.dumps(rows, ensure_ascii=False).encode())
    register(path, URL, params={k: v for k, v in params.items() if k != "pageNumber"})
    return read(name)


def read(name: str) -> pd.DataFrame:
    rows = json.loads((RAW / "eastmoney" / f"{name}.json").read_text())
    df = pd.DataFrame(rows).rename(columns={"REPORT_DATE": "date", "INDICATOR_VALUE": "value"})
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    return df[["date", "value"]]


def run() -> dict[str, str]:
    status = {}
    for name in INDICATORS:
        try:
            df = fetch(name)
            status[name] = f"ok {len(df)} rows {df['date'].min().date()} to {df['date'].max().date()}"
        except Exception as exc:
            status[name] = f"stale: {exc}"
    return status
