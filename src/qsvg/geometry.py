"""The page grid — the part that is identical on all 604 pages.

Every number here is a constant. Nothing in this module may depend on which
page is being rendered: that is what lets the decorative shell and the baseline
grid be provably the same everywhere.

The page is 1000 x 2231, which is a phone's shape, not a printed page's. That
is deliberate and it is forced: a 20:9 screen is 0.448 wide for its height, a
2:3 page is 0.667, and no scale shows the whole of a 2:3 page on a 20:9 screen
without either cropping the border away or wasting a third of the display.
Measured in the app on a 1280 x 2856 device, fitting the old page by width left
936 px dead and filling the height cropped the frame off both sides entirely.

So the page carries the screen's proportions and spends the extra height on its
margins: 1000/2856*1280 = 2231. The *text* keeps the printed mushaf's metrics
exactly - same panel width, same 15-line block, same line pitch, same type
size - and is centred in the taller box. Nothing about the type changes; only
the paper around it grows.
"""

from __future__ import annotations

from dataclasses import dataclass

VIEW_W = 1000.0
#: 1000 / (1280 / 2856), the aspect of the device the app targets. A page that
#: is taller than the screen letterboxes gently; one that is shorter gets its
#: frame cropped, which is the failure this number exists to prevent.
VIEW_H = 2231.0

# --- Ornamental band --------------------------------------------------------
# The border is what the type size is spent on. A line of this mushaf is 16 em
# wide by construction, so the em is the panel width over 16, and every unit
# the frame takes from the panel comes straight off the letters: at 124 units a
# side the text set 60 px on a 1280 px screen, where the app's cropped view of
# the old files set it at 76. The band is therefore pushed out to the page edge
# and made a fine ribbon rather than a broad slab - 25 units a side, all in,
# which buys back the whole difference.
MARGIN_RULE = 3.5        # the gilt hairline out at the page margin
BAND_OUTER = 6.0         # outer edge of the illuminated band
BAND_WIDTH = 13.0        # its depth
RULE_GAP = 3.0           # gap between the heavy rule and the hairline inside it

# --- Text panel -------------------------------------------------------------
# The rule box keeps its printed size and stays wrapped tightly around the
# fifteen lines; it is the *margin* that grew. Stretching the rule box to the
# taller page instead leaves its top edge stranded 380 units above the first
# line, which reads as an empty box rather than as a margin - the page has to
# look like a wide-margined mushaf, not like text lost in a frame.
# The panel stops 38 units in. Measured across every built page, the ink of a
# line-final word reaches 11.4 units past its advance - the tails sweep left -
# and the text shifts 3 more toward the spine, against a border whose inner
# rule is at 20. Anything wider puts letters through the border, which is what
# was happening on page 5: ink at x=16.6, inside the band.
RULE_X = 34.0
RULE_W = 932.0

TEXT_INSET_X = 4.0       # breathing room between the rule and the glyphs
TEXT_INSET_Y = 12.0

PANEL_X = RULE_X + TEXT_INSET_X
PANEL_W = RULE_W - 2 * TEXT_INSET_X

LINES_PER_PAGE = 15

# The printed mushaf sets these fifteen lines at a pitch of 76 units, which is
# tight enough that the ink of one line reaches into the next. On a page 731
# units taller than the printed one, holding that pitch parks the whole block
# in the middle and leaves a dead band above and below it. Opening the pitch
# spends the height where it belongs - between the lines - and pulls the
# running head and the page number in behind it, because the rule box and the
# margins are both measured from this number.
#
# The type size does not change: the words are the same size, further apart.
# 133 units = 2.24 em. The pitch is not a free choice on a screen this shape:
# fifteen lines of 16-em measure on a page 2.231 times as tall as it is wide
# have to sit about 2.2 em apart to reach the margins at all. The printed
# mushaf's 1.62 em would leave a third of the display empty.
LINE_PITCH = 133.0
PANEL_H = LINES_PER_PAGE * LINE_PITCH

# --- which side of the opening a page falls on ------------------------------
# A mushaf is bound right-to-left, and its classic illuminated opening prints
# al-Fatihah facing the start of al-Baqarah with al-Fatihah on the right. That
# makes odd pages recto (right-hand) and even pages verso (left-hand).
#
# Bound pages are not centred on their leaf: the gutter margin is tighter than
# the fore-edge, so the content sits a little toward the spine. Reproducing
# that is what tells a reader which side they are looking at, without anything
# being added to the page. Flip RECTO_IS_ODD if this edition binds the other
# way round - it is the only assumption involved.
RECTO_IS_ODD = True
# Only the text and the chrome move; the frame is flush with the page edge and
# has nowhere to go. On a printed leaf the asymmetry shows as a wider fore-edge
# margin inside a fixed border, which is exactly this.
GUTTER_SHIFT = 3.0       # viewBox units the content moves toward the spine


