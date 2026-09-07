"""The page stylesheet, and the contract that lets an app recolour it.

There is one set of SVGs, not one per theme. Every colour on a page lives in a
single block of plain class rules between two markers:

    /* THEME:BEGIN mushaf */
    .q-rasm{fill:#1A1208}
    .q-band{fill:#FCF2D9}
    ...
    /* THEME:END */

Nothing outside the block carries colour, and nothing inside it carries
anything else. An app switches theme by replacing the text between the
markers, and builds a custom theme by writing that block from its own palette.
`schema()` tells it how: for each of the tokens a theme defines, the exact
selectors and properties that token drives. No CSS knowledge is needed beyond
a loop.

The block deliberately uses literal colours rather than CSS custom properties.
`var()` renders as black in resvg and in the same family of native mobile
renderers, and gradient stops cannot take a `var()` at all - whereas a class
rule setting `fill`, `stroke` or `stop-color` is honoured everywhere.

The template below, written with `var(--q-<token>)`, is the single source of
truth. It is parsed once: declarations that name a token become the theme
block, and everything else - `fill:none`, line caps, dash patterns, display
rules - becomes the structural stylesheet that never changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

BEGIN = "/* THEME:BEGIN"
END = "/* THEME:END */"

TEMPLATE = """.q-bg{fill:var(--q-bg)}
.q-paper{fill:var(--q-paper)}
.q-orn-ground{fill:var(--q-orn-ground)}
.q-orn-flower{fill:var(--q-orn-flower)}
.q-orn-scroll{fill:var(--q-orn-scroll)}
.q-orn-panel{fill:var(--q-orn-panel)}
.q-orn-scroll-stroke{stroke:var(--q-orn-scroll)}
.q-orn-outline{stroke:var(--q-orn-outline);stroke-width:2.4;stroke-linejoin:round;stroke-linecap:round}
.q-orn-line{fill:none}
.q-basmalah{fill:var(--q-ink)}
.q-rasm{fill:var(--q-ink)}
.q-tashkeel{fill:var(--q-tashkeel)}
.q-waqf{fill:var(--q-waqf)}
.q-ayah-ring{fill:var(--q-ayah-ring)}
.q-ayah-field{fill:var(--q-ayah-fill)}
.q-ayah-digit{fill:var(--q-ayah-digit)}
.q-chrome{fill:var(--q-chrome)}
.q-chrome-muted{fill:var(--q-chrome-muted)}
.q-catchword{fill:var(--q-catchword)}
.q-h-name{fill:var(--q-title)}
.q-h-meta{fill:var(--q-title-note)}
.q-word.q-lafz .q-rasm{fill:var(--q-lafz)}
.q-ayah.is-active .q-rasm{fill:var(--q-ink-ayah-active)}
.q-ayah.is-active .q-tashkeel{fill:var(--q-tashkeel-active)}
.q-ayah.is-active .q-ayah-ring{fill:var(--q-ayah-ring-active)}
.q-word.is-active .q-rasm{fill:var(--q-ink-word-active)}
.q-word.is-active .q-tashkeel{fill:var(--q-tashkeel-active)}
.q-word.is-selected .q-rasm{fill:var(--q-ink-select)}
.q-no-frame #q-frame{display:none}
.q-no-chrome #q-chrome{display:none}
.q-no-illumination #q-illumination{display:none}
"""

_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_TOKEN = re.compile(r"var\(--q-([a-z0-9-]+)\)")


@dataclass(frozen=True)
class Binding:
    selector: str
    property: str
    token: str


@dataclass(frozen=True)
class Parsed:
    structural: str
    bindings: tuple[Binding, ...]

    @property
    def tokens(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for b in self.bindings:
            seen.setdefault(b.token)
        return tuple(seen)


def _parse(css: str) -> Parsed:
    structural: list[str] = []
    bindings: list[Binding] = []
    for match in _RULE.finditer(css):
        selector = match.group(1).strip()
        plain: list[str] = []
        for declaration in match.group(2).split(";"):
            declaration = declaration.strip()
            if not declaration:
                continue
            prop, _, value = declaration.partition(":")
            token = _TOKEN.search(value)
            if token:
                bindings.append(Binding(selector, prop.strip(), token.group(1)))
            else:
                plain.append(f"{prop.strip()}:{value.strip()}")
        if plain:
            structural.append(f"{selector}{{{';'.join(plain)}}}")
    return Parsed("\n".join(structural) + "\n", tuple(bindings))


@lru_cache(maxsize=1)
def parsed() -> Parsed:
    from . import newlook

    return _parse(TEMPLATE + newlook.css())


def structural_css() -> str:
    """Rules that never change between themes."""
    return parsed().structural


def theme_block(name: str, colors: dict[str, str]) -> str:
    """The swappable block, with every colour written as a literal."""
    missing = [t for t in parsed().tokens if t not in colors]
    if missing:
        raise ValueError(f"theme {name!r} does not define: {', '.join(missing)}")
    lines = [f"{BEGIN} {name} */"]
    for b in parsed().bindings:
        lines.append(f"{b.selector}{{{b.property}:{colors[b.token]}}}")
    lines.append(END)
    return "\n".join(lines)


def schema() -> dict[str, list[dict[str, str]]]:
    """token -> the rules it drives. Published for the app as themes/schema.json."""
    out: dict[str, list[dict[str, str]]] = {}
    for b in parsed().bindings:
        out.setdefault(b.token, []).append({"selector": b.selector, "property": b.property})
    return out


def swap(svg_text: str, block: str) -> str:
    """Replace the theme block of an already-built page."""
    start = svg_text.find(BEGIN)
    end = svg_text.find(END)
    if start == -1 or end == -1:
        raise ValueError("no THEME block found - was this file built by qsvg?")
    return svg_text[:start] + block + svg_text[end + len(END):]
