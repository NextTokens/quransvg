"""Build a page: data in, finished SVG out."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import (
    header as header_art,
    mushaf,
    numerals,
    shell,
    sources,
    theme as theming,
)
from .geometry import (
    ASCENT_EM,
    DEFAULT as DEFAULT_GEOMETRY,
    DESCENT_EM,
    Geometry,
    gutter_offset,
    page_side,
)
from .glyphs import PageFont
from .layout import PageLayout, PlacedWord, lay_out_page
from .svg import PageChrome, render
from .typeset import SurahNames, Typeface, juz_label

FONT_DIR = sources.FONT_DIR
AMIRI = FONT_DIR / "Amiri-Regular.ttf"
# Ayah and page numbers are small; the regular cut goes thin and grey at
# that size, so the numerals come from the bold one.
AMIRI_BOLD = FONT_DIR / "Amiri-Bold.ttf"
SURAH_NAME_FONT = FONT_DIR / "QUL_SurahName_v1.ttf"
BASMALAH_FONT = FONT_DIR / "QCF_BSML.TTF"

# The basmalah lives at this codepoint in the KFGQPC heading font, set in the
# elongated style the printed mushaf uses above a surah's first ayah.
BASMALAH_CODEPOINT = 0xFC21

#: Set as words so it shapes and spaces like text.
BASMALAH = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"

# Chrome sits inside the cartouches the shell cuts into the band.
CHROME_INSET = 8.0
SURAH_SIZE = 38.0
JUZ_SIZE = 28.0
PAGE_NUMBER_SIZE = 38.0        # ceiling; shrunk to fit its allowance
PAGE_NUMBER_FILL = 0.78        # of the field's diameter

# The catchword: the opening of the following page, set small in the lower
# margin so a reader turning the leaf sees the sense continue. Three words, or
# the whole of the first ayah when it is shorter than that — a catchword should
# never break off mid-ayah when the ayah would have fitted whole. It is set from
# the *next* page's own font, since each page's glyphs live only in its own.
CATCHWORD_WORDS = 3
CATCHWORD_SCALE = 0.55         # of the body type size

# The rosette sits slightly above the baseline, centred on the run of text.
ROSETTE_RISE_EM = 0.33
DIGIT_FILL = 0.94       # of the usable width inside the ayah oval
DIGIT_MAX_SIZE = 30.0

# Outline simplification tolerance, in font units. One font unit is 0.0202
# viewBox units, so 12 is about a quarter of a viewBox unit - a tenth of a
# pixel on a 400px-wide phone, and under a third of one at 1000px.
SIMPLIFY_TOLERANCE = 12.0

#: The theme written into a page unless another is asked for.
DEFAULT_THEME = "green-pink"

# Opening lines: the surah heading band and the basmalah beneath it.
OPENING_RISE_EM = 0.35        # band centre above the line's baseline
BAND_HEIGHT_RATIO = 0.86      # of the line pitch
BAND_WIDTH_RATIO = 0.80       # of the panel width
SURAH_TITLE_SIZE = 50.0
# 1.0: the band's ink is placed to the panel measure, which is the width of a
# full line. It was 1.06 when the panel was 752 units on a 1000-wide page and
# the surplus had nowhere to go but empty margin; against a 950-unit panel the
# same ratio puts the band's ink 1007 units wide - wider than the page - and it
# runs out over the border.
HEADER_WIDTH_RATIO = 1.0
HEADER_CLEAR = 8.0          # room left above the band
BASMALAH_CLEAR = 7.0        # room left around the basmalah
BASMALAH_WIDTH_RATIO = 0.52
# Height governs here. The band above and the first ayah below leave only
# about 57 units between them, so a basmalah cut to the full width would
# graze the header even though it clears the text.
BASMALAH_HEIGHT_RATIO = 0.55   # of the panel width


@dataclass(frozen=True)
class BuiltPage:
    page: int
    theme: str
    svg: str
    layout: PageLayout

    @property
    def word_count(self) -> int:
        return len(self.layout.words)


def _require(path: Path, what: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(
            f"missing {what}: {path}\nRun `python -m qsvg fetch` to download assets."
        )
    return path


def _chrome_markup(
    *,
    surah: int,
    juz: int,
    page: int,
    geometry: Geometry,
    digits: numerals.NumeralSet,
) -> str:
    """Surah name, juz label and page number, all as outlines.

    The running head always carries the surah name. It is the reader's
    orientation on the page and does not depend on what else the page holds.
    """
    names = SurahNames(_require(SURAH_NAME_FONT, "surah-name font"))
    body = Typeface(_require(AMIRI, "Amiri"))

    hx, hy, hw, hh = shell.header_box(geometry)
    baseline = hy + hh / 2 + SURAH_SIZE * 0.34
    right = hx + hw - CHROME_INSET
    left = hx + CHROME_INSET

    juz_run = body.run(juz_label(juz), JUZ_SIZE, left, baseline, anchor="start")
    surah_run = names.run(surah, SURAH_SIZE, right, baseline, anchor="end")
    surah_markup = (
        f'<path class="q-chrome" id="q-surah" data-surah="{surah}" '
        f'd="{surah_run.path}"/>'
    )

    fx, fy, fw, fh = shell.footer_box(geometry)
    # Fit the number to the medallion rather than trusting a fixed size: three
    # Arabic-Indic digits are nearly twice the width of one.
    field = shell.footer_field_diameter()
    span = digits.width(page) / digits.units_per_em
    size = min(PAGE_NUMBER_SIZE, field * PAGE_NUMBER_FILL / span)
    page_digits = digits.place(
        page, fx + fw / 2, fy + fh / 2, size, "q-chrome"
    )
    return (
        surah_markup
        + f'<path class="q-chrome-muted" id="q-juz" data-juz="{juz}" d="{juz_run.path}"/>'
        + f'<g id="q-page-number" data-page="{page}">{page_digits}</g>'
        + _side_mark(page, fx + fw / 2, fy + fh / 2, span * size / 2)
    )


def _catchword_markup(page: int, geometry: Geometry, *, simplify: float) -> str:
    """The opening words of the next page, set in the lower margin."""
    if page >= sources.PAGE_COUNT:
        return ""
    try:
        data = mushaf.page_data(page + 1) if mushaf.available() else sources.page_data(page + 1)
        font = PageFont(sources.page_font(page + 1))
    except Exception:
        return ""

    words = []
    first_ayah = None
    for verse in data["verses"]:
        for word in verse["words"]:
            if word["char_type_name"] != "word":
                continue
            ayah = ":".join(word["location"].split(":")[:2])
            if first_ayah is None:
                first_ayah = ayah
            elif ayah != first_ayah:
                break                      # the opening ayah ended first
            if len(words) >= CATCHWORD_WORDS:
                break
            words.append(word)
        else:
            continue
        break
    if not words:
        return ""

    shaped = font.shape(" ".join(w["code_v2"] for w in words))
    scale = geometry.scale * CATCHWORD_SCALE
    fx, fy, fw, fh = shell.footer_box(geometry)
    left = shell.RULE_X + 14.0
    baseline = fy + fh * 0.66

    parts: list[str] = []
    pen = 0.0
    for glyph in shaped:
        if not glyph.is_space and not font.is_blank(glyph.glyph_name):
            parts.append(
                font.path_data(
                    glyph.glyph_name,
                    scale=scale,
                    translate=(left + (pen + glyph.x_offset) * scale,
                               baseline - glyph.y_offset * scale),
                    simplify=simplify,
                )
            )
        pen += glyph.advance

    text = " ".join(w["text_uthmani"] for w in words)
    return (
        f'<g id="q-catchword" data-next-page="{page + 1}" '
        f'data-loc="{words[0]["location"]}">'
        f'<title>{_esc(text)}</title>'
        f'<path class="q-catchword" d="{"".join(parts)}"/>'
        f"</g>"
    )


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _marker_renderer(geometry: Geometry, digits: numerals.NumeralSet):
    """Return a callback that draws one end-of-ayah rosette.

    The mushaf font ships its own ornate marker glyph, but we draw our own so
    the ring, the field and the number can each take a colour from the theme —
    and so the marker is identical on every page rather than varying with
    whatever the per-page font happens to contain.
    """

    def _n(value: float, places: int = 2) -> str:
        rounded = round(value, places)
        if rounded == int(rounded):
            return str(int(rounded))
        return f"{rounded:.{places}f}".rstrip("0").rstrip(".")

    def render_marker(word: PlacedWord, number: int) -> str:
        cx = word.x + word.width / 2
        cy = word.baseline - geometry.em * ROSETTE_RISE_EM
        width_em = digits.width(number) / digits.units_per_em
        size = min(DIGIT_MAX_SIZE, shell.ayah_field_width() * DIGIT_FILL / width_em)
        surah, ayah, index = word.location.split(":")
        return (
            f'<g class="q-mark" id="q-e{surah}-{ayah}" data-loc="{word.location}" '
            f'data-ayah="{surah}:{ayah}" data-line="{word.line}" data-number="{number}">'
            f'<use href="#q-ayah-rosette" transform="translate({_n(cx)} {_n(cy)})"/>'
            + digits.place(number, cx, cy, size, "q-ayah-digit")
            + "</g>"
        )

    return render_marker


def _fit_baseline(face_run, target_w: float, target_h: float, ceiling: float,
                  cx: float, baseline: float):
    """Size a run to a box, centre it horizontally, and sit it on `baseline`.

    Used where the artwork specifies a baseline: centring the ink vertically
    instead would let a short line drift up into the one above it.
    """
    probe = face_run(100.0, 0.0, 0.0)
    if not probe.ink or probe.ink_width <= 0 or probe.ink_height <= 0:
        return face_run(ceiling, cx, baseline)
    size = min(ceiling, target_w / probe.ink_width * 100.0,
               target_h / probe.ink_height * 100.0)
    run = face_run(size, cx, baseline)
    if run.ink:
        run = face_run(size, cx + cx - (run.ink[0] + run.ink[2]) / 2, baseline)
    return run


def _fit_ink(face_run, target_w: float, target_h: float, ceiling: float,
             cx: float, cy: float):
    """Size a run to a box using its measured ink, then centre that ink.

    Decorative faces paint well outside their advance box, so anything that has
    to sit inside a cartouche must be fitted to the ink or it will overflow.
    """
    probe = face_run(100.0, 0.0, 0.0)
    if not probe.ink or probe.ink_width <= 0 or probe.ink_height <= 0:
        return face_run(ceiling, cx, cy)
    size = min(ceiling, target_w / probe.ink_width * 100.0,
               target_h / probe.ink_height * 100.0)
    run = face_run(size, cx, cy)
    if run.ink:
        dx = cx - (run.ink[0] + run.ink[2]) / 2
        dy = cy - (run.ink[1] + run.ink[3]) / 2
        run = face_run(size, cx + dx, cy + dy)
    return run


def _line_ink(layout, number: int):
    """Where a text line's ink actually reaches, if that line carries words."""
    if layout is None:
        return None
    for line in layout.lines:
        if line.number == number and line.ink_top is not None:
            return line.ink_top, line.ink_bottom
    return None


