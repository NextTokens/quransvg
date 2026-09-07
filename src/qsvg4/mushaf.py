"""The v4 edition's own line plan, read from its word table.

The v2 build has to reconcile three sources — quran.com's page grouping, the
QUL layout table's word ranges, and a measured offset between their numbering.
None of that is needed here: this table states, for every glyph of the mushaf,
its page, its line, the ayah and word it belongs to, and what kind of thing it
is. Line kinds fall straight out of it:

    ayah = -1   the surah heading
    ayah =  0   the basmalah
    ayah >= 1   a line of verses

and `word = 999` is the end-of-ayah rosette, of which there are exactly 6,236.

What the table does *not* give is line breaks this edition can use. Its `line`
column carries the 1421H setting, which the v2 build follows; the v4 fonts are
cut for the 1441H one, and on many pages they break differently. Kept to the
table, page 351 gets a line 8,052 font units over the measure — a fifth of a
line, which is words on top of each other. So the breaks are re-derived from
the font that sets the page: see `layout.reflow`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache

from . import sources

AYAH = "ayah"
SURAH_NAME = "surah_name"
BASMALLAH = "basmallah"

# What the table's `discriminator` column says a glyph is.
D_WORD = 0
D_LAFZ = 1            # the word الله
D_WAQF = 5            # a pause sign, drawn over the word with no advance
D_SURAH_NAME = 7
D_RUB = 8             # rub'-el-hizb
D_SAJDAH_LINE = 9
D_SAJDAH_MARK = 10
D_AYAH_END = 11

#: Word-index slots the table reserves for page furniture rather than text.
#: Read off the data, not assumed: index 0 is always the rub'-el-hizb (199 of
#: them), 998 always the sajdah mark (15) and 999 always the end-of-ayah
#: rosette (6,236). Every other index is a word. The sajdah *line* and the waqf
#: signs are not in this list, because they share the index of the word they
#: are drawn over - taking them out would take 26 words of the text with them.
ROSETTE = 999
SAJDAH_MARK = 998
RUB = 0
FURNITURE = frozenset({RUB, SAJDAH_MARK, ROSETTE})


@dataclass(frozen=True)
class Glyph:
    """One glyph of the page: a PUA character and what it stands for."""

    char: str
    discriminator: int


@dataclass
class Word:
    """A word of the mushaf, which the font may draw as more than one glyph."""

    surah: int
    ayah: int
    index: int
    glyphs: list[Glyph]
    line: int

    @property
    def location(self) -> str:
        return f"{self.surah}:{self.ayah}:{self.index}"

    @property
    def kind(self) -> str:
        """word | end | mark.

        Which rows are furniture is decided by the index, not the
        discriminator: the sajdah *line* and the waqf signs share the index of
        the word they are drawn over, so testing the discriminator took 26
        words of the text out with them.
        """
        if self.index == ROSETTE:
            return "end"
        if self.index in FURNITURE:
            return "mark"
        return "word"

    @property
    def divine_name(self) -> bool:
        return any(g.discriminator == D_LAFZ for g in self.glyphs)


@dataclass
class Line:
    number: int
    kind: str
    words: list[Word] = field(default_factory=list)
    centered: bool = False
    surah: int | None = None          # set on a heading line


@dataclass
class PagePlan:
    page: int
    lines: list[Line]
    #: How many physical lines the page has. Fifteen everywhere but the two
    #: opening pages, which have eight.
    grid: int = 15
    #: Set when the heading move has changed how many text lines this page has,
    #: so its line breaks must be re-derived from the font rather than taken
    #: from the table.
    reflow: bool = False

    @property
    def body(self) -> list[Line]:
        return [line for line in self.lines if line.kind == AYAH]

    @property
    def openings(self) -> tuple[Line, ...]:
        """Heading and basmalah lines - the ones that carry no verse text."""
        return tuple(line for line in self.lines if line.kind != AYAH)

    def line(self, number: int) -> Line | None:
        for entry in self.lines:
            if entry.number == number:
                return entry
        return None


@lru_cache(maxsize=1)
def _rows() -> tuple[tuple, ...]:
    path = sources.words_db()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return tuple(
            connection.execute(
                "SELECT a.page, w.line, a.surah, a.ayah, w.word, "
                "w.discriminator, w.text "
                "FROM words w JOIN ayat a ON w.ayah_id = a.id ORDER BY w.id"
            )
        )
    finally:
        connection.close()


@lru_cache(maxsize=1)
def _pages() -> dict[int, PagePlan]:
    grouped: dict[int, list[tuple]] = {}
    for row in _rows():
        grouped.setdefault(row[0], []).append(row)

    out: dict[int, PagePlan] = {}
    for page, rows in grouped.items():
        lines: dict[int, Line] = {}
        current: Word | None = None
        for _page, number, surah, ayah, index, discriminator, char in rows:
            kind = (
                SURAH_NAME if ayah == -1
                else BASMALLAH if ayah == 0
                else AYAH
            )
            line = lines.get(number)
            if line is None:
                line = lines[number] = Line(number=number, kind=kind)
            # A line that opens a surah carries only the heading; a line that
            # carries any verse text is an ayah line whatever else is on it.
            if kind == AYAH:
                line.kind = AYAH
            if kind == SURAH_NAME:
                line.surah = surah
            if (
                current is None
                or (current.surah, current.ayah, current.index) != (surah, ayah, index)
                or current.line != number
            ):
                current = Word(surah=surah, ayah=ayah, index=index,
                               glyphs=[], line=number)
                line.words.append(current)
            current.glyphs.append(Glyph(char=char, discriminator=discriminator))
        ordered = [lines[n] for n in sorted(lines)]
        for line in ordered:
            line.centered = line.kind != AYAH
        out[page] = PagePlan(page=page, lines=ordered,
                             grid=max(l.number for l in ordered))
    return out


#: Pages whose word table files a surah heading one page too early *for this
#: edition*. The table carries the 1421H line breaks, which the v2 build uses
#: and which put the band on the last line of page N. The v4 fonts are cut for
#: something else: solving the page's own advances against the measure gives
#: 14.9 text lines for page N where the table allows 14, and 13.1 for page N+1
#: where the table allows 14. Seventeen of these eighteen are unanimous to two
#: decimal places; 584 is the one loose case and follows the same shape.
#:
#: So the band and its basmalah move to the head of the following page, and
#: both pages have their line breaks re-derived from the font - see
#: `layout.reflow`. Left alone, page N is fifteen lines of type set on fourteen
#: baselines, which is what crushed the words together on page 76.
HEADING_MOVES = frozenset({
    76, 207, 331, 341, 349, 366, 376, 414,
    417, 445, 452, 498, 506, 525, 548, 555, 557, 584,
})


def plan(page: int) -> PagePlan:
    """A fresh copy of the page's plan, with the heading moves applied.

    `layout.reflow` moves words between lines, so handing out the cached
    object would let one page's layout alter the next caller's plan.
    """
    import copy

    pages = _pages()
    if page not in pages:
        raise KeyError(f"no v4 layout for page {page}")
    entry = copy.deepcopy(pages[page])

    if page in HEADING_MOVES and entry.lines and entry.lines[-1].kind == SURAH_NAME:
        entry.lines.pop()                     # the band goes to the next page
        entry.reflow = True
    if page - 1 in HEADING_MOVES:
        previous = pages[page - 1]
        if previous.lines and previous.lines[-1].kind == SURAH_NAME:
            heading = copy.deepcopy(previous.lines[-1])
            for line in entry.lines:
                line.number += 1
                for word in line.words:      # a word carries its own line number
                    word.line = line.number
            heading.number = 1
            for word in heading.words:
                word.line = 1
            entry.lines.insert(0, heading)
            entry.reflow = True
    return entry


def available() -> bool:
    return sources.available()


@lru_cache(maxsize=1)
def _quarters() -> dict[int, int]:
    """page -> the first rub' (quarter) on it. 240 quarters, eight to a juz."""
    path = sources.words_db()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT page, MIN(quarter) FROM ayat GROUP BY page"
        ).fetchall()
    finally:
        connection.close()
    return {int(page): int(quarter) for page, quarter in rows}


