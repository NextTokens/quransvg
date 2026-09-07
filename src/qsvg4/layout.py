"""Place a v4 page's words on the fixed baseline grid.

Two partitions of the same ink cross each other here.

*The ink layer* — rasm, tashkeel, waqf — is what an ordinary theme colours, and
it is inferred exactly as the v2 build infers it, by `qsvg.marks`, from the
word's Uthmani spelling.

*The tajweed segment* is not inferred at all: it is the colour layer the font
declares for each part of the glyph.

A contour belongs to one of each, so a word is emitted as one path per
combination that actually occurs in it — usually two or three, at most a
handful. An ordinary theme reads the first partition and ignores the second; a
tajweed theme colours by the second, which outranks it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from qsvg.geometry import Geometry

from . import ink, mushaf, rules
from .glyphs import ColourPageFont

#: Fall back to centring rather than stretching, as the v2 layout does.
CENTRE_THRESHOLD = 0.86

#: The most a gap may be *opened* before a line is centred instead. A line that
#: falls this far short of the measure is not a justified line at all - it is
#: the last line of a surah - and stretching it would leave lakes between words.
MAX_GAP_ADJUST_EM = 0.35

#: We substitute our own ayah rosette for the font's, so the line should
#: reserve the width of the mark that is actually drawn. The font's glyph is
#: 2,509 units wide - 2,164 of ink with a 339-unit bearing on one side and 6 on
#: the other, so its own spacing is already inside the advance - while the
#: rosette we draw is 50 page units across. On a page of short ayahs the
#: difference tells: page 585 sets 40 of them in thirteen lines, and reserving
#: the font's width plus a word space at each side asked for a third of a line
#: more than the page has.
ROSETTE_CLEAR = 0.0            # the mark's own width is all it reserves

#: The least a gap may be closed to. An over-set line tightens its spaces down
#: to this and no further; it never goes negative, which laid words on top of
#: one another, and it is never centred, which hung the line off both edges of
#: the page at once.
MIN_GAP_UNITS = 8.0


@dataclass(frozen=True)
class InkPath:
    """One path of a word: which ink layer, which tajweed rule, what data."""

    layer: str            # q-rasm | q-tashkeel | q-waqf
    rule: str | None      # a tajweed token, or None for ordinary ink
    data: str
    #: Part of the edition's boxed waqf note rather than the word itself.
    #: Hidden unless the page is in tajweed mode - see `ink.annotations`.
    note: bool = False


@dataclass
class PlacedWord:
    location: str
    line: int
    kind: str             # word | end | mark
    text: str
    paths: list[InkPath]
    divine_name: bool
    x: float
    width: float
    baseline: float
    ink_x0: float
    ink_x1: float
    ink_y0: float
    ink_y1: float


@dataclass
class LayoutLine:
    number: int
    baseline: float
    words: list[PlacedWord] = field(default_factory=list)
    justified: bool = True
    ink_top: float | None = None
    ink_bottom: float | None = None


@dataclass
class PageLayout:
    page: int
    geometry: Geometry
    lines: list[LayoutLine]

    @property
    def words(self) -> list[PlacedWord]:
        return [word for line in self.lines for word in line.words]


#: A contour smaller than this share of the word's largest, and standing this
#: far clear of the rest of it, is not part of the word.
SPECK_AREA = 0.005
SPECK_CLEAR_EM = 1.0


def _ink_box(boxes, em):
    """The word's ink, ignoring any speck the font leaves away from the word.

    Some v4 glyphs carry a stray fragment thousands of units from the letters:
    page 289's بِمَا is drawn with a 27x16 speck 14,000 units to the right of a
    word whose whole advance is 1,648. On screen it is a fifth of a page unit
    and invisible - but left in the box it made that word's tap target nine
    times too wide and laid it across two of its neighbours. The speck is still
    drawn; it is only kept out of the published box.
    """
    if not boxes:
        return None
    largest = max((b[1] - b[0]) * (b[3] - b[2]) for b in boxes)
    core = [b for b in boxes
            if (b[1] - b[0]) * (b[3] - b[2]) >= SPECK_AREA * largest]
    if not core:
        core = boxes
    box = [min(b[0] for b in core), max(b[1] for b in core),
           min(b[2] for b in core), max(b[3] for b in core)]
    clear = SPECK_CLEAR_EM * em
    for b in boxes:
        if b in core:
            continue
        if (box[0] - clear <= b[0] and b[1] <= box[1] + clear
                and box[2] - clear <= b[2] and b[3] <= box[3] + clear):
            box = [min(box[0], b[0]), max(box[1], b[1]),
                   min(box[2], b[2]), max(box[3], b[3])]
    return tuple(box)


def _advance(word, font, geometry) -> float:
    """How much room the line must leave for a word - or for an ayah mark."""
    if word.kind == "end":
        from qsvg.newlook import AYAH_R

        return (2 * AYAH_R + 2 * ROSETTE_CLEAR) / geometry.scale
    return sum(font.word_width(g.char) for g in word.glyphs)


def _partition(widths, count, measure, space):
    """Split a run of words into `count` lines, each as near the measure as it can be.

    An exact partition, not a greedy walk: the mushaf's lines are justified as a
    set and a word pushed off one line has to be paid for on the next. The cost
    is asymmetric - a line over the measure is four times as expensive as one
    the same amount under it - because a short line is what the end of a surah
    looks like, while a long one is words on top of each other.
    """
    n = len(widths)
    if count <= 1 or n <= count:
        return [n] if count <= 1 else [1] * count
    prefix = [0.0]
    for w in widths:
        prefix.append(prefix[-1] + w)

    def cost(i, j):                      # words[i:j] as one line
        if j <= i:
            return float("inf")
        width = prefix[j] - prefix[i] + space * (j - i - 1)
        delta = width - measure
        return delta * delta if delta > 0 else 0.25 * delta * delta

    best = [[float("inf")] * (n + 1) for _ in range(count + 1)]
    cut = [[0] * (n + 1) for _ in range(count + 1)]
    best[0][0] = 0.0
    for k in range(1, count + 1):
        for j in range(k, n - (count - k) + 1):
            for i in range(k - 1, j):
                if best[k - 1][i] == float("inf"):
                    continue
                value = best[k - 1][i] + cost(i, j)
                if value < best[k][j]:
                    best[k][j] = value
                    cut[k][j] = i
    counts = []
    j = n
    for k in range(count, 0, -1):
        i = cut[k][j]
        counts.append(j - i)
        j = i
    return list(reversed(counts))


def _segments(plan: mushaf.PagePlan, grid: int):
    """The page's runs of text lines, and the free baselines in each.

    A surah band and its basmalah are fixed to a baseline, and they cut the page
    into runs that words may not cross: the first ayah of a surah cannot be set
    on a line *above* that surah's own heading. Everything below re-derives
    breaks one run at a time for that reason.
    """
    fixed = sorted(line.number for line in plan.lines if line.kind != mushaf.AYAH)

    def which(number: int) -> int:
        return sum(1 for band in fixed if band < number)

    bands = set(fixed)
    slots: dict[int, list[int]] = defaultdict(list)
    for number in range(1, grid + 1):
        if number not in bands:
            slots[which(number)].append(number)

    words: dict[int, list] = defaultdict(list)
    for line in plan.lines:
        if line.kind == mushaf.AYAH:
            words[which(line.number)].extend(line.words)
    return slots, words


def reflow(plan: mushaf.PagePlan, font: ColourPageFont, geometry: Geometry) -> None:
    """Re-derive a page's line breaks from the font that sets it.

    The word table carries the 1421H line breaks. The v4 fonts are cut for the
    1441H setting, which breaks many pages differently: kept to the table's
    breaks, page 351 has a line 8,052 units over the measure, page 387 one
    7,916 over - a fifth of a line's width, which is words on top of each other.
    Re-derived, the worst line on those pages is about 1,000 over.

    The signature that this is recovery and not over-fitting: a wrong break
    cannot make *all fifteen* lines of a page land within a couple of percent
    of one measure, and that is what the partition finds. Where the table is
    already right the partition returns the table's own breaks unchanged.

    The partition runs once per run of text lines, never once per page. Solved
    over the page as a whole it will move a word past a surah band to even out
    the measures, and a heading is not something a word can pass: page 545 set
    the first two words of Al-Hashr on the last line of Al-Mujadila, above
    Al-Hashr's own band, and page 600 pushed the closing mark of Al-'Adiyat
    down below Al-Qari'ah's. Ten pages read that way.
    """
    from qsvg.build import OPENING_PAGES

    # Pages 1 and 2 are not set to the measure and must not be solved against
    # it. Their lines are short by design and sit inside an oval that is cut to
    # fit them, so packing each one out to the full panel both broke
    # al-Fatihah's line-per-ayah setting and forced the oval - and with it the
    # whole opening panel - to grow until it filled the sheet.
    if plan.page in OPENING_PAGES:
        return

    grid = getattr(plan, "grid", geometry.lines)
    slots, runs = _segments(plan, grid)
    if not runs:
        return
    measure = geometry.panel_w / geometry.scale

    rebuilt = [line for line in plan.lines if line.kind != mushaf.AYAH]
    for key, words in sorted(runs.items()):
        free = slots.get(key, [])
        if not words:
            continue
        if not free:
            # No baseline to re-derive onto - keep the table's own lines for
            # this run rather than losing its words.
            held = {id(word) for word in words}
            rebuilt.extend(line for line in plan.lines
                           if line.kind == mushaf.AYAH and line.words
                           and id(line.words[0]) in held)
            continue
        widths = [_advance(w, font, geometry) for w in words]
        counts = _partition(widths, len(free), measure, font.space)
        made: list[mushaf.Line] = []
        index = 0
        for number, count in zip(free, counts):
            chunk = words[index:index + count]
            index += count
            for word in chunk:
                word.line = number
            made.append(mushaf.Line(number=number, kind=mushaf.AYAH, words=chunk))
        if index < len(words) and made:              # never drop a word
            made[-1].words.extend(words[index:])
            for word in words[index:]:
                word.line = made[-1].number
        rebuilt.extend(line for line in made if line.words)
    plan.lines = sorted(rebuilt, key=lambda line: line.number)


def lay_out_page(
    page: int,
    plan: mushaf.PagePlan,
    font: ColourPageFont,
    geometry: Geometry,
    *,
    simplify: float = 0.0,
    shift=0.0,
    spellings: dict[str, str] | None = None,
) -> PageLayout:
    spellings = spellings if spellings is not None else mushaf.uthmani()
    reflow(plan, font, geometry)
    measure = geometry.panel_w / geometry.scale
    lines: list[LayoutLine] = []

    for entry in plan.lines:
        if entry.kind != mushaf.AYAH or not entry.words:
            continue
        drawn = [w for w in entry.words if any(font.glyph_name(g.char) for g in w.glyphs)]
        if not drawn:
            continue
        # On an opening page `shift` is the callable `opening` hands back: it
        # both moves a line into the panel and re-spaces it at the opening's
        # own pitch. Elsewhere it is nothing at all.
        offset = shift(entry.number) if callable(shift) else shift
        baseline = geometry.baseline(entry.number) + offset
        line = LayoutLine(number=entry.number, baseline=baseline)

        widths = [_advance(w, font, geometry) for w in drawn]
        # A gap beside the ayah mark is already inside the mark's own width.
        nominal = [
            0.0 if (a.kind == "end" or b.kind == "end") else font.space
            for a, b in zip(drawn, drawn[1:])
        ]
        natural = sum(widths) + sum(nominal)
        start = 0.0
        gaps = len(drawn) - 1
        spacing = list(nominal)
        if gaps < 1:
            # A single word - a centred line of one word, or a stray.
            start = max(0.0, (measure - natural) / 2)
            line.justified = False
        elif natural < measure * CENTRE_THRESHOLD or                 (measure - natural) / gaps > MAX_GAP_ADJUST_EM * font.units_per_em:
            # Genuinely short: centre it rather than stretch it.
            start = (measure - natural) / 2
            line.justified = False
        else:
            # Justify. Opening the gaps is unbounded within the test above;
            # closing them stops at MIN_GAP_UNITS, and whatever is left over
            # runs off the left edge rather than off both - a line centred with
            # a negative start hangs half its overflow into the right margin,
            # where the border is.
            share = (measure - natural) / gaps
            spacing = [max(0.0, n + share) if n else max(0.0, share)
                       for n in nominal]
            if natural > measure:
                spacing = [max(MIN_GAP_UNITS if n else 0.0, v)
                           for n, v in zip(nominal, spacing)]
                line.justified = False

        # The word table lists a line in reading order, which runs right to
        # left; the pen runs left to right. So the line is laid out reversed -
        # the first word of the line ends up furthest right, where it belongs.
        # (The v2 build never needs this: HarfBuzz hands back an RTL buffer
        # already in visual order.)
        pen = start
        order = list(zip(drawn, widths))[::-1]
        gaps_rtl = spacing[::-1]
        for index, (word, width) in enumerate(order):
            placed = _place_word(
                word, font, geometry, pen, baseline, spellings,
                simplify=simplify, advance=width,
            )
            if placed is not None:
                line.words.append(placed)
                if placed.ink_y0 is not None:
                    line.ink_top = (placed.ink_y0 if line.ink_top is None
                                    else min(line.ink_top, placed.ink_y0))
                    line.ink_bottom = (placed.ink_y1 if line.ink_bottom is None
                                       else max(line.ink_bottom, placed.ink_y1))
            pen += width + (gaps_rtl[index] if index < len(gaps_rtl) else 0.0)
        line.words.sort(key=lambda w: w.x)
        lines.append(line)

    return PageLayout(page=page, geometry=geometry, lines=lines)


def _place_word(word, font, geometry, pen, baseline, spellings, *, simplify, advance):
    """One word: its figures split by ink layer and by tajweed segment."""
    groups = []          # (contours, palette, translate, stated_waqf)
    boxes = []           # every contour's box in page coordinates
    counter = 0
    offset = 0.0
    # A word drawn as more than one glyph lists them in reading order too, so
    # they are placed reversed for the same reason the line is. HarfBuzz cannot
    # help here: these are PUA codepoints with no script property, so it guesses
    # left-to-right and reorders nothing.
    for glyph in reversed(word.glyphs):
        name = font.glyph_name(glyph.char)
        if name is None:
            continue
        stated_waqf = glyph.discriminator == mushaf.D_WAQF
        for placed in font.shape_word(glyph.char):
            translate = (
                geometry.panel_x + (pen + offset + placed.x) * geometry.scale,
                baseline,
            )
            for layer in font.layers(placed.glyph_name):
                if layer.palette in rules.ORNAMENT:
                    continue
                shifted = []
                for contour in font.contours(layer.glyph_name):
                    # Shifted by the offset *within the word* only. `ink`
                    # compares a word's shapes against each other, so the line
                    # pen cancels out of every test it makes - but it does not
                    # cancel out of the ray cast in `_encloses`, which checks a
                    # moved box against an unmoved outline. Adding the pen put
                    # every box thousands of units from its own outline and
                    # killed the counter test outright.
                    shifted.append(contour.shifted(offset + placed.x, counter))
                    counter += 1
                    x0, y0, x1, y1 = contour.bounds
                    boxes.append((translate[0] + x0 * geometry.scale,
                                  translate[0] + x1 * geometry.scale,
                                  translate[1] - y1 * geometry.scale,
                                  translate[1] - y0 * geometry.scale))
                if shifted:
                    groups.append((shifted, layer.palette, translate, stated_waqf))
            offset += placed.advance
    if not groups:
        return None

    figures = ink.build_figures(groups)
    # The boxed waqf note is not part of the word: it is kept out of the mark
    # census (which counts the spelling's own vowels and would be thrown by an
    # extra tanween), out of the published box (it is hidden by default, and a
    # tap target should describe what is drawn) and into its own paths.
    noted = ink.annotations(figures)
    aside = {c.index for f in figures if id(f) in noted for c in f.contours}
    ink_box = _ink_box([b for i, b in enumerate(boxes) if i not in aside] or boxes,
                       geometry.em)
    if ink_box is None:
        return None

    body = [f for f in figures if id(f) not in noted]
    text = spellings.get(word.location, "")
    if word.kind == "word" and text:
        rasm, tashkeel, waqf = ink.classify(body, ink.census(text))
    else:
        rasm, tashkeel, waqf = body, [], []
    layer_of: dict[int, str] = {}
    for name, group in (("q-rasm", rasm), ("q-tashkeel", tashkeel), ("q-waqf", waqf)):
        for figure in group:
            layer_of[id(figure)] = name

    # One path per (ink layer, tajweed rule). A figure is never split across
    # paths: its outer contour and its holes travel together, so the fill rule
    # still sees the hole and punches it.
    buckets: dict[tuple[str, str | None, bool], list] = defaultdict(list)
    for figure in figures:
        key = (layer_of.get(id(figure), "q-rasm"),
               rules.rule_for(figure.palette),
               id(figure) in noted)
        buckets[key].append(figure)

    paths: list[InkPath] = []
    for (layer, rule, note), group in buckets.items():
        by_translate: dict[tuple, list] = defaultdict(list)
        for figure in group:
            by_translate[figure.translate].extend(figure.contours)
        data = "".join(
            font.encode_contours(cs, scale=geometry.scale, translate=t,
                                 simplify=simplify)
            for t, cs in by_translate.items()
        )
        if data:
            paths.append(InkPath(layer=layer, rule=rule, data=data, note=note))
    paths.sort(key=lambda p: (p.note, p.layer, p.rule or ""))

    # The rosette we draw is centred on the word's box, so for an ayah mark
    # that box has to describe the ornament and not the advance. The font's
    # rosette ink sits off-centre inside its advance - x0 339, x1 2503 of 2509 -
    # so centring on the advance put our star nearly 4 page units to one side
    # and crowded the last word of the ayah.
    left = geometry.panel_x + pen * geometry.scale
    width = advance * geometry.scale
    if word.kind == "end":
        left, width = ink_box[0], ink_box[1] - ink_box[0]

    return PlacedWord(
        location=word.location,
        line=word.line,
        kind=word.kind,
        text=text,
        paths=paths,
        divine_name=word.divine_name,
        x=left,
        width=width,
        baseline=baseline,
        ink_x0=ink_box[0], ink_x1=ink_box[1], ink_y0=ink_box[2], ink_y1=ink_box[3],
    )
