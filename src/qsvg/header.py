"""The illuminated band that opens a surah.

The artwork in `assets/surah-header.svg` is adopted rather than redrawn: a
cusped cartouche flanked by panels of scrolling vine over a lattice ground,
with plum end-caps. Three things have to change before it can be used here.

*The text has to go.* It arrives as `<text>` with a `font-family` list, which
puts us back at the mercy of whatever the device has installed — and several
mobile SVG renderers do no Arabic shaping at all. The two text groups are
emptied and refilled with outlines placed at the same local coordinates, so
the artwork itself never moves.

*The colours have to become classes.* They arrive as literals, so the band
would ignore the theme. Every distinct fill, stroke and stop-colour is mapped
to a class, and the classes resolve through the same theme tokens as the page
frame. Gradient stops accept a class but *not* a `var()` — verified against the
renderer — which is exactly why the flattened output resolves them.

*The ids have to be unique.* A page may open two or three surahs, so anything
carrying an id is emitted once into the page's own `<defs>` and the body is
repeated per occurrence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ASSET = Path(__file__).resolve().parents[2] / "assets" / "surah-header.svg"

#: The artwork's palette, mapped onto the theme's vocabulary. Anything not
#: listed keeps its literal colour and is reported by `unmapped()`.
PALETTE: dict[str, str] = {
    "#c9992f": "ribbon-a",
    "#8a2437": "floret",
    "#6b4a12": "rule-gold",
    "#fbf1d8": "band",
    "#a8771f": "leaf",
    "#7d5716": "rule-gold",
    "#d98aa3": "floret-dot",
    "#f1c85c": "floret-heart",
    "#5e1a2a": "header-ground",
    "#e3c473": "ribbon-b",
    "#8a5f18": "rule-gold",
    "#f3e2bd": "band",
    "#f6e2ac": "floret-heart",
    "#521726": "cartouche",
    "#d8b158": "ribbon-b",
    "#f6e6ae": "band",
    "#f8ecc0": "band",
    "#fdf5e2": "band",
    "#3d1017": "header-ground",
    "#fbe9d2": "band",
    "#c9718a": "header-floret",
    "#e58fb0": "header-floret-soft",
    "#9a2a3f": "header-ground-top",
    "#7f1f33": "header-ground",
}

NAME_BASELINE = 12.0     # where the original <text> sat, in header units
META_BASELINE = 36.0
VIEW_W = 1000.0
VIEW_H = 160.0

# How the name and its note are fitted inside the band. Published so a second
# artwork can be swapped in behind the same call.
TEXT_CX = 0.0            # the artwork's own group already centres the text
NAME_W_RATIO = 0.30
NAME_H = 46.0
NAME_CEILING = 52.0
META_W_RATIO = 0.26
META_H = 15.0
META_CEILING = 16.0

#: The artwork's own margin. Measured from a render: the ink occupies
#: x 19.0..980.5, y 15.0..144.5, so a fifth of its height is empty. Placing by
#: the viewBox would waste that on a page where vertical room is the scarce
#: thing, so the band is placed by its ink instead.
INK_X = 19.0
INK_Y = 15.0
INK_W = 961.5
INK_H = 129.5


def band_height(width: float) -> float:
    """How tall the band stands when drawn `width` wide."""
    return width / INK_W * INK_H

_COLOUR = re.compile(r'(fill|stroke|stop-color)="(#[0-9a-fA-F]{6})"')
_TEXT_GROUP = re.compile(r'(<g id="(surah-name|surah-meta)">).*?(</g>)', re.S)


@dataclass(frozen=True)
class Artwork:
    defs: str
    body: str
    classes: dict[str, str]        # class name -> theme token
    unmapped: tuple[str, ...]


def _classify(markup: str, classes: dict[str, str]) -> str:
    """Replace literal paint with classes drawn from the theme."""

    def swap(match: re.Match) -> str:
        prop, colour = match.group(1), match.group(2).lower()
        token = PALETTE.get(colour)
        if token is None:
            return match.group(0)
        # Distinct prefixes per property: deriving them from the first letter
        # made `stroke` and `stop-color` collide, and the stops lost their
        # colour entirely, which rendered the whole band black.
        prefix = {"fill": "q-hf", "stroke": "q-hk", "stop-color": "q-hp"}[prop]
        name = f"{prefix}-{token}"
        classes[name] = f"{prop}:var(--q-{token})"
        return f"__CLASS__{name}__"

    marked = _COLOUR.sub(swap, markup)

    # Fold the placeholders on each element into one class attribute.
    def fold(match: re.Match) -> str:
        element = match.group(0)
        names = re.findall(r"__CLASS__([\w-]+)__", element)
        if not names:
            return element
        element = re.sub(r"\s*__CLASS__[\w-]+__", "", element)
        existing = re.search(r'class="([^"]*)"', element)
        joined = " ".join(dict.fromkeys(names))
        if existing:
            return element.replace(
                existing.group(0), f'class="{existing.group(1)} {joined}"'
            )
        # Insert before the tag close, keeping a self-closing slash where it is:
        # appending after it produced `<path d="..."/ class="...">`.
        close = "/>" if element.rstrip().endswith("/>") else ">"
        return element.rstrip()[: -len(close)].rstrip() + f' class="{joined}"{close}"'[:-1]

    return re.sub(r"<[^>]*>", fold, marked)


@lru_cache(maxsize=1)
def load() -> Artwork:
    if not ASSET.exists():
        raise FileNotFoundError(f"surah header artwork missing: {ASSET}")
    source = ASSET.read_text(encoding="utf-8")

    defs = re.search(r"<defs>(.*?)</defs>", source, re.S)
    if not defs:
        raise ValueError(f"{ASSET.name} has no <defs>")
    body = source[source.index("</defs>") + len("</defs>"):]
    body = body[: body.rindex("</svg>")]
    body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.S)

    # The artwork's own <style> sits inside <defs> and carries a font-family
    # list. Left in, it reintroduces exactly the device-font dependency the
    # whole pipeline exists to avoid.
    defs_inner = re.sub(r"<style[^>]*>.*?</style>", "", defs.group(1), flags=re.S)

    # empty the two text groups; the caller refills them with outlines
    body = _TEXT_GROUP.sub(lambda m: f"{m.group(1)}{{{m.group(2)}}}{m.group(3)}", body)

    # Anything carrying an id must live in the page's <defs>, emitted
    # once: a page may open two or three surahs and ids would collide.
    extra_defs = "".join(re.findall(r"<clipPath.*?</clipPath>", body, re.S))
    body = re.sub(r"<clipPath.*?</clipPath>", "", body, flags=re.S)

    classes: dict[str, str] = {}
    defs_markup = _classify(defs_inner + extra_defs, classes)
    body_markup = _classify(body, classes)

    seen = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", source)}
    return Artwork(
        defs=defs_markup,
        body=body_markup,
        classes=dict(classes),
        unmapped=tuple(sorted(seen - set(PALETTE))),
    )


def css() -> str:
    """Rules binding the artwork's classes to the theme."""
    art = load()
    return "".join(f".{name}{{{rule}}}\n" for name, rule in sorted(art.classes.items()))


