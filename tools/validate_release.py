"""Validate the public QCF v4 corpus without downloading build inputs."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from build_manifest import MANIFEST, PAGE_COUNT, ROOT, build_manifest, encoded, page_paths

SVG = "{http://www.w3.org/2000/svg}"
HEX = re.compile(r"#[0-9A-Fa-f]{6}$")
LOCATION = re.compile(r"(\d+):(\d+):(\d+)$")
REQUIRED_IDS = {"q-ground", "q-frame", "q-page", "q-chrome", "q-openings", "q-text"}


def page_errors(path: Path, page: int) -> list[str]:
    errors: list[str] = []
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8")
        root = ET.fromstring(text)
    except (UnicodeDecodeError, ET.ParseError) as exc:
        return [f"not valid UTF-8 SVG: {exc}"]

    if root.tag != SVG + "svg":
        errors.append("root element is not SVG")
    expected = {
        "data-page": str(page),
        "data-edition": "qcf-v4",
        "viewBox": "0 0 1000 2231",
        "role": "img",
    }
    for name, value in expected.items():
        if root.get(name) != value:
            errors.append(f"{name} is {root.get(name)!r}; expected {value!r}")
    if root.get("aria-labelledby") != "q-title q-desc":
        errors.append("accessible title/description link is missing")

    if "<text" in text or "font-family" in text or "@font-face" in text:
        errors.append("contains a runtime font or <text> dependency")
    if "var(" in text:
        errors.append("contains CSS var(), which is unsupported by target renderers")
    if text.count("/* THEME:BEGIN") != 1 or text.count("/* THEME:END */") != 1:
        errors.append("does not contain exactly one replaceable theme block")

    ids: list[str] = []
    words = 0
    ayahs = 0
    for element in root.iter():
        element_id = element.get("id")
        if element_id:
            ids.append(element_id)
        classes = set((element.get("class") or "").split())
        if "q-ayah" in classes:
            ayahs += 1
            if not element.get("data-ayah"):
                errors.append(f"{element_id or 'ayah'} has no data-ayah")
        if "q-word" not in classes:
            continue
        words += 1
        location = element.get("data-loc", "")
        match = LOCATION.fullmatch(location)
        if not match:
            errors.append(f"{element_id or 'word'} has invalid data-loc {location!r}")
        elif element_id != f"q-w{match.group(1)}-{match.group(2)}-{match.group(3)}":
            errors.append(f"word id {element_id!r} does not match data-loc {location!r}")
        try:
            x, y, width, height = map(float, element.get("data-box", "").split())
            if width <= 0 or height <= 0 or x < -100 or y < -100:
                raise ValueError
        except ValueError:
            errors.append(f"{element_id or 'word'} has invalid data-box")

    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate id: {duplicates[0]}")
    missing_ids = REQUIRED_IDS - set(ids)
    if missing_ids:
        errors.append(f"missing layer(s): {', '.join(sorted(missing_ids))}")
    if not words or not ayahs:
        errors.append(f"empty addressable content ({words} words, {ayahs} ayahs)")
    return errors


def theme_errors() -> list[str]:
    errors: list[str] = []
    theme_dir = ROOT / "themes-v4"
    schema = json.loads((theme_dir / "schema.json").read_text(encoding="utf-8"))
    tokens = set(schema.get("tokens", {}))
    defaults = set(schema.get("defaults", {}))
    if schema.get("edition") != "qcf-v4":
        errors.append("themes-v4/schema.json has the wrong edition")
    if tokens != defaults:
        errors.append("theme schema defaults do not cover exactly the declared tokens")

    theme_names = []
    for path in sorted(theme_dir.glob("*.json")):
        if path.stem == "schema":
            continue
        theme_names.append(path.stem)
        data = json.loads(path.read_text(encoding="utf-8"))
        colors = data.get("colors", {})
        if set(colors) != tokens:
            errors.append(f"{path.name} does not define exactly the schema tokens")
        invalid = [value for value in colors.values() if not HEX.fullmatch(value)]
        if invalid:
            errors.append(f"{path.name} contains an invalid colour: {invalid[0]!r}")
    if theme_names != ["blue", "green-pink", "night", "olive-gold", "sepia"]:
        errors.append(f"unexpected bundled themes: {theme_names}")
    return errors


def main() -> int:
    failures: list[str] = []
    try:
        paths = page_paths()
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    for page, path in enumerate(paths, 1):
        failures.extend(f"{path.name}: {error}" for error in page_errors(path, page))
    failures.extend(theme_errors())

    actual_manifest = encoded(build_manifest())
    if not MANIFEST.exists() or MANIFEST.read_text(encoding="utf-8") != actual_manifest:
        failures.append("manifest.json is missing or stale; run tools/build_manifest.py")

    if failures:
        for failure in failures[:50]:
            print(f"FAIL: {failure}", file=sys.stderr)
        if len(failures) > 50:
            print(f"...and {len(failures) - 50} more", file=sys.stderr)
        return 1

    manifest = json.loads(actual_manifest)
    print(
        f"PASS: {PAGE_COUNT} QCF v4 pages, "
        f"{sum(page['ayahs'] for page in manifest['pages']):,} ayah groups, "
        f"{sum(page['words'] for page in manifest['pages']):,} words, "
        f"{manifest['total_bytes'] / 1024 / 1024:.1f} MiB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
