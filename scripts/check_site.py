"""Static checks on the site and the repository, run in CI and by `make site-check`.

1. Every local file referenced by index.html, the CSS and the JavaScript modules exists.
2. Nothing is loaded from another host at runtime (no CDN).
3. Every view's JSON exists, parses and stays small enough to load on demand.
4. JavaScript modules parse (node --check), when Node is available.
5. No long dashes (U+2014, U+2013) in tracked text files, the site or the PDF text.
6. No placeholder markers in code, data or site copy.

Exit status 1 on any failure.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:  # the PDF text check then fails with a clear message
    PdfReader = None

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
VIEWS = ["meta", "overview", "window", "freight", "mill", "calculator", "method", "downloads"]
MAX_VIEW_KB = 400
LONG_DASHES = ("—", "–")
PLACEHOLDERS = re.compile(r"\b(TODO|FIXME|TBD|lorem ipsum|placeholder text)\b", re.IGNORECASE)
TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".mjs",
    ".css",
    ".html",
    ".md",
    ".json",
    ".csv",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
    ".svg",
}
# Third-party files kept byte for byte (their licences are part of them).
VENDORED = ("site/assets/vendor/", "site/assets/fonts/", "vendor/")

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def check_references() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="([^"#][^"]*)"', html)
    for ref in refs:
        if ref.startswith(("http://", "https://")):
            if re.search(r"<(script|link)[^>]+(src|href)=\"" + re.escape(ref), html):
                fail(f"index.html loads a remote resource: {ref}")
            continue
        if not (SITE / ref).exists():
            fail(f"index.html references a missing file: {ref}")
    css = (SITE / "assets/css/site.css").read_text(encoding="utf-8")
    for ref in re.findall(r"url\(\"?([^\")]+)\"?\)", css):
        if ref.startswith(("http", "//")):
            fail(f"site.css loads a remote resource: {ref}")
        elif not (SITE / "assets/css" / ref).resolve().exists():
            fail(f"site.css references a missing file: {ref}")
    for js in (SITE / "assets/js").rglob("*.js"):
        text = js.read_text(encoding="utf-8")
        for ref in re.findall(r"import\s*(?:[^'\"]*from\s*)?\(?['\"]([^'\"]+)['\"]", text):
            if ref.startswith(("http", "//")):
                fail(f"{js.relative_to(ROOT)} imports a remote module: {ref}")
            elif not (js.parent / ref).resolve().exists():
                fail(f"{js.relative_to(ROOT)} imports a missing module: {ref}")
        if re.search(r"fetch\(\s*['\"`]https?://", text):
            fail(f"{js.relative_to(ROOT)} fetches from another host")


def check_data() -> None:
    for name in VIEWS:
        path = SITE / "data" / f"{name}.json"
        if not path.exists():
            fail(f"missing site/data/{name}.json")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            fail(f"site/data/{name}.json does not parse: {e}")
        kb = path.stat().st_size / 1024
        if kb > MAX_VIEW_KB:
            fail(f"site/data/{name}.json is {kb:.0f} KB (limit {MAX_VIEW_KB})")
    meta = json.loads((SITE / "data/meta.json").read_text(encoding="utf-8"))
    for key in ("build_date", "version", "asof", "sources"):
        if key not in meta:
            fail(f"meta.json lacks {key}")
    dl = json.loads((SITE / "data/downloads.json").read_text(encoding="utf-8"))
    for f in dl["files"]:
        if not (SITE / "downloads" / f["file"]).exists():
            fail(f"downloads.json lists a missing file: {f['file']}")


def check_js_syntax() -> None:
    node = shutil.which("node")
    if not node:
        print("node not found: JavaScript syntax check skipped")
        return
    with tempfile.TemporaryDirectory() as tmp:
        for js in (SITE / "assets/js").rglob("*.js"):
            copy = Path(tmp) / (js.stem + ".mjs")
            copy.write_text(js.read_text(encoding="utf-8"), encoding="utf-8")
            r = subprocess.run([node, "--check", str(copy)], capture_output=True, text=True, check=False)
            if r.returncode != 0:
                fail(f"{js.relative_to(ROOT)} does not parse: {r.stderr.strip()[:300]}")


def tracked_files() -> list[Path]:
    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False)
    files = [ROOT / p for p in r.stdout.splitlines()] if r.returncode == 0 else []
    files += [p for p in SITE.rglob("*") if p.is_file()]
    files += [ROOT / "README.md"] if (ROOT / "README.md").exists() else []
    return sorted({p for p in files if p.exists()})


def pdf_text(path: Path) -> str | None:
    if PdfReader is None:
        return None
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def check_text() -> None:
    dash_hits, placeholder_hits = [], []
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() == ".pdf":
            text = pdf_text(path)
            if text is None:
                fail(f"cannot extract text from {rel} (install pypdf)")
                continue
        elif path.suffix.lower() in TEXT_SUFFIXES or path.name in ("Makefile", "LICENSE"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
        else:
            continue
        for ch in LONG_DASHES:
            if ch in text:
                dash_hits.append(f"{rel}: {text.count(ch)} x U+{ord(ch):04X}")
        if not rel.startswith(VENDORED) and rel != "scripts/check_site.py":
            for m in PLACEHOLDERS.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                placeholder_hits.append(f"{rel}:{line}: {m.group(0)}")
    for h in dash_hits:
        fail(f"long dash: {h}")
    for h in placeholder_hits:
        fail(f"placeholder marker: {h}")


def main() -> int:
    check_references()
    check_data()
    check_js_syntax()
    check_text()
    if errors:
        print("Site check failed:")
        for e in errors:
            print(f"  {e}")
        return 1
    print("Site check passed: references, data, JavaScript syntax, long dashes (0), placeholders (0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
