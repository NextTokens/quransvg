"""The floral look: the border and surah band supplied in `build/newlook`.

Two frames and two headers arrived, but the pairs are geometrically identical —
only five named colours differ between them. So this is one artwork with two
palettes, which is exactly the shape the rest of the pipeline already assumes:
the drawing is adopted once, its colours become classes bound to theme tokens,
and the two looks ship as two theme files.

The border is *not* scaled as a finished drawing. It arrives laid out for an A4
page, 1050 x 1485, where its band is 3% of the page width — on our page that is
30 units a side, and the panel only has 32 to give before the type starts
shrinking again. So the artwork is treated as a kit: its rules, its repeating
edge tile and its corner piece are re-laid to this page's proportions and to the
19.5 units the finalised layout leaves for a border. The tile count follows the
page, which is why the sides carry 30 repeats where the A4 original carried 12.

Nothing here takes a page number: the border is the same object on every page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .geometry import Geometry

ASSETS = Path(__file__).resolve().parents[2] / "assets"
FRAME_ASSET = ASSETS / "newlook-frame.svg"
HEADER_ASSET = ASSETS / "newlook-header.svg"
OPENING_ASSET = ASSETS / "newlook-opening.svg"

#: The artwork's own class names, renamed for what they paint. "green" is a
#: ground and "pink" is a flower; in the night theme they are navy and rose.
#: The page stylesheet binds these five to theme tokens of the same names.
CLASS_MAP: dict[str, str] = {
    "green": "q-orn-ground",
    "pink": "q-orn-flower",
    "cream": "q-orn-scroll",
    "sage": "q-orn-panel",
    "cream-stroke": "q-orn-scroll-stroke",
    "outline": "q-orn-outline",
    "line": "q-orn-line",
}

ID_PREFIX = "nl-"

# --- the artwork's own coordinates ------------------------------------------
ART_W = 1050.0           # the frame sheet
ART_H = 1485.0
ART_BAND_OUTER = 37.0    # outermost rule
ART_BAND_INNER = 68.0    # innermost rule
ART_RULES = (37.0, 40.0, 43.0, 65.0, 68.0)
ART_ORNAMENT = 53.0      # the centre line the edge tiles and corners sit on
ART_TILE = 118.0         # one repeat of the edge vine

HEADER_W = 1800.0        # the surah band sheet
HEADER_H = 210.0

# --- where the border sits on our page --------------------------------------
# The layout puts the text panel at 38 and a line-final word's ink up to 11.4
# units before that, with a 3-unit gutter shift on top: 20 is the last unit a
# border may occupy without letters running through it.
BAND_OUTER = 3.5
BAND_INNER = 20.0


def _scale() -> float:
    """Artwork band units -> page units."""
    return (BAND_INNER - BAND_OUTER) / (ART_BAND_INNER - ART_BAND_OUTER)


def _inset(art_inset: float) -> float:
    return BAND_OUTER + (art_inset - ART_BAND_OUTER) * _scale()


@dataclass(frozen=True)
class Artwork:
    defs: str
    body: str


def _classify(markup: str) -> str:
    """Rename the artwork's colour classes into our namespace."""

    def swap(match: re.Match) -> str:
        names = [CLASS_MAP.get(n, n) for n in match.group(1).split()]
        return f'class="{" ".join(names)}"'

    return re.sub(r'class="([^"]+)"', swap, markup)


@lru_cache(maxsize=1)
def _artwork_ids() -> tuple[str, ...]:
    """Every id either sheet declares.

    Collected across both files before anything is renamed: the header's body
    points at `#left-decoration`, which is declared in the *defs*, so renaming
    each section against only its own ids left that `<use>` pointing at nothing
    and the band lost its floral ends.
    """
    ids: set[str] = set()
    for path in (FRAME_ASSET, HEADER_ASSET, OPENING_ASSET):
        ids |= set(re.findall(r'\sid="([\w-]+)"', path.read_text(encoding="utf-8")))
    return tuple(sorted(ids - {"title", "desc"}, key=len, reverse=True))


