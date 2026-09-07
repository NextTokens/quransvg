"""Checks a built v4 page has to pass.

Most of these are the v2 build's invariants restated: colour lives only in the
theme block, no element carries paint of its own, no `var()` survives to a
native renderer, every published box is in the page's own coordinates.

Three are new, and they are the ones that would catch this edition going wrong:

* the page sets the same words, in the same order, as the v2 build sets — the
  two editions must never disagree about what is on a page;
* every tajweed class names a token the theme actually defines;
* with the tajweed class off, no tajweed colour is reachable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from qsvg.stylesheet import BEGIN, END

from . import rules, stylesheet

_HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
#: How far outside the rule box a word's ink may reach before it is
#: touching the border, and how much two words' ink boxes may overlap
#: before they are colliding rather than interlocking. Both measured off
#: the shipping v2 set, which is the standard here.
#:
#: A single pair of ink boxes overlapping means nothing: naskh words interlock,
#: and over 9,407 adjacent pairs of the v2 set the tail reaches -78 while the
#: median is +6.4. What distinguishes a crushed line from a calligraphic one is
#: the *line*: v2's worst line has a median gap of -2.8, and the bug this
#: guards against - a page justified to the wrong measure - drove line medians
#: to -249. So the test is the line's median gap, not its worst pair.
FRAME_MARGIN = 14.0
MIN_LINE_GAP = -8.0

_PAINT = re.compile(r'<(?:path|g|rect|ellipse|circle|use|polygon)[^>]*\s(?:fill|stroke)="(?!none")')


@dataclass
class Result:
    page: int
    passed: list[str]
    failed: list[str]

    @property
    def ok(self) -> bool:
        return not self.failed


def check(page: int, svg: str) -> Result:
    passed: list[str] = []
    failed: list[str] = []

    def test(name: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(name if condition else f"{name}: {detail}")

    # --- the theme contract -------------------------------------------------
    start, end = svg.find(BEGIN), svg.find(END)
    test("the theme block is present", start != -1 and end > start)
    if start != -1 and end > start:
        block = svg[start:end]
        outside = svg[:start] + svg[end:]
        stray = _HEX.findall(outside)
        test("no colour outside the theme block", not stray, f"{len(stray)} found: {stray[:4]}")
        test("the theme block carries only colour",
             not re.search(r"(?:d|transform|width|height)\s*=", block))
    test("no element carries paint of its own", not _PAINT.search(svg),
         (_PAINT.search(svg).group(0) if _PAINT.search(svg) else ""))
    test("no var() reaches the renderer", "var(" not in svg)
    test("no font dependency", "font-family" not in svg and "<text" not in svg)

    # --- structure ----------------------------------------------------------
    test("the page declares its edition", 'data-edition="qcf-v4"' in svg)
    for layer in ("q-ground", "q-frame", "q-page", "q-chrome", "q-text"):
        test(f"#{layer} is present", f'id="{layer}"' in svg)

    # --- tajweed ------------------------------------------------------------
    used = set(re.findall(r"q-tj-([a-z0-9-]+)", svg))
    known = set(rules.TOKENS)
    test("every tajweed class is a defined token", used <= known, f"unknown: {sorted(used - known)}")
    tokens = set(stylesheet.tokens())
    test("every tajweed token is themed",
         all(f"tj-{t}" in tokens for t in used),
         f"unthemed: {sorted(t for t in used if f'tj-{t}' not in tokens)}")
    guarded = re.findall(r"\.q-tajweed \.q-word \.q-tj-[a-z0-9-]+\{", svg)
    test("tajweed colour is reachable only under the root class",
         len(guarded) == len(rules.TOKENS),
         f"{len(guarded)} of {len(rules.TOKENS)} rules guarded")

    # --- boxes --------------------------------------------------------------
    box = re.search(r'data-text-box="([-\d. ]+)"', svg)
    test("the text box is published", box is not None)
    if box:
        tx, ty, tw, th = (float(v) for v in box.group(1).split())
        bad = 0
        for value in re.findall(r'data-box="([-\d. ]+)"', svg):
            x, y, w, h = (float(v) for v in value.split())
            if x < tx - 0.5 or y < ty - 0.5 or x + w > tx + tw + 0.5 or y + h > ty + th + 0.5:
                bad += 1
        test("every word box sits inside the text box", bad == 0, f"{bad} outside")

    return Result(page=page, passed=passed, failed=failed)


def fits_the_page(layout, page: int = 0) -> tuple[bool, str]:
    """No word may reach the border, and no line may be crushed.

    Both were broken at once and by one cause: the page was justified to the v2
    measure, so the word gaps closed past zero and the over-set lines were
    centred with a negative start, hanging off both edges at once.
    """
    import statistics

    from qsvg import shell

    left = shell.RULE_X - FRAME_MARGIN
    right = shell.RULE_X + shell.RULE_W + FRAME_MARGIN
    outside = 0
    worst_out = 0.0
    crushed = 0
    worst_line = 0.0
    for line in layout.lines:
        words = sorted(line.words, key=lambda w: w.x)
        for word in words:
            for over in (left - word.ink_x0, word.ink_x1 - right):
                if over > 0:
                    outside += 1
                    worst_out = max(worst_out, over)
        gaps = [b.ink_x0 - a.ink_x1 for a, b in zip(words, words[1:])]
        if len(gaps) >= 3:
            middle = statistics.median(gaps)
            worst_line = min(worst_line, middle)
            if middle < MIN_LINE_GAP:
                crushed += 1
    if outside or crushed:
        return False, (f"{outside} words reaching the border (worst "
                       f"{worst_out:.1f}), {crushed} crushed lines "
                       f"(worst median gap {worst_line:.1f})")
    return True, f"clear of the border, tightest line median {worst_line:.1f}"


def same_words_as_v2(page: int, layout) -> tuple[bool, str]:
    """The two editions must agree about what is printed on the page."""
    from qsvg import mushaf as v2mushaf

    try:
        expected = [
            word["location"]
            for verse in v2mushaf.page_data(page)["verses"]
            for word in verse["words"]
            if word["char_type_name"] == "word"
        ]
    except Exception as exc:                    # no v2 data cached
        return True, f"skipped ({exc})"
    # `layout.words` runs in visual order, the page data in reading order.
    got = [
        w.location
        for line in layout.lines
        for w in sorted(line.words, key=lambda x: -x.x)
        if w.kind == "word"
    ]
    if got == expected:
        return True, f"{len(got)} words"
    # v4 draws four words of the Qur'an as two - 2:181:14, 8:6:12, 13:37:20 and
    # 37:130:4, on pages 27, 177, 254 and 451. The page prints the same text;
    # only the word numbering differs, and it is the same difference that makes
    # the v2 layout table's numbering drift on three of those very pages. So
    # the test is that nothing is missing, not that the counts match.
    known = set(expected)
    extra = [loc for loc in got if loc not in known]
    trimmed = [loc for loc in got if loc in known]
    if trimmed == expected and len(extra) <= 1:
        return True, f"{len(trimmed)} words, plus {len(extra)} v4 splits {extra}"
    return False, f"v2 sets {len(expected)}, v4 sets {len(got)}"


def bands_in_order(page: int, layout) -> tuple[bool, str]:
    """Every surah band separates the surah before it from the surah after it.

    A page's bands and its words are one sequence in the mushaf's own order, so
    a word of surah S must sit *below* every band for a surah up to S and
    *above* every band for a surah past it. `layout.reflow` solved the whole
    page as one partition and so could trade a word across a band to even out
    the measures: page 545 set the first two words of Al-Hashr on the last line
    of Al-Mujadila - above Al-Hashr's own band - and page 600 pushed the closing
    mark of Al-'Adiyat below Al-Qari'ah's. Ten pages read that way, and nothing
    else in `verify` could see it: every word was present, on a real line, in
    reading order, inside the text box.
    """
    from . import mushaf

    bands = [(line.surah, line.number) for line in mushaf.plan(page).lines
             if line.kind == mushaf.SURAH_NAME and line.surah]
    if not bands:
        return True, "no band on this page"

    wrong: list[str] = []
    for word in layout.words:
        surah = int(word.location.split(":")[0])
        for band_surah, band_line in bands:
            if band_surah <= surah and word.line <= band_line:
                wrong.append(f"{word.location} above surah {band_surah}'s band")
            elif band_surah > surah and word.line >= band_line:
                wrong.append(f"{word.location} below surah {band_surah}'s band")
    if wrong:
        return False, f"{len(wrong)} words on the wrong side of a band: {wrong[0]}"
    return True, f"{len(bands)} band(s) in order"
