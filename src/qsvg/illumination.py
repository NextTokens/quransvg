"""The illuminated opening of the mushaf - pages 1 and 2.

The rest of the book sets fifteen justified lines in a plain panel. The first
two pages set eight short centred lines whose lengths swell and taper, and the
printed mushaf answers that shape with a round medallion: the text on a disc,
the disc in a ring, and the field around it worked all over.

The field is cream, not the deep ground of the surah band: a solid dark field
around the medallion overwhelms the page, and the reference openings are dense
rather than dark. So the deep colour is spent as accent - a halo ring around
the medallion, the florets, the corner bosses - while the field itself carries
the header's lattice, a seeded array of small florets at the lattice's rhythm,
and gilt vines with leaves sweeping in from the corners.

Everything here is drawn in the vocabulary already on the page, so the opening
reads as the same hand, only richer. It is an extra layer between the frame
and the text; the frame itself is untouched and every page still shares one.
"""

from __future__ import annotations

import math

from .geometry import Geometry, RULE_H, RULE_W, RULE_X, RULE_Y
from .shell import _floret, _n, _ogee, _place, _pt, FLORET_PETALS, RIBBON_W

DISC_R = 305.0            # the cream disc the text sits on
RING_W = 32.0             # the interlace ring around it
HALO_W = 24.0             # the deep ring outside that
RING_SEGMENTS = 22
RING_AMP = 0.36
RING_FLORET_R = 7.0

SPANDREL_INSET = 10.0
SPANDREL_R = 24.0
SEED_PITCH = 58.0         # spacing of the small florets seeded over the field


def opening(geometry: Geometry, centre_y: float) -> str:
    """The medallion centred on (panel centre, `centre_y`), in its worked field."""
    cx = geometry.panel_x + geometry.panel_w / 2
    cy = centre_y
    r_in = DISC_R
    r_ring = DISC_R + RING_W
    r_out = r_ring + HALO_W
    return "".join(
        (
            _field(geometry),
            _lattice(geometry, cx, cy, r_out),
            _seeded(geometry, cx, cy, r_out),
            _vines(geometry, cx, cy, r_out),
            _halo(cx, cy, r_ring, r_out),
            f'<circle class="q-paper" cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r_ring)}"/>',
            _ring(cx, cy, r_in + RING_W / 2),
            f'<circle class="q-paper" cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r_in)}"/>',
            f'<circle class="q-rule-gold" fill="none" cx="{_n(cx)}" cy="{_n(cy)}"'
            f' r="{_n(r_in)}" stroke-width="2.4"/>',
            f'<circle class="q-rule-red" fill="none" cx="{_n(cx)}" cy="{_n(cy)}"'
            f' r="{_n(r_in - 7.0)}" stroke-width="1.1"/>',
        )
    )


# --- the field ----------------------------------------------------------------

def _box(geometry: Geometry):
    x = RULE_X + SPANDREL_INSET
    top = geometry.opening_top + SPANDREL_INSET
    return (x, top, RULE_W - 2 * SPANDREL_INSET, RULE_Y + RULE_H - SPANDREL_INSET - top)


def _rounded(box, d: float = 0.0) -> str:
    x, y, w, h = box
    x, y, w, h = x + d, y + d, w - 2 * d, h - 2 * d
    k = SPANDREL_R - d
    return (
        f"M{_pt(x + k, y)}H{_n(x + w - k)}Q{_pt(x + w, y)} {_pt(x + w, y + k)}"
        f"V{_n(y + h - k)}Q{_pt(x + w, y + h)} {_pt(x + w - k, y + h)}"
        f"H{_n(x + k)}Q{_pt(x, y + h)} {_pt(x, y + h - k)}"
        f"V{_n(y + k)}Q{_pt(x, y)} {_pt(x + k, y)}z"
    )


def _field(geometry: Geometry) -> str:
    """Cream ground carrying the header's lattice, ruled in gold and red."""
    box = _box(geometry)
    outer = _rounded(box)
    return (
        f'<path class="q-band" d="{outer}"/>'
        f'<path class="q-rule-gold" fill="none" stroke-width="2.2" d="{outer}"/>'
        f'<path class="q-rule-red" fill="none" stroke-width="1.0" d="{_rounded(box, 6.0)}"/>'
        f'<path class="q-rule-gold" fill="none" stroke-width="0.9" d="{_rounded(box, 11.0)}"/>'
    )


