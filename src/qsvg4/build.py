"""Build a page of the v4 colour mushaf.

Everything around the text is the v2 build's, imported rather than copied: the
border, the surah band, the opening decoration, the ayah rosette, the running
head, the folio and its side mark, the geometry. This module supplies only what
changes — the edition the words are set from, and the tajweed segments that
come with it.

Nothing here writes to `mushaf/`, and nothing here imports anything from the v2
build that it can modify. The two sets are built by two packages that share
their furniture and nothing else.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from qsvg import numerals, shell, sources as v2sources
from qsvg.build import (
    AMIRI_BOLD,
    CATCHWORD_SCALE,
    CATCHWORD_WORDS,
    DEFAULT_GEOMETRY,
    OPENING_PAGES,
    SIMPLIFY_TOLERANCE,
    _art,
    _chrome_markup,
    _marker_renderer,
    _opening,
    _openings_markup,
    _require,
    juz_label,
)
from qsvg.geometry import ASCENT_EM, DESCENT_EM, Geometry, gutter_offset, page_side

from . import mushaf, sources, theme as theming
from .glyphs import ColourPageFont
from .layout import PageLayout, lay_out_page
from .svg import PageChrome, render

DEFAULT_THEME = "green-pink"

#: The v4 fonts are cut to a wider measure than the v2 fonts: over all 604
#: pages the median justified line runs 41,050 font units against v2's 40,000.
#: Borrowing the v2 calibration left every line 2.6% over-set, so the justifier
#: closed the gaps to nothing - three quarters of all lines were being handed a
#: *negative* word space, which is why words touched. The em drops 2.6% with it
#: (57.75 -> 56.27) and the type does not get smaller: v4 draws its letters
#: about 4% taller at the same units-per-em, so the printed letter height lands
#: within about 1% of the v2 set's.
V4_MEASURE_UNITS = 41_050.0
V4_GEOMETRY = dataclasses.replace(DEFAULT_GEOMETRY, measure_units=V4_MEASURE_UNITS)


@dataclass(frozen=True)
class BuiltPage:
    page: int
    theme: str
    svg: str
    layout: PageLayout

    @property
    def word_count(self) -> int:
        return len(self.layout.words)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _catchword_markup(page: int, geometry: Geometry, *, simplify: float) -> str:
    """The opening of the next page, set small in the lower margin."""
    if page >= sources.PAGE_COUNT:
        return ""
    try:
        plan = mushaf.plan(page + 1)
        font = ColourPageFont(sources.page_font(page + 1))
    except Exception:
        return ""

    words = []
    first_ayah = None
    # Only verse lines: a page that opens a surah begins with a heading and a
    # basmalah, and neither is a word of the text.
    for line in plan.lines:
        if line.kind != mushaf.AYAH:
            continue
        for word in line.words:
            if word.kind != "word":
                continue
            key = f"{word.surah}:{word.ayah}"
            if first_ayah is None:
                first_ayah = key
            elif key != first_ayah:
                break
            if len(words) >= CATCHWORD_WORDS:
                break
            words.append(word)
        else:
            continue
        break
    if not words:
        return ""

    scale = geometry.scale * CATCHWORD_SCALE
    fx, fy, fw, fh = shell.footer_box(geometry)
    left = shell.RULE_X + 14.0
    baseline = fy + fh * 0.66

    parts: list[str] = []
    pen = 0.0
    for word in words:
        for glyph in word.glyphs:
            name = font.glyph_name(glyph.char)
            if name is None:
                continue
            for placed in font.shape_word(glyph.char):
                contours = [
                    contour
                    for layer in font.layers(placed.glyph_name)
                    for contour in font.contours(layer.glyph_name)
                ]
                parts.append(
                    font.encode_contours(
                        contours,
                        scale=scale,
                        translate=(left + (pen + placed.x) * scale, baseline),
                        simplify=simplify,
                    )
                )
                pen += placed.advance
        pen += font.space

    spellings = mushaf.uthmani()
    text = " ".join(spellings.get(w.location, "") for w in words)
    return (
        f'<g id="q-catchword" data-next-page="{page + 1}" '
        f'data-loc="{words[0].location}">'
        f"<title>{_esc(text)}</title>"
        f'<path class="q-catchword" d="{"".join(parts)}"/>'
        f"</g>"
    )


def build_page(
    page: int,
    theme_name: str = DEFAULT_THEME,
    *,
    geometry: Geometry = V4_GEOMETRY,
    simplify: float = SIMPLIFY_TOLERANCE,
    tajweed: bool = False,
) -> BuiltPage:
    # Ensure a clean checkout has the shared page-furniture fonts instead of
    # requiring an undocumented v2 setup step. Existing local files stay put.
    sources.common_fonts()
    plan = mushaf.plan(page)
    font = ColourPageFont(sources.page_font(page))
    spellings = mushaf.uthmani()

    # An opening page is laid out twice, as in the v2 build: once to learn how
    # wide its lines actually run, and again once the oval cut to them is known.
    half_widths: list[float] = []
    if page in OPENING_PAGES:
        probe = lay_out_page(page, mushaf.plan(page), font, geometry,
                             simplify=0.0, spellings=spellings)
        measured = {
            line.number: (max(w.x + w.width for w in line.words)
                          - min(w.x for w in line.words)) / 2
            for line in probe.lines if line.words
        }
        numbers = sorted(l.number for l in plan.lines if l.number >= 2)
        half_widths = [
            measured.get(n, geometry.panel_w * 0.52 / 2) for n in numbers
        ]

    shift_fn, illumination, panel = _opening(page, plan, geometry, half_widths)
    layout = lay_out_page(
        page, plan, font, geometry, simplify=simplify,
        shift=shift_fn or 0.0, spellings=spellings,
    )

    # The running head names the surah whose *text* begins on the page - not
    # merely one whose band appears on it. The band for the next surah is set
    # at the foot of the page before it, so heading off the band alone made
    # page 76 read An-Nisa when every word on it is Ali 'Imran. A surah begins
    # where its basmalah or its first word is printed.
    begins: list[int] = []
    for line in plan.lines:
        if line.kind == mushaf.BASMALLAH and line.words:
            surah_here = line.words[0].surah
            if surah_here not in begins:
                begins.append(surah_here)
        for word in line.words:
            if word.kind == "word" and word.ayah == 1 and word.index == 1:
                if word.surah not in begins:
                    begins.append(word.surah)
    first_word = next((w for line in plan.lines for w in line.words
                       if w.kind == "word"), None)
    surah = begins[0] if begins else (first_word.surah if first_word else 1)
    juz = mushaf.page_juz(page)

    chapters = {c["id"]: c for c in v2sources.chapters()}
    surah_name = chapters[surah]["name_arabic"]

    digits = numerals.load(_require(AMIRI_BOLD, "Amiri Bold"))
    active = theming.load(theme_name)

    svg = render(
        layout,
        active,
        PageChrome(
            page=page,
            surah_name=surah_name,
            juz_label=juz_label(juz),
            page_label=str(page),
        ),
        ground=shell.ground(geometry),
        frame=_art().frame(geometry),
        defs=shell.defs(geometry) + digits.defs() + _art().defs(),
        chrome_markup=_chrome_markup(
            surah=surah, juz=juz, page=page, geometry=geometry, digits=digits
        ),
        openings=_openings_markup(
            page, plan, geometry=geometry, layout=layout,
            shift=shift_fn, panel=panel,
        )
        + _catchword_markup(page, geometry, simplify=simplify),
        illumination=illumination,
        marker_for=_marker_renderer(geometry, digits),
        side=page_side(page),
        gutter=gutter_offset(page),
        tajweed=tajweed,
    )
    return BuiltPage(page=page, theme=theme_name, svg=svg, layout=layout)


def write_page(page: int, out_dir: Path, **kwargs) -> Path:
    built = build_page(page, **kwargs)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"page-{page:03d}.svg"
    path.write_text(built.svg, encoding="utf-8")
    return path
