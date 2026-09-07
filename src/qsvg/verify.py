"""Checks that keep the mushaf consistent across all 604 pages.

The project's central promise is that the background, the frame and the ayah
decoration are the same on every page, and that a theme changes colour and
nothing else. Those are the kind of promises that quietly stop being true, so
they are asserted mechanically rather than trusted.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import numerals, shell, sources, theme as theming
from .build import AMIRI, DEFAULT_THEME, build_page
from .geometry import DEFAULT as DEFAULT_GEOMETRY

SHELL_RE = re.compile(r'<g id="q-frame">(.*?)</g>\s*<g id="q-', re.S)
DEFS_RE = re.compile(r"<defs>(.*?)</defs>", re.S)
STYLE_RE = re.compile(r"<style>(.*?)</style>", re.S)
THEME_BLOCK_RE = re.compile(r"/\* THEME:BEGIN.*?/\* THEME:END \*/", re.S)
# A literal colour is a theming leak; a url(#...) points at a gradient or
# pattern whose own stops carry theme classes, so it is not one.
PAINT_RE = re.compile(r'\s(?:fill|stroke)="(?!none\b|url\()([^"]+)"')


@dataclass
class Result:
    name: str
    passed: bool
    detail: str


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.results.append(Result(name, passed, detail))

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results)

    def render(self) -> str:
        lines = []
        for result in self.results:
            mark = "PASS" if result.passed else "FAIL"
            lines.append(f"  [{mark}] {result.name}: {result.detail}")
        lines.append("")
        lines.append("all checks passed" if self.ok else "FAILURES PRESENT")
        return "\n".join(lines)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=None)
def _svg(page: int, theme: str = DEFAULT_THEME) -> str:
    """Build once per (page, theme) per run.

    Several checks sweep the same page list; over a whole surah that was three
    full rebuilds of every page. `check_build_is_reproducible` deliberately
    calls `build_page` directly instead, or it would compare a value with
    itself."""
    return build_page(page, theme).svg


def check_shell_is_page_independent() -> Result:
    """The shell must not be able to vary: it is built from constants alone."""
    first = shell.build(DEFAULT_GEOMETRY) + shell.defs(DEFAULT_GEOMETRY)
    again = shell.build(DEFAULT_GEOMETRY) + shell.defs(DEFAULT_GEOMETRY)
    same = first == again
    return Result(
        "shell is deterministic",
        same,
        f"sha {_digest(first)}, {len(first):,} bytes",
    )


def check_pages_share_one_shell(pages: list[int], theme_name: str = DEFAULT_THEME) -> list[Result]:
    """Every page's shell subtree and <defs> must hash identically."""
    shells: dict[str, list[int]] = {}
    defs: dict[str, list[int]] = {}
    for page in pages:
        svg = _svg(page, theme_name)
        shell_match = SHELL_RE.search(svg)
        defs_match = DEFS_RE.search(svg)
        if not shell_match or not defs_match:
            return [Result("pages share one shell", False, f"page {page}: no shell/defs found")]
        shells.setdefault(_digest(shell_match.group(1)), []).append(page)
        defs.setdefault(_digest(defs_match.group(1)), []).append(page)

    return [
        Result(
            "every page shares one shell",
            len(shells) == 1,
            f"{len(shells)} distinct shell hash(es) across pages {pages}"
            + ("" if len(shells) == 1 else f": {shells}"),
        ),
        Result(
            "every page shares one defs",
            len(defs) == 1,
            f"{len(defs)} distinct defs hash(es) across pages {pages}"
            + ("" if len(defs) == 1 else f": {defs}"),
        ),
    ]


def check_theme_changes_only_colour(page: int = 248) -> list[Result]:
    """Swapping themes must touch the theme block and nothing else."""
    base = build_page(page, "green-pink").svg
    results = []
    for name in theming.available():
        if name == DEFAULT_THEME:
            continue
        swapped = theming.swap(base, theming.load(name))
        stripped_base = THEME_BLOCK_RE.sub("", base)
        stripped_swapped = THEME_BLOCK_RE.sub("", swapped)
        results.append(
            Result(
                f"retheme to {name} changes only colour",
                stripped_base == stripped_swapped,
                f"{len(stripped_base):,} bytes outside the theme block unchanged",
            )
        )
    return results


def check_no_hardcoded_paint(page: int = 248) -> Result:
    """No element may carry its own colour; all paint comes from the theme."""
    svg = build_page(page, "green-pink").svg
    offenders = sorted(set(PAINT_RE.findall(svg)))
    return Result(
        "no hardcoded paint attributes",
        not offenders,
        "all paint flows through CSS classes"
        if not offenders
        else f"found literal paint: {offenders[:5]}",
    )


def check_themes_are_complete() -> Result:
    """Every theme defines every token, so nothing renders unpainted."""
    problems = []
    for name in theming.available():
        try:
            theming.load(name)
        except (ValueError, FileNotFoundError) as exc:
            problems.append(f"{name}: {exc}")
    return Result(
        "themes define every token",
        not problems,
        f"{len(theming.available())} themes x {len(theming.TOKENS)} tokens"
        if not problems
        else "; ".join(problems),
    )