def _ceiling_for(number: int, geometry: Geometry, layout) -> float:
    """The lowest thing above line `number` that an opening must clear."""
    if number <= 1:
        _, hy, _, hh = shell.header_box(geometry)
        return hy + hh
    ink = _line_ink(layout, number - 1)
    if ink:
        return ink[1]
    return geometry.baseline(number - 1) + geometry.em * DESCENT_EM


def _floor_for(number: int, geometry: Geometry, layout) -> float:
    """The highest thing below line `number` that an opening must clear."""
    if number >= geometry.lines:
        return geometry.panel_y + geometry.panel_h
    ink = _line_ink(layout, number + 1)
    if ink:
        return ink[0]
    return geometry.baseline(number + 1) - geometry.em * ASCENT_EM


def _surah_band(line, *, width, cx, cy, names, body, chapters) -> str:
    """One illuminated surah band, with its name and metadata set as outlines."""
    art = _art()
    chapter = chapters.get(line.surah, {})
    place = chapter.get("revelation_place", "")
    verses = chapter.get("verses_count", 0)
    meta = f"{PLACE_NAMES.get(place, place)} · آياتها {_arabic_digits(verses)}"

    name = _fit_baseline(
        lambda size, x, y: names.run(line.surah, size, x, y, anchor="middle"),
        art.VIEW_W * art.NAME_W_RATIO, art.NAME_H, art.NAME_CEILING,
        art.TEXT_CX, art.NAME_BASELINE,
    )
    note = _fit_baseline(
        lambda size, x, y: body.run(meta, size, x, y, anchor="middle"),
        art.VIEW_W * art.META_W_RATIO, art.META_H, art.META_CEILING,
        art.TEXT_CX, art.META_BASELINE,
    )
    return art.instance(
        cx=cx, cy=cy, width=width,
        name_path=name.path, meta_path=note.path,
        surah=line.surah, line=line.number,
    )


