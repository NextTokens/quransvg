"""Upstream asset acquisition, with an on-disk cache.

Everything this module fetches is re-fetchable, so `data/` is gitignored. Two
upstreams, both verified to cover all 604 pages:

  * KFGQPC "QCF v2" per-page mushaf fonts.  One font per page, in which every
    glyph is a whole *word* of that page and the line advances are already
    justified by the type designer (measured spread across page 248's fifteen
    lines: 0.6%).  Using them means we reproduce the printed Madani mushaf's
    line breaks and word spacing rather than inventing our own.
  * quran.com API v4, which supplies each word's glyph codepoint (`code_v2`),
    its line number on the page, and its char type.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "cache"
FONT_DIR = ROOT / "data" / "fonts"

PAGE_COUNT = 604

FONT_URL = "https://raw.githubusercontent.com/mustafa0x/qpc-fonts/master/mushaf-v2/QCF2{page:03d}.ttf"
#: The v1 page fonts, used only where the v2 set is short of glyphs.
FONT_V1_URL = "https://raw.githubusercontent.com/mustafa0x/qpc-fonts/master/mushaf/QCF_P{page:03d}.TTF"
PAGE_API_URL = (
    "https://api.quran.com/api/v4/verses/by_page/{page}"
    "?words=true"
    "&word_fields=code_v1,code_v2,line_number,text_uthmani,char_type_name,position,location"
    "&fields=text_uthmani,chapter_id,juz_number,hizb_number,rub_el_hizb_number,sajdah_number"
    "&per_page=50"
)
CHAPTERS_API_URL = "https://api.quran.com/api/v4/chapters?language=ar"

# The mushaf line plan: which of a page's fifteen lines are ayah, surah heading
# or basmalah, and which are set centred. Published by the Quranic Universal
# Library; this mirror serves it without a signed-in session.
LAYOUT_DB_URL = (
    "https://raw.githubusercontent.com/blueheron786/"
    "quranic-universal-library-mushaf-layouts/main/qpc-v2-15-lines.db.zip"
)

_USER_AGENT = "quransvg/1.0 (+offline mushaf SVG generator)"


def _check_page(page: int) -> int:
    if not 1 <= page <= PAGE_COUNT:
        raise ValueError(f"page must be in 1..{PAGE_COUNT}, got {page!r}")
    return page


def _download(url: str, dest: Path, *, retries: int = 3) -> Path:
    """Fetch `url` to `dest`, atomically. Returns `dest` untouched if cached."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
            if not payload:
                raise OSError(f"empty response from {url}")
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(payload)
            tmp.replace(dest)
            return dest
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to download {url}: {last_error}") from last_error


def page_font(page: int) -> Path:
    """Local path to the QCF v2 font for `page`, downloading it if needed.

    The file is checked, not just measured. Five of the 604 arrived with a
    damaged cmap - large enough to look like a font, complete enough for
    fontTools to open, but HarfBuzz maps every character in them to .notdef and
    the page lays out as a row of blanks 100 units wide. A non-empty response
    is not evidence of a good download.
    """
    page = _check_page(page)
    path = FONT_DIR / f"QCF2{page:03d}.ttf"
    for attempt in range(3):
        path = _download(FONT_URL.format(page=page), path)
        if _font_is_usable(path) or _repair_cmap(path):
            return path
        path.unlink(missing_ok=True)        # force a fresh fetch
    raise RuntimeError(f"page {page}: font downloaded but unusable after 3 tries")


def page_font_v1(page: int) -> Path:
    """The v1 page font. A fallback, not a choice - see `build.font_for`."""
    page = _check_page(page)
    return _download(FONT_V1_URL.format(page=page), FONT_DIR / f"QCF_P{page:03d}_v1.TTF")


def _repair_cmap(path: Path) -> bool:
    """Rewrite a font whose cmap has an unreadable subtable.

    Page 245's font carries a truncated Macintosh subtable. Every character it
    is asked for comes back as .notdef - HarfBuzz rejects the table rather than
    falling back to the Windows one beside it, which is perfectly good. Dropping
    the bad subtable and re-serialising recovers the page.
    """
    try:
        from fontTools.ttLib import TTFont

        with TTFont(path) as tt:
            good = []
            for table in tt["cmap"].tables:
                try:
                    table.ensureDecompiled()
                    good.append(table)
                except Exception:
                    pass
            if not good or len(good) == len(tt["cmap"].tables):
                return False
            tt["cmap"].tables = good
            tt.save(path)
        return True
    except Exception:
        return False


def _font_is_usable(path: Path) -> bool:
    """Can this font actually map the characters it is supposed to carry?"""
    try:
        from fontTools.ttLib import TTFont

        with TTFont(path, lazy=True) as tt:
            for table in tt["cmap"].tables:
                table.ensureDecompiled()    # the damaged ones throw here
            return bool(tt.getBestCmap())
    except Exception:
        return False


def page_data(page: int) -> dict:
    """Raw quran.com verse+word payload for `page`, downloading if needed."""
    page = _check_page(page)
    path = _download(PAGE_API_URL.format(page=page), CACHE_DIR / f"page-{page:03d}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def chapters() -> list[dict]:
    """Chapter metadata (Arabic names, verse counts, revelation place)."""
    path = _download(CHAPTERS_API_URL, CACHE_DIR / "chapters.json")
    return json.loads(path.read_text(encoding="utf-8"))["chapters"]


def layout_db() -> Path:
    """Local path to the mushaf line-plan database, downloading if needed."""
    target = CACHE_DIR / "layout" / "qpc-v2-15-lines.db"
    if target.exists() and target.stat().st_size > 0:
        return target
    archive = _download(LAYOUT_DB_URL, CACHE_DIR / "layout" / "qpc-v2-15-lines.db.zip")
    import zipfile

    with zipfile.ZipFile(archive) as bundle:
        names = [n for n in bundle.namelist() if n.endswith(".db")]
        if not names:
            raise RuntimeError(f"no .db inside {archive}: {bundle.namelist()}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with bundle.open(names[0]) as source:
            target.write_bytes(source.read())
    return target
