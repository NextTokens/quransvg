"""Chrome text as outlines: surah name, juz label, page number.

The Qur'anic text is already font-free, and the chrome has to be too. An SVG
that falls back to ``<text>`` for the surah name would render differently on
every device - and on the several mobile SVG renderers that do no Arabic
shaping at all, it would render as disconnected letters, which is worse than
wrong. So the chrome is shaped once here and emitted as paths.

Two typefaces do the work:

* the QUL surah-name font, in which each surah's name is a single decorative
  glyph in the private use area at ``U+E000 + surah``. ``U+E000`` itself holds
  the word "surah", so the two together compose the header the printed mushaf
  actually shows;
* Amiri, an OFL naskh face, for the juz label and anything else in words.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

from .pathenc import encode, scale_flip

#: Arabic-Indic and ASCII digits — the runs that must stay left-to-right when
#: everything around them is being reversed for right-to-left setting.
_DIGITS = re.compile(r"[0-9٠-٩۰-۹]+")

SURAH_NAME_BASE = 0xE000

#: Arabic ordinals for the thirty ajza. Written out rather than derived,
#: because Arabic ordinals are irregular and a generated form would be wrong.
JUZ_ORDINALS = (
    "الأول", "الثاني", "الثالث", "الرابع", "الخامس",
    "السادس", "السابع", "الثامن", "التاسع", "العاشر",
    "الحادي عشر", "الثاني عشر", "الثالث عشر", "الرابع عشر", "الخامس عشر",
    "السادس عشر", "السابع عشر", "الثامن عشر", "التاسع عشر", "العشرون",
    "الحادي والعشرون", "الثاني والعشرون", "الثالث والعشرون", "الرابع والعشرون",
    "الخامس والعشرون", "السادس والعشرون", "السابع والعشرون", "الثامن والعشرون",
    "التاسع والعشرون", "الثلاثون",
)


def juz_label(juz: int) -> str:
    if not 1 <= juz <= 30:
        raise ValueError(f"juz must be in 1..30, got {juz}")
    return f"الجزء {JUZ_ORDINALS[juz - 1]}"


@dataclass(frozen=True)
class Run:
    """A shaped, outlined piece of text ready to place."""

    path: str
    width: float     # advance width, which for decorative faces can differ
    ascent: float
    descent: float
    #: The real extent of the marks on the page. Decorative glyphs routinely
    #: paint well outside their advance, so anything that has to *fit* must be
    #: measured against this rather than against `width`.
    ink: tuple[float, float, float, float] | None = None

    @property
    def ink_width(self) -> float:
        return (self.ink[2] - self.ink[0]) if self.ink else self.width

    @property
    def ink_height(self) -> float:
        return (self.ink[3] - self.ink[1]) if self.ink else 0.0


class Typeface:
    """Shape a string with a real font and return its outlines."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        data = self.path.read_bytes()
        self._hb = hb.Font(hb.Face(hb.Blob(data)))
        self._tt = TTFont(self.path)
        self._glyphs = self._tt.getGlyphSet()
        self._order = self._tt.getGlyphOrder()
        self.units_per_em = self._tt["head"].unitsPerEm

    @lru_cache(maxsize=512)
    def _record(self, glyph_name: str) -> tuple:
        pen = DecomposingRecordingPen(self._glyphs)
        self._glyphs[glyph_name].draw(pen)
        return tuple(pen.value)

    def measure(self, text: str, size: float) -> float:
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(self._hb, buffer, {})
        units = sum(p.x_advance for p in buffer.glyph_positions)
        return units * size / self.units_per_em

    def run(
        self,
        text: str,
        size: float,
        x: float,
        y: float,
        anchor: str = "start",
        *,
        rtl: bool = False,
    ) -> Run:
        """Outline `text` at `size`, with its baseline at `y`.

        `anchor` follows the SVG convention: start, middle or end.

        Pass `rtl` when the string is Arabic but its codepoints do not say so —
        private-use glyphs such as the decorative surah names carry no script
        property, so HarfBuzz guesses left-to-right and silently reverses the
        reading order.
        """
        buffer = hb.Buffer()
        buffer.add_str(text)
        if rtl:
            buffer.direction = "rtl"
            buffer.script = "Arab"
        else:
            buffer.guess_segment_properties()

        if str(buffer.direction) == "rtl" and _DIGITS.search(text):
            # HarfBuzz shapes; it does not run the bidi algorithm. In an RTL
            # buffer it reverses everything, and a number is the one thing that
            # must not be reversed: Arabic-Indic digits are bidi class AN and
            # read left to right inside right-to-left text. Un-reversed, 286
            # was set as ٦٨٢ in every surah header that carries a three-digit
            # ayah count. Flipping each digit run here means HarfBuzz's own
            # reversal puts it back the right way round.
            buffer = hb.Buffer()
            buffer.add_str(_DIGITS.sub(lambda m: m.group(0)[::-1], text))
            buffer.direction = "rtl"
            buffer.script = "Arab"

        hb.shape(self._hb, buffer, {})

        scale = size / self.units_per_em
        total = sum(p.x_advance for p in buffer.glyph_positions) * scale
        if anchor == "middle":
            origin = x - total / 2
        elif anchor == "end":
            origin = x - total
        else:
            origin = x

        parts: list[str] = []
        bounds: list[float] = []
        pen = 0.0
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
            name = self._order[info.codepoint]
            contours = self._record(name)
            if contours:
                tx = origin + (pen + position.x_offset) * scale
                ty = y - position.y_offset * scale
                parts.append(encode(contours, scale_flip(scale, tx, ty), places=1))
                pen_bounds = BoundsPen(self._glyphs)
                for command, points in contours:
                    getattr(pen_bounds, command)(*points)
                if pen_bounds.bounds:
                    gx0, gy0, gx1, gy1 = pen_bounds.bounds
                    box = (tx + gx0 * scale, ty - gy1 * scale,
                           tx + gx1 * scale, ty - gy0 * scale)
                    bounds = box if not bounds else (
                        min(bounds[0], box[0]), min(bounds[1], box[1]),
                        max(bounds[2], box[2]), max(bounds[3], box[3]),
                    )
            pen += position.x_advance
        return Run(
            path="".join(parts), width=total,
            ascent=size * 0.8, descent=size * 0.2,
            ink=tuple(bounds) if bounds else None,
        )