#: The half-leaf beside the folio: which side of the opening this page is.
SIDE_MARK_W = 11.0
SIDE_MARK_H = 15.0
SIDE_MARK_GAP = 11.0        # clear of the folio's own digits


def _side_mark(page: int, cx: float, cy: float, digits_half: float) -> str:
    """A tiny half-leaf next to the folio, opening away from the spine.

    The gutter shift already says which side of the opening a page is, but it
    is a 3-unit asymmetry - true to the binding and far too quiet to read
    deliberately. This is the deliberate version: half a leaf, its spine edge
    straight and its fore-edge round, set on the page's own outer side. Both
    the shape and where it sits carry the same information.
    """
    recto = page_side(page) == "recto"
    direction = 1.0 if recto else -1.0
    # measured from the digits, not from their centre: a three-digit folio is
    # twice the width of a one-digit one and the mark was landing on top of it
    x = cx + direction * (digits_half + SIDE_MARK_GAP)
    w, h = SIDE_MARK_W, SIDE_MARK_H
    spine_x = x - direction * w / 2
    edge_x = x + direction * w / 2
    top, bottom = cy - h / 2, cy + h / 2
    # straight at the spine, swelling to a round fore-edge - half a leaf seen
    # from above, which is the shape the outer margin of an open book makes
    leaf = (
        f"M{_num(spine_x)} {_num(top)}"
        f"H{_num(edge_x - direction * w * 0.5)}"
        f"C{_num(edge_x)} {_num(top)} {_num(edge_x)} {_num(bottom)} "
        f"{_num(edge_x - direction * w * 0.5)} {_num(bottom)}"
        f"H{_num(spine_x)}Z"
    )
    return (
        f'<g id="q-side" data-side="{"recto" if recto else "verso"}">'
        f'<path class="q-chrome-muted" d="{leaf}"/>'
        f'<rect class="q-chrome" x="{_num(min(spine_x, spine_x + direction * 2.0))}" '
        f'y="{_num(top)}" width="2" height="{_num(h)}"/>'
        f"</g>"
    )


