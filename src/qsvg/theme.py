"""Colour themes.

The design rule that makes the project work: a theme may change *colour and
nothing else*.  Geometry, stroke widths, ornament shapes and the baseline grid
are structural constants defined elsewhere, so switching themes can never
disturb the page's identity — which is precisely the guarantee we want across
604 pages.

Every paintable element in a generated page carries a semantic class and no
paint attributes of its own.  A small stylesheet maps those classes to CSS
custom properties, and the theme supplies only the property values.  Restyling
an already-built page is therefore a matter of replacing the few lines between
the THEME:BEGIN and THEME:END markers — no regeneration, no font work.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

THEME_DIR = Path(__file__).resolve().parents[2] / "themes"

#: The theme baked into a page as built. An app swaps the block for another.
DEFAULT = "green-pink"


#: Every colour on a page, and a theme sets all of them.
#:
#: There used to be a fixed half - paper, ink, the vowel marks - on the grounds
#: that a theme recolours the illumination and not the book. A night theme
#: cannot honour that: a dark page needs light ink by definition. So the split
#: is gone and the rule it protected is enforced where it belongs, in `verify`:
#: a theme changes colour and nothing else, whichever colour it changes.
#:
#: Five of these are the adopted artwork's own palette, named for what they
#: paint rather than for the hue they happen to be in one theme - the "green"
#: of the supplied files is a ground, and in the night theme it is navy.
TOKENS: tuple[str, ...] = (
    # the sheet
    "bg",                # the page ground, and the surround beyond it
    "paper",             # the open field inside a panel
    # the ornament: border, surah band and opening decoration all share these
    "orn-ground",        # the band the scrollwork is drawn on
    "orn-flower",        # the flowers and buds
    "orn-scroll",        # the vine and the scrollwork
    "orn-panel",         # panel fills and leaves
    "orn-outline",       # the drawn outline around every motif
    # the text
    "ink",               # the rasm, and the basmalah
    "tashkeel",          # the vowel marks
    "waqf",              # pause and recitation signs
    "lafz",              # the divine name
    # recitation states, expressed as ink: nothing is ever painted behind text
    "ink-ayah-active",
    "ink-word-active",
    "ink-select",
    "tashkeel-active",
    # the end-of-ayah mark
    "ayah-ring",         # the outer star
    "ayah-fill",         # the field the number sits on
    "ayah-digit",
    "ayah-ring-active",
    # the running head, folio and catchword
    "chrome",
    "chrome-muted",
    "catchword",
    # the surah band's own lettering
    "title",
    "title-note",
)

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


@dataclass(frozen=True)
class Theme:
    name: str
    title: str
    description: str
    dark: bool
    colors: dict[str, str]

    def block(self) -> str:
        """The swappable block: every colour on the page as a literal rule."""
        from . import stylesheet

        return stylesheet.theme_block(self.name, self.all_colors)

    def resolve(self, token: str) -> str:
        return self.colors[token]

    @property
    def all_colors(self) -> dict[str, str]:
        """Every colour the page uses."""
        return dict(self.colors)


def load(name: str) -> Theme:
    path = THEME_DIR / f"{name}.json"
    if not path.exists():
        available = ", ".join(sorted(t.stem for t in THEME_DIR.glob("*.json")))
        raise FileNotFoundError(f"unknown theme {name!r}; available: {available}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    colors = raw.get("colors", {})

    missing = [t for t in TOKENS if t not in colors]
    if missing:
        raise ValueError(f"theme {name!r} is missing colours: {', '.join(missing)}")
    unknown = [t for t in colors if t not in TOKENS]
    if unknown:
        raise ValueError(f"theme {name!r} defines unknown colours: {', '.join(unknown)}")
    bad = [f"{t}={colors[t]}" for t in TOKENS if not _HEX.match(colors[t])]
    if bad:
        raise ValueError(f"theme {name!r} has non-hex colours: {', '.join(bad)}")

    return Theme(
        name=name,
        title=raw.get("title", name),
        description=raw.get("description", ""),
        dark=bool(raw.get("dark", False)),
        colors={t: colors[t] for t in TOKENS},
    )


def available() -> list[str]:
    # themes/schema.json describes the theme contract for the app; it is not a
    # theme itself and must not be offered as one
    return sorted(p.stem for p in THEME_DIR.glob("*.json") if p.stem != "schema")


def swap(svg_text: str, theme: Theme) -> str:
    """Replace the theme block in an already-generated SVG.

    This is the whole point of the block convention: retheming a built page
    is a string substitution, not a rebuild - and it is exactly what an app
    does at runtime to switch or customise the theme.
    """
    from . import stylesheet

    return stylesheet.swap(svg_text, theme.block())
