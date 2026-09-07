"""What each palette index of the v4 colour font means.

The font states the colours but not their names, so the names were *derived*
rather than assumed: for every word where the font uses exactly one non-base
palette index and an independent rule source (quran.com's tajweed markup)
reports exactly one rule, the two were tallied against each other over a
sample of pages. Four indices came back unanimous — 1 and 15 hamzat wasl, 4
madd 2/4/6, 5 madd 2, 8 qalqalah, 9 madd 4/5 — and the rest resolved to a
single family: 6 is the nasalisation group (ghunnah, ikhfa, idgham with
ghunnah), 7 the merging group, 2 the letters that are written but not read.

That is the Dar al-Ma'rifah key the printed tajweed masahif use, arrived at
from the data rather than from the convention, which is the check worth having.

Indices 10-12 colour the end-of-ayah rosette, which the font also draws. We
draw our own, from the same artwork as the rest of the page, so they never
reach the stylesheet.
"""

from __future__ import annotations

#: palette index -> the token a theme colours it with. An index absent from
#: this map is ordinary ink and carries no tajweed class at all.
RULES: dict[int, str] = {
    1: "hamzat-wasl",     # the alif of a joining hamza: written, not sounded
    15: "hamzat-wasl",
    2: "silent",          # a letter written but not read
    3: "madd-6",          # madd lazim: six counts
    4: "madd-246",        # madd 'arid / lin: two, four or six
    5: "madd-2",          # the natural madd: two counts
    9: "madd-45",         # madd wajib muttasil: four or five
    6: "ghunnah",         # nasalisation - ghunnah, ikhfa, idgham with ghunnah
    7: "idgham",          # merging
    8: "qalqalah",        # the echoed stop
}

#: The indices the font uses for its own ayah rosette. We draw the rosette from
#: the page's own artwork, so glyphs carrying these are skipped entirely.
ORNAMENT = frozenset({10, 11, 12})

#: Every token a theme has to define for tajweed, in a stable order.
TOKENS: tuple[str, ...] = (
    "hamzat-wasl",
    "silent",
    "madd-2",
    "madd-246",
    "madd-45",
    "madd-6",
    "ghunnah",
    "idgham",
    "qalqalah",
)


def rule_for(palette_index: int) -> str | None:
    """The tajweed token for a palette index, or None for ordinary ink."""
    return RULES.get(palette_index)