def _num(value: float, places: int = 2) -> str:
    rounded = round(value, places)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{places}f}".rstrip("0").rstrip(".")


def _arabic_digits(value: int) -> str:
    return "".join("٠١٢٣٤٥٦٧٨٩"[int(d)] for d in str(value))


PLACE_NAMES = {"makkah": "مكية", "madinah": "مدنية"}


def _openings_markup(
    page: int,
    plan,
    *,
    geometry: Geometry,
    layout=None,
    shift=None,
    panel=None,
) -> str:
    """Surah heading bands and basmalah lines.

    These occupy whole lines of the grid and carry no words of their own, so
    they are drawn from the mushaf's line plan rather than from the verse data.

    The band is set to the full text measure - that is what makes it read as
    part of the page rather than a plaque dropped on it - which at the
    artwork's proportions makes it taller than one line slot. So it is placed
    against whatever sits above it (the running head on line one, the previous
    line's ink otherwise) and the basmalah beneath is then centred in the space
    that is actually left, instead of being crowded into a fixed slot.
    """
    if plan is None:
        return ""

    names = SurahNames(_require(SURAH_NAME_FONT, "surah-name font"))
    body = Typeface(_require(AMIRI, "Amiri"))
    chapters = {c["id"]: c for c in sources.chapters()}
    centre_x = geometry.panel_x + geometry.panel_w / 2
    band_bottoms: dict[int, float] = {}
    parts: list[str] = []

    # Work out every basmalah's room first and set them all to the tightest.
    # A page that opens three surahs would otherwise show the same words at
    # three different sizes, which reads as a mistake rather than a rhythm.
    width = geometry.panel_w * HEADER_WIDTH_RATIO
    band_h = _art().band_height(width)
    rooms: dict[int, float] = {}
    for line in sorted(plan.openings, key=lambda l: l.number):
        if line.kind != mushaf.BASMALLAH:
            continue
        prev = line.number - 1
        opens = any(
            o.number == prev and o.kind == mushaf.SURAH_NAME for o in plan.openings
        )
        above = (
            _ceiling_for(prev, geometry, layout) + HEADER_CLEAR + band_h
            if opens
            else _ceiling_for(line.number, geometry, layout)
        )
        below = _floor_for(line.number, geometry, layout)
        rooms[line.number] = max(12.0, below - above - 2 * BASMALAH_CLEAR)
    if rooms:
        tightest = min(rooms.values())
        rooms = {k: tightest for k in rooms}

    for line in sorted(plan.openings, key=lambda l: l.number):
        if line.kind == mushaf.SURAH_NAME and line.surah:
            # A band and its basmalah are given two consecutive lines by the
            # mushaf's own plan, so treat those two slots as one block and
            # stack them inside it. Measuring against the neighbours' worst
            # case instead would refuse a full-width band outright.
            if panel is not None:
                # An opening page has a slot cut for the band inside its own
                # panel; placing it on the body grid leaves it floating above
                # the decoration it belongs to.
                band_bottoms[line.number] = panel.title_cy + band_h / 2
                parts.append(
                    _surah_band(
                        line, width=panel.title_w, cx=panel.title_cx,
                        cy=panel.title_cy, names=names, body=body, chapters=chapters,
                    )
                )
            else:
                top = _ceiling_for(line.number, geometry, layout) + HEADER_CLEAR
                band_bottoms[line.number] = top + band_h
                parts.append(
                    _surah_band(
                        line, width=width, cx=centre_x, cy=top + band_h / 2,
                        names=names, body=body, chapters=chapters,
                    )
                )
        elif line.kind == mushaf.BASMALLAH and shift is not None:
            # on an opening page the basmalah is a line of the medallion,
            # set on its own grid line rather than tucked under the band
            baseline = geometry.baseline(line.number) + shift(line.number)
            face = Typeface(_require(BASMALAH_FONT, "basmalah font"))
            run = _fit_ink(
                lambda size, x, y: face.run(
                    chr(BASMALAH_CODEPOINT), size, x, y, anchor="middle"
                ),
                geometry.panel_w * BASMALAH_WIDTH_RATIO,
                geometry.line_pitch * 0.62,
                geometry.em * 2.0,
                centre_x,
                baseline - geometry.em * OPENING_RISE_EM,
            )
            parts.append(
                f'<g class="q-opening" id="q-basmalah-{line.number}" '
                f'data-line="{line.number}">'
                f'<path class="q-basmalah" d="{run.path}"/>'
                f"</g>"
            )
        elif line.kind == mushaf.BASMALLAH:
            above = band_bottoms.get(line.number - 1)
            if above is None:
                above = _ceiling_for(line.number, geometry, layout)
            below = _floor_for(line.number, geometry, layout)
            room = rooms[line.number]
            face = Typeface(_require(BASMALAH_FONT, "basmalah font"))
            # Fit on measured ink, not the advance: this glyph's advance runs a
            # quarter wider than the marks it paints (641 against 508 at size
            # 100), so sizing by advance drew it small.
            run = _fit_ink(
                lambda size, x, y: face.run(
                    chr(BASMALAH_CODEPOINT), size, x, y, anchor="middle"
                ),
                geometry.panel_w * BASMALAH_WIDTH_RATIO,
                room,
                geometry.em * 2.0,
                centre_x,
                (above + below) / 2,
            )
            parts.append(
                f'<g class="q-opening" id="q-basmalah-{line.number}" '
                f'data-line="{line.number}">'
                f'<path class="q-basmalah" d="{run.path}"/>'
                f"</g>"
            )
    return "".join(parts)