def page_side(page: int) -> str:
    """'recto' for a right-hand page, 'verso' for a left-hand one."""
    odd = page % 2 == 1
    return "recto" if odd == RECTO_IS_ODD else "verso"


def gutter_offset(page: int) -> float:
    """How far the content shifts, positive to the right.

    A recto's spine is on its left, so its content moves left and its
    fore-edge margin on the right grows. A verso is the mirror of that.
    """
    return -GUTTER_SHIFT if page_side(page) == "recto" else GUTTER_SHIFT

# Calibration: the width, in font units, that a fully justified mushaf line
# occupies. Measured across sampled pages (2, 77, 150, 248, 300, 450, 600) the
# full lines span 39_312..41_114 units, clustering near 40_000. Anchoring the
# scale here keeps every page at one type size; the per-line remainder (well
# under 2%) is absorbed by the word gaps, exactly as a typesetter would.
MEASURE_UNITS = 40_000.0
UNITS_PER_EM = 2500.0

# Ink reaches about 1.28em above and 0.62em below the baseline in these fonts,
# so lines interleave slightly — as they do in the printed mushaf, where the
# baseline grid is rigid and the calligraphy is allowed to breathe across it.
ASCENT_EM = 1.283
DESCENT_EM = 0.621

# How far a line's ink reaches past its advance box. Measured across all 604
# pages: 11.4 units to the left, where the tails of the line-final letters
# sweep out, and 21 to the right on page 146, the widest reach in the mushaf.
# The published text box has to allow for it or it does not contain the text it
# claims to - and a sampled measurement is how you end up one page short.
INK_OVERHANG_EM = 0.36

# The grid's ascent and descent above place the lines; these are how far the
# ink of the widest-reaching glyph actually goes, measured across every built
# page. The published boxes use these - a hit box cut to the grid's numbers
# clipped the top of a letter on page 249 by 5.5 units.
INK_ASCENT_EM = 1.60
INK_DESCENT_EM = 0.82

# The block of ink, top of line one to the last line's descenders. The rule box
# wraps it at the same inset as the printed page and the pair is centred on the
# sheet; the header and footer bands are then whatever is left, which is how
# opening the line pitch tightens them. Everything here needs the type size to
# know how deep the descenders reach, which is why it is resolved last.
EM = UNITS_PER_EM * PANEL_W / MEASURE_UNITS
# The true extent of the ink: first line's ascent to last line's descenders.
# `PANEL_H` counts a fifteenth pitch below the last baseline that no glyph
# occupies, and centring on that pushed the whole block 28 units off centre.
INK_BLOCK_H = (LINES_PER_PAGE - 1) * LINE_PITCH + (ASCENT_EM + DESCENT_EM) * EM
RULE_H = INK_BLOCK_H + 2 * TEXT_INSET_Y
RULE_Y = (VIEW_H - RULE_H) / 2
PANEL_Y = RULE_Y + TEXT_INSET_Y


@dataclass(frozen=True)
class Geometry:
    """Resolved page grid. Constructed once, shared by every page."""

    view_w: float = VIEW_W
    view_h: float = VIEW_H
    panel_x: float = PANEL_X
    panel_y: float = PANEL_Y
    panel_w: float = PANEL_W
    panel_h: float = PANEL_H
    lines: int = LINES_PER_PAGE
    measure_units: float = MEASURE_UNITS
    units_per_em: float = UNITS_PER_EM

    @property
    def scale(self) -> float:
        """Font units -> viewBox units. One value for the whole mushaf."""
        return self.panel_w / self.measure_units

    @property
    def em(self) -> float:
        """Type size in viewBox units."""
        return self.units_per_em * self.scale

    @property
    def line_pitch(self) -> float:
        """Baseline-to-baseline distance."""
        return self.panel_h / self.lines

    def baseline(self, line_number: int) -> float:
        """Baseline y for a 1-based line number.

        Lines sit on a rigid grid: the first baseline is dropped by one ascent
        so the tallest ink on line 1 stays inside the panel, and the rest follow
        at a fixed pitch.
        """
        if not 1 <= line_number <= self.lines:
            raise ValueError(f"line must be in 1..{self.lines}, got {line_number}")
        first = self.panel_y + self.em * ASCENT_EM
        return first + (line_number - 1) * self.line_pitch

    @property
    def baselines(self) -> list[float]:
        return [self.baseline(n) for n in range(1, self.lines + 1)]

    @property
    def opening_top(self) -> float:
        """Where the medallion's ground may begin on an opening page: just
        below the surah band on line one."""
        return self.baseline(1) - self.em * 0.35 + 78.0

    @property
    def ink_block_h(self) -> float:
        """Top of line one's ascent to the last line's descenders."""
        return (self.lines - 1) * self.line_pitch + (ASCENT_EM + DESCENT_EM) * self.em

    @property
    def viewbox(self) -> str:
        return f"0 0 {_n(self.view_w)} {_n(self.view_h)}"


def _n(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:g}"


DEFAULT = Geometry()