class SurahNames:
    """The decorative one-glyph-per-surah face."""

    def __init__(self, path: Path | str):
        self._face = Typeface(path)
        cmap = TTFont(str(path)).getBestCmap()
        self._available = {
            code - SURAH_NAME_BASE
            for code in cmap
            if SURAH_NAME_BASE < code < SURAH_NAME_BASE + 200
        }
        self._has_word = SURAH_NAME_BASE in cmap

    def has(self, surah: int) -> bool:
        return surah in self._available

    def run(
        self,
        surah: int,
        size: float,
        x: float,
        y: float,
        anchor: str = "middle",
        *,
        with_word: bool = True,
    ) -> Run:
        """Outline a surah's decorative name.

        The word "surah" and the name are separate glyphs, placed individually
        so the space between them can be controlled. They share one baseline:
        the font already draws them to sit level, and nudging them apart to
        match ink boxes only staggers them, since those boxes take in the
        diacritics above and the descenders below rather than where the letters
        rest.
        """
        if not self.has(surah):
            raise ValueError(
                f"the surah-name font has no glyph for surah {surah}; "
                f"it covers {min(self._available)}..{max(self._available)}"
            )
        # Reading order: the word "surah" first, then the name.
        chars = [chr(SURAH_NAME_BASE + surah)]
        if with_word and self._has_word:
            chars = [chr(SURAH_NAME_BASE)] + chars

        probes = [self._face.run(c, size, 0.0, 0.0, "start") for c in chars]
        gap = size * 0.10
        total = sum(p.width for p in probes) + gap * (len(probes) - 1)
        if anchor == "middle":
            left = x - total / 2
        elif anchor == "end":
            left = x - total
        else:
            left = x

        paths: list[str] = []
        box: tuple[float, float, float, float] | None = None
        cursor = left + total          # right-to-left: the word sits rightmost
        for char, probe in zip(chars, probes):
            cursor -= probe.width
            placed = self._face.run(char, size, cursor, y, "start")
            paths.append(placed.path)
            if placed.ink:
                box = placed.ink if box is None else (
                    min(box[0], placed.ink[0]), min(box[1], placed.ink[1]),
                    max(box[2], placed.ink[2]), max(box[3], placed.ink[3]),
                )
            cursor -= gap
        return Run(
            path="".join(paths), width=total,
            ascent=size * 0.8, descent=size * 0.2, ink=box,
        )