OPENING_PAGES = (1, 2)

def _art():
    """The module supplying the border, the surah band and the ayah mark."""
    from . import newlook

    return newlook


def _opening(page: int, plan, geometry: Geometry, half_widths):
    """For pages 1 and 2: the decoration, and the shift that drops the page's
    short lines into its writing panel. Elsewhere, nothing."""
    from . import opening as art

    if page not in OPENING_PAGES or plan is None:
        return None, "", None
    numbers = [l.number for l in plan.lines if l.number >= 2]
    if not numbers:
        return None, "", None
    first, last = min(numbers), max(numbers)
    block_h = (last - first) * geometry.line_pitch + geometry.em * (ASCENT_EM + DESCENT_EM)

    panel = art.opening(geometry, page, half_widths)
    block_h = (last - first) * art.OPENING_PITCH + geometry.em * (ASCENT_EM + DESCENT_EM)
    want_first = panel.text_centre - block_h / 2 + geometry.em * ASCENT_EM

    def shift(line_number: int) -> float:
        """Re-space as well as reposition: an opening page sets its handful of
        lines at its own pitch, not at the body page's."""
        if line_number < 2:
            return 0.0
        want = want_first + (line_number - first) * art.OPENING_PITCH
        return want - geometry.baseline(line_number)

    return shift, panel.markup, panel


