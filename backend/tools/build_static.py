"""Build a static, server-less copy of VIPER for Netlify (or any static host).

    python backend/tools/build_static.py          -> ./dist

Output:
    dist/index.html, dist/src/...   the unchanged frontend
    dist/py/viper.zip               backend Python package + documentation,
                                    loaded by Pyodide in the browser
    dist/_headers                   cache rules for Netlify

Standard library only, so it runs on Netlify's build image without installs.
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DIST = ROOT / "dist"

# Server-only or dev-only parts that are not needed (or not importable) in the browser.
EXCLUDE_DIRS = {"tests", "tools", "data", "__pycache__"}
EXCLUDE_FILES = {"main.py", "conftest.py", "routes.py", "ws.py"}

HEADERS = """/py/*
  Cache-Control: no-cache
/src/*
  Cache-Control: no-cache
/index.html
  Cache-Control: no-cache
"""


def backend_files() -> list[Path]:
    out = []
    for p in sorted(BACKEND.rglob("*.py")):
        rel = p.relative_to(BACKEND)
        if set(rel.parts[:-1]) & EXCLUDE_DIRS or p.name in EXCLUDE_FILES:
            continue
        out.append(p)
    return out


def build(dist: Path = DIST) -> Path:
    if dist.exists():
        shutil.rmtree(dist)
    shutil.copytree(ROOT / "frontend", dist)
    (dist / "py").mkdir()
    bundle = dist / "py" / "viper.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        for p in backend_files():
            z.write(p, p.relative_to(ROOT).as_posix())
        for p in sorted((ROOT / "documentation").glob("*.md")):
            z.write(p, p.relative_to(ROOT).as_posix())
    (dist / "_headers").write_text(HEADERS, encoding="utf-8")
    return bundle


if __name__ == "__main__":
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DIST
    b = build(target)
    with zipfile.ZipFile(b) as z:
        n = len(z.namelist())
    print(f"Static build written to {target} ({n} files in {b.name}, {b.stat().st_size // 1024} KB)")
