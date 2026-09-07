"""Assemble a v4 page into a self-contained SVG.

The document is the v2 build's, unchanged in every part an app depends on: the
same layer ids, the same `q-word` groups, the same `data-loc`, `data-line` and
`data-box`, the same ayah grouping. What differs is inside a word. There a word
is no longer up to three paths but up to a handful, because each path carries
both the ink layer a theme colours and, where the font declares one, the
tajweed segment a recitation rule colours:

    <g class="q-word" id="q-w12-104-5" data-loc="12:104:5" data-box="...">
      <path class="q-rasm"/>
      <path class="q-rasm q-tj-madd-2"/>
      <path class="q-tashkeel"/>
    </g>

With the root class absent the tajweed classes carry no colour at all and the
page is coloured by ink layer exactly as the v2 build's is. Add `q-tajweed` and
the rules take over the letters they belong to.
"""

from __future__ import annotations

from dataclasses import dataclass

from qsvg.geometry import (
    DESCENT_EM,
    INK_ASCENT_EM,
    INK_DESCENT_EM,
    INK_OVERHANG_EM,
    Geometry,
)

from . import stylesheet
from .layout import PageLayout, PlacedWord
from .theme import Theme

SVG_NS = "http://www.w3.org/2000/svg"


@dataclass(frozen=True)
class PageChrome:
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
    order: list[str] = []
    groups: dict[str, list[PlacedWord]] = {}
    for line in layout.lines:
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
    tajweed: bool = False,
) -> str:
    geometry: Geometry = layout.geometry

    overhang = geometry.em * 0.05
    column = geometry.em * (INK_OVERHANG_EM + 0.05)
    ink_up = geometry.em * INK_ASCENT_EM
    ink_down = geometry.em * INK_DESCENT_EM

    numbers = [line.number for line in layout.lines]
    lines_on_page = len(numbers)
    line_range = f"{min(numbers)}-{max(numbers)}" if numbers else "0-0"

    # The text box is the column the text occupies - the panel plus the room
    # naskh paints beyond its advance - and then widened to hold this page's
    # own ink. v4 draws a few forms with a very long tail (the stretched
    # basmalah of page 1 reaches 1.6 em past its advance), and a column cut to
    # the worst of those across 604 pages would be a column mostly empty. So
    # the constant covers the ordinary case and the page states the rest.
    box_x0 = geometry.panel_x + gutter - column
    box_x1 = geometry.panel_x + gutter + geometry.panel_w + column
    box_y0 = geometry.baseline(1) - ink_up - overhang
    box_y1 = box_y0 + (geometry.lines - 1) * geometry.line_pitch + ink_up + ink_down + 2 * overhang
    for word in layout.words:
        if word.kind == "end":
            continue
        box_x0 = min(box_x0, min(word.x, word.ink_x0) - overhang + gutter)
        box_x1 = max(box_x1, max(word.x + word.width, word.ink_x1) + overhang + gutter)
        box_y0 = min(box_y0, word.ink_y0 - overhang)
        box_y1 = max(box_y1, word.ink_y1 + overhang)

    style = f"{stylesheet.structural_css()}{theme.block()}\n"
    # `q-tajweed-plain` is what makes the page read as a tajweed mushaf rather
    # than as an ordinary page with rules laid over it: only a recitation rule
    # carries colour. Dropping that one class - and keeping `q-tajweed` - gives
    # the mixed look back, with the vowel marks and the divine name in red too.
    root_class = "q-tajweed q-tajweed-plain" if tajweed else ""

    out: list[str] = []
    add = out.append
    add(
        f'<svg xmlns="{SVG_NS}" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="100%" height="100%" '
        f'viewBox="{geometry.viewbox}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        + (f'class="{root_class}" ' if root_class else "")
        + f'aria-labelledby="q-title q-desc" data-page="{chrome.page}" '
        f'data-theme="{theme.name}" data-edition="qcf-v4" '
        f'data-lines="{lines_on_page}" '
        f'data-line-range="{line_range}" data-side="{side}" '
        f'data-text-box="{_n(box_x0)} {_n(box_y0)} '
        f'{_n(box_x1 - box_x0)} {_n(box_y1 - box_y0)}">'
    )
    add(f'<title id="q-title">{_esc(f"Quran page {chrome.page}")}</title>')
    add(
        f'<desc id="q-desc">{_esc(chrome.surah_name)} — '
        f'{_esc(chrome.juz_label)} — page {chrome.page} of 604</desc>'
    )
    add(f"<style>\n{style}</style>")
    add(f"<defs>{defs}</defs>")
    add(f'<g id="q-ground">{ground}</g>')
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
            if word.kind == "end":
                add(marker_for(word, int(ayah)))
                continue
            index = word.location.split(":")[2]
            if word.kind == "mark":
                # The rub'-el-hizb and the sajdah marks. The v2 build draws
                # both but has nowhere to put them; this edition's word table
                # states where they go, so here they are placed - as page
                # furniture with their own class, never as words of the text.
                add(f'<g class="q-page-mark" data-loc="{word.location}" '
                    f'data-line="{word.line}">')
                for path in word.paths:
                    add(f'<path class="{path.layer}" d="{path.data}"/>')
                add("</g>")
                continue
            left = min(word.x, word.ink_x0) - overhang + gutter
            right = max(word.x + word.width, word.ink_x1) + overhang + gutter
            top = word.ink_y0 - overhang
            bottom = word.ink_y1 + overhang
            box = f"{_n(left)} {_n(top)} {_n(right - left)} {_n(bottom - top)}"
            classes = "q-word q-lafz" if word.divine_name else "q-word"
            add(
                f'<g class="{classes}" id="q-w{surah}-{ayah}-{index}" '
                f'data-loc="{word.location}" data-line="{word.line}" '
                f'data-box="{box}">'
            )
            for path in word.paths:
                cls = path.layer if path.rule is None else f"{path.layer} q-tj-{path.rule}"
                if path.note:
                    cls += " q-note"
                add(f'<path class="{cls}" d="{path.data}"/>')
            add("</g>")
        add("</g>")
    add("</g>")
    add("</g>")
    add("</svg>")
    return "\n".join(out) + "\n"
