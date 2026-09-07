"""Shaping and outline extraction for the KFGQPC per-page mushaf fonts.

A QCF v2 page font is unusual: it contains only the glyphs for *one* page, and
each glyph is a whole word rather than a letter.  The type designer justified
the lines by hand, so the fifteen shaped line widths on a page agree to within
well under one percent.  That means we never invent spacing for Qur'anic text —
we reproduce the printed line, and only absorb the sub-percent residual.

Measured facts about these fonts that the code below relies on:

  * units per em is 2500;
  * U+0020 is absent from the cmap, so an inter-word space maps to glyph 0,
    which has no outline and an advance of 100 units;
  * these fonts do no shaping worth the name: GSUB has no lookups, and the one
    GPOS `kern` feature adjusts nothing. Measured over all fifteen lines of
    page 248, HarfBuzz and a plain cmap+hmtx walk agree exactly — same glyph
    ids, zero offsets, and identical advances to the unit. HarfBuzz is used
    here for the RTL reordering and as a guard against a future page font that
    does carry real shaping, not because these fonts need it;
  * HarfBuzz returns the RTL buffer in visual order, so a plain left-to-right
    advance accumulation places the glyphs correctly.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont

from .pathenc import encode, scale_flip
from .simplify import simplify_contours

# The word separator is not in the cmap; shaping still gives it an advance.
SPACE = " "


@dataclass(frozen=True)
class ShapedGlyph:
    """One shaped glyph, positioned along the line in font units."""

    glyph_name: str
    x: float          # pen position at the glyph's origin, from the line's left edge
    x_offset: float
    y_offset: float
    advance: float
    cluster: int      # index into the shaping input string
    is_space: bool


class PageFont:
    """A single page's mushaf font: shaping plus outline extraction."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        data = self.path.read_bytes()
        self._hb_font = hb.Font(hb.Face(hb.Blob(data)))
        self._tt = TTFont(self.path)
        self._glyph_set = self._tt.getGlyphSet()
        self._glyph_order = self._tt.getGlyphOrder()
        self.units_per_em: int = self._tt["head"].unitsPerEm

    def covers(self, codepoints) -> bool:
        """Does this font map every one of these characters?"""
        cmap = self._tt.getBestCmap()
        return all(code in cmap for code in codepoints)

    def shape(self, text: str) -> list[ShapedGlyph]:
        """Shape `text`, returning glyphs in visual (left-to-right) order."""
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(self._hb_font, buffer, {})

        glyphs: list[ShapedGlyph] = []
        pen_x = 0.0
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
            glyphs.append(
                ShapedGlyph(
                    glyph_name=self._glyph_order[info.codepoint],
                    x=pen_x,
                    x_offset=position.x_offset,
                    y_offset=position.y_offset,
                    advance=position.x_advance,
                    cluster=info.cluster,
                    is_space=info.codepoint == 0,
                )
            )
            pen_x += position.x_advance
        return glyphs

    @lru_cache(maxsize=None)
    def _outline(self, glyph_name: str) -> tuple:
        """The glyph's contours, recorded once in font units (y up)."""
        from fontTools.pens.recordingPen import DecomposingRecordingPen

        pen = DecomposingRecordingPen(self._glyph_set)
        self._glyph_set[glyph_name].draw(pen)
        return tuple(pen.value)

    def path_data(
        self,
        glyph_name: str,
        *,
        scale: float,
        translate: tuple[float, float],
        precision: int = 1,
        simplify: float = 0.0,
    ) -> str:
        """SVG path data for a glyph, baked into page coordinates.

        Position and the y-flip (fonts are y-up, SVG is y-down) are baked into
        the coordinates rather than expressed as a `transform` attribute, so the
        emitted `<path>` stands alone — which the weakest mobile SVG renderers
        handle far more reliably than nested transforms.
        """
        contours = self._outline(glyph_name)
        if not contours:
            return ""
        if simplify > 0:
            contours = simplify_contours(contours, simplify)
        tx, ty = translate
        return encode(contours, scale_flip(scale, tx, ty), places=precision)

    def is_blank(self, glyph_name: str) -> bool:
        return not self._outline(glyph_name)

    @lru_cache(maxsize=None)
    def contours(self, glyph_name: str) -> tuple:
        """The glyph's individual closed contours, for mark separation."""
        from .marks import split_contours

        return tuple(split_contours(self._glyph_set, glyph_name))

    @staticmethod
    def encode_contour(contour, *, scale: float, translate: tuple[float, float],
                       precision: int = 1, simplify: float = 0.0) -> str:
        """Path data for one contour, baked into page coordinates."""
        ops = list(contour.ops)
        if simplify > 0:
            ops = simplify_contours(ops, simplify)
        tx, ty = translate
        return encode(ops, scale_flip(scale, tx, ty), places=precision)


def _fmt(value: float, precision: int) -> str:
    """Shortest round-trip-stable decimal, so output is byte-reproducible."""
    rounded = round(value, precision)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{precision}f}".rstrip("0").rstrip(".")
