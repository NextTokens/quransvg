"""The illuminated opening: pages 1 and 2.

The supplied artwork is an A4 spread — a panel with a crested crown top and
bottom, a column of vine down each side, a title band, a shaped writing panel,
a lower cartouche and a star at each corner. None of that survives being
squashed onto a page two and a half times as tall as it is wide, so, as with
the border, the drawing is treated as a kit: every motif keeps its own
proportions and the *stack* is re-laid for this page.

Two things are drawn here rather than lifted. The writing panel's outline is a
fixed-proportion path whose lobes would smear if it were stretched to our
height, so it is redrawn in the same idiom — three nested rules, same weights,
same colours. And the margin jewel has nowhere to go: it lives in a wide outer
margin that this page, with its border hard against the screen edge, does not
have.

`opening()` returns the decoration and the band the text has to sit inside;
`build` centres the lines in that band.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import newlook
from .geometry import ASCENT_EM, DESCENT_EM, Geometry

# --- the panel, in page units -----------------------------------------------
PANEL_X = 30.0
PANEL_W = 940.0
PANEL_TOP = 210.0        # the crown rises 172 units above this
BOTTOM_MARGIN = 210.0

ART_PANEL_W = 732.0      # the artwork's own panel, for scaling its motifs
ART_PANEL_X = 159.0
ART_PANEL_Y = 270.0
ART_CROWN_RISE = 134.0   # how far the crown stands above the panel edge

RULE_INSETS = (0.0, 9.0, 17.0)     # sage, cream, ground - as the artwork nests them
TITLE_W_RATIO = 0.76               # of the panel, as in the artwork
#: Inset of the four stars from the panel corner. 16 is what the artwork
#: uses; on this page the border sits only 7 units outside the panel, so a
#: star placed there overlapped it - 456 pixels of it survived `q-no-frame`.
CORNER_STAR = 38.0
COLUMN_INSET = 44.0                # where the vine column runs, from the panel edge


def _n(value: float, places: int = 2) -> str:
    rounded = round(value, places)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{places}f}".rstrip("0").rstrip(".")


def _scale() -> float:
    return PANEL_W / ART_PANEL_W


@dataclass(frozen=True)
class Opening:
    markup: str
    text_centre: float     # where the block of lines is centred
    title_cx: float        # the panel's own slot for the surah band
    title_cy: float
    title_w: float


def _rounded(x: float, y: float, w: float, h: float, r: float) -> str:
    return (
        f"M{_n(x + r)} {_n(y)}H{_n(x + w - r)}A{_n(r)} {_n(r)} 0 0 1 {_n(x + w)} {_n(y + r)}"
        f"V{_n(y + h - r)}A{_n(r)} {_n(r)} 0 0 1 {_n(x + w - r)} {_n(y + h)}"
        f"H{_n(x + r)}A{_n(r)} {_n(r)} 0 0 1 {_n(x)} {_n(y + h - r)}"
        f"V{_n(y + r)}A{_n(r)} {_n(r)} 0 0 1 {_n(x + r)} {_n(y)}Z"
    )


def _oval(cx: float, cy: float, a: float, b: float, cls: str, stroke: float) -> str:
    return (
        f'<ellipse class="{cls}" cx="{_n(cx)}" cy="{_n(cy)}" rx="{_n(a)}" ry="{_n(b)}" '
        f'stroke-width="{_n(stroke)}"/>'
    )


def _writing_oval(cx: float, cy: float, a: float, b: float) -> str:
    """The field the opening page's lines sit in.

    An oval, not a rectangle, because the lines of an opening page are already
    a lozenge - on page 1 they run 400, 554, 705, 715, 680, 532, 313 units wide
    - and a rectangle wide enough for the middle of that is a rectangle mostly
    empty at its corners. Not a true circle either: one containing this block
    would need to be 1,157 units across and the page is 940.
    """
    return (
        _oval(cx, cy, a, b, "q-orn-panel q-orn-outline", 1.8)
        + _oval(cx, cy, a - 9, b - 9, "q-orn-scroll q-orn-outline", 1.2)
        + _oval(cx, cy, a - 17, b - 17, "q-bg q-orn-outline", 0.9)
    )


#: An opening page carries six or seven lines, not fifteen, so it does not use
#: the body pitch. At 133 the block alone is 909 units tall and the oval that
#: circumscribes it 1,320 - which forces the whole composition to fill the
#: screen top to bottom. At 105 the page can be what it should be: a compact
#: panel centred on the sheet with clear ground around it.
OPENING_PITCH = 105.0
OVAL_CLEAR = 14.0        # ink to rule
OVAL_MAX_A = 420.0       # the widest oval the panel can hold


def _semi_axis_a(half_widths, pitch: float, ascent: float, descent: float, b: float):
    """The narrowest oval of half-height `b` that clears every line's ink."""
    block = (len(half_widths) - 1) * pitch + ascent + descent
    a = 0.0
    for index, half in enumerate(half_widths):
        top = -block / 2 + index * pitch
        for y in (top, top + ascent + descent):
            room = 1.0 - ((abs(y) + OVAL_CLEAR) / b) ** 2
            if room <= 0.0:
                return None
            a = max(a, (half + OVAL_CLEAR) / room ** 0.5)
    return a


def fit_oval(half_widths, pitch: float, ascent: float, descent: float) -> tuple[float, float]:
    """The shortest oval that holds the block without exceeding the panel.

    Height and width trade off: squat ovals have to be very wide to clear the
    long middle lines, tall ones are narrow but stretch the page. This walks up
    from the shortest and stops at the first that fits across."""
    block = (len(half_widths) - 1) * pitch + ascent + descent
    b = block / 2 + OVAL_CLEAR
    while b < 4 * block:
        a = _semi_axis_a(half_widths, pitch, ascent, descent, b)
        if a is not None and a <= OVAL_MAX_A:
            return a + 17.0, b + 17.0       # plus the three nested rules
        b += 10.0
    raise ValueError("no oval of a sane shape holds this opening block")