def _localise(markup: str) -> str:
    """Prefix every id and reference, so the artwork cannot collide with ours."""
    for name in _artwork_ids():
        markup = markup.replace(f'id="{name}"', f'id="{ID_PREFIX}{name}"')
        markup = markup.replace(f'href="#{name}"', f'href="#{ID_PREFIX}{name}"')
    # Carry both spellings. The artwork references its defs with SVG 1.1's
    # xlink:href; a renderer that only knows SVG 2 wants a bare href, and one
    # that only knows 1.1 wants the prefixed form. Both on one element is legal
    # and costs a few bytes that gzip takes straight back.
    return re.sub(
        r'xlink:href="(#[\w-]+)"',
        lambda m: f'href="{m.group(1)}" xlink:href="{m.group(1)}"',
        markup,
    )


def _adopt(path: Path) -> Artwork:
    source = path.read_text(encoding="utf-8")
    defs = re.search(r"<defs>(.*?)</defs>", source, re.S)
    if not defs:
        raise ValueError(f"{path.name} has no <defs>")
    body = source[source.index("</defs>") + len("</defs>"):]
    body = body[: body.rindex("</svg>")]
    # The artwork's <style> carries its literal palette; the theme block owns
    # colour here, so it goes.
    inner = re.sub(r"<style[^>]*>.*?</style>", "", defs.group(1), flags=re.S)
    body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    inner = re.sub(r"<!--.*?-->", "", inner, flags=re.S)
    return Artwork(defs=_localise(_classify(inner)), body=_localise(_classify(body)))


@lru_cache(maxsize=1)
def _frame_art() -> Artwork:
    return _adopt(FRAME_ASSET)


@lru_cache(maxsize=1)
def _header_art() -> Artwork:
    return _adopt(HEADER_ASSET)


@lru_cache(maxsize=1)
def _header_body() -> str:
    """Header artwork safe to instantiate more than once in one document.

    The source groups have editor-friendly IDs, but no output reference points
    at them. Keeping those IDs in every Surah band creates duplicate DOM IDs on
    pages containing multiple openings and on pages 1-2, whose illumination
    also carries a band.
    """
    return re.sub(
        r'\s+id="nl-(?:frame|central-cartouche|floral-decoration)"',
        "",
        _header_art().body,
    )


@lru_cache(maxsize=1)
def _opening_art() -> Artwork:
    return _adopt(OPENING_ASSET)


def opening_defs() -> str:
    """The motifs only the two opening pages use.

    Emitted inside `#q-illumination` rather than into the page's own <defs>,
    so every page's <defs> stays byte-identical - the guarantee that the shell
    is one object across the mushaf - without 602 pages carrying a crown they
    never draw.
    """
    have = set(re.findall(r'\sid="([\w-]+)"', defs()))
    out = []
    for block in re.findall(
        r'<g\s[^>]*id="[\w-]+".*?</g>', _opening_art().defs, re.S
    ):
        name = re.search(r'\sid="([\w-]+)"', block).group(1)
        if name not in have:
            out.append(block)
            have.add(name)
    return f"<defs>{''.join(out)}</defs>"


def opening_body(part: str) -> str:
    """One named group out of the opening artwork, ready to place."""
    art = _opening_art().body
    start = art.index(f'<g id="{ID_PREFIX}{part}"')
    depth, i = 0, start
    while i < len(art):
        if art.startswith("<g", i):
            depth += 1; i += 2
        elif art.startswith("</g>", i):
            depth -= 1; i += 4
            if depth == 0:
                return art[start:i]
        else:
            i += 1
    raise ValueError(f"unterminated group {part}")


def css() -> str:
    """Extra rules the adopted artwork needs beyond the page stylesheet.

    None: its seven classes are declared in the stylesheet template like every
    other class on the page, so the theme block paints them.
    """
    return ""


