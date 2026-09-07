"""Conservative outline simplification.

The KFGQPC page fonts carry roughly 677 points and nine contours per glyph -
the signature of outlines traced from a printed master rather than drawn as
curves. At the size a page is actually viewed, most of those points describe
detail finer than a pixel: one font unit is 0.0202 viewBox units, which on a
400px-wide phone is about 0.008px. There is a great deal of room to remove
points that no display can resolve.

The method is adjacent-quadratic merging. Two neighbouring curve segments are
replaced by the single quadratic through their endpoints whose control point
is where their outer tangents meet, but only when the replacement stays within
`tolerance` font units of the original everywhere along its length.

Two rules keep this safe for calligraphy:

* **Corners are never merged across.** Where the tangent direction turns
  sharply, the point is a real feature - the terminal of a stroke, the cusp
  where two strokes meet - and removing it would visibly round off the
  letterform. Such joints are pinned.
* **Contours are never removed.** The dots (i'jam) and vowel marks (harakat)
  are small closed contours, and losing one changes the word. The count of
  contours in equals the count out, always.
"""

from __future__ import annotations

import math
from typing import Sequence

Point = tuple[float, float]

#: Tangent turn beyond which a joint is treated as a corner and pinned.
CORNER_DEGREES = 32.0

#: Samples used when measuring how far a merged curve strays from the original.
SAMPLES = 24


def _quad_at(p0: Point, c: Point, p1: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
        u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1],
    )


def _line_intersection(a0: Point, a1: Point, b0: Point, b1: Point) -> Point | None:
    dx1, dy1 = a1[0] - a0[0], a1[1] - a0[1]
    dx2, dy2 = b1[0] - b0[0], b1[1] - b0[1]
    denominator = dx1 * dy2 - dy1 * dx2
    if abs(denominator) < 1e-9:
        return None
    t = ((b0[0] - a0[0]) * dy2 - (b0[1] - a0[1]) * dx2) / denominator
    return (a0[0] + t * dx1, a0[1] + t * dy1)


def _distance(point: Point, other: Point) -> float:
    return math.hypot(point[0] - other[0], point[1] - other[1])


def _angle(a: Point, b: Point) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _sane(p0: Point, control: Point, p2: Point, tolerance: float) -> bool:
    """Reject a control point thrown far away by near-parallel tangents.

    When two tangents are almost collinear their intersection races off toward
    infinity, and the resulting curve — though it may pass the sampled distance
    test — is numerically fragile. Keep the control point near the chord.
    """
    chord = _distance(p0, p2)
    limit = chord * 3.0 + tolerance * 4.0
    return _distance(control, p0) <= limit and _distance(control, p2) <= limit


def _at(p0: Point, control: Point | None, p1: Point, t: float) -> Point:
    if control is None:
        return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
    return _quad_at(p0, control, p1, t)


#: Where to probe. Each entry pairs a parameter on the merged curve with the
#: matching parameter on one of the two originals. The merged curve covers the
#: first original over [0, .5] and the second over [.5, 1].
_PROBES = (
    (0.125, 0, 0.25),
    (0.25, 0, 0.5),
    (0.375, 0, 0.75),
    (0.5, 0, 1.0),
    (0.625, 1, 0.25),
    (0.75, 1, 0.5),
    (0.875, 1, 0.75),
)


def _deviation(
    p0: Point,
    c0: Point | None,
    p1: Point,
    c1: Point | None,
    p2: Point,
    control: Point,
    tolerance: float,
) -> float:
    """How far the merged curve strays from the pair it replaces.

    Probing a fixed handful of matched parameters is far cheaper than a full
    nearest-point search and, because a merged quadratic tracks its originals
    at close to the same rate, tight enough in practice — the corner test
    upstream has already excluded the cases where the rates diverge badly.
    """
    worst = 0.0
    for t, which, local in _PROBES:
        candidate = _quad_at(p0, control, p2, t)
        original = (
            _at(p0, c0, p1, local) if which == 0 else _at(p1, c1, p2, local)
        )
        gap = _distance(candidate, original)
        if gap > worst:
            worst = gap
            if worst > tolerance:
                return worst
    return worst


