"""The invariant decoration - identical on every one of the 604 pages.

Nothing in this module accepts a page number, a surah, or any other per-page
input. That is deliberate, and it is the mechanism behind the project's central
guarantee: if the shell cannot see which page it is drawing, it cannot vary
between pages.

The border is an interlace, not a solid band. Two ribbons run the length of
each side in opposite phase, crossing at regular intervals, and the pointed
ovals they enclose each hold a small floret. Leaves tuck into the concave
spaces at the crossings and a pair of small dots marks each one. The ground
stays the colour of the paper, so the frame reads as fine linework rather than
as a heavy slab.

Every motif is drawn in a canonical orientation and rotated into place by
computing its coordinates rather than by emitting a `transform`. Baked
coordinates survive the weakest mobile SVG renderers, which is the same reason
depth comes from layered flat shapes rather than gradients and blur filters.
"""

from __future__ import annotations

import math

from .geometry import (
    BAND_OUTER,
    BAND_WIDTH,
    MARGIN_RULE,
    RULE_H,
    RULE_W,
    RULE_X,
    RULE_Y,
    Geometry,
)

BAND_INNER = BAND_OUTER + BAND_WIDTH
BAND_MID = BAND_OUTER + BAND_WIDTH / 2

EDGE_RULE = 1.1              # the gilt rules bounding the band
INTERIOR = BAND_WIDTH - 2 * EDGE_RULE

VESICA_PITCH = 26.0          # one pointed oval per repeat
RIBBON_AMP = 0.86            # of the interior half-width
RIBBON_W = 1.0

FLORET_R = 2.45
FLORET_PETALS = 6
FLORET_HEART = 0.8
CROSS_DOT = 0.65
LEAF_H = 2.9              # every motif above is BAND_WIDTH/34 of what it was

HAIRLINE = 0.7
INNER_HAIRLINE = 21.0        # the fine red rule just outside the panel
PANEL_R = 18.0

AYAH_RX = 20.8               # the oval field carrying the number
AYAH_RY = 22.1
AYAH_CROWN = 10.7             # the floral cap above and below it

FOOTER_INNER = 22.0


def _n(value: float, places: int = 2) -> str:
    rounded = round(value, places)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{places}f}".rstrip("0").rstrip(".")


def _pt(x: float, y: float) -> str:
    return f"{_n(x)} {_n(y)}"


def _rect(cls, x, y, w, h, rx=None, stroke=None) -> str:
    extra = f' rx="{_n(rx)}"' if rx else ""
    if stroke is not None:
        extra += f' stroke-width="{_n(stroke)}"'
    return (
        f'<rect class="{cls}" x="{_n(x)}" y="{_n(y)}"'
        f' width="{_n(w)}" height="{_n(h)}"{extra}/>'
    )


def _place(spec, cx: float, cy: float, angle: float) -> str:
    """Render a local-coordinate motif rotated and translated into place."""
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    out = []
    for command, points in spec:
        coords = [
            _pt(cx + px * cos_a - py * sin_a, cy + px * sin_a + py * cos_a)
            for px, py in points
        ]
        out.append(command + " ".join(coords))
    return "".join(out)


def _ogee(height: float, width: float):
    """A pointed leaf."""
    return [
        ("M", [(0.0, -height)]),
        ("Q", [(width * 0.95, -height * 0.58), (width * 0.26, 0.0)]),
        ("Q", [(0.0, height * 0.10), (-width * 0.26, 0.0)]),
        ("Q", [(-width * 0.95, -height * 0.58), (0.0, -height)]),
        ("z", []),
    ]


def _floret(cx: float, cy: float, radius: float, petals: int) -> str:
    """A small rounded flower, the motif seated in each pointed oval."""
    out = []
    for index in range(petals):
        angle = -math.pi / 2 + index * 2 * math.pi / petals
        px, py = cx + math.cos(angle) * radius * 0.62, cy + math.sin(angle) * radius * 0.62
        out.append(
            f"M{_pt(px, py)}m{_n(-radius * 0.38)} 0"
            f"a{_n(radius * 0.38)} {_n(radius * 0.38)} 0 1 0 {_n(radius * 0.76)} 0"
            f"a{_n(radius * 0.38)} {_n(radius * 0.38)} 0 1 0 {_n(-radius * 0.76)} 0z"
        )
    return "".join(out)


# --- the band ---------------------------------------------------------------

