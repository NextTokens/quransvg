"""The mushaf's own line plan for each of the 604 pages.

The verse API says which line each word falls on, but not what a line *is*. A
page that opens a surah gives two of its fifteen lines to the surah heading and
the basmalah, and several pages set their last line centred rather than
justified. Without that, those lines come out blank or wrongly stretched.

The Quranic Universal Library publishes exactly this as a small SQLite table -
one row per line of the mushaf, 9,046 rows in all - covering line type,
centring, and which surah a heading announces. Its own `info` table identifies
it as "QCF V2 ( 1421H print )", the same edition as the page fonts, so the two
agree by construction.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import sources
from .sources import CACHE_DIR

LAYOUT_DB = CACHE_DIR / "layout" / "qpc-v2-15-lines.db"

AYAH = "ayah"
SURAH_NAME = "surah_name"
BASMALLAH = "basmallah"


@dataclass(frozen=True)
class Line:
    number: int
    kind: str          # ayah | surah_name | basmallah
    centered: bool
    surah: int | None  # set on a surah_name line
    #: How many words the mushaf sets on this line, from the layout table's own
    #: word range. Zero on a heading or basmalah line, which carries none.
    words: int = 0
    first: int = 0     # the table's own word numbering, 1-based over the Qur'an
    last: int = 0


@dataclass(frozen=True)
class PagePlan:
    page: int
    lines: tuple[Line, ...]

    def line(self, number: int) -> Line | None:
        for entry in self.lines:
            if entry.number == number:
                return entry
        return None

    @property
    def openings(self) -> tuple[Line, ...]:
        """Heading and basmalah lines — the ones with no words of their own."""
        return tuple(line for line in self.lines if line.kind != AYAH)


class LayoutUnavailable(RuntimeError):
    """Raised when the mushaf layout database is not present."""


def _require_db() -> Path:
    if LAYOUT_DB.exists():
        return LAYOUT_DB
    try:
        return sources.layout_db()
    except Exception as exc:          # offline, mirror moved, or a bad archive
        raise LayoutUnavailable(
            f"mushaf layout database is not at {LAYOUT_DB} and could not be "
            f"downloaded: {exc}"
        ) from exc


@lru_cache(maxsize=1)
def _all_pages() -> dict[int, PagePlan]:
    path = _require_db()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT page_number, line_number, line_type, is_centered, surah_number, "
            "first_word_id, last_word_id FROM pages ORDER BY page_number, line_number"
        ).fetchall()
    finally:
        connection.close()

    grouped: dict[int, list[Line]] = {}
    for page, number, kind, centered, surah, first, last in rows:
        try:
            count = int(last) - int(first) + 1
        except (TypeError, ValueError):
            count = 0
        grouped.setdefault(page, []).append(
            Line(
                number=number,
                kind=kind,
                centered=bool(centered),
                surah=int(surah) if str(surah).strip() else None,
                words=count,
                first=int(first) if count else 0,
                last=int(last) if count else 0,
            )
        )
    return {page: PagePlan(page, tuple(lines)) for page, lines in grouped.items()}


def plan(page: int) -> PagePlan:
    pages = _all_pages()
    if page not in pages:
        raise KeyError(f"no layout for page {page}")
    return pages[page]


def available() -> bool:
    if LAYOUT_DB.exists():
        return True
    try:
        _require_db()
        return True
    except LayoutUnavailable:
        return False


# --- pagination -------------------------------------------------------------

@lru_cache(maxsize=1)
def _sequence() -> tuple[dict, ...]:
    """Every word of the Qur'an in reading order, ayah marks included.

    Assembled from the cached page payloads, which partition the text between
    them, so concatenating them in page order reproduces the sequence the
    layout table numbers its lines against.
    """
    from . import sources

    out: list[dict] = []
    for page in range(1, sources.PAGE_COUNT + 1):
        for verse in sources.page_data(page)["verses"]:
            for word in verse["words"]:
                out.append(
                    {
                        "location": word["location"],
                        "code_v1": word.get("code_v1"),
                        "code_v2": word["code_v2"],
                        "text_uthmani": word["text_uthmani"],
                        "char_type_name": word["char_type_name"],
                        "position": word["position"],
                        "line_number": word["line_number"],
                        "chapter_id": verse["chapter_id"],
                        "juz_number": verse["juz_number"],
                    }
                )
    return tuple(out)


@lru_cache(maxsize=1)
def _offsets() -> dict[int, int]:
    """How far the layout table's word numbering runs ahead of the text.

    The table counts three words the verse data does not, and the difference
    appears in three steps - at pages 28, 178 and 255 - so its ids cannot be
    used as indices without correcting for it. The step is measured, not
    assumed: on a page where the table and the data agree on how many words the
    page holds, the difference between the table's first id and the running
    word count *is* the offset. Pages where they disagree carry the offset
    forward from the last page that agreed, which is what makes the disagreeing
    pages - the ones this whole mechanism exists to fix - harmless here.
    """
    from . import sources

    out: dict[int, int] = {}
    running = 0
    offset = 0
    for page in range(1, sources.PAGE_COUNT + 1):
        counted = sum(len(v["words"]) for v in sources.page_data(page)["verses"])
        lines = [line for line in plan(page).lines if line.words]
        if lines:
            tabled = sum(line.words for line in lines)
            if tabled == counted:
                offset = min(l.first for l in lines) - (running + 1)
        out[page] = offset
        running += counted
    return out


def page_words(page: int) -> list[dict]:
    """The words the mushaf prints on this page.

    Taken from the layout table rather than from quran.com's own page
    grouping. The two disagree about where a page ends on 39 pages, and the
    table is the one the fonts follow: sliced its way, every page's words are
    covered by that page's font; sliced quran.com's way, five pages ask for
    glyphs their font does not contain.
    """
    lines = [line for line in plan(page).lines if line.words]
    if not lines:
        return []
    sequence = _sequence()
    offsets = _offsets()
    # The drift can happen *inside* a page - it does on 27, 177 and 254 - so the
    # end of the range is corrected by the offset that applies after this page,
    # not the one that applied at its start. Without that the last line of each
    # of those three pages picks up a word that belongs to the next page.
    start = offsets[page]
    end = offsets.get(page + 1, start)
    return list(
        sequence[min(l.first for l in lines) - start - 1:max(l.last for l in lines) - end]
    )


def page_data(page: int) -> dict:
    """`page_words`, shaped like the payload the rest of the build expects."""
    words = page_words(page)
    verses: list[dict] = []
    for word in words:
        key = ":".join(word["location"].split(":")[:2])
        if not verses or verses[-1]["verse_key"] != key:
            verses.append(
                {
                    "verse_key": key,
                    "chapter_id": word["chapter_id"],
                    "juz_number": word["juz_number"],
                    "words": [],
                }
            )
        verses[-1]["words"].append(word)
    return {"verses": verses}