def defs() -> str:
    """The reusable ornament, emitted once per page.

    Both sheets carry the same vine, petal and rosette definitions; the frame
    adds the edge tile and corner, so its copy wins and only the header's
    extras are appended.
    """
    frame = _frame_art().defs
    have = set(re.findall(r'\sid="([\w-]+)"', frame))
    extra = []
    for block in re.findall(r'<(?:g|path|clipPath)\s[^>]*id="[\w-]+".*?(?:</(?:g|clipPath)>|/>)',
                            _header_art().defs, re.S):
        name = re.search(r'\sid="([\w-]+)"', block).group(1)
        if name not in have:
            extra.append(block)
            have.add(name)
    return frame + "".join(extra)


# --- the border -------------------------------------------------------------

def _n(value: float, places: int = 2) -> str:
    rounded = round(value, places)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{places}f}".rstrip("0").rstrip(".")


def _ring(cls: str, w: float, h: float, outer: float, inner: float, stroke: float) -> str:
    """A rectangular ring, drawn the way the artwork draws its rules."""
    d = (
        f"M{_n(outer)} {_n(outer)}H{_n(w - outer)}V{_n(h - outer)}H{_n(outer)}Z"
        f"M{_n(inner)} {_n(inner)}V{_n(h - inner)}H{_n(w - inner)}V{_n(inner)}Z"
    )
    return (
        f'<path class="{cls}" fill-rule="evenodd" stroke-width="{_n(stroke)}" d="{d}"/>'
    )


def _edge(count: int, span: float, scale: float) -> str:
    """One run of edge tiles, stretched a fraction to land on the corners."""
    fit = span / (count * ART_TILE * scale)
    tiles = "".join(
        f'<use href="#{ID_PREFIX}edge-tile" xlink:href="#{ID_PREFIX}edge-tile" '
        f'transform="translate({_n(i * ART_TILE)} 0)"/>'
        for i in range(count)
    )
    return f'<g transform="scale({_n(fit * scale, 6)} {_n(scale, 6)})">{tiles}</g>'


def frame(geometry: Geometry) -> str:
    """The border, laid out for this page.

    Page-independent by construction: every number below comes from the
    geometry constants, never from a page.
    """
    w, h = geometry.view_w, geometry.view_h
    s = _scale()
    rules = [_inset(v) for v in ART_RULES]
    line = _inset(ART_ORNAMENT)          # centre line of the ornament strip
    tile = ART_TILE * s

    across = max(4, round((w - 2 * line) / tile))
    down = max(6, round((h - 2 * line) / tile))

    parts = [
        _ring("q-orn-panel q-orn-outline", w, h, rules[0], rules[1], 0.55),
        _ring("q-orn-scroll q-orn-outline", w, h, rules[1], rules[2], 0.45),
        _ring("q-orn-ground q-orn-outline", w, h, rules[2], rules[3], 0.5),
        _ring("q-orn-scroll q-orn-outline", w, h, rules[3], rules[4], 0.45),
        # the four runs, each starting on a corner and ending on the next
        f'<g transform="translate({_n(line)} {_n(line)})">'
        f"{_edge(across, w - 2 * line, s)}</g>",
        f'<g transform="translate({_n(w - line)} {_n(h - line)}) rotate(180)">'
        f"{_edge(across, w - 2 * line, s)}</g>",
        f'<g transform="translate({_n(w - line)} {_n(line)}) rotate(90)">'
        f"{_edge(down, h - 2 * line, s)}</g>",
        f'<g transform="translate({_n(line)} {_n(h - line)}) rotate(-90)">'
        f"{_edge(down, h - 2 * line, s)}</g>",
    ]
    for cx, cy, angle in (
        (line, line, 0), (w - line, line, 90),
        (w - line, h - line, 180), (line, h - line, 270),
    ):
        parts.append(
            f'<use href="#{ID_PREFIX}frame-corner" xlink:href="#{ID_PREFIX}frame-corner" '
            f'transform="translate({_n(cx)} {_n(cy)}) '
            f'rotate({angle}) scale({_n(s, 6)})"/>'
        )
    return "".join(parts)