def _runs(geometry: Geometry):
    """Each side of the band: start, end, outward angle, repeat count."""
    w, h = geometry.view_w, geometry.view_h
    across = max(4, round((w - 2 * BAND_INNER) / VESICA_PITCH))
    down = max(6, round((h - 2 * BAND_INNER) / VESICA_PITCH))
    return (
        ((BAND_INNER, BAND_MID), (w - BAND_INNER, BAND_MID), -math.pi / 2, across),
        ((w - BAND_MID, BAND_INNER), (w - BAND_MID, h - BAND_INNER), 0.0, down),
        ((w - BAND_INNER, h - BAND_MID), (BAND_INNER, h - BAND_MID), math.pi / 2, across),
        ((BAND_MID, h - BAND_INNER), (BAND_MID, BAND_INNER), math.pi, down),
    )


def _interlace(geometry: Geometry) -> str:
    """Two ribbons in opposite phase, and what sits in and between them."""
    amp = (INTERIOR / 2) * RIBBON_AMP
    ribbon_a, ribbon_b = [], []
    florets, hearts, leaves, dots = [], [], [], []
    leaf = _ogee(LEAF_H, 4.6)

    cx0, cy0 = geometry.view_w / 2, geometry.view_h / 2
    for (ax, ay), (bx, by), _unused, count in _runs(geometry):
        dx, dy = (bx - ax) / count, (by - ay) / count
        # Take the normal from the run direction itself. Deriving it from an
        # angle convention is what made every ribbon run flat: on the
        # horizontal runs the "normal" came out parallel to the run.
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        mx0, my0 = (ax + bx) / 2, (ay + by) / 2
        if (mx0 + nx - cx0) ** 2 + (my0 + ny - cy0) ** 2 < (mx0 - cx0) ** 2 + (my0 - cy0) ** 2:
            nx, ny = -nx, -ny          # make it point away from the page centre
        angle = math.atan2(nx, -ny)    # rotation that sends a motif outward

        for phase, bucket in ((1, ribbon_a), (-1, ribbon_b)):
            parts = [f"M{_pt(ax, ay)}"]
            for index in range(count):
                swing = amp * 2 * phase
                mx = ax + dx * (index + 0.5) + nx * swing
                my = ay + dy * (index + 0.5) + ny * swing
                parts.append(
                    f"Q{_pt(mx, my)} {_pt(ax + dx * (index + 1), ay + dy * (index + 1))}"
                )
            bucket.append("".join(parts))

        for index in range(count):
            cx = ax + dx * (index + 0.5)
            cy = ay + dy * (index + 0.5)
            florets.append(_floret(cx, cy, FLORET_R, FLORET_PETALS))
            hearts.append(
                f'<circle class="q-floret-heart" cx="{_n(cx)}" cy="{_n(cy)}"'
                f' r="{_n(FLORET_HEART)}"/>'
            )
            # crossings: a leaf out and a leaf in, with a pair of dots
            if index < count - 1:
                jx = ax + dx * (index + 1)
                jy = ay + dy * (index + 1)
                leaves.append(_place(leaf, jx + nx * amp * 0.5, jy + ny * amp * 0.5, angle))
                leaves.append(
                    _place(leaf, jx - nx * amp * 0.5, jy - ny * amp * 0.5, angle + math.pi)
                )
                for side in (-1, 1):
                    dot_x = jx + (dx / VESICA_PITCH) * 4.0 * side
                    dot_y = jy + (dy / VESICA_PITCH) * 4.0 * side
                    dots.append(
                        f'<circle class="q-floret-dot" cx="{_n(dot_x)}"'
                        f' cy="{_n(dot_y)}" r="{_n(CROSS_DOT)}"/>'
                    )

    return (
        f'<path class="q-ribbon-b" fill="none" stroke-width="{_n(RIBBON_W)}"'
        f' d="{"".join(ribbon_b)}"/>'
        f'<path class="q-ribbon-a" fill="none" stroke-width="{_n(RIBBON_W)}"'
        f' d="{"".join(ribbon_a)}"/>'
        f'<path class="q-leaf" d="{"".join(leaves)}"/>'
        + "".join(dots)
        + f'<path class="q-floret" d="{"".join(florets)}"/>'
        + "".join(hearts)
    )


