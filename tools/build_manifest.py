"""Build deterministic metadata for the published QCF v4 SVG corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE_DIR = ROOT / "mushaf-v4"
THEME_DIR = ROOT / "themes-v4"
MANIFEST = ROOT / "manifest.json"
PAGE_COUNT = 604
PAGE_NAME = re.compile(r"page-(\d{3})\.svg$")


def page_paths() -> list[Path]:
    paths = sorted(PAGE_DIR.glob("page-*.svg"))
    expected = [PAGE_DIR / f"page-{page:03d}.svg" for page in range(1, PAGE_COUNT + 1)]
    if paths != expected:
        missing = [path.name for path in expected if not path.exists()]
        extra = [path.name for path in paths if path not in expected]
        details = []
        if missing:
            details.append(f"missing {len(missing)} page(s), first: {missing[0]}")
        if extra:
            details.append(f"unexpected files: {', '.join(extra[:3])}")
        raise RuntimeError("invalid page corpus: " + "; ".join(details))
    return paths


def page_record(path: Path) -> dict[str, int | str]:
    payload = path.read_bytes()
    text = payload.decode("utf-8")
    match = PAGE_NAME.fullmatch(path.name)
    assert match is not None
    return {
        "page": int(match.group(1)),
        "file": path.as_posix().removeprefix(ROOT.as_posix() + "/"),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "ayahs": len(re.findall(r'class="q-ayah(?:\s|\")', text)),
        "words": len(re.findall(r'class="q-word(?:\s|\")', text)),
    }


def build_manifest() -> dict:
    pages = [page_record(path) for path in page_paths()]
    themes = sorted(
        path.stem for path in THEME_DIR.glob("*.json") if path.stem != "schema"
    )
    return {
        "schema_version": 1,
        "edition": "qcf-v4",
        "page_count": PAGE_COUNT,
        "page_pattern": "mushaf-v4/page-{page:03d}.svg",
        "view_box": [0, 0, 1000, 2231],
        "default_theme": "green-pink",
        "themes": themes,
        "total_bytes": sum(int(page["bytes"]) for page in pages),
        "pages": pages,
    }


def encoded(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if manifest.json is stale"
    )
    args = parser.parse_args(argv)
    current = encoded(build_manifest())
    if args.check:
        if not MANIFEST.exists() or MANIFEST.read_text(encoding="utf-8") != current:
            print("manifest.json is missing or stale", file=sys.stderr)
            return 1
        print(f"manifest matches {PAGE_COUNT} QCF v4 pages")
        return 0
    MANIFEST.write_text(current, encoding="utf-8", newline="\n")
    print(f"wrote {MANIFEST} for {PAGE_COUNT} QCF v4 pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