def _segments(contour: list) -> list[tuple[Point, Point | None, Point]]:
    """Normalise a contour to a list of (start, control, end) segments.

    A control of None means a straight line. TrueType's runs of consecutive
    off-curve points are expanded here into explicit quadratics through their
    implied on-curve midpoints.
    """
    out: list[tuple[Point, Point | None, Point]] = []
    for kind, points in contour:
        if kind == "L":
            out.append((points[0], None, points[1]))
        else:
            start, controls, end = points
            count = len(controls)
            current = start
            for index, control in enumerate(controls):
                if index < count - 1:
                    nxt = controls[index + 1]
                    stop = ((control[0] + nxt[0]) / 2, (control[1] + nxt[1]) / 2)
                else:
                    stop = end
                out.append((current, control, stop))
                current = stop
    return out


def _to_contours(recording: Sequence[tuple[str, Sequence]]) -> list[list]:
    """Split pen operations into contours of normalised segments."""
    contours: list[list] = []
    current: list = []
    start: Point | None = None
    position: Point | None = None

    for op, args in recording:
        if op == "moveTo":
            if current:
                contours.append(current)
            current = []
            start = position = args[0]
        elif op == "lineTo":
            current.append(("L", (position, args[0])))
            position = args[0]
        elif op == "qCurveTo":
            points = list(args)
            if points and points[-1] is None:
                # An all-off-curve contour: TrueType implies the on-curve
                # midpoint between the last and first control points.
                controls = points[:-1]
                implied = (
                    (controls[-1][0] + controls[0][0]) / 2,
                    (controls[-1][1] + controls[0][1]) / 2,
                )
                position = start = implied
                current.append(("Q", (implied, controls, implied)))
                continue
            end = points[-1]
            controls = points[:-1]
            if not controls:
                current.append(("L", (position, end)))
            else:
                current.append(("Q", (position, controls, end)))
            position = end
        elif op == "closePath":
            if current:
                contours.append(current)
            current = []
            position = start
    if current:
        contours.append(current)
    return contours


def _merge_pass(segments: list, tolerance: float) -> tuple[list, bool]:
    """One sweep of adjacent-segment merging. Returns (segments, changed)."""
    if len(segments) < 3:
        return segments, False

    corner = math.radians(CORNER_DEGREES)
    out: list = []
    index = 0
    changed = False

    while index < len(segments):
        if index + 1 >= len(segments):
            out.append(segments[index])
            break

        first = segments[index]
        second = segments[index + 1]
        p0, c0, p1 = first
        _, c1, p2 = second

        # A corner is a break in tangent direction *at the shared point* —
        # arriving along one direction and leaving along another. Measuring the
        # turn across the whole pair instead would flag every ordinary curve.
        arriving = c0 if c0 is not None else p0
        leaving = c1 if c1 is not None else p2
        if _distance(arriving, p1) < 1e-9 or _distance(p1, leaving) < 1e-9:
            turn = 0.0
        else:
            turn = abs(_angle(arriving, p1) - _angle(p1, leaving))
            turn = min(turn, 2 * math.pi - turn)

        merged = None
        if turn < corner:
            tangent_out = c0 if c0 is not None else p1
            tangent_in = c1 if c1 is not None else p1
            control = _line_intersection(p0, tangent_out, tangent_in, p2)
            if control is not None and _sane(p0, control, p2, tolerance):
                worst = _deviation(p0, c0, p1, c1, p2, control, tolerance)
                if worst <= tolerance:
                    merged = (p0, control, p2)

        if merged is not None:
            out.append(merged)
            index += 2
            changed = True
        else:
            out.append(first)
            index += 1

    return out, changed


def simplify_contours(recording: Sequence[tuple[str, Sequence]], tolerance: float) -> list:
    """Return pen operations equivalent to `recording` with fewer points."""
    if tolerance <= 0:
        return list(recording)

    result: list[tuple[str, tuple]] = []
    for contour in _to_contours(recording):
        segments = _segments(contour)
        if not segments:
            continue
        for _ in range(6):
            segments, changed = _merge_pass(segments, tolerance)
            if not changed:
                break

        result.append(("moveTo", (segments[0][0],)))
        for _, control, end in segments:
            if control is None:
                result.append(("lineTo", (end,)))
            else:
                result.append(("qCurveTo", (control, end)))
        result.append(("closePath", ()))
    return result