def _corner_florets(geometry: Geometry) -> str:
    """A larger flower turning each corner."""
    w, h = geometry.view_w, geometry.view_h
    out = []
    for cx, cy in (
        (BAND_MID, BAND_MID), (w - BAND_MID, BAND_MID),
        (BAND_MID, h - BAND_MID), (w - BAND_MID, h - BAND_MID),
    ):
        out.append(_floret(cx, cy, FLORET_R * 1.5, 8))
    hearts = "".join(
        f'<circle class="q-floret-heart" cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(FLORET_HEART * 1.4)}"/>'
        for cx, cy in (
            (BAND_MID, BAND_MID), (w - BAND_MID, BAND_MID),
            (BAND_MID, h - BAND_MID), (w - BAND_MID, h - BAND_MID),
        )
    )
    return f'<path class="q-floret" d="{"".join(out)}"/>' + hearts


def _rules(geometry: Geometry) -> str:
    w, h = geometry.view_w, geometry.view_h
    return (
        _rect("q-rule-gold", MARGIN_RULE, MARGIN_RULE,
              w - 2 * MARGIN_RULE, h - 2 * MARGIN_RULE, None, HAIRLINE)
        + _rect("q-rule-gold", BAND_OUTER + EDGE_RULE / 2, BAND_OUTER + EDGE_RULE / 2,
                w - 2 * (BAND_OUTER + EDGE_RULE / 2), h - 2 * (BAND_OUTER + EDGE_RULE / 2),
                None, EDGE_RULE)
        + _rect("q-rule-gold", BAND_INNER - EDGE_RULE / 2, BAND_INNER - EDGE_RULE / 2,
                w - 2 * (BAND_INNER - EDGE_RULE / 2), h - 2 * (BAND_INNER - EDGE_RULE / 2),
                None, EDGE_RULE)
        + _rect("q-rule-red", INNER_HAIRLINE, INNER_HAIRLINE,
                w - 2 * INNER_HAIRLINE, h - 2 * INNER_HAIRLINE, None, HAIRLINE)
    )


# --- panel and chrome -------------------------------------------------------

def _panel(geometry: Geometry) -> str:
    """Nothing. The text sits directly on the page.

    The rounded panel and its dotted edge used to box the text in; without them
    the gilt rules alone hold the page, which is how the printed mushaf reads.
    """
    return ""


def header_box(geometry: Geometry):
    top = BAND_INNER + 6.0
    return RULE_X, top, RULE_W, RULE_Y - top - 8.0


def footer_box(geometry: Geometry):
    top = RULE_Y + RULE_H
    return geometry.view_w / 2 - 60.0, top, 120.0, geometry.view_h - BAND_INNER - top


def footer_field_diameter() -> float:
    """Room the plain page number may occupy."""
    return 78.0


def _footer_mark(geometry: Geometry) -> str:
    """Nothing. The page number is set plain, with no ornament behind it."""
    return ""


HEADER_H = 64.0              # the illuminated band that opens a surah
HEADER_RULE = 2.2
HEADER_CARTOUCHE_W = 330.0
HEADER_CARTOUCHE_H = 42.0
HEADER_VESICA = 38.0
HEADER_FLORET = 5.0
HEADER_CREST = 6.0


def _mini_interlace(x0: float, x1: float, cy: float, amp: float) -> str:
    """The frame's interlace, run at a smaller scale inside the header."""
    span = x1 - x0
    count = max(2, round(span / HEADER_VESICA))
    step = span / count
    ribbons = {1: [], -1: []}
    florets, hearts, leaves = [], [], []
    leaf = _ogee(amp * 0.92, 3.4)

    for phase in (1, -1):
        parts = [f"M{_pt(x0, cy)}"]
        for index in range(count):
            mx = x0 + step * (index + 0.5)
            parts.append(f"Q{_pt(mx, cy + amp * 2 * phase)} {_pt(x0 + step * (index + 1), cy)}")
        ribbons[phase].append("".join(parts))

    for index in range(count):
        cx = x0 + step * (index + 0.5)
        florets.append(_floret(cx, cy, HEADER_FLORET, FLORET_PETALS))
        hearts.append(
            f'<circle class="q-floret-heart" cx="{_n(cx)}" cy="{_n(cy)}"'
            f' r="{_n(HEADER_FLORET * 0.32)}"/>'
        )
        if index < count - 1:
            jx = x0 + step * (index + 1)
            leaves.append(_place(leaf, jx, cy - amp * 0.55, 0.0))
            leaves.append(_place(leaf, jx, cy + amp * 0.55, math.pi))
    return (
        f'<path class="q-ribbon-b" fill="none" stroke-width="{_n(RIBBON_W * 0.8)}"'
        f' d="{"".join(ribbons[-1])}"/>'
        f'<path class="q-ribbon-a" fill="none" stroke-width="{_n(RIBBON_W * 0.8)}"'
        f' d="{"".join(ribbons[1])}"/>'
        f'<path class="q-leaf" d="{"".join(leaves)}"/>'
        f'<path class="q-floret" d="{"".join(florets)}"/>'
        + "".join(hearts)
    )