def page_juz(page: int) -> int:
    """Which of the thirty parts this page belongs to."""
    quarter = _quarters().get(page, 1)
    return max(1, min(30, (quarter - 1) // 8 + 1))


@lru_cache(maxsize=1)
def surah_pages() -> dict[int, int]:
    """The page each surah's heading appears on."""
    out: dict[int, int] = {}
    for page, number, surah, ayah, index, discriminator, char in _rows():
        if ayah == -1:
            out.setdefault(surah, page)
    return out


def uthmani() -> dict[str, str]:
    """`surah:ayah:word` -> the Uthmani spelling, from the v2 build's cache.

    The v4 table gives glyphs, not text, and `marks` needs the spelling to know
    how many vowel marks a word carries. Every one of quran.com's 77,429 words
    is present in the v4 table under the same (surah, ayah, word) key, so the
    two join without any reconciliation.
    """
    return _uthmani()


@lru_cache(maxsize=1)
def _uthmani() -> dict[str, str]:
    from qsvg import sources as v2sources

    out: dict[str, str] = {}
    for page in range(1, v2sources.PAGE_COUNT + 1):
        for verse in v2sources.page_data(page)["verses"]:
            for word in verse["words"]:
                if word["char_type_name"] == "word":
                    out[word["location"]] = word["text_uthmani"]
    return out
