"""Upstream assets for the v4 colour mushaf.

Everything here is re-fetchable and cached under `data/v4/`, kept apart from
the v2 build's `data/` so the two can never tread on each other.

Two upstreams:

  * The King Fahd Complex's **colour** page fonts, served by quran.com as
    `p{page}.ttf` — 604 of them, one per page. Each carries `COLR` and `CPAL`
    tables: a word glyph is a list of layer glyphs, one per tajweed segment,
    each pointing at a palette entry. The separation is the publisher's.
  * A word table for the same edition: every glyph of the mushaf with its
    surah, ayah, word index, line, and a *discriminator* naming what it is —
    an ordinary word, the lafz al-jalalah, a waqf sign, a surah name, a
    rub'-el-hizb or sajdah mark, an end-of-ayah rosette.

The page furniture also needs Amiri, the QUL surah-name font and the QCF
basmalah font. They are fetched into the shared cache with pinned URLs so a
clean checkout can run the v4 builder without a separate v2 setup step.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V4_DIR = ROOT / "data" / "v4"
FONT_DIR = V4_DIR / "fonts"

PAGE_COUNT = 604

#: The publisher's own colour edition, one font per page.
FONT_URL = "https://quran.com/fonts/quran/hafs/v4/colrv1/ttf/p{page}.ttf"

#: The word table for the same edition. `description.comment` inside it names
#: the font URL above as its source, which is what ties the two together.
WORDS_DB_URL = (
    "https://raw.githubusercontent.com/MohamedAshref371/"
    "Hafs-V4-Tajweed-TTF/main/000.db"
)

# Shared page-furniture fonts. These files are build inputs only and are kept
# out of Git. Git-hosted inputs are pinned to the exact commits used to build
# this corpus; hashes make any replacement or corrupted cache fail loudly.
COMMON_FONTS = {
    "Amiri-Regular.ttf": (
        "https://raw.githubusercontent.com/google/fonts/"
        "5e35378e6bda803962ee6fd257e444a7d459660d/ofl/amiri/Amiri-Regular.ttf",
        "ab391c4147d054c48976e98322ad0eefe1427aa0e0502a12a4c75d80a70cfcd7",
    ),
    "Amiri-Bold.ttf": (
        "https://raw.githubusercontent.com/google/fonts/"
        "5e35378e6bda803962ee6fd257e444a7d459660d/ofl/amiri/Amiri-Bold.ttf",
        "cfccb794268e7d573d857e6d6a67f89cf8a053e8ffd85dfa0c8ec1bb36fc4827",
    ),
    "QUL_SurahName_v1.ttf": (
        "https://static-cdn.tarteel.ai/qul/fonts/surah-names/v1/surah-name-v1.ttf",
        "24928ce6a9be4c534ccdcaca7e68e6b9402b5188a9ad201baa3539cf6ca5c7ca",
    ),
    "QCF_BSML.TTF": (
        "https://raw.githubusercontent.com/quran/quran.com-images/"
        "dbda5689691defc7e3b28314cc2d035ff027795c/res/fonts/QCF_BSML.TTF",
        "6a6f234ee351be146e46e897f4cd47610df0b078a82888e5ca15f313f813698c",
    ),
}

_USER_AGENT = "quransvg/1.0 (+offline mushaf SVG generator)"


def _check_page(page: int) -> int:
    if not 1 <= page <= PAGE_COUNT:
        raise ValueError(f"page must be in 1..{PAGE_COUNT}, got {page!r}")
    return page


def _download(url: str, dest: Path, *, retries: int = 3) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
            if not payload:
                raise OSError(f"empty response from {url}")
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(payload)
            tmp.replace(dest)
            return dest
        except (urllib.error.URLError, OSError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to download {url}: {last}") from last


def _download_checked(url: str, dest: Path, sha256: str) -> Path:
    """Download a pinned build input and verify it before returning it."""
    if dest.exists() and dest.stat().st_size > 0:
        actual = hashlib.sha256(dest.read_bytes()).hexdigest()
        if actual == sha256:
            return dest
        dest.unlink()
    path = _download(url, dest)
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != sha256:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            f"checksum mismatch for {dest.name}: expected {sha256}, got {actual}"
        )
    return path


def common_fonts() -> tuple[Path, ...]:
    """Fetch the small, shared fonts used for page furniture."""
    from qsvg import sources as shared

    return tuple(
        _download_checked(url, shared.FONT_DIR / name, sha256)
        for name, (url, sha256) in COMMON_FONTS.items()
    )


def page_font(page: int) -> Path:
    """The colour page font, downloading it if needed.

    Checked rather than merely fetched: a page font that cannot be opened, or
    that carries no colour table, is not the file we asked for.
    """
    page = _check_page(page)
    path = FONT_DIR / f"p{page:03d}.ttf"
    for _ in range(3):
        path = _download(FONT_URL.format(page=page), path)
        if _font_is_usable(path):
            return path
        path.unlink(missing_ok=True)
    raise RuntimeError(f"page {page}: colour font downloaded but unusable")


def _font_is_usable(path: Path) -> bool:
    try:
        from fontTools.ttLib import TTFont

        with TTFont(path, lazy=True) as tt:
            if "COLR" not in tt or "CPAL" not in tt:
                return False
            for table in tt["cmap"].tables:
                table.ensureDecompiled()
            return bool(tt.getBestCmap())
    except Exception:
        return False


def words_db() -> Path:
    """The v4 word table."""
    return _download(WORDS_DB_URL, V4_DIR / "words.db")


def available() -> bool:
    try:
        return words_db().exists()
    except Exception:
        return False
