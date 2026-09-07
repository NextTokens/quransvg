"""The QCF v4 colour page fonts.

Like the v2 fonts these carry one glyph per word, drawn for one page only. What
is new is `COLR`/`CPAL`: a word glyph is not a single outline but a list of
*layer* glyphs, each pointing at an entry in a colour palette. Those layers are
the tajweed separation — a layer is the letter, or run of letters, a rule
applies to — and they were cut by the people who drew the page.

Five palettes ship alongside the default, one of them built for a dark ground.
We do not use the palettes as colours: they are read once to learn which index
means which rule, and the colours themselves come from the theme, like every
other colour on the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont

from qsvg.marks import split_contours
from qsvg.pathenc import encode, scale_flip
from qsvg.simplify import simplify_contours

#: The palette index a glyph layer carries when it is ordinary ink.
BASE_INDEX = 0

#: The edition's word space, in font units. Read from the fonts rather than
#: assumed - and then fixed as a constant, because six of the 604 declare 1000
#: (pages 14, 18, 19, 23, 30, 41) and one declares 0 (page 61) where the other
#: 597 declare 100. Trusting each font's own figure inflated every line on
#: those seven pages by up to a fifth.
SPACE_UNITS = 100.0


@dataclass(frozen=True)
class PlacedGlyph:
    glyph_name: str
    x: float          # pen position within the word, in font units
    advance: float


@dataclass(frozen=True)
class Layer:
    """One colour layer of a glyph: an outline and what it means."""

    glyph_name: str
    palette: int


class ColourPageFont:
    """One page of the v4 colour mushaf."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        data = self.path.read_bytes()
        self._hb = hb.Font(hb.Face(hb.Blob(data)))
        self._tt = TTFont(self.path)
        self._glyph_set = self._tt.getGlyphSet()
        self._order = self._tt.getGlyphOrder()
        self._cmap = self._tt.getBestCmap()
        self._hmtx = self._tt["hmtx"]
        self._layers = self._tt["COLR"].ColorLayers
        self.units_per_em: int = self._tt["head"].unitsPerEm

    # --- what is on the page ------------------------------------------------

    def has(self, char: str) -> bool:
        return ord(char) in self._cmap

    def glyph_name(self, char: str) -> str | None:
        return self._cmap.get(ord(char))

    def advance(self, glyph_name: str) -> float:
        return float(self._hmtx[glyph_name][0])

    @property
    def space(self) -> float:
        name = self._cmap.get(0x20)
        declared = self.advance(name) if name else SPACE_UNITS
        # Seven of the 604 fonts declare a space that is not the edition's.
        return declared if 0 < declared <= 2 * SPACE_UNITS else SPACE_UNITS

    def shape_word(self, chars: str) -> list[PlacedGlyph]:
        """Place a word's glyphs, letting the font's own kerning apply.

        Most words are a single glyph; 4,301 of them are drawn as two and one
        as three, and those are the ones the `kern` feature has anything to say
        about.
        """
        usable = "".join(c for c in chars if self.has(c))
        if not usable:
            return []
        if len(usable) == 1:
            name = self._cmap[ord(usable)]
            return [PlacedGlyph(name, 0.0, self.advance(name))]
        buffer = hb.Buffer()
        buffer.add_str(usable)
        buffer.guess_segment_properties()
        hb.shape(self._hb, buffer, {})
        out: list[PlacedGlyph] = []
        pen = 0.0
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
            name = self._order[info.codepoint]
            out.append(PlacedGlyph(name, pen, float(position.x_advance)))
            pen += position.x_advance
        return out

    def word_width(self, chars: str) -> float:
        return sum(g.advance for g in self.shape_word(chars))

    # --- colour -------------------------------------------------------------

    @lru_cache(maxsize=None)
    def layers(self, glyph_name: str) -> tuple[Layer, ...]:
        """The glyph's colour layers, or the glyph itself if it has none."""
        listed = self._layers.get(glyph_name)
        if not listed:
            return (Layer(glyph_name, BASE_INDEX),)
        return tuple(Layer(entry.name, entry.colorID) for entry in listed)

    @lru_cache(maxsize=None)
    def contours(self, glyph_name: str) -> tuple:
        return tuple(split_contours(self._glyph_set, glyph_name))

    def palette(self, index: int = 0) -> list[str]:
        table = self._tt["CPAL"].palettes[index]
        return ["#%02X%02X%02X" % (c.red, c.green, c.blue) for c in table]

    @property
    def palette_count(self) -> int:
        return len(self._tt["CPAL"].palettes)

    def is_blank(self, glyph_name: str) -> bool:
        return not self.contours(glyph_name)

    @staticmethod
    def encode_contours(contours, *, scale: float, translate, precision: int = 1,
                        simplify: float = 0.0) -> str:
        """Path data for a set of contours, baked into page coordinates."""
        ops = [op for contour in contours for op in contour.ops]
        if not ops:
            return ""
        if simplify > 0:
            ops = simplify_contours(ops, simplify)
        tx, ty = translate
        return encode(ops, scale_flip(scale, tx, ty), places=precision)


@lru_cache(maxsize=8)
def load(path: str) -> ColourPageFont:
    return ColourPageFont(path)