# --- the surah band ---------------------------------------------------------

#: Where the name and its note sit inside the cartouche, in artwork units. The
#: cartouche's flat centre runs x 639..1161, y 22..188.
NAME_BASELINE = 132.0
META_BASELINE = 180.0
VIEW_W = HEADER_W
VIEW_H = HEADER_H

TEXT_CX = 900.0          # this artwork has no group to centre the text for us
NAME_W_RATIO = 0.28      # the cartouche's flat centre is 522 of 1800 units
NAME_H = 86.0
NAME_CEILING = 104.0
META_W_RATIO = 0.17
META_H = 26.0
META_CEILING = 30.0


def band_height(width: float) -> float:
    return width / HEADER_W * HEADER_H


def blank_band(cx: float, cy: float, width: float) -> str:
    """The surah band with nothing written in it — the artwork's own foot piece."""
    scale = width / HEADER_W
    x = cx - width / 2
    y = cy - band_height(width) / 2
    return (
        f'<g transform="translate({_n(x)} {_n(y)}) scale({_n(scale, 5)})">'
        f"{_header_body()}</g>"
    )


def instance(
    *,
    cx: float,
    cy: float,
    width: float,
    name_path: str,
    meta_path: str,
    surah: int,
    line: int,
) -> str:
    """One surah band, scaled to `width` and centred on (cx, cy)."""
    scale = width / HEADER_W
    x = cx - width / 2
    y = cy - band_height(width) / 2
    return (
        f'<g class="q-opening" id="q-surah-open-{surah}" data-line="{line}" '
        f'data-surah="{surah}" '
        f'transform="translate({_n(x)} {_n(y)}) scale({_n(scale, 5)})">'
        f"{_header_body()}"
        f'<path class="q-h-name" d="{name_path}"/>'
        f'<path class="q-h-meta" d="{meta_path}"/>'
        f"</g>"
    )


# --- the end-of-ayah mark ---------------------------------------------------

#: The opening artwork's star, lifted so the ayah mark belongs to the same
#: hand as the border and the surah band. Its own centre carries a rosette;
#: here the centre is the field the number sits on, so the star reads as a
#: medallion rather than as a flower with digits pasted over it.
STAR_OUTER = (
    "M0 -31L9 -23L23 -23L23 -9L31 0L23 9L23 23L9 23L0 31"
    "L-9 23L-23 23L-23 9L-31 0L-23 -9L-23 -23L-9 -23Z"
)
STAR_INNER = (
    "M0 -25L8 -19L19 -19L19 -8L25 0L19 8L19 19L8 19L0 25"
    "L-8 19L-19 19L-19 8L-25 0L-19 -8L-19 -19L-8 -19Z"
)
STAR_ART_R = 31.0        # the outer star's radius in artwork units
AYAH_R = 25.0            # what it becomes on the page
AYAH_FIELD = 0.82        # of the inner star's width, usable for the number


def ayah_mark() -> str:
    """The mark, centred on the origin. Emitted once into the page's defs."""
    s = AYAH_R / STAR_ART_R
    return (
        f'<g id="q-ayah-rosette">'
        f'<path class="q-ayah-ring q-orn-outline" stroke-width="{_n(1.1 * s)}" '
        f'transform="scale({_n(s, 5)})" d="{STAR_OUTER}"/>'
        f'<path class="q-ayah-field q-orn-outline" stroke-width="{_n(0.8 * s)}" '
        f'transform="scale({_n(s, 5)})" d="{STAR_INNER}"/>'
        f"</g>"
    )


def ayah_field_width() -> float:
    """Room inside the mark for the number, so digits can be fitted to it."""
    inner = 25.0 * AYAH_R / STAR_ART_R      # the inner star's radius on the page
    return 2 * inner * AYAH_FIELD