LATTICE_PITCH = 29.0      # half the seed pitch, so florets sit on lattice nodes


def _lattice(geometry: Geometry, cx: float, cy: float, r: float) -> str:
    """A diamond lattice of gilt hairlines over the field, clipped around the
    medallion. Drawn as plain segments rather than a <pattern>, because a
    pattern is one more thing a native renderer may drop; segments are not."""
    x, top, w, h = _box(geometry)
    inset = 16.0
    x0, y0, x1, y1 = x + inset, top + inset, x + w - inset, top + h - inset
    keep_out = r + 8.0
    parts = []

    def clip_to_rect(px, py, dx, dy):
        """t-range for which (px + t*dx, py + t*dy) lies inside the rect."""
        lo, hi = -1e9, 1e9
        for p_, d_, a, b in ((px, dx, x0, x1), (py, dy, y0, y1)):
            if d_ == 0:
                if not (a <= p_ <= b):
                    return None
                continue
            t_a, t_b = (a - p_) / d_, (b - p_) / d_
            lo, hi = max(lo, min(t_a, t_b)), min(hi, max(t_a, t_b))
        return (lo, hi) if lo < hi else None

    def emit(px, py, dx, dy, lo, hi):
        """The segment from t=lo to t=hi, minus the part inside the medallion."""
        # solve |p(t) - c|^2 = R^2 for the crossing points
        fx, fy = px - cx, py - cy
        a = dx * dx + dy * dy
        b = 2 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - keep_out * keep_out
        disc = b * b - 4 * a * c
        pieces = [(lo, hi)]
        if disc > 0:
            t1, t2 = (-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a)
            pieces = [(lo, min(hi, t1)), (max(lo, t2), hi)]
        for s_, e_ in pieces:
            if e_ - s_ > 4.0:
                parts.append(f"M{_pt(px + s_ * dx, py + s_ * dy)}L{_pt(px + e_ * dx, py + e_ * dy)}")

    span = (x1 - x0) + (y1 - y0)
    n = int(span / LATTICE_PITCH) + 2
    for k in range(-n, n + 1):
        c_ = k * LATTICE_PITCH
        # lines x - y = c  (rising)  and  x + y = c  (falling), through the box
        for (px, py, dx, dy) in (
            (x0 + c_ + (y0 - y0), y0, 1.0, 1.0),          # x - y = x0 + c - y0
            (x0 + c_, y1, 1.0, -1.0),                       # x + y = x0 + c + y1
        ):
            rng = clip_to_rect(px, py, dx, dy)
            if rng:
                emit(px, py, dx, dy, *rng)
    return (
        f'<path class="q-rule-gold" fill="none" stroke-width="0.55" opacity="0.7" '
        f'd="{"".join(parts)}"/>'
    )


def _seeded(geometry: Geometry, cx: float, cy: float, r: float) -> str:
    """Small florets on a staggered grid across the field, clear of the
    medallion, the edges and the corners where the bosses sit."""
    x, top, w, h = _box(geometry)
    florets, hearts = [], []
    rows = int(h / (SEED_PITCH * 0.866)) + 1
    for j in range(rows):
        y = top + 30.0 + j * SEED_PITCH * 0.866
        if y > top + h - 26.0:
            break
        offset = SEED_PITCH / 2 if j % 2 else 0.0
        cols = int(w / SEED_PITCH) + 1
        for i in range(cols):
            px = x + 30.0 + offset + i * SEED_PITCH
            if px > x + w - 26.0:
                break
            if math.hypot(px - cx, y - cy) < r + 22.0:
                continue
            near_corner = min(
                math.hypot(px - kx, y - ky)
                for kx, ky in ((x, top), (x + w, top), (x, top + h), (x + w, top + h))
            )
            if near_corner < 92.0:
                continue
            florets.append(_floret(px, y, 6.2, FLORET_PETALS))
            hearts.append(
                f'<circle class="q-floret-heart" cx="{_n(px)}" cy="{_n(y)}" r="1.9"/>'
            )
    return f'<path class="q-floret" d="{"".join(florets)}"/>' + "".join(hearts)