def _cresting(x0: float, x1: float, y: float, outward: int) -> str:
    """Finials along the header's edge.

    A tall palmette alternating with a small bud, rather than one shape
    repeated: an even row of identical teardrops reads as a machine rule, which
    is exactly what an illuminated band should not look like.
    """
    span = x1 - x0
    count = max(6, round(span / 21.0))
    step = span / count
    angle = 0.0 if outward < 0 else math.pi
    tall = _ogee(HEADER_CREST * 2.1, HEADER_CREST * 0.95)
    small = _ogee(HEADER_CREST * 1.05, HEADER_CREST * 0.62)
    talls, smalls = [], []
    for index in range(count):
        cx = x0 + step * (index + 0.5)
        (talls if index % 2 == 0 else smalls).append(
            _place(tall if index % 2 == 0 else small, cx, y, angle)
        )
    return (
        f'<path class="q-leaf" d="{"".join(talls)}"/>'
        f'<path class="q-floret" d="{"".join(smalls)}"/>'
    )


def surah_header(cx: float, cy: float, width: float):
    """The illuminated band that opens a surah.

    Built from the same vocabulary as the page frame - interlaced ribbons,
    florets seated in the ovals they enclose, leaves at the crossings - so the
    opening reads as part of the border rather than a label dropped onto it.
    The surah's name sits in a cartouche at the centre; the caller draws it and
    is told where it goes.

    Returns the markup and the (centre, baseline, usable width) for the name.
    """
    half_w, half_h = width / 2, HEADER_H / 2
    x0, x1 = cx - half_w, cx + half_w
    top, bottom = cy - half_h, cy + half_h

    car_half = HEADER_CARTOUCHE_W / 2
    car = chamfered_band(cx, cy, car_half, HEADER_CARTOUCHE_H / 2)
    amp = (HEADER_H / 2 - 10.0) * 0.5
    gap = 12.0

    inner = chamfered_band(cx, cy, car_half - 5.0, HEADER_CARTOUCHE_H / 2 - 5.0)
    parts = [
        _rect("q-band", x0, top, width, HEADER_H),
        _mini_interlace(x0 + gap, cx - car_half - gap, cy, amp),
        _mini_interlace(cx + car_half + gap, x1 - gap, cy, amp),
        _cresting(x0, x1, top, -1),
        _cresting(x0, x1, bottom, 1),
        _rect("q-rule-gold", x0, top, width, HEADER_H, None, HEADER_RULE),
        # the cartouche: ground, a heavy rule, and a hairline set inside it
        f'<path class="q-cartouche" d="{car}"/>',
        f'<path class="q-rule-gold" fill="none" stroke-width="{_n(HEADER_RULE * 1.4)}" d="{car}"/>',
        f'<path class="q-rule-gold" fill="none" stroke-width="{_n(HAIRLINE * 0.9)}" d="{inner}"/>',
    ]
    # a floret at each pointed end of the cartouche, and one in every corner of
    # the band, so the panel is closed off rather than just stopping
    florets, hearts = [], []
    for side in (-1, 1):
        px = cx + side * car_half
        florets.append(_floret(px, cy, HEADER_FLORET * 1.5, 8))
        hearts.append(
            f'<circle class="q-floret-heart" cx="{_n(px)}" cy="{_n(cy)}"'
            f' r="{_n(HEADER_FLORET * 0.42)}"/>'
        )
    for ox in (x0 + 11.0, x1 - 11.0):
        for oy in (top + 11.0, bottom - 11.0):
            florets.append(_floret(ox, oy, HEADER_FLORET * 1.1, 6))
            hearts.append(
                f'<circle class="q-floret-heart" cx="{_n(ox)}" cy="{_n(oy)}"'
                f' r="{_n(HEADER_FLORET * 0.32)}"/>'
            )
    parts.append(f'<path class="q-floret" d="{"".join(florets)}"/>')
    parts.extend(hearts)
    return "".join(parts), (cx, cy, HEADER_CARTOUCHE_W - 52.0)


def chamfered_band(cx: float, cy: float, half_w: float, half_h: float) -> str:
    cut = min(20.0, half_h * 1.4)
    return (
        f"M{_pt(cx - half_w + cut, cy - half_h)}L{_pt(cx + half_w - cut, cy - half_h)}"
        f"L{_pt(cx + half_w, cy)}L{_pt(cx + half_w - cut, cy + half_h)}"
        f"L{_pt(cx - half_w + cut, cy + half_h)}L{_pt(cx - half_w, cy)}z"
    )