def check_build_is_reproducible(page: int = 248) -> Result:
    """Building twice must produce identical bytes."""
    first = build_page(page, "green-pink").svg
    second = build_page(page, "green-pink").svg
    return Result(
        "build is byte-reproducible",
        first == second,
        f"sha {_digest(first)}",
    )


def check_text_is_addressable(page: int = 248) -> list[Result]:
    """Every word must be one element with a stable id, grouped by ayah."""
    built = build_page(page, "green-pink")
    svg = built.svg
    word_ids = re.findall(r'<g class="q-word(?: q-lafz)?" id="(q-w[\d-]+)"', svg)
    ayah_groups = re.findall(r'<g class="q-ayah" id="(q-a[\d-]+)"', svg)
    marks = re.findall(r'<g class="q-mark" id="(q-e[\d-]+)"', svg)
    expected_words = sum(1 for w in built.layout.words if w.kind == "word")
    expected_marks = sum(1 for w in built.layout.words if w.kind == "end")

    return [
        Result(
            "one element per word",
            len(word_ids) == expected_words == len(set(word_ids)),
            f"{len(word_ids)} word groups, {len(set(word_ids))} unique, expected {expected_words}",
        ),
        Result(
            "ink layers separated",
            len(re.findall(r'class="q-rasm"', svg)) == expected_words,
            f"{len(re.findall(chr(99)+'lass=\"q-rasm\"', svg))} rasm, "
            f"{len(re.findall(chr(99)+'lass=\"q-tashkeel\"', svg))} tashkeel, "
            f"{len(re.findall(chr(99)+'lass=\"q-waqf\"', svg))} waqf layers",
        ),
        Result(
            "words grouped by ayah",
            len(ayah_groups) == len(set(ayah_groups)) == expected_marks,
            f"{len(ayah_groups)} ayah groups, {expected_marks} ayah markers",
        ),
        Result(
            "ayah markers addressable",
            len(marks) == expected_marks,
            f"{len(marks)} markers with stable ids",
        ),
    ]


def check_highlight_hooks(page: int = 248) -> Result:
    """The stylesheet must define the recitation states the app toggles."""
    svg = build_page(page, "green-pink").svg
    style = STYLE_RE.search(svg)
    needed = (
        ".q-ayah.is-active .q-rasm",
        ".q-ayah.is-active .q-tashkeel",
        ".q-word.is-active .q-rasm",
        ".q-word.is-selected .q-rasm",
        ".q-ayah.is-active .q-ayah-ring",
        ".q-word.q-lafz .q-rasm",
    )
    body = style.group(1) if style else ""
    missing = [rule for rule in needed if rule not in body]
    return Result(
        "highlight states defined",
        not missing,
        "ayah, word and selection states all present"
        if not missing
        else f"missing: {missing}",
    )


def check_no_css_variables(page: int = 248) -> Result:
    """The stylesheet must not lean on var(): native renderers draw it black."""
    svg = build_page(page, "green-pink").svg
    hits = re.findall(r"var\(--", svg)
    return Result(
        "no CSS custom properties",
        not hits,
        "every colour is a literal class rule" if not hits else f"{len(hits)} var() uses",
    )


def check_colour_only_in_theme_block(page: int = 248) -> Result:
    """All colour lives between the markers; nothing outside carries any."""
    svg = build_page(page, "green-pink").svg
    block = THEME_BLOCK_RE.search(svg)
    outside = THEME_BLOCK_RE.sub("", svg)
    stray = re.findall(r"(?:fill|stroke|stop-color)\s*[:=]\s*\"?#[0-9a-fA-F]{3,8}", outside)
    return Result(
        "all colour inside the theme block",
        bool(block) and not stray,
        "swapping the block recolours everything" if not stray else f"stray: {stray[:3]}",
    )


def check_frame_is_removable(page: int = 248) -> Result:
    """Hiding #q-frame must leave a clean page with nothing painted outside."""
    svg = build_page(page, "green-pink").svg
    has_layers = '<g id="q-ground">' in svg and '<g id="q-frame">' in svg
    has_toggle = ".q-no-frame #q-frame{display:none}" in svg
    has_box = 'data-text-box="' in svg
    return Result(
        "frame is a removable layer",
        has_layers and has_toggle and has_box,
        "#q-ground / #q-frame split, q-no-frame toggle, data-text-box published"
        if has_layers and has_toggle and has_box
        else f"layers={has_layers} toggle={has_toggle} box={has_box}",
    )


def check_no_font_dependency(page: int = 248) -> Result:
    """Nothing may rely on a font being installed on the device."""
    svg = build_page(page, "green-pink").svg
    problems = []
    if "<text" in svg:
        problems.append("<text> element present")
    if "font-family" in svg:
        problems.append("font-family declared")
    if "@font-face" in svg:
        problems.append("@font-face declared")
    return Result(
        "no font dependency",
        not problems,
        "all glyphs are outlines" if not problems else "; ".join(problems),
    )


