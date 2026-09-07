"""Turn a page's word list into positioned outlines on the fixed baseline grid.

The mushaf fonts already justify each line, so this module's job is modest and
deliberately conservative: place the shaped glyphs on the grid, and absorb the
sub-two-percent remainder between the font's natural line width and the panel
width in the inter-word gaps. Qur'anic word forms are never stretched, squeezed
or re-spaced beyond that remainder.

Each word comes out as three separate outlines — rasm, tashkeel and waqf — so a
theme can colour the consonantal skeleton, the vowel marks and the recitation
signs independently, the way a colour-separated mushaf does.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from . import marks as markmod
from .geometry import Geometry
from .glyphs import PageFont

# Fallback used only when the mushaf line plan is unavailable: a line whose
# natural width falls this far short of the measure cannot be a justified body
# line, so it is centred rather than stretched across the page.
CENTRE_THRESHOLD = 0.86

# Guard rail: if justification would ever have to move a gap by more than this
# fraction of an em, something is wrong with the calibration and we want to know.
MAX_GAP_ADJUST_EM = 0.35


@dataclass(frozen=True)
class PlacedWord:
    """One word of the mushaf, positioned in viewBox coordinates."""

    location: str          # "surah:ayah:word", e.g. "12:104:1"
    line: int
    kind: str              # "word" | "end"
    text: str              # Uthmani text, for accessibility and search
    rasm: str              # consonantal skeleton, including the letters' dots
    tashkeel: str          # vowel marks
    waqf: str              # pause and recitation signs
    divine_name: bool      # carries the lafz al-jalalah
    x: float               # left edge of the word's advance box
    width: float
    baseline: float
    #: Where this word's ink actually reaches. Naskh paints past its advance,
    #: by 3 units on a body page and more on the opening pages' wider forms, so
    #: a hit box derived from the advance alone clips the tips of the letters.
    ink_x0: float
    ink_x1: float
    ink_y0: float
    ink_y1: float

    @property
    def path(self) -> str:
        """Every layer of the word, for callers that want it as one outline."""
        return self.rasm + self.tashkeel + self.waqf


@dataclass
class LayoutLine:
    number: int
    baseline: float
    words: list[PlacedWord] = field(default_factory=list)
    justified: bool = True
    natural_em: float = 0.0
    gap_adjust_em: float = 0.0
    #: Where this line's ink actually reaches, in page coordinates. The
    #: page-wide ascent and descent are worst cases across every glyph in the
    #: mushaf; using them to place a surah band would refuse arrangements that
    #: in fact have room.
    ink_top: float | None = None
    ink_bottom: float | None = None


@dataclass
class PageLayout:
    page: int
    geometry: Geometry
    lines: list[LayoutLine]

    @property
    def words(self) -> list[PlacedWord]:
        return [w for line in self.lines for w in line.words]


def _group_words(page_data: dict, plan=None) -> dict[int, list[dict]]:
    """Words per line, in logical (reading) order.

    The mushaf's own layout table says how many words sit on each line, and it
    is the better authority: quran.com's `line_number` puts 18 words on line 1
    of page 144 where the printed page sets 9, and does the same on a handful
    of other pages - 25 lines in all, each of them running half again to twice
    the width of the measure. Where the table's counts add up to the page's
    words, they decide; otherwise the API's numbering stands.
    """
    ordered = [word for verse in page_data["verses"] for word in verse["words"]]
    if plan is not None:
        ayah_lines = [line for line in plan.lines if line.words]
        if sum(line.words for line in ayah_lines) == len(ordered):
            out: dict[int, list[dict]] = {}
            cursor = 0
            for line in ayah_lines:
                out[line.number] = ordered[cursor:cursor + line.words]
                cursor += line.words
            return out

    lines: dict[int, list[dict]] = defaultdict(list)
    for word in ordered:
        lines[word["line_number"]].append(word)
    return dict(sorted(lines.items()))


def _cluster_to_word(codes: list[str]) -> dict[int, int]:
    """Map each character index of the shaping string to its word index."""
    mapping: dict[int, int] = {}
    cursor = 0
    for index, code in enumerate(codes):
        for offset in range(len(code)):
            mapping[cursor + offset] = index
        cursor += len(code)
        mapping[cursor] = index      # the separator that follows this word
        cursor += 1
    return mapping


def lay_out_page(
    page: int,
    page_data: dict,
    font: PageFont,
    geometry: Geometry,
    *,
    simplify: float = 0.0,
    plan=None,
    shift=None,
    code_field: str = "code_v2",
    measure: float | None = None,
) -> PageLayout:
    """`shift(line_number)` moves a line's baseline, for the opening pages whose
    eight short lines are gathered into a medallion rather than set from the
    top of the grid."""
    grouped = _group_words(page_data, plan)
    measure = measure or geometry.measure_units
    lines: list[LayoutLine] = []

    for number, words in grouped.items():
        codes = [w[code_field] for w in words]
        shaped = font.shape(" ".join(codes))
        cluster_map = _cluster_to_word(codes)

        natural = sum(g.advance for g in shaped)
        gaps = sum(1 for g in shaped if g.is_space)

        # The mushaf's own line plan knows which lines are set centred — the
        # closing line of a surah, most often. Fall back to measuring only when
        # that plan is unavailable.
        planned = plan.line(number) if plan is not None else None
        if planned is not None:
            justified = not planned.centered
        else:
            justified = natural >= CENTRE_THRESHOLD * measure

        if justified and gaps:
            gap_adjust = (measure - natural) / gaps
            start = 0.0
        else:
            gap_adjust = 0.0
            start = (measure - natural) / 2 if not justified else 0.0

        baseline = geometry.baseline(number) + (shift(number) if shift else 0.0)
        line = LayoutLine(
            number=number,
            baseline=baseline,
            justified=justified,
            natural_em=natural / geometry.units_per_em,
            gap_adjust_em=gap_adjust / geometry.units_per_em,
        )
        if abs(line.gap_adjust_em) > MAX_GAP_ADJUST_EM:
            # Not every line the plan calls justified can be: a line of four
            # words at half the measure would need two ems in every gap. Centre
            # it instead of stretching it, and instead of stopping the build.
            gap_adjust = 0.0
            start = (measure - natural) / 2
            line.justified = False
            line.gap_adjust_em = 0.0

        # Walk the shaped glyphs left to right, accumulating the pen position.
        # A word's glyphs stay contiguous, so its contours can be gathered and
        # classified together before any of them are written out.
        pen = start
        pending: dict[int, dict] = {}
        counter = 0
        for glyph in shaped:
            if glyph.is_space:
                pen += glyph.advance + gap_adjust
                continue
            index = cluster_map[glyph.cluster]
            entry = pending.setdefault(
                index, {"x": pen, "end": pen, "items": [], "ink": None}
            )
            entry["x"] = min(entry["x"], pen)
            entry["end"] = max(entry["end"], pen + glyph.advance)
            translate = (
                geometry.panel_x + (pen + glyph.x_offset) * geometry.scale,
                baseline - glyph.y_offset * geometry.scale,
            )
            for contour in font.contours(glyph.glyph_name):
                # Shift the box along the line so contours from different
                # glyphs of one word are compared in the same space.
                entry["items"].append((contour.shifted(pen, counter), translate))
                counter += 1
                cx0, cy0, cx1, cy1 = contour.bounds
                left = translate[0] + cx0 * geometry.scale
                right = translate[0] + cx1 * geometry.scale
                top = translate[1] - cy1 * geometry.scale
                bottom = translate[1] - cy0 * geometry.scale
                entry["ink"] = (
                    (left, right, top, bottom)
                    if entry["ink"] is None
                    else (
                        min(entry["ink"][0], left),
                        max(entry["ink"][1], right),
                        min(entry["ink"][2], top),
                        max(entry["ink"][3], bottom),
                    )
                )
                line.ink_top = top if line.ink_top is None else min(line.ink_top, top)
                line.ink_bottom = (
                    bottom if line.ink_bottom is None else max(line.ink_bottom, bottom)
                )
            pen += glyph.advance

        for index, word in enumerate(words):
            entry = pending.get(index)
            if entry is None:
                continue
            text = word["text_uthmani"]
            items = entry["items"]
            rasm, tashkeel, waqf = markmod.classify(
                [contour for contour, _ in items], markmod.census(text)
            )

            def render(selected) -> str:
                chosen = {contour.index for contour in selected}
                return "".join(
                    font.encode_contour(
                        contour,
                        scale=geometry.scale,
                        translate=translate,
                        simplify=simplify,
                    )
                    for contour, translate in items
                    if contour.index in chosen
                )

            line.words.append(
                PlacedWord(
                    location=word["location"],
                    line=number,
                    kind="end" if word["char_type_name"] == "end" else "word",
                    text=text,
                    rasm=render(rasm),
                    tashkeel=render(tashkeel),
                    waqf=render(waqf),
                    divine_name=markmod.is_divine_name(text),
                    x=geometry.panel_x + entry["x"] * geometry.scale,
                    width=(entry["end"] - entry["x"]) * geometry.scale,
                    baseline=baseline,
                    ink_x0=(entry["ink"] or (0.0,) * 4)[0],
                    ink_x1=(entry["ink"] or (0.0,) * 4)[1],
                    ink_y0=(entry["ink"] or (0.0,) * 4)[2],
                    ink_y1=(entry["ink"] or (0.0,) * 4)[3],
                )
            )
        line.words.sort(key=lambda w: w.x)
        lines.append(line)

    return PageLayout(page=page, geometry=geometry, lines=lines)