def font_for(page: int, data: dict):
    """The font a page is set in, and which code field addresses it.

    Five of the 604 v2 page fonts are short of glyphs the page's own word list
    asks for - 24 words on page 121, fewer elsewhere - and every mirror,
    quran.com's own CDN included, serves the same file. Those pages fall back
    to the v1 font, which does carry them. v1 line widths vary where v2's are
    pre-justified, so such a page also gets its own measure: the widest line it
    actually sets, rather than the mushaf-wide constant.
    """
    font = PageFont(sources.page_font(page))
    needed = {
        ord(ch)
        for verse in data["verses"]
        for word in verse["words"]
        for ch in word["code_v2"]
        if ch != " "
    }
    if font.covers(needed):
        return font, "code_v2", None

    fallback = PageFont(sources.page_font_v1(page))
    lines: dict[int, list] = {}
    for verse in data["verses"]:
        for word in verse["words"]:
            lines.setdefault(word["line_number"], []).append(word)
    measure = max(
        sum(g.advance for g in fallback.shape(" ".join(w["code_v1"] for w in words)))
        for words in lines.values()
    )
    return fallback, "code_v1", measure


def build_page(
    page: int,
    theme_name: str = DEFAULT_THEME,
    *,
    geometry: Geometry = DEFAULT_GEOMETRY,
    simplify: float = SIMPLIFY_TOLERANCE,
) -> BuiltPage:
    data = mushaf.page_data(page) if mushaf.available() else sources.page_data(page)
    font, code_field, measure = font_for(page, data)
    plan = mushaf.plan(page) if mushaf.available() else None

    # An opening page is laid out twice: once to measure how wide its lines
    # actually run, and again once the oval cut to them is known. Two passes
    # for two pages of 604 is cheaper than guessing the widest line.
    half_widths: list[float] = []
    if page in OPENING_PAGES:
        probe = lay_out_page(page, data, font, geometry, simplify=0.0, plan=plan,
                             code_field=code_field, measure=measure)
        measured = {
            line.number: (max(w.x + w.width for w in line.words)
                          - min(w.x for w in line.words)) / 2
            for line in probe.lines
            if line.words
        }
        # The basmalah is a line of the block but carries no words, so it has
        # nothing to measure; without it the oval would be fitted to six lines
        # and asked to hold seven.
        numbers = sorted(l.number for l in plan.lines if l.number >= 2) if plan else []
        half_widths = [
            measured.get(n, geometry.panel_w * BASMALAH_WIDTH_RATIO / 2) for n in numbers
        ]
    shift, illumination, panel = _opening(page, plan, geometry, half_widths)
    layout = lay_out_page(
        page, data, font, geometry, simplify=simplify, plan=plan, shift=shift,
        code_field=code_field, measure=measure,
    )

    first = data["verses"][0]
    # The running head names the surah that *begins* on the page where one
    # does. A page that opens with the tail of the previous surah and then
    # starts a new one was being headed with the old name - page 586 read
    # 'Abasa when At-Takwir starts on it. Where several begin, the first of
    # them takes the head; the rest are named by their own bands.
    opening = [
        line.surah
        for line in (plan.lines if plan else ())
        if line.kind == mushaf.SURAH_NAME and line.surah
    ]
    surah = opening[0] if opening else first["chapter_id"]
    juz = first["juz_number"]

    chapters = {c["id"]: c for c in sources.chapters()}
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
            page, plan, geometry=geometry, layout=layout, shift=shift, panel=panel
        )
        + _catchword_markup(page, geometry, simplify=simplify),
        illumination=illumination,
        marker_for=_marker_renderer(geometry, digits),
        side=page_side(page),
        gutter=gutter_offset(page),
    )
    return BuiltPage(page=page, theme=theme_name, svg=svg, layout=layout)