# --- shared symbols ---------------------------------------------------------

def _legacy_ayah_field_width() -> float:
    """The retired oval's field. Kept only as a record of what it measured."""
    return 2 * (AYAH_RX - 1.8) * 0.92


def _rosette() -> str:
    """The end-of-ayah mark.

    The number is the point of it, so the oval field carries most of the mark
    and the ornament caps it above and below rather than encircling it. A ring
    of petals around the outside would squeeze the digits into a small centre,
    which is what the printed mushaf avoids.
    """
    crown = _ogee(AYAH_CROWN, 4.8)
    side = _ogee(AYAH_CROWN * 0.62, 3.4)
    petals = []
    for sign in (1, -1):
        base = -(AYAH_RY - 2.0) * sign
        angle = 0.0 if sign == 1 else math.pi
        petals.append(_place(crown, 0.0, base, angle))
        for lean in (-1, 1):
            petals.append(
                _place(side, lean * 2.8, base + 0.8 * sign, angle + math.radians(52) * lean)
            )
    return (
        '<g id="q-ayah-rosette">'
        f'<path class="q-ayah-accent" d="{"".join(petals)}"/>'
        f'<ellipse class="q-ayah-ring" cx="0" cy="0"'
        f' rx="{_n(AYAH_RX)}" ry="{_n(AYAH_RY)}"/>'
        f'<ellipse class="q-ayah-field" cx="0" cy="0"'
        f' rx="{_n(AYAH_RX - 1.6)}" ry="{_n(AYAH_RY - 1.6)}"/>'
        "</g>"
    )


def _marker_symbols() -> str:
    return (
        '<g id="q-rub">'
        '<path class="q-marker" d="M0-12l12 12l-12 12l-12-12z"/>'
        '<path class="q-marker" opacity="0.5" d="M0-6.4l6.4 6.4l-6.4 6.4l-6.4-6.4z"/>'
        "</g>"
        '<g id="q-sajdah">'
        '<path class="q-marker" d="M-10 6h20v3h-20z"/>'
        '<path class="q-marker" d="M-6-9h12v4h-12zM-2-5h4v9h-4z"/>'
        "</g>"
    )


def defs(geometry: Geometry) -> str:
    """What the page's <defs> needs. The end-of-ayah mark now comes from the
    adopted artwork, so it matches the border and the surah band."""
    from . import newlook

    return newlook.ayah_mark()


def ayah_field_width() -> float:
    """Usable width inside the mark, so the number can be fitted to it."""
    from . import newlook

    return newlook.ayah_field_width()


#: How far the ground reaches beyond the page, in viewBox units. An app gives
#: the page whatever box its screen has - 1000x2200 on a tall phone - and a
#: `meet` fit then leaves a band above and below the 2:3 page. A ground rect
#: that stopped at the viewBox would leave those bands *transparent*, so the
#: page would sit on whatever the app painted behind it. Reaching well past
#: the viewBox fills them with the page's own colour instead. The outermost
#: <svg> clips to the viewport, so nothing here can escape the app's box, and
#: rendering at the page's own size is unchanged - the surplus is clipped away.
GROUND_BLEED = 4000.0


def ground(geometry: Geometry) -> str:
    """The sheet the page is printed on. Stays when the frame is removed."""
    return _rect(
        "q-bg",
        -GROUND_BLEED,
        -GROUND_BLEED,
        geometry.view_w + 2 * GROUND_BLEED,
        geometry.view_h + 2 * GROUND_BLEED,
    )


def frame(geometry: Geometry) -> str:
    """The illuminated border, in draw order.

    Kept apart from the ground so an app can hide it as one element - by
    adding `q-no-frame` to the root, or setting `display:none` on `#q-frame` -
    and be left with a clean sheet, not a sheet with holes in it.
    """
    w, h = geometry.view_w, geometry.view_h
    return "".join(
        (
            _rect("q-band", BAND_OUTER, BAND_OUTER,
                  w - 2 * BAND_OUTER, h - 2 * BAND_OUTER),
            _interlace(geometry),
            _corner_florets(geometry),
            _rules(geometry),
        )
    )


def build(geometry: Geometry) -> str:
    """Ground and frame together, for callers that want the whole shell."""
    return ground(geometry) + frame(geometry)
