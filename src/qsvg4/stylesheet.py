"""The v4 page stylesheet: the v2 contract, plus the tajweed rules.

The rule that made the v2 build work is unchanged — every colour lives between
the THEME:BEGIN/END markers as a literal, nothing outside the block carries
colour, and nothing inside it carries anything else. Tajweed simply adds nine
more tokens to the block, so an app that already builds a custom theme from
`schema.json` gets a tajweed palette by the same loop.

Order in this template is load-bearing, because CSS ties are broken by
document order and three of these selectors weigh the same:

    .q-word.q-lafz .q-rasm          the divine name, our own convention
    .q-tajweed-plain .q-word .q-*   clear everything a rule did not colour
    .q-tajweed .q-word .q-tj-*      a recitation rule
    .q-ayah.is-active .q-rasm       the reader's own highlight

They are written in that order deliberately. A tajweed rule outranks the lafz
colour, because in a tajweed mushaf the rules are the point and the name is
coloured by whatever rule falls on it. The highlight outranks both, because it
answers a tap and has to be visible whatever is underneath it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from qsvg.stylesheet import BEGIN, END, Binding, Parsed, _parse

from . import rules as ruleset

_BASE = """.q-bg{fill:var(--q-bg)}
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
"""

#: With `q-tajweed-plain` on the root, nothing on the page carries colour except
#: a recitation rule. The vowel marks and the pause signs drop to the text's own
#: ink, and so does the divine name - in a tajweed mushaf الله is coloured by
#: whatever rule falls on it, and painting it red as well puts two unrelated
#: meanings in one colour. Every rule here weighs (0,3,0), the same as the lafz
#: rule above it and the tajweed rules below it, so document order alone decides
#: all three: the lafz colour is cancelled, and a recitation rule still wins.
#:
#: It reuses `--q-ink`, so it adds no token and every existing theme already
#: satisfies it. Written as its own class rather than folded into `q-tajweed`
#: so the mixed look stays reachable by dropping one class.
_PLAIN = "".join(
    f".q-tajweed-plain .q-word .q-{layer}{{fill:var(--q-ink)}}\n"
    for layer in ("rasm", "tashkeel", "waqf")
)

_TAJWEED = "".join(
    f".q-tajweed .q-word .q-tj-{token}{{fill:var(--q-tj-{token})}}\n"
    for token in ruleset.TOKENS
)

#: The edition's boxed waqf note: shown only when the page is in tajweed mode.
#: These carry no colour, so they sit outside the theme block with the other
#: layer toggles - the note's own ink comes from whichever `q-tj-*` rule the
#: font gave it, exactly as it would if it were part of the word.
_NOTES = """.q-note{display:none}
.q-tajweed .q-note{display:inline}
"""

_STATES = """.q-ayah.is-active .q-rasm{fill:var(--q-ink-ayah-active)}
.q-ayah.is-active .q-tashkeel{fill:var(--q-tashkeel-active)}
.q-ayah.is-active .q-ayah-ring{fill:var(--q-ayah-ring-active)}
.q-word.is-active .q-rasm{fill:var(--q-ink-word-active)}
.q-word.is-active .q-tashkeel{fill:var(--q-tashkeel-active)}
.q-word.is-selected .q-rasm{fill:var(--q-ink-select)}
.q-no-frame #q-frame{display:none}
.q-no-chrome #q-chrome{display:none}
.q-no-illumination #q-illumination{display:none}
"""

TEMPLATE = _BASE + _PLAIN + _TAJWEED + _NOTES + _STATES


@lru_cache(maxsize=1)
def parsed() -> Parsed:
    from qsvg import newlook

    return _parse(TEMPLATE + newlook.css())


def structural_css() -> str:
    return parsed().structural


def tokens() -> tuple[str, ...]:
    return parsed().tokens


def theme_block(name: str, colors: dict[str, str]) -> str:
    missing = [t for t in parsed().tokens if t not in colors]
    if missing:
        raise ValueError(f"theme {name!r} does not define: {', '.join(missing)}")
    lines = [f"{BEGIN} {name} */"]
    for binding in parsed().bindings:
        lines.append(f"{binding.selector}{{{binding.property}:{colors[binding.token]}}}")
    lines.append(END)
    return "\n".join(lines)


def schema() -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for binding in parsed().bindings:
        out.setdefault(binding.token, []).append(
            {"selector": binding.selector, "property": binding.property}
        )
    return out


def swap(svg_text: str, block: str) -> str:
    start = svg_text.find(BEGIN)
    end = svg_text.find(END)
    if start == -1 or end == -1:
        raise ValueError("no THEME block found - was this file built by qsvg4?")
    return svg_text[:start] + block + svg_text[end + len(END):]
