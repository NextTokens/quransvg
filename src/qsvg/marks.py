"""Separating tashkeel from the rasm inside a word glyph.

A colour-separated mushaf sets the consonantal skeleton (the *rasm*, together
with the letter-identifying dots) in one colour and the vowel marks (*tashkeel*)
in another. Doing that here is awkward, because the KFGQPC page fonts give us
no help at all:

* the word glyphs are **flat traced outlines** — 178 simple glyphs, zero
  composites — so there are no components to pull apart;
* every mark was traced individually, so identical marks are not identical
  shapes. Clustering the page's 1,308 contours by shape yields 1,280 distinct
  signatures: no two of the 192 fathas match.

So the split has to be inferred from geometry. What makes that tractable is a
constraint from outside the font: the Uthmani text of each word says exactly how
many combining marks it carries. Rather than applying a global threshold — which
cannot separate dots from harakat, since both are small and both sit off the
letter body — each word is scored on its own and only its own mark count is
taken. Errors stay local to a word instead of accumulating across the page.

This is inference, not ground truth. It never moves or reshapes an outline: a
misclassification changes a colour, never a letter.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from fontTools.pens.boundsPen import BoundsPen

from .geometry import UNITS_PER_EM
from fontTools.pens.recordingPen import DecomposingRecordingPen

#: Marks that belong to the rasm for colouring purposes. The superscript alef
#: is a letter that happens to be encoded as a combining mark, and hamza sits
#: on the rasm rather than above it; both usually fuse into the letter outline.
RASM_MARKS = frozenset({"ٰ", "ٔ", "ٕ", "ٓ"})

#: Waqf and recitation signs — where to pause, where pausing is preferable,
#: sajdah, and the small letters that record variant readings. They are not
#: vowels and a colour-separated mushaf treats them as their own layer. They
#: also sit clear above everything else, which is what lets them be told apart
#: from the harakat below them.
#: U+06D6..U+06ED is the Qur'anic annotation block: the waqf ligatures,
#: the small high/low letters, and the "zero" signs marking silent letters.
WAQF_MARKS = frozenset(chr(cp) for cp in range(0x06D6, 0x06EE))

#: Marks that hang below the baseline. Everything else rides above it. Knowing
#: which side a mark belongs on lets the two sides be ranked independently, so
#: a kasra below a letter is never confused with a sukun above it.
BELOW_MARKS = frozenset({"ِ", "ٍ", "ۭ"})

#: A contour this large relative to the biggest one in the glyph is a letter
#: body, never a mark.
BODY_AREA_RATIO = 0.25

#: A vowel mark never crosses the writing line: harakat sit clear above it,
#: kasra and the small low meem clear below. A contour that straddles the line
#: is a letter, however small - and some letters are small. A lone waw is a
#: fifth the area of the alif beside it, so `و` in وَيُقِيمُونَ and the opening
#: waw of وَلَـٰكِن fell under the area test, joined the pool of satellites, and
#: got taken as a haraka: 61 letters painted as marks across 32 pages.
#: Measured in glyph space, where y=0 is the baseline.
LINE_BELOW = 0.03        # em a letter must reach under the line
LINE_ABOVE = 0.12        # and over it


@dataclass(frozen=True)
class Contour:
    ops: tuple
    bounds: tuple[float, float, float, float]
    #: Distinguishes contours that happen to have the same shape and box, so a
    #: word containing two identical dots does not collapse them into one.
    index: int = 0

    def shifted(self, dx: float, index: int) -> "Contour":
        """The same outline, with its box moved along the line."""
        x0, y0, x1, y1 = self.bounds
        return Contour(self.ops, (x0 + dx, y0, x1 + dx, y1), index)

    @property
    def area(self) -> float:
        x0, y0, x1, y1 = self.bounds
        return (x1 - x0) * (y1 - y0)


@dataclass(frozen=True)
class MarkCensus:
    """How many marks of each kind a word carries, per side of the line."""

    tashkeel_above: int = 0
    tashkeel_below: int = 0
    waqf_above: int = 0
    waqf_below: int = 0

    @property
    def total(self) -> int:
        return (
            self.tashkeel_above + self.tashkeel_below
            + self.waqf_above + self.waqf_below
        )


def census(text: str) -> MarkCensus:
    """Count a word's marks by kind and by side, from its Uthmani spelling."""
    ta = tb = wa = wb = 0
    for ch in text:
        if not unicodedata.category(ch).startswith("M") or ch in RASM_MARKS:
            continue
        below = ch in BELOW_MARKS
        if ch in WAQF_MARKS:
            wb, wa = (wb + 1, wa) if below else (wb, wa + 1)
        else:
            tb, ta = (tb + 1, ta) if below else (tb, ta + 1)
    return MarkCensus(ta, tb, wa, wb)


