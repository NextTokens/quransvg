"""Arabic-Indic numerals as reusable outlines.

Ayah numbers, the page number and the juz number are all set in Arabic-Indic
digits (٠١٢٣٤٥٦٧٨٩).  Rather than depend on a font being present on the
device — which no SVG renderer can be trusted to do — the ten digits are
extracted once as path outlines and emitted into the document's <defs>.  Ten
shapes then serve every number on the page, and every page of the mushaf.

Digits are normalised to a 1-unit em box at the origin so a caller can place a
number at any size with a single transform.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
FIRST_CODEPOINT = 0x0660


@dataclass(frozen=True)
class Digit:
    value: int
    path: str      # outline in a 1000-unit em, y down, baseline at y=0
    advance: float # advance width in the same 1000-unit em
    top: float     # ink extremes, y down: `top` is negative above the baseline
    bottom: float


@dataclass(frozen=True)
class NumeralSet:
    """The ten digits, plus enough metrics to typeset a number."""

    digits: tuple[Digit, ...]
    units_per_em: float = 1000.0

    def width(self, number: int) -> float:
        return sum(self.digits[int(c)].advance for c in str(number))

    def ink_middle(self, number: int) -> float:
        """Vertical centre of a number's ink, relative to its baseline.

        Arabic-Indic digits sit almost entirely above the baseline, so
        centring them on a rosette means centring the *ink*, not the em box.
        """
        used = [self.digits[int(c)] for c in str(number)]
        return (min(d.top for d in used) + max(d.bottom for d in used)) / 2

    def symbol_ids(self) -> list[str]:
        return [f"q-d{d.value}" for d in self.digits]

    def defs(self) -> str:
        """Reusable definitions for the ten digits."""
        return "".join(
            f'<g id="q-d{d.value}">'
            f'<path d="{d.path}"/></g>'
            for d in self.digits
        )

    def place(self, number: int, cx: float, cy: float, size: float, css_class: str) -> str:
        """Render `number` centred on (cx, cy) at the given em size.

        Arabic-Indic digits run most-significant-first, exactly like Western
        ones, so the digit string needs no reordering.
        """
        scale = size / self.units_per_em
        total = self.width(number) * scale
        x = cx - total / 2
        cy = cy - self.ink_middle(number) * scale
        parts = [f'<g class="{css_class}">']
        for char in str(number):
            digit = self.digits[int(char)]
            parts.append(
                f'<use href="#q-d{digit.value}" x="0" y="0" '
                f'transform="translate({_n(x)} {_n(cy)}) scale({_n(scale, 5)})"/>'
            )
            x += digit.advance * scale
        parts.append("</g>")
        return "".join(parts)


def _n(value: float, places: int = 2) -> str:
    rounded = round(value, places)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{places}f}".rstrip("0").rstrip(".")


def _encode(recording, scale: float, y_shift: float, places: int = 1) -> str:
    """Relative path data, y-flipped into SVG's coordinate sense."""
    out: list[str] = []
    cx = cy = 0.0
    start_x = start_y = 0.0
    control = None

    def fmt(value: float) -> str:
        rounded = round(value, places)
        if rounded == int(rounded):
            return str(int(rounded))
        text = f"{rounded:.{places}f}".rstrip("0").rstrip(".")
        return text[1:] if text.startswith("0.") else text

    def pair(x: float, y: float) -> str:
        sx, sy = fmt(x), fmt(y)
        return f"{sx} {sy}" if not sy.startswith("-") else f"{sx}{sy}"

    def to_svg(point):
        return point[0] * scale, y_shift - point[1] * scale

    for op, args in recording:
        if op == "moveTo":
            x, y = to_svg(args[0])
            out.append(f"M{pair(x - cx, y - cy)}" if out else f"M{pair(x, y)}")
            if out[-1].startswith("M") and len(out) > 1:
                out[-1] = f"m{pair(x - cx, y - cy)}"
            cx, cy = x, y
            start_x, start_y = x, y
            control = None
        elif op == "lineTo":
            x, y = to_svg(args[0])
            out.append(f"l{pair(x - cx, y - cy)}")
            cx, cy = x, y
            control = None
        elif op in ("qCurveTo", "curveTo"):
            points = [p for p in args if p is not None]
            if op == "curveTo":
                x, y = to_svg(points[-1])
                c1 = to_svg(points[0])
                c2 = to_svg(points[1])
                out.append(
                    f"c{pair(c1[0] - cx, c1[1] - cy)} "
                    f"{pair(c2[0] - cx, c2[1] - cy)} {pair(x - cx, y - cy)}"
                )
                cx, cy = x, y
                control = None
                continue
            count = len(points)
            for index in range(count - 1):
                ctrl = to_svg(points[index])
                nxt = to_svg(points[index + 1])
                end = (
                    ((ctrl[0] + nxt[0]) / 2, (ctrl[1] + nxt[1]) / 2)
                    if index < count - 2
                    else nxt
                )
                smooth = (
                    control is not None
                    and abs((2 * cx - control[0]) - ctrl[0]) < 0.6
                    and abs((2 * cy - control[1]) - ctrl[1]) < 0.6
                )
                if smooth:
                    out.append(f"t{pair(end[0] - cx, end[1] - cy)}")
                else:
                    out.append(
                        f"q{pair(ctrl[0] - cx, ctrl[1] - cy)} {pair(end[0] - cx, end[1] - cy)}"
                    )
                control = ctrl
                cx, cy = end
        elif op == "closePath":
            out.append("z")
            # After `z` the current point returns to where the subpath began,
            # not to the last point drawn. Carrying the last point forward made
            # every following relative moveto start from the wrong origin, so
            # contours after a closed one landed displaced.
            cx, cy = start_x, start_y
            control = None
    return "".join(out)


@lru_cache(maxsize=4)
def load(font_path: str | Path) -> NumeralSet:
    font = TTFont(str(font_path))
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    upem = font["head"].unitsPerEm
    scale = 1000.0 / upem
    hmtx = font["hmtx"]

    digits = []
    for value in range(10):
        codepoint = FIRST_CODEPOINT + value
        name = cmap.get(codepoint)
        if name is None:
            raise ValueError(
                f"{Path(font_path).name} has no glyph for U+{codepoint:04X} "
                f"({ARABIC_INDIC[value]}) — it cannot set ayah numbers"
            )
        pen = DecomposingRecordingPen(glyph_set)
        glyph_set[name].draw(pen)
        bounds = BoundsPen(glyph_set)
        glyph_set[name].draw(bounds)
        # Font space is y-up; negate to match SVG's y-down sense.
        top = -bounds.bounds[3] * scale if bounds.bounds else 0.0
        bottom = -bounds.bounds[1] * scale if bounds.bounds else 0.0
        digits.append(
            Digit(
                value=value,
                path=_encode(pen.value, scale, 0.0),
                advance=hmtx[name][0] * scale,
                top=top,
                bottom=bottom,
            )
        )
    return NumeralSet(digits=tuple(digits))