def _divider(cx: float, y: float, width: float) -> str:
    """A run of the border's own edge tile, laid flat across the panel."""
    s = _scale() * 0.62
    tile = newlook.ART_TILE * s
    count = max(3, round(width / tile))
    fit = width / (count * tile)
    tiles = "".join(
        f'<use href="#nl-edge-tile" xlink:href="#nl-edge-tile" '
        f'transform="translate({_n(i * newlook.ART_TILE)} 0)"/>'
        for i in range(count)
    )
    return (
        f'<g transform="translate({_n(cx - width / 2)} {_n(y)}) '
        f'scale({_n(fit * s, 6)} {_n(s, 6)})">{tiles}</g>'
    )


def _column(x: float, top: float, bottom: float) -> str:
    """The vine running down one side of the panel."""
    s = _scale()
    step = newlook.ART_TILE * 1.5 * s
    count = max(4, round((bottom - top) / step))
    fit = (bottom - top) / (count * step)
    parts = []
    for i in range(count):
        parts.append(
            f'<use href="#nl-edge-tile" xlink:href="#nl-edge-tile" '
            f'transform="translate(0 {_n(i * newlook.ART_TILE)}) rotate(90) '
            f'scale({_n(1.5 * s * fit, 6)} {_n(2.35 * s, 6)})"/>'
        )
    return (
        f'<g transform="translate({_n(x)} {_n(top)}) '
        f'scale(1 {_n(fit, 6)})">{"".join(parts)}</g>'
    )


#: Clear space kept between the writing panel's rule and the ink inside it.
FIELD_PAD = 46.0


def opening(geometry: Geometry, page: int, half_widths) -> Opening:
    """The decoration for an opening page, and where its text may sit.

    `half_widths` are the page's own lines, longest first or not: the writing
    oval is cut to fit them, so the decoration follows the text rather than the
    text being squeezed into decoration drawn before anyone measured it."""
    s = _scale()
    x0, x1 = PANEL_X, PANEL_X + PANEL_W
    cx = (x0 + x1) / 2

    title_w = PANEL_W * TITLE_W_RATIO
    title_h = newlook.band_height(title_w)
    a, b = fit_oval(
        half_widths,
        OPENING_PITCH,
        geometry.em * ASCENT_EM,
        geometry.em * DESCENT_EM,
    )
    # Cut the panel to what it holds, then centre it on the sheet. Stretching
    # it to the screen is what a body page does because a body page has fifteen
    # lines to fill; six lines in a panel that tall is a moat, not a margin.
    height = 46 + title_h + 24 + 2 * b + 24 + title_h + 46
    y0 = (geometry.view_h - height) / 2
    y1 = y0 + height

    parts = [newlook.opening_defs()]

    # the panel's three nested rules
    for index, (cls, inset) in enumerate(
        zip(("q-orn-panel", "q-orn-scroll", "q-orn-ground"), RULE_INSETS)
    ):
        parts.append(
            f'<path class="{cls} q-orn-outline" stroke-width="{_n(1.4 - index * 0.2)}" '
            f'd="{_rounded(x0 + inset, y0 + inset, PANEL_W - 2 * inset, height - 2 * inset, 4)}"/>'
        )

    # crown top and bottom, at the artwork's own proportions
    crown_dx = x0 - ART_PANEL_X * s
    parts.append(
        f'<g transform="translate({_n(crown_dx)} {_n(y0 - ART_PANEL_Y * s)}) '
        f'scale({_n(s, 6)})">'
        f'<use href="#nl-opening-crown" xlink:href="#nl-opening-crown"/></g>'
    )
    parts.append(
        f'<g transform="translate({_n(crown_dx)} {_n(y1 + ART_PANEL_Y * s)}) '
        f'scale({_n(s, 6)} {_n(-s, 6)})">'
        f'<use href="#nl-opening-crown" xlink:href="#nl-opening-crown"/></g>'
    )

    # a vine column down each side
    col_top, col_bottom = y0 + 34, y1 - 34
    parts.append(_column(x0 + COLUMN_INSET, col_top, col_bottom))
    parts.append(_column(x1 - COLUMN_INSET, col_top, col_bottom))

    # the title band above, the cartouche that answers it below, and the oval
    # between them
    div_top = y0 + 46 + title_h + 24
    div_bottom = y1 - 46 - title_h - 24
    parts.append(_divider(cx, div_top, title_w))
    parts.append(_divider(cx, div_bottom, title_w))
    field_cy = (div_top + div_bottom) / 2
    parts.append(_writing_oval(cx, field_cy, a, b))
    # the foot piece: the same band as the title, with nothing written in it,
    # exactly as the supplied artwork sets it
    parts.append(newlook.blank_band(cx, y1 - 46 - title_h / 2, title_w))

    # the corner stars
    for px in (x0 + CORNER_STAR, x1 - CORNER_STAR):
        for py in (y0 + CORNER_STAR, y1 - CORNER_STAR):
            parts.append(
                f'<use href="#nl-opening-star" xlink:href="#nl-opening-star" '
                f'transform="translate({_n(px)} {_n(py)}) scale({_n(s * 0.8, 5)})"/>'
            )

    return Opening(
        markup="".join(parts),
        text_centre=field_cy,
        title_cx=cx,
        title_cy=y0 + 46 + title_h / 2,
        title_w=title_w,
    )
