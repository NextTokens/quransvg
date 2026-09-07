"""Assemble a page into a self-contained, highlight-ready SVG document.

Structure of a generated page:

    <svg>
      <style>            theme block (swappable) + structural rules
      <defs>             ornament symbols, shared by every page
      <g id="q-ground">  the page ground
      <g id="q-frame">   the illuminated border — identical everywhere, removable
      <g id="q-chrome">  surah name, juz name, page number
      <g id="q-text">    one <g class="q-ayah"> per ayah, one <path> per word

Two decisions here matter for the app that will consume these files.

*Highlighting recolours the letterforms.*  Each word is exactly one `<path>`
whose `fill` comes from a CSS custom property, so marking a word or an ayah
active changes the ink itself.  Nothing is ever painted behind the text: a
block of colour sitting behind Qur'anic calligraphy reads as defacing it.

*Grouping follows recitation, not layout.*  An ayah routinely spans several
lines, so grouping by line would make "highlight this ayah" a scattered
multi-element operation.  Word coordinates are baked into the path data, which
makes grouping free — so words nest under their ayah and merely carry
`data-line`.  Highlighting an ayah is then one class on one element.
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Geometry
from .layout import PageLayout, PlacedWord
from .theme import Theme

SVG_NS = "http://www.w3.org/2000/svg"


@dataclass(frozen=True)
class PageChrome:
    """The only text that legitimately differs from page to page."""

    page: int
    surah_name: str
    juz_label: str
    page_label: str


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _n(value: float, places: int = 2) -> str:
    rounded = round(value, places)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{places}f}".rstrip("0").rstrip(".")


def _ayah_groups(layout: PageLayout) -> list[tuple[str, list[PlacedWord]]]:
    """Words grouped by ayah, in reading order, preserving first appearance."""
    order: list[str] = []
    groups: dict[str, list[PlacedWord]] = {}
    for line in layout.lines:
        # Reading order within a line is right to left.
        for word in sorted(line.words, key=lambda w: -w.x):
            key = ":".join(word.location.split(":")[:2])
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(word)
    return [(key, groups[key]) for key in order]


def render(
    layout: PageLayout,
    theme: Theme,
    chrome: PageChrome,
    *,
    ground: str,
    frame: str,
    defs: str,
    chrome_markup: str,
    openings: str = "",
    illumination: str = "",
    marker_for=None,
    side: str = "recto",
    gutter: float = 0.0,
    extra_css: str = "",
) -> str:
    """Serialise a page.

    `ground`, `frame` and `defs` are the invariant decoration; `marker_for`
    renders one end-of-ayah mark. Passing them in keeps this module purely
    about document structure.
    """
    geometry: Geometry = layout.geometry
    from . import stylesheet
    from .geometry import (
        DESCENT_EM,
        INK_ASCENT_EM,
        INK_DESCENT_EM,
        INK_OVERHANG_EM,
    )

    # The box is the union of the advance box and the word's measured ink, plus
    # a little. A constant guess at the overhang was 6 pixels short of one of
    # al-Fatihah's words - the opening pages use wider forms than a body page.
    overhang = geometry.em * 0.05          # breathing room around the measured ink
    column = geometry.em * (INK_OVERHANG_EM + 0.05)   # the text column, ink included
    ink_up = geometry.em * INK_ASCENT_EM
    ink_down = geometry.em * INK_DESCENT_EM
    descent = geometry.em * DESCENT_EM     # the last line's descenders

    # The page's own line count, not the grid's. Pages 1 and 2 carry seven and
    # six lines inside the opening medallion; declaring fifteen there is a
    # statement about the grid that is false about the page, and anything that
    # reads the attribute is wrong on exactly the two pages that differ.
    numbers = [line.number for line in layout.lines]
    lines_on_page = len(numbers)
    line_range = f"{min(numbers)}-{max(numbers)}" if numbers else "0-0"

    # A preview look's palette goes after the theme block so it wins where
    # the two touch the same class; the block itself stays intact.
    style = f"{stylesheet.structural_css()}{theme.block()}\n{extra_css}"

    out: list[str] = []
    add = out.append
    # width/height as percentages, not the page's own pixel size: an intrinsic
    # 1000x1500 makes a renderer hand back a 1000x1500 bitmap however large a
    # box the app asked for. With percentages the document fills the box it is
    # given, and `meet` keeps the page's proportions inside it - the text is
    # never stretched to fit a phone's aspect.
    add(
        # xlink is declared for the adopted ornament, which references its own
        # defs with xlink:href - understood by every renderer we target.
        f'<svg xmlns="{SVG_NS}" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="100%" height="100%" '
        f'viewBox="{geometry.viewbox}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-labelledby="q-title q-desc" data-page="{chrome.page}" '
        f'data-theme="{theme.name}" data-lines="{lines_on_page}" '
        f'data-line-range="{line_range}" data-side="{side}" '
        f'data-text-box="{_n(geometry.panel_x + gutter - column)} '
        f'{_n(geometry.baseline(1) - ink_up - overhang)} '
        f'{_n(geometry.panel_w + 2 * column)} '
        f'{_n((geometry.lines - 1) * geometry.line_pitch + ink_up + ink_down + 2 * overhang)}">'
    )
    add(f'<title id="q-title">{_esc(f"Quran page {chrome.page}")}</title>')
    add(
        f'<desc id="q-desc">{_esc(chrome.surah_name)} — '
        f'{_esc(chrome.juz_label)} — page {chrome.page} of 604</desc>'
    )
    add(f"<style>\n{style}</style>")
    add(f"<defs>{defs}</defs>")
    add(f'<g id="q-ground">{ground}</g>')
    # The frame sits outside the gutter shift, with the ground. It is flush with
    # the page edge now, so shifting it simply pushed one side off the page -
    # 8,892 pixels of it, clipped away. What moves toward the spine is the text.
    add(f'<g id="q-frame">{frame}</g>')
    add(f'<g id="q-page" transform="translate({_n(gutter)} 0)">')
    if illumination:
        add(f'<g id="q-illumination">{illumination}</g>')
    add(f'<g id="q-chrome">{chrome_markup}</g>')
    if openings:
        add(f'<g id="q-openings">{openings}</g>')

    add('<g id="q-text">')
    for key, words in _ayah_groups(layout):
        surah, ayah = key.split(":")
        add(
            f'<g class="q-ayah" id="q-a{surah}-{ayah}" data-ayah="{key}" '
            f'data-surah="{surah}" data-number="{ayah}">'
        )
        for word in words:
            index = word.location.split(":")[2]
            # The hit box is the advance box widened by the ink overhang: a
            # naskh word paints a little beyond its advance at both ends, and
            # a tap target that misses the tips of the letters is a bad one.
            #
            # It is published in the page's own viewBox coordinates, gutter
            # included — the same space as `data-text-box`. The word element
            # itself lives under `#q-page`'s translate, so its *local* x is
            # `gutter` smaller; publishing that raw would hand the app two
            # boxes in two coordinate systems, and a tap target off by 9 units.
            left = min(word.x, word.ink_x0) - overhang + gutter
            right = max(word.x + word.width, word.ink_x1) + overhang + gutter
            top = word.ink_y0 - overhang
            bottom = word.ink_y1 + overhang
            box = f"{_n(left)} {_n(top)} {_n(right - left)} {_n(bottom - top)}"
            if word.kind == "end":
                add(marker_for(word, int(ayah)))
                continue
            classes = "q-word q-lafz" if word.divine_name else "q-word"
            add(
                f'<g class="{classes}" id="q-w{surah}-{ayah}-{index}" '
                f'data-loc="{word.location}" data-line="{word.line}" '
                f'data-box="{box}">'
            )
            for layer, data in (
                ("q-rasm", word.rasm),
                ("q-tashkeel", word.tashkeel),
                ("q-waqf", word.waqf),
            ):
                if data:
                    add(f'<path class="{layer}" d="{data}"/>')
            add("</g>")
        add("</g>")
    add("</g>")
    add("</g>")
    add("</svg>")
    return "\n".join(out) + "\n"