def _vines(geometry: Geometry, cx: float, cy: float, r: float) -> str:
    """Gilt vines sweeping from each corner boss toward the medallion, with
    leaves either side, buds between, and a floret midway."""
    x, top, w, h = _box(geometry)
    x1, bottom = x + w, top + h
    leaf = _ogee(13.0, 5.0)
    bud = _ogee(8.0, 3.4)
    bosses, hearts, leaves, buds, vines, curls = [], [], [], [], [], []

    def on(p0, c1, c2, p3, t):
        m = 1 - t
        return (m**3 * p0[0] + 3 * m * m * t * c1[0] + 3 * m * t * t * c2[0] + t**3 * p3[0],
                m**3 * p0[1] + 3 * m * m * t * c1[1] + 3 * m * t * t * c2[1] + t**3 * p3[1])

    for kx, ky in ((x, top), (x1, top), (x, bottom), (x1, bottom)):
        dx, dy = cx - kx, cy - ky
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        angle = math.atan2(ux, -uy)
        reach = length - r - 28.0

        # the corner boss: a large floret with a ring of buds
        fx, fy = kx + ux * 44.0, ky + uy * 44.0
        bosses.append(_floret(fx, fy, 18.0, 8))
        hearts.append(f'<circle class="q-floret-heart" cx="{_n(fx)}" cy="{_n(fy)}" r="5.4"/>')
        for k in range(7):
            a = angle + math.radians(-90 + k * 30)
            buds.append(_place(bud, fx + math.sin(a) * 29.0, fy - math.cos(a) * 29.0, a))

        for side in (-1, 1):
            p0 = (fx + ux * 20.0, fy + uy * 20.0)
            tip = (kx + ux * reach + nx * side * 64.0, ky + uy * reach + ny * side * 64.0)
            c1 = (p0[0] + ux * reach * 0.30 + nx * side * 82.0, p0[1] + uy * reach * 0.30 + ny * side * 82.0)
            c2 = (p0[0] + ux * reach * 0.72 + nx * side * 30.0, p0[1] + uy * reach * 0.72 + ny * side * 30.0)
            vines.append(f"M{_pt(*p0)}C{_pt(*c1)} {_pt(*c2)} {_pt(*tip)}")
            # a curl at the tip, turning away from the medallion
            sx, sy = -uy * side, ux * side
            q = 15.0
            curls.append(
                f"M{_pt(*tip)}"
                f"Q{_pt(tip[0] + sx * q, tip[1] + sy * q)} "
                f"{_pt(tip[0] + sx * q - ux * q * 0.7, tip[1] + sy * q - uy * q * 0.7)}"
                f"Q{_pt(tip[0] + sx * q * 0.5 - ux * q * 1.3, tip[1] + sy * q * 0.5 - uy * q * 1.3)} "
                f"{_pt(tip[0] + sx * q * 0.15 - ux * q * 0.9, tip[1] + sy * q * 0.15 - uy * q * 0.9)}"
            )
            for i, t in enumerate((0.20, 0.36, 0.52, 0.68, 0.84)):
                vx, vy = on(p0, c1, c2, tip, t)
                lean = 1 if i % 2 == 0 else -1
                leaves.append(_place(leaf, vx + nx * lean * 9.0, vy + ny * lean * 9.0,
                                     angle + lean * math.radians(60)))
                if i in (1, 3):
                    bx, by = on(p0, c1, c2, tip, t + 0.08)
                    buds.append(_place(bud, bx - nx * lean * 9.0, by - ny * lean * 9.0,
                                       angle - lean * math.radians(60)))
            vx, vy = on(p0, c1, c2, tip, 0.56)
            bosses.append(_floret(vx, vy, 9.5, FLORET_PETALS))
            hearts.append(f'<circle class="q-floret-heart" cx="{_n(vx)}" cy="{_n(vy)}" r="2.8"/>')

    # a boss in each side margin level with the medallion, and one below it
    for mx, my in ((x + 36.0, cy), (x1 - 36.0, cy), (cx, bottom - 36.0)):
        bosses.append(_floret(mx, my, 13.5, 8))
        hearts.append(f'<circle class="q-floret-heart" cx="{_n(mx)}" cy="{_n(my)}" r="4"/>')
        for k in range(8):
            a = k * math.pi / 4
            buds.append(_place(bud, mx + math.sin(a) * 23.0, my - math.cos(a) * 23.0, a))

    return (
        f'<path class="q-ribbon-a" fill="none" stroke-width="{_n(RIBBON_W * 0.9)}"'
        f' d="{"".join(vines)}{"".join(curls)}"/>'
        f'<path class="q-leaf" d="{"".join(leaves)}"/>'
        f'<path class="q-hf-header-floret-soft" d="{"".join(buds)}"/>'
        f'<path class="q-hf-header-floret" d="{"".join(bosses)}"/>'
        + "".join(hearts)
    )


