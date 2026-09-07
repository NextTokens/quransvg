"""Splitting a v4 word into rasm, tashkeel and waqf.

The v2 build infers all three from geometry, because its fonts say nothing. The
v4 edition says two of the three outright, and the third is easier to infer once
the first two are taken out of the way — so this is `qsvg.marks` with its
premises corrected rather than a second guess at the same problem.

Three things differ.

*A figure, not a contour.* A letter and the counter inside it are one shape, and
so are a damma and its eye. `qsvg.marks` classifies contour by contour, and the
v4 build then emits one path per class — so a ring could go to one path and its
hole to another, and the nonzero fill rule filled the hole in solid. That is the
"smudge" over a tanween. Here the unit of both classification and emission is a
*figure*: an outer contour with whatever it encloses, kept together from end to
end. Containment is resolved inside one COLR layer glyph, which is where a real
hole always sits.

*The waqf signs are stated.* The word table marks them with discriminator 5, so
they are not inferred at all, and the marks left to rank are purely vowels.

*A letter may stand clear of the writing line.* `qsvg.marks` keeps a contour out
of the mark pool if it is a quarter the size of the largest, or if it straddles
the line. A v4 initial alif with hamza below does neither — it is slim, and its
foot stops just above the line — so it was ranked as a haraka and painted in the
vowel colour. A tall narrow shape whose foot comes down to the line is a letter,
whether or not it crosses it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from qsvg.geometry import UNITS_PER_EM
from qsvg.marks import (
    BODY_AREA_RATIO,
    WAQF_MARKS,
    BELOW_MARKS,
    RASM_MARKS,
    MarkCensus,
    _encloses,
    _on_the_line,
)

#: A shape this tall whose foot reaches the writing line is a letter, however
#: slim it is and whether or not it crosses the line.
TALL_EM = 0.50
FOOT_EM = 0.05


@dataclass
class Figure:
    """One shape of a word: an outer contour and the counters inside it."""

    outer: object
    holes: list = field(default_factory=list)
    palette: int = 0
    translate: tuple = (0.0, 0.0)
    stated_waqf: bool = False

    @property
    def contours(self) -> list:
        return [self.outer, *self.holes]

    @property
    def bounds(self):
        return self.outer.bounds

    @property
    def area(self) -> float:
        return self.outer.area


def build_figures(groups) -> list[Figure]:
    """Resolve containment inside each layer glyph.

    `groups` is a sequence of (contours, palette, translate, stated_waqf), one
    per COLR layer glyph of the word. A hole is always drawn in the same layer
    as the shape it punches, so containment is never tested across layers -
    which is what stops a letter from swallowing the mark sitting inside its
    bounding box but drawn separately.
    """
    out: list[Figure] = []
    for contours, palette, translate, stated_waqf in groups:
        ordered = sorted(contours, key=lambda c: -c.area)
        taken: set[int] = set()
        figures: list[Figure] = []
        for outer in ordered:
            if outer.index in taken:
                continue
            taken.add(outer.index)
            figure = Figure(outer=outer, palette=palette, translate=translate,
                            stated_waqf=stated_waqf)
            for inner in ordered:
                if inner.index in taken:
                    continue
                if _encloses(outer, inner):
                    figure.holes.append(inner)
                    taken.add(inner.index)
            figures.append(figure)
        out.extend(figures)
    return out


def _is_letter(figure: Figure, largest: float) -> bool:
    x0, y0, x1, y1 = figure.bounds
    if figure.area >= BODY_AREA_RATIO * largest:
        return True
    if _on_the_line(figure.outer):
        return True
    # A tall shape standing on the line: the initial alif, the lone lam.
    return (y1 - y0) >= TALL_EM * UNITS_PER_EM and y0 <= FOOT_EM * UNITS_PER_EM


def classify(figures: list[Figure], census: MarkCensus):
    """Split a word's figures into (rasm, tashkeel, waqf).

    Same shape as `qsvg.marks.classify` - letter bodies, then the satellites
    ranked by how far clear of the letter band they stand, then exactly as many
    of each taken as the spelling calls for - but over figures, and with the
    waqf signs removed first because the table names them.
    """
    if not figures:
        return [], [], []

    waqf = [f for f in figures if f.stated_waqf]
    rest = [f for f in figures if not f.stated_waqf]
    if not rest:
        return [], [], waqf

    largest = max(f.area for f in rest)
    bodies = [f for f in rest if _is_letter(f, largest)]
    if not bodies:
        return rest, [], waqf

    wanted = census.tashkeel_above + census.tashkeel_below
    if wanted <= 0:
        return rest, [], waqf

    band_bottom = min(f.bounds[1] for f in bodies)
    band_top = max(f.bounds[3] for f in bodies)

    rasm = list(bodies)
    above: list[Figure] = []
    below: list[Figure] = []
    body_ids = {id(f) for f in bodies}
    for figure in rest:
        if id(figure) in body_ids:
            continue
        over = figure.bounds[3] - band_top
        under = band_bottom - figure.bounds[1]
        (above if over >= under else below).append(figure)

    above.sort(key=lambda f: f.bounds[3], reverse=True)
    below.sort(key=lambda f: f.bounds[1])

    tashkeel: list[Figure] = []
    for side, count in ((above, census.tashkeel_above),
                        (below, census.tashkeel_below)):
        cut = min(count, len(side))
        tashkeel.extend(side[:cut])
        rasm.extend(side[cut:])          # the letters' own dots
    return rasm, tashkeel, waqf


def census(text: str) -> MarkCensus:
    """The word's vowel marks. Waqf signs are excluded: the table states them."""
    import unicodedata

    above = below = 0
    for ch in text:
        if not unicodedata.category(ch).startswith("M") or ch in RASM_MARKS:
            continue
        if ch in WAQF_MARKS:
            continue
        if ch in BELOW_MARKS:
            below += 1
        else:
            above += 1
    return MarkCensus(tashkeel_above=above, tashkeel_below=below)


def _is_quad(contour) -> bool:
    """A closed contour of at most four straight lines.

    No Arabic letterform or mark in these fonts is one: they are traced
    outlines, averaging nine contours of hundreds of points. A three- or
    four-sided polygon is drawn furniture.
    """
    return (all(op[0] in ("moveTo", "lineTo", "closePath") for op in contour.ops)
            and sum(1 for op in contour.ops if op[0] == "lineTo") <= 4)


def annotations(figures: list[Figure]) -> set[int]:
    """The thin rectangles QCF v4 draws around a mark, and nothing else.

    This edition boxes the parts of a word that are dropped if the reader stops
    there. At `غِشَـٰوَةٌۭ ۖ` on page 3 - a صلے, where stopping is allowed - the
    tanween and the two dots of the ta marbuta each sit in their own thin
    rectangle and are greyed with the "silent" colour, because at that pause the
    tanween is not pronounced and the ta marbuta is read as ha.

    What is boxed is therefore *real ink*: without the tanween and those dots
    the word is not spelled. Only the rectangle is the annotation, and only the
    rectangle is marked here - `svg` hides it unless the page is in tajweed
    mode, which leaves the plain page reading exactly as the printed one does
    and keeps the note where it means something.

    A frame is a rectangle with a rectangular hole; `build_figures` has already
    paired the two. Nothing else in these fonts is a straight-sided polygon.
    """
    return {id(f) for f in figures
            if _is_quad(f.outer) and f.holes and all(_is_quad(h) for h in f.holes)}