def check_page_sides(pages: list[int]) -> list[Result]:
    """Recto and verso must differ only by the gutter shift.

    The side is carried by one transform on the page wrapper, so the shell
    itself stays identical between the two - a page cannot drift into being a
    third kind of page.
    """
    shifts: dict[str, set[float]] = {"recto": set(), "verso": set()}
    for page in pages:
        svg = _svg(page)
        side = re.search(r'data-side="(\w+)"', svg)
        shift = re.search(r'id="q-page" transform="translate\(([-\d.]+)', svg)
        if not side or not shift:
            return [Result("pages declare a side", False, f"page {page}: no side marked")]
        shifts[side.group(1)].add(float(shift.group(1)))

    used = {k: v for k, v in shifts.items() if v}
    single = all(len(v) == 1 for v in used.values())
    opposed = (
        len(used) < 2
        or sum(next(iter(v)) for v in used.values()) == 0
    )
    return [
        Result(
            "each side has one gutter",
            single,
            ", ".join(f"{k}={sorted(v)}" for k, v in used.items()),
        ),
        Result(
            "recto and verso mirror each other",
            opposed,
            "the two shifts are equal and opposite"
            if opposed
            else f"shifts do not mirror: {used}",
        ),
    ]


def check_boxes_share_the_view_box(pages: list[int]) -> Result:
    """Every published box must be in the page's own viewBox coordinates.

    The app reads `data-text-box` to place the text column and each word's
    `data-box` to hit-test a tap. If those two are in different coordinate
    systems the app cannot tell — the numbers look reasonable either way — and
    every tap target sits a gutter's width off. So they are checked against
    each other: a word box that escapes the text box means one of them is
    being written in `#q-page`'s local space instead of the page's.
    """
    worst = None
    for page in pages:
        svg = _svg(page)
        tb = re.search(r'data-text-box="([^"]+)"', svg)
        if not tb:
            return Result("published boxes share one coordinate space", False,
                          f"page {page}: no data-text-box")
        x0, y0, w0, h0 = (float(v) for v in tb.group(1).split())
        for box in re.findall(r'data-box="([^"]+)"', svg):
            bx, by, bw, bh = (float(v) for v in box.split())
            escape = max(x0 - bx, bx + bw - (x0 + w0), y0 - by, by + bh - (y0 + h0))
            if worst is None or escape > worst[0]:
                worst = (escape, page, box)
    if worst is None:
        return Result("published boxes share one coordinate space", False, "no word boxes found")
    escape, page, box = worst
    return Result(
        "published boxes share one coordinate space",
        escape <= 0.05,
        f"every word box sits inside data-text-box (worst margin {-escape:.2f} units)"
        if escape <= 0.05
        else f"page {page}: box {box} escapes data-text-box by {escape:.2f} units",
    )


def check_fills_any_viewport(page: int = 248) -> Result:
    """The page must survive being put in a box that is not its own shape.

    An app hands the document a phone-shaped box - 1000x2200 was the one that
    failed - and a `meet` fit then centres this 2:3 page in it, leaving a band
    top and bottom. Two things have to hold for that band not to read as a
    bug: the document must fill the box it is given rather than report an
    intrinsic 1000x1500 size, and the ground must reach past the viewBox so
    the band is the page's own colour instead of nothing at all.
    """
    svg = _svg(page)
    root = svg[: svg.index(">") + 1]
    responsive = 'width="100%"' in root and 'height="100%"' in root
    fit = 'preserveAspectRatio="xMidYMid meet"' in root
    rect = re.search(
        r'<g id="q-ground">\s*<rect class="q-bg" x="([-\d.]+)" y="([-\d.]+)"'
        r' width="([\d.]+)" height="([\d.]+)"',
        svg,
    )
    bleed = 0.0
    if rect:
        x, y, w, h = (float(v) for v in rect.groups())
        bleed = min(-x, -y, x + w - DEFAULT_GEOMETRY.view_w, y + h - DEFAULT_GEOMETRY.view_h)
    ok = responsive and fit and bleed >= 1000
    return Result(
        "fills any viewport the app gives it",
        ok,
        f"root sizes to its box, aspect kept, ground bleeds {bleed:,.0f} units past the page"
        if ok
        else f"responsive={responsive} meet={fit} bleed={bleed}",
    )


def run(pages: list[int] | None = None) -> Report:
    pages = pages or [248]
    report = Report()
    report.results.append(check_shell_is_page_independent())
    report.results.append(check_themes_are_complete())
    report.results.append(check_no_hardcoded_paint())
    report.results.append(check_no_css_variables())
    report.results.append(check_colour_only_in_theme_block())
    report.results.append(check_frame_is_removable())
    report.results.append(check_no_font_dependency())
    report.results.append(check_build_is_reproducible())
    report.results.append(check_highlight_hooks())
    report.results.extend(check_text_is_addressable())
    report.results.extend(check_theme_changes_only_colour())
    if len(pages) > 1:
        report.results.extend(check_pages_share_one_shell(pages))
        report.results.extend(check_page_sides(pages))
    report.results.append(check_boxes_share_the_view_box(pages))
    report.results.append(check_fills_any_viewport())
    return report
