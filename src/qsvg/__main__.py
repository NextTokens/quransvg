"""Command line entry point: python -m qsvg <command>."""

from __future__ import annotations

import argparse
import gzip
import sys
import time
from pathlib import Path

from . import sources, theme as theming
from .build import build_page
from .verify import run as run_checks

ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = ROOT / "build"


def _out_path(page: int, out_dir: Path) -> Path:
    # One file per page. Themes are not baked into separate sets; the app
    # swaps the theme block inside this one file.
    return out_dir / f"page-{page:03d}.svg"


def cmd_build(args: argparse.Namespace) -> int:
    out_dir = Path(args.out or BUILD_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    from . import build as build_mod

    build_mod.LOOK = getattr(args, "look", "classic")
    pages = _page_list(args.pages)
    total_raw = total_gz = 0
    started = time.time()

    for page in pages:
        built = build_page(page, args.theme, simplify=args.simplify)
        destination = _out_path(page, out_dir)
        destination.write_text(built.svg, encoding="utf-8")
        raw = len(built.svg.encode("utf-8"))
        packed = len(gzip.compress(built.svg.encode("utf-8")))
        total_raw += raw
        total_gz += packed
        if len(pages) <= 20 or page % 50 == 0:
            print(
                f"  {destination.name}  {built.word_count:>4} words  "
                f"{raw / 1024:>7,.0f} KB  gzip {packed / 1024:>6,.0f} KB"
            )

    elapsed = time.time() - started
    print(
        f"\n{len(pages)} page(s) in {elapsed:.1f}s  "
        f"total {total_raw / 1024 / 1024:.1f} MB, gzip {total_gz / 1024 / 1024:.1f} MB"
    )
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    pages = _page_list(args.pages)
    print(f"fetching data and fonts for {len(pages)} page(s)...")
    sources.chapters()
    sources.layout_db()
    for index, page in enumerate(pages, 1):
        sources.page_data(page)
        sources.page_font(page)
        if index % 25 == 0 or index == len(pages):
            print(f"  {index}/{len(pages)}")
    print("cached under data/")
    return 0


def cmd_retheme(args: argparse.Namespace) -> int:
    target = Path(args.file)
    svg = target.read_text(encoding="utf-8")
    swapped = theming.swap(svg, theming.load(args.theme))
    destination = Path(args.out) if args.out else target
    destination.write_text(swapped, encoding="utf-8")
    changed = sum(1 for a, b in zip(svg, swapped) if a != b)
    print(
        f"rethemed {target.name} -> {args.theme} "
        f"({changed:,} of {len(svg):,} characters differ; no geometry touched)"
    )
    return 0


def cmd_theme_block(args: argparse.Namespace) -> int:
    """Print the block an app would splice in to apply a theme."""
    print(theming.load(args.theme).block())
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    """Write themes/schema.json: token -> the rules it drives, plus defaults."""
    import json

    from . import stylesheet

    payload = {
        "markers": {"begin": stylesheet.BEGIN, "end": stylesheet.END},
        "tokens": stylesheet.schema(),
        "defaults": theming.load(theming.DEFAULT).all_colors,
        # Every removable layer, not just the border: hiding #q-frame leaves the
        # running head, the page number and the opening medallion in place, and
        # an app that wants a bare page needs to know they are separate.
        "layer_toggles": [
            {"root_class": "q-no-frame", "element_id": "q-frame",
             "holds": "the illuminated border"},
            {"root_class": "q-no-chrome", "element_id": "q-chrome",
             "holds": "running head, juz label, page number"},
            {"root_class": "q-no-illumination", "element_id": "q-illumination",
             "holds": "the opening medallion on pages 1-2"},
        ],
        "addressable_layers": {
            "catchword": "q-catchword",
            "surah_openings": "q-openings",
            "text": "q-text",
        },
        "frame_toggle": {"root_class": "q-no-frame", "element_id": "q-frame"},
        "highlight": {
            "ayah": {"element": "g.q-ayah", "id": "q-a{surah}-{ayah}", "class": "is-active"},
            "word": {"element": "g.q-word", "id": "q-w{surah}-{ayah}-{word}", "class": "is-active"},
            "selected": {"element": "g.q-word", "class": "is-selected"},
            "marker": {"element": "g.q-mark", "id": "q-e{surah}-{ayah}"},
        },
    }
    target = ROOT / "themes" / "schema.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target} ({len(payload['tokens'])} tokens)")
    return 0


def cmd_themes(args: argparse.Namespace) -> int:
    for name in theming.available():
        active = theming.load(name)
        kind = "dark " if active.dark else "light"
        print(f"  {name:10s} [{kind}] {active.title:14s} {active.description}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    pages = _page_list(args.pages)
    print(f"verifying across pages {pages}...")
    report = run_checks(pages)
    print(report.render())
    return 0 if report.ok else 1


def _page_list(spec: str | None) -> list[int]:
    if not spec or spec == "248":
        return [248]
    if spec == "all":
        return list(range(1, sources.PAGE_COUNT + 1))
    pages: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            start, end = chunk.split("-")
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(chunk))
    return pages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qsvg", description="Generate the Madani mushaf as themeable SVG."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="render page(s) to SVG")
    build.add_argument("pages", nargs="?", default="248",
                       help="page, list, range or 'all' (e.g. 248, 1-10, all)")
    build.add_argument("--theme", default=theming.DEFAULT,
                       help="theme written into the file's swappable block")
    build.add_argument("--simplify", type=float, default=None,
                       help="outline tolerance in font units (default 12)")
    build.add_argument("--out", default=None, help="output directory")
    build.add_argument("--look", default="classic",
                       choices=("classic", "olive-gold", "green-pink"),
                       help="which border and surah band to draw")
    build.set_defaults(func=cmd_build)

    fetch = sub.add_parser("fetch", help="download page data and fonts")
    fetch.add_argument("pages", nargs="?", default="248")
    fetch.set_defaults(func=cmd_fetch)

    retheme = sub.add_parser("retheme", help="recolour an already-built SVG in place")
    retheme.add_argument("file")
    retheme.add_argument("--theme", required=True)
    retheme.add_argument("--out", default=None)
    retheme.set_defaults(func=cmd_retheme)

    themes = sub.add_parser("themes", help="list available themes")
    themes.set_defaults(func=cmd_themes)

    block = sub.add_parser("theme-block", help="print a theme's swappable block")
    block.add_argument("--theme", default=theming.DEFAULT)
    block.set_defaults(func=cmd_theme_block)

    schema = sub.add_parser("schema", help="write themes/schema.json for the app")
    schema.set_defaults(func=cmd_schema)

    verify = sub.add_parser("verify", help="run the consistency checks")
    verify.add_argument("pages", nargs="?", default="248")
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    if getattr(args, "simplify", None) is None and args.command == "build":
        from .build import SIMPLIFY_TOLERANCE

        args.simplify = SIMPLIFY_TOLERANCE
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
