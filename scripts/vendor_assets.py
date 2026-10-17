"""Fetch the pinned front-end libraries and fonts into site/assets (run once;
the results are committed). Library code is never loaded from a CDN at runtime.

- Apache ECharts 5.5.1 (Apache-2.0), dist/echarts.min.js
- Archivo variable font 5.3.0 from @fontsource-variable/archivo (SIL OFL 1.1)

One modification to the ECharts bundle: the two long-dash characters inside
its Chinese accessibility strings are written as JavaScript escapes
(\\u2014), which leaves the strings identical at runtime and keeps the
repository free of literal long dashes.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "site/assets/vendor/echarts-5.5.1/echarts.min.js": "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js",
    "site/assets/vendor/echarts-5.5.1/LICENSE": "https://cdn.jsdelivr.net/npm/echarts@5.5.1/LICENSE",
    "site/assets/fonts/archivo-latin-wdth-normal.woff2": "https://cdn.jsdelivr.net/npm/@fontsource-variable/archivo@5.3.0/files/archivo-latin-wdth-normal.woff2",
    "site/assets/fonts/archivo-latin-wdth-italic.woff2": "https://cdn.jsdelivr.net/npm/@fontsource-variable/archivo@5.3.0/files/archivo-latin-wdth-italic.woff2",
    "site/assets/fonts/OFL-Archivo.txt": "https://cdn.jsdelivr.net/npm/@fontsource-variable/archivo@5.3.0/LICENSE",
    "vendor/world-atlas-2.0.2/land-110m.json": "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/land-110m.json",
    "vendor/world-atlas-2.0.2/LICENSE": "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/LICENSE",
}


def escape_long_dashes(text: str) -> str:
    return text.replace("\u2014", "\\u2014").replace("\u2013", "\\u2013")


def main() -> int:
    for rel, url in FILES.items():
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        data = r.content
        if rel.endswith(".js"):
            data = escape_long_dashes(data.decode("utf-8")).encode("utf-8")
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(rel, hashlib.sha256(data).hexdigest()[:16], len(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