def is_divine_name(text: str) -> bool:
    """Whether a word carries the lafz al-jalalah.

    Tested on the bare consonants so the many vowelled spellings collapse to
    one form. This matches the name alone and with a proclitic (bi-, li-, wa-),
    which on page 248 covers all four occurrences.
    """
    bare = "".join(
        ch for ch in text if not unicodedata.category(ch).startswith("M")
    ).strip()
    return bare.endswith("لله")      # ...l-l-h


def split_contours(glyph_set, glyph_name: str) -> list[Contour]:
    """Every closed contour of a glyph, with its bounding box."""
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[glyph_name].draw(pen)

    groups: list[list] = []
    current: list = []
    for op, args in pen.value:
        if op == "moveTo" and current:
            groups.append(current)
            current = []
        current.append((op, args))
    if current:
        groups.append(current)

    out: list[Contour] = []
    for group in groups:
        bounds = BoundsPen(glyph_set)
        for op, args in group:
            getattr(bounds, op)(*args)
        if bounds.bounds:
            out.append(Contour(ops=tuple(group), bounds=bounds.bounds, index=len(out)))
    return out


def _on_the_line(contour) -> bool:
    """Does this contour sit on the writing line? Then it is a letter."""
    return (
        contour.bounds[1] < -LINE_BELOW * UNITS_PER_EM
        and contour.bounds[3] > LINE_ABOVE * UNITS_PER_EM
    )


def _points(contour: "Contour") -> list[tuple[float, float]]:
    """The contour flattened to its points, enough to test containment."""
    out: list[tuple[float, float]] = []
    for _command, points in contour.ops:
        out.extend((float(x), float(y)) for x, y in points)
    return out


def _inside(polygon: list[tuple[float, float]], x: float, y: float) -> bool:
    """Ray cast: is (x, y) within this outline?"""
    hit = False
    count = len(polygon)
    for index in range(count):
        x0, y0 = polygon[index]
        x1, y1 = polygon[(index + 1) % count]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-12) + x0:
            hit = not hit
    return hit


def _encloses(outer: "Contour", inner: "Contour") -> bool:
    """Is `inner` a counter of `outer` - the hole inside a letter?

    The box test alone is not enough, and the difference is visible: the wide
    box of a ك covers the kasra written beneath it, so the mark was read as a
    counter and left in the rasm, unpainted. A counter's centre lies *within*
    the letter's outline; a mark below it does not.
    """
    ob, ib = outer.bounds, inner.bounds
    if not (ob[0] <= ib[0] and ob[1] <= ib[1] and ob[2] >= ib[2] and ob[3] >= ib[3]):
        return False
    polygon = _points(outer)
    if len(polygon) < 3:
        return False
    return _inside(polygon, (ib[0] + ib[2]) / 2, (ib[1] + ib[3]) / 2)


def classify(
    contours: list[Contour], marks: MarkCensus
) -> tuple[list[Contour], list[Contour], list[Contour]]:
    """Split a word's contours into (rasm, tashkeel, waqf).

    Letter bodies are the large contours, and whatever they enclose is a
    counter, so both stay with the rasm. The rest are satellites, split by which
    side of the letter band they sit on and ranked by how far clear of it they
    stand: dots hug the letters, harakat stand off them, and the waqf signs
    stand furthest of all. Taking exactly as many of each as the text calls for
    keeps any error inside the word that caused it.
    """
    if not contours:
        return [], [], []
    if marks.total <= 0:
        return list(contours), [], []

    largest = max(c.area for c in contours)
    bodies = [
        c for c in contours
        if c.area >= BODY_AREA_RATIO * largest or _on_the_line(c)
    ]
    if not bodies:
        return list(contours), [], []

    band_bottom = min(c.bounds[1] for c in bodies)
    band_top = max(c.bounds[3] for c in bodies)

    rasm: list[Contour] = list(bodies)
    above: list[Contour] = []
    below: list[Contour] = []
    for contour in contours:
        if contour in bodies:
            continue
        if any(_encloses(body, contour) for body in bodies):
            rasm.append(contour)                      # a counter inside a letter
            continue
        over = contour.bounds[3] - band_top
        under = band_bottom - contour.bounds[1]
        (above if over >= under else below).append(contour)

    above.sort(key=lambda c: c.bounds[3], reverse=True)
    below.sort(key=lambda c: c.bounds[1])

    tashkeel: list[Contour] = []
    waqf: list[Contour] = []
    for side, n_waqf, n_tashkeel in (
        (above, marks.waqf_above, marks.tashkeel_above),
        (below, marks.waqf_below, marks.tashkeel_below),
    ):
        cut_waqf = min(n_waqf, len(side))
        cut_tash = min(n_waqf + n_tashkeel, len(side))
        waqf.extend(side[:cut_waqf])
        tashkeel.extend(side[cut_waqf:cut_tash])
        rasm.extend(side[cut_tash:])                  # the letters' own dots

    return rasm, tashkeel, waqf
