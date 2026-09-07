"""One path encoder, shared by every layer of the page.

Path data dominates the size of a generated page, so how it is written matters
as much as what is drawn.  Three things do the work here:

* **Relative commands.**  Outline coordinates move in small steps, so deltas
  are far shorter to write than absolute positions.
* **The `t` shorthand.**  TrueType stores runs of off-curve points with implied
  on-curve points between them; each such segment is a smooth continuation of
  the last, which `t` expresses in two numbers instead of four.
* **Terse number syntax.**  A leading zero is never needed, and a minus sign is
  itself a separator, so `l5-3` is legal and shorter than `l 5 -3`.

The encoder is deterministic: identical input always produces identical bytes,
which is what lets the build be reproducible and the shell provably invariant.
"""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

Point = tuple[float, float]
Transform = Callable[[Point], Point]


def scale_flip(scale: float, dx: float = 0.0, dy: float = 0.0) -> Transform:
    """Font space (y up) to page space (y down), scaled and translated."""

    def apply(point: Point) -> Point:
        return (dx + point[0] * scale, dy - point[1] * scale)

    return apply


def encode(
    recording: Iterable[tuple[str, Sequence]],
    transform: Transform,
    *,
    places: int = 1,
) -> str:
    """Serialise pen operations as compact relative SVG path data."""
    out: list[str] = []
    cx = cy = 0.0
    start_x = start_y = 0.0
    control: Point | None = None
    started = False

    def num(value: float) -> str:
        rounded = round(value, places)
        if rounded == int(rounded):
            text = str(int(rounded))
        else:
            text = f"{rounded:.{places}f}".rstrip("0").rstrip(".")
        if text.startswith("0."):
            return text[1:]
        if text.startswith("-0."):
            return "-" + text[2:]
        return text

    def pair(x: float, y: float) -> str:
        sx, sy = num(x), num(y)
        # A minus sign separates numbers on its own; a space is only needed
        # when the second number is positive.
        return sx + sy if sy.startswith("-") else f"{sx} {sy}"

    for op, args in recording:
        if op == "moveTo":
            x, y = transform(args[0])
            out.append(("M" if not started else "m") + pair(x - (0 if not started else cx), y - (0 if not started else cy)))
            started = True
            cx, cy = x, y
            start_x, start_y = x, y
            control = None
        elif op == "lineTo":
            x, y = transform(args[0])
            dx, dy = x - cx, y - cy
            if abs(dy) < 10 ** -places / 2:
                out.append("h" + num(dx))
            elif abs(dx) < 10 ** -places / 2:
                out.append("v" + num(dy))
            else:
                out.append("l" + pair(dx, dy))
            cx, cy = x, y
            control = None
        elif op == "qCurveTo":
            points = [transform(p) for p in args if p is not None]
            count = len(points)
            if count == 1:                       # degenerate: a line
                x, y = points[0]
                out.append("l" + pair(x - cx, y - cy))
                cx, cy = x, y
                control = None
                continue
            for index in range(count - 1):
                ctrl = points[index]
                nxt = points[index + 1]
                end = (
                    ((ctrl[0] + nxt[0]) / 2, (ctrl[1] + nxt[1]) / 2)
                    if index < count - 2
                    else nxt
                )
                tolerance = 10 ** -places
                smooth = control is not None and (
                    abs((2 * cx - control[0]) - ctrl[0]) < tolerance
                    and abs((2 * cy - control[1]) - ctrl[1]) < tolerance
                )
                if smooth:
                    out.append("t" + pair(end[0] - cx, end[1] - cy))
                else:
                    out.append(
                        "q" + pair(ctrl[0] - cx, ctrl[1] - cy) + " " + pair(end[0] - cx, end[1] - cy)
                    )
                control = ctrl
                cx, cy = end
        elif op == "curveTo":
            points = [transform(p) for p in args]
            c1, c2, end = points[0], points[1], points[2]
            out.append(
                "c" + pair(c1[0] - cx, c1[1] - cy) + " "
                + pair(c2[0] - cx, c2[1] - cy) + " "
                + pair(end[0] - cx, end[1] - cy)
            )
            cx, cy = end
            control = None
        elif op == "closePath":
            out.append("z")
            # After `z` the current point returns to where the subpath began,
            # not to the last point drawn. Carrying the last point forward made
            # every following relative moveto start from the wrong origin, so
            # contours after a closed one landed displaced.
            cx, cy = start_x, start_y
            control = None

    return "".join(out)