# --- the medallion ------------------------------------------------------------

def _halo(cx: float, cy: float, r_in: float, r_out: float) -> str:
    """The deep ring around the medallion, ruled in gold, dotted with buds -
    where the surah band's colour is spent on these pages."""
    bud = _ogee(7.0, 3.0)
    buds = []
    n = 40
    for i in range(n):
        a = i * 2 * math.pi / n
        px, py = cx + math.cos(a) * (r_in + r_out) / 2, cy + math.sin(a) * (r_in + r_out) / 2
        buds.append(_place(bud, px, py, a + math.pi / 2))
    return (
        f'<circle class="q-hf-header-ground" cx="{_n(cx)}" cy="{_n(cy)}" r="{_n(r_out)}"/>'
        f'<path class="q-hf-header-floret-soft" d="{"".join(buds)}"/>'
        f'<circle class="q-rule-gold" fill="none" cx="{_n(cx)}" cy="{_n(cy)}"'
        f' r="{_n(r_out)}" stroke-width="2.6"/>'
        f'<circle class="q-rule-gold" fill="none" cx="{_n(cx)}" cy="{_n(cy)}"'
        f' r="{_n(r_in)}" stroke-width="2.2"/>'
    )


def _ring(cx: float, cy: float, r_mid: float) -> str:
    """The frame's interlace, closed into a ring around the disc."""
    amp = RING_W * RING_AMP
    n = RING_SEGMENTS
    step = 2 * math.pi / n

    def point(radius: float, theta: float) -> tuple[float, float]:
        return cx + math.cos(theta) * radius, cy + math.sin(theta) * radius

    ribbons = {1: [], -1: []}
    for phase in (1, -1):
        parts = [f"M{_pt(*point(r_mid, 0.0))}"]
        for i in range(n):
            a0, a1 = i * step, (i + 1) * step
            mid = point(r_mid + amp * 2 * phase, (a0 + a1) / 2)
            parts.append(f"Q{_pt(*mid)} {_pt(*point(r_mid, a1))}")
        ribbons[phase].append("".join(parts))

    florets, hearts, leaves = [], [], []
    leaf = _ogee(8.0, 3.8)
    for i in range(n):
        theta = (i + 0.5) * step
        fx, fy = point(r_mid, theta)
        florets.append(_floret(fx, fy, RING_FLORET_R, FLORET_PETALS))
        hearts.append(f'<circle class="q-floret-heart" cx="{_n(fx)}" cy="{_n(fy)}" r="1.9"/>')
        jt = (i + 1) * step
        outward = jt + math.pi / 2
        for sign in (1, -1):
            lx, ly = point(r_mid + sign * amp * 0.55, jt)
            leaves.append(_place(leaf, lx, ly, outward + (0.0 if sign > 0 else math.pi)))

    return (
        f'<path class="q-ribbon-b" fill="none" stroke-width="{_n(RIBBON_W)}" d="{"".join(ribbons[-1])}"/>'
        f'<path class="q-ribbon-a" fill="none" stroke-width="{_n(RIBBON_W)}" d="{"".join(ribbons[1])}"/>'
        f'<path class="q-leaf" d="{"".join(leaves)}"/>'
        f'<path class="q-floret" d="{"".join(florets)}"/>'
        + "".join(hearts)
    )
