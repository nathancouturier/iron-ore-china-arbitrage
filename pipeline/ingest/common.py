"""Shared download helpers: polite HTTP with retries, raw cache and manifest.

Every raw file written by the pipeline is registered in ``data/raw/manifest.json``
with its source URL, request parameters, retrieval time (UTC) and SHA-256.
Files under folders listed in ``NON_REDISTRIBUTABLE`` are kept out of git (see
``.gitignore``); their manifest entries are committed so the provenance of every
derived number stays traceable.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.json"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
NON_REDISTRIBUTABLE = ("dce", "sina", "shfe", "eastmoney", "sgx", "safe", "gacc", "wits", "other")

_session: requests.Session | None = None


def session() -> requests.Session:
    """Return a shared requests session with a browser-like user agent."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": USER_AGENT})
    return _session


class FetchError(RuntimeError):
    """Raised when a source cannot be fetched after retries."""


def http(
    url: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    retries: int = 3,
    backoff: float = 2.0,
    ok_statuses: tuple[int, ...] = (200,),
) -> requests.Response:
    """HTTP request with bounded exponential backoff (2 s, 4 s, 8 s).

    Retries only on network errors and 5xx responses, never on 4xx, so a
    blocked or missing resource is not hammered.
    """
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = session().request(
                method, url, params=params, json=json_body, data=data, headers=headers, timeout=timeout
            )
            if r.status_code in ok_statuses:
                return r
            if 400 <= r.status_code < 500:
                raise FetchError(f"{url} returned HTTP {r.status_code}")
            last = FetchError(f"{url} returned HTTP {r.status_code}")
        except requests.RequestException as exc:  # network level
            last = exc
        time.sleep(backoff * (2**attempt))
    raise FetchError(f"{url} failed after {retries} attempts: {last}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest() -> dict[str, dict[str, Any]]:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {}


def save_manifest(manifest: dict[str, dict[str, Any]]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    ordered = dict(sorted(manifest.items()))
    MANIFEST.write_text(json.dumps(ordered, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass
class RawRecord:
    path: Path
    source_url: str
    retrieved_at: str
    sha256: str
    params: dict[str, Any] | None = None


def register(
    path: Path,
    source_url: str,
    params: dict[str, Any] | None = None,
    retrieved_at: str | None = None,
    note: str | None = None,
) -> RawRecord:
    """Add or update the manifest entry for a raw file already on disk."""
    data = path.read_bytes()
    rel = path.resolve().relative_to(RAW).as_posix()
    stamp = retrieved_at or now_utc()
    entry: dict[str, Any] = {
        "source_url": source_url,
        "retrieved_at": stamp,
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "redistributed": rel.split("/")[0] not in NON_REDISTRIBUTABLE,
    }
    if params:
        entry["params"] = params
    if note:
        entry["note"] = note
    manifest = load_manifest()
    manifest[rel] = entry
    save_manifest(manifest)
    return RawRecord(path, source_url, stamp, entry["sha256"], params)


def register_many(entries: list[tuple[Path, str, dict[str, Any] | None]]) -> None:
    """Register many files with one manifest write (used for large batches)."""
    manifest = load_manifest()
    stamp = now_utc()
    for path, url, params in entries:
        data = path.read_bytes()
        rel = path.resolve().relative_to(RAW).as_posix()
        entry: dict[str, Any] = {
            "source_url": url,
            "retrieved_at": stamp,
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "redistributed": rel.split("/")[0] not in NON_REDISTRIBUTABLE,
        }
        if params:
            entry["params"] = params
        manifest[rel] = entry
    save_manifest(manifest)


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def manifest_entry(path: Path) -> dict[str, Any] | None:
    rel = path.resolve().relative_to(RAW).as_posix()
    return load_manifest().get(rel)


def reconcile(folder: Path, pattern: str, url_for) -> int:
    """Register cached files under ``folder`` that have no manifest entry (for
    example after an interrupted or parallel download). Retrieval time is taken
    from the file's modification time."""
    manifest = load_manifest()
    added = 0
    for path in sorted(folder.glob(pattern)):
        rel = path.resolve().relative_to(RAW).as_posix()
        if rel in manifest:
            continue
        data = path.read_bytes()
        stamp = (
            datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        manifest[rel] = {
            "source_url": url_for(path),
            "retrieved_at": stamp,
            "sha256": sha256_bytes(data),
            "bytes": len(data),
            "redistributed": rel.split("/")[0] not in NON_REDISTRIBUTABLE,
        }
        added += 1
    if added:
        save_manifest(manifest)
    return added