def defs() -> str:
    """Gradients, the lattice and the end-cap. Emitted once per page."""
    return load().defs


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
    """One header, scaled to `width` and centred on (cx, cy).

    The outlines are supplied already positioned in the artwork's own
    coordinates, so they land exactly where the original text sat.
    """
    scale = width / INK_W
    x = cx - width / 2 - INK_X * scale
    y = cy - band_height(width) / 2 - INK_Y * scale
    body = (
        load()
        .body.replace("{surah-name}", f'<path class="q-h-name" d="{name_path}"/>')
        .replace("{surah-meta}", f'<path class="q-h-meta" d="{meta_path}"/>')
    )
    # Make every id in this instance unique. A page may open three surahs, and
    # three copies of the same id would leave later headers pointing at the
    # first one's clip path. Suffixing here cannot be defeated by whatever the
    # artwork happens to declare.
    body = _localise(body, surah)
    return (
        f'<g class="q-opening" id="q-surah-open-{surah}" data-line="{line}" '
        f'data-surah="{surah}" '
        f'transform="translate({_n(x)} {_n(y)}) scale({_n(scale, 5)})">'
        f"{body}</g>"
    )


def _localise(markup: str, surah: int) -> str:
    """Suffix every id, and every reference to one, with the surah number."""
    ids = set(re.findall(r'\sid="([\w-]+)"', markup))
    for name in ids:
        markup = markup.replace(f'id="{name}"', f'id="{name}-{surah}"')
        markup = markup.replace(f"url(#{name})", f"url(#{name}-{surah})")
        markup = markup.replace(f'href="#{name}"', f'href="#{name}-{surah}"')
    return markup


def _n(value: float, places: int = 2) -> str:
    rounded = round(value, places)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{places}f}".rstrip("0").rstrip(".")
