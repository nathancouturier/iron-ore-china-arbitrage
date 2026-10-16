"""Pipeline runner: ``python -m pipeline <stage> [--full]``.

Stages: ingest, validate, transform, model, export, report, audit, all.

- ``--full`` re-fetches every source from the start of its history, including
  the DCE annual files (headless Chromium) and every SHFE and SGX daily file.
- Without it (the weekly refresh), only recent exchange data are fetched; older
  dates come from the committed derived snapshots in ``data/derived``.

A source that fails keeps its last good snapshot and is marked stale in
``data/derived/source_status.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "data" / "derived" / "source_status.json"


def _record(results: dict[str, Any], name: str, fn, *args, **kwargs) -> None:
    t0 = time.time()
    try:
        out = fn(*args, **kwargs)
        ok = not any(str(v).startswith("stale") for v in (out or {}).values())
        results[name] = {"ok": ok, "detail": out, "seconds": round(time.time() - t0, 1)}
    except Exception as exc:  # keep going: the stage falls back to snapshots
        results[name] = {
            "ok": False,
            "detail": f"stale: {type(exc).__name__}: {exc}",
            "seconds": round(time.time() - t0, 1),
        }
    print(f"[{name}] {'ok' if results[name]['ok'] else 'STALE'} {results[name]['detail']}", flush=True)


def ingest(full: bool) -> dict[str, Any]:
    from .ingest import dce, eastmoney, fred, safe, sgx, shfe, sina, worldbank  # noqa: PLC0415

    res: dict[str, Any] = {}
    _record(res, "fred", fred.run)
    _record(res, "worldbank", worldbank.run)
    _record(res, "eastmoney", eastmoney.run)
    _record(res, "safe", safe.run)
    _record(res, "sina", sina.run, full=full)
    _record(res, "shfe", shfe.run, full=full)
    _record(res, "sgx", sgx.run, full=full)
    if full:
        _record(res, "dce_annual", dce.run)
    prev = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    prev.update({"ingest": res, "ingest_mode": "full" if full else "incremental"})
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(prev, indent=1, default=str) + "\n")
    return res


def stage(name: str, full: bool) -> None:
    if name == "ingest":
        ingest(full)
    elif name == "validate":
        from . import validate  # noqa: PLC0415

        print(validate.run())
    elif name == "transform":
        from . import routes, transform  # noqa: PLC0415

        print(routes.run())
        print(transform.run())
    elif name == "model":
        from . import model  # noqa: PLC0415

        print(model.run())
    elif name == "export":
        from . import export  # noqa: PLC0415

        print(export.run())
    elif name == "report":
        from . import report  # noqa: PLC0415

        print(report.run())
    elif name == "audit":
        from . import audit  # noqa: PLC0415

        print(audit.run())
    else:
        raise SystemExit(f"unknown stage {name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline")
    ap.add_argument("stage", choices=["ingest", "validate", "transform", "model", "export", "report", "audit", "all"])
    ap.add_argument("--full", action="store_true", help="re-fetch every source from the start of its history")
    args = ap.parse_args(argv)
    stages = (
        ["ingest", "transform", "validate", "model", "report", "export", "audit"]
        if args.stage == "all"
        else [args.stage]
    )
    for s in stages:
        print(f"== {s}", flush=True)
        stage(s, args.full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
