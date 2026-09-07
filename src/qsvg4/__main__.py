"""Build, inspect and verify the published QCF v4 SVG corpus."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import __version__, build as builder, rules as ruleset
from . import sources, stylesheet, theme as theming, verify as checks

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "mushaf-v4"
THEME_DIR = ROOT / "themes-v4"


def _pages(spec: str) -> list[int]:
    """Parse ``1,2,10-20`` into a validated, de-duplicated page list."""
    pages: list[int] = []
    try:
        for raw in spec.split(","):
            part = raw.strip()
            if not part:
                raise ValueError("empty page item")
            if "-" in part:
                start_text, end_text = part.split("-", 1)
                start, end = int(start_text), int(end_text)
                if start > end:
                    raise ValueError(f"descending range {part!r}")
                pages.extend(range(start, end + 1))
            else:
                pages.append(int(part))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid page selection {spec!r}; use 1,2,10-20"
        ) from exc

    outside = [page for page in pages if not 1 <= page <= sources.PAGE_COUNT]
    if outside:
        raise argparse.ArgumentTypeError(
            f"page must be between 1 and {sources.PAGE_COUNT}: {outside[0]}"
        )
    return list(dict.fromkeys(pages))


def cmd_fetch(args: argparse.Namespace) -> int:
    sources.common_fonts()
    sources.words_db()
    for index, page in enumerate(args.pages, 1):
        sources.page_font(page)
        if not args.quiet and (index % 25 == 0 or index == len(args.pages)):
            print(f"  {index}/{len(args.pages)} page fonts")
    print(f"fetched inputs for {len(args.pages)} page(s) under data/")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else OUT_DIR
    failures = 0
    for page in args.pages:
        try:
            path = builder.write_page(
                page, out, theme_name=args.theme, tajweed=args.tajweed
            )
            if not args.quiet:
                print(f"page {page:>3} -> {path}")
        except Exception as exc:  # keep a full-corpus build going
            failures += 1
            print(
                f"page {page:>3} FAILED: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
    print(f"built {len(args.pages) - failures} of {len(args.pages)} pages into {out}")
    return 1 if failures else 0


def cmd_verify(args: argparse.Namespace) -> int:
    bad = 0
    for page in args.pages:
        built = builder.build_page(page, theme_name=args.theme)
        result = checks.check(page, built.svg)
        same, detail = checks.same_words_as_v2(page, built.layout)
        fits, fit_detail = checks.fits_the_page(built.layout, page)
        ordered, order_detail = checks.bands_in_order(page, built.layout)
        if result.ok and same and fits and ordered:
            if not args.quiet:
                print(f"page {page:>3}: ok ({len(result.passed) + 3} checks, {detail})")
            continue
        bad += 1
        print(f"page {page:>3}: FAILED")
        for failure in result.failed:
            print(f"    x {failure}")
        if not same:
            print(f"    x word sequence differs: {detail}")
        if not fits:
            print(f"    x {fit_detail}")
        if not ordered:
            print(f"    x {order_detail}")
    print(f"{len(args.pages) - bad} of {len(args.pages)} pages pass")
    return 1 if bad else 0


def cmd_retheme(args: argparse.Namespace) -> int:
    source = Path(args.file)
    svg = source.read_text(encoding="utf-8")
    updated = stylesheet.swap(svg, theming.load(args.theme).block())
    updated, count = re.subn(
        r'(<svg\b[^>]*\bdata-theme=")[^"]*(")',
        rf"\g<1>{args.theme}\g<2>",
        updated,
        count=1,
    )
    if count != 1:
        raise ValueError(f"{source} does not declare an SVG data-theme attribute")
    target = Path(args.out) if args.out else source
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated, encoding="utf-8")
    print(f"rethemed {source} -> {args.theme} at {target}")
    return 0


def cmd_theme_block(args: argparse.Namespace) -> int:
    print(theming.load(args.theme).block())
    return 0


def cmd_list_themes(_args: argparse.Namespace) -> int:
    for name in theming.names():
        active = theming.load(name)
        print(f"{name}\t{active.title}\t{'dark' if active.dark else 'light'}")
    return 0


def cmd_schema(_args: argparse.Namespace) -> int:
    """Write the machine-readable theme and interaction contract."""
    import json

    payload = {
        "markers": {"begin": stylesheet.BEGIN, "end": stylesheet.END},
        "edition": "qcf-v4",
        "tokens": stylesheet.schema(),
        "defaults": theming.load(theming.DEFAULT).colors,
        "tajweed": {
            "root_class": "q-tajweed",
            "plain_class": "q-tajweed-plain",
            "tokens": list(ruleset.TOKENS),
            "note_class": "q-note",
            "note": (
                "q-tajweed enables recitation-rule colours. q-tajweed-plain "
                "sets ordinary vowel, pause and divine-name ink to the base "
                "text colour so only recitation rules remain coloured."
            ),
        },
        "layer_toggles": [
            {
                "root_class": "q-no-frame",
                "element_id": "q-frame",
                "holds": "border",
            },
            {
                "root_class": "q-no-chrome",
                "element_id": "q-chrome",
                "holds": "running head and page number",
            },
            {
                "root_class": "q-no-illumination",
                "element_id": "q-illumination",
                "holds": "opening decoration on pages 1-2",
            },
        ],
        "addressable_layers": {
            "catchword": "q-catchword",
            "surah_openings": "q-openings",
            "text": "q-text",
        },
        "highlight": {
            "ayah": {
                "element": "g.q-ayah",
                "id": "q-a{surah}-{ayah}",
                "class": "is-active",
            },
            "word": {
                "element": "g.q-word",
                "id": "q-w{surah}-{ayah}-{word}",
                "class": "is-active",
            },
            "selected": {"element": "g.q-word", "class": "is-selected"},
        },
    }
    target = THEME_DIR / "schema.json"
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {target} ({len(payload['tokens'])} tokens)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quransvg",
        description="Build, inspect and verify the QCF v4 Quran SVG corpus.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("schema", help="regenerate themes-v4/schema.json").set_defaults(
        handler=cmd_schema
    )
    sub.add_parser("list-themes", help="list bundled themes").set_defaults(
        handler=cmd_list_themes
    )

    block = sub.add_parser(
        "theme-block", help="print a ready-to-insert CSS theme block"
    )
    block.add_argument("--theme", default=theming.DEFAULT, choices=theming.names())
    block.set_defaults(handler=cmd_theme_block)

    retheme = sub.add_parser(
        "retheme", help="replace only the theme block in an SVG"
    )
    retheme.add_argument("file")
    retheme.add_argument("--theme", required=True, choices=theming.names())
    retheme.add_argument("--out")
    retheme.set_defaults(handler=cmd_retheme)

    for name, handler in (
        ("build", cmd_build),
        ("verify", cmd_verify),
        ("fetch", cmd_fetch),
    ):
        command = sub.add_parser(name)
        command.add_argument(
            "pages",
            type=_pages,
            help="page, list or range (for example 248 or 1,2,10-20)",
        )
        command.add_argument("--quiet", action="store_true")
        if name in {"build", "verify"}:
            command.add_argument(
                "--theme", default=theming.DEFAULT, choices=theming.names()
            )
        if name == "build":
            command.add_argument("--tajweed", action="store_true")
            command.add_argument("--out")
        command.set_defaults(handler=handler)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
