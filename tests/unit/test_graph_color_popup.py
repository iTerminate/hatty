# hatty — MIT License. See LICENSE file for details.
"""Unit tests for the graph color picker's swatch rendering (issue #66).

The picker used to preview each plotext color with hand-picked Rich color names,
which drifted from what plotext actually draws (plotext resolves named colors to
ANSI 0-15 through the terminal palette — its "orange" is ANSI 3 / yellow). These
tests pin the swatch to plotext's own color_codes so it can never disagree again.
"""

from plotext._utility import color_codes
from textual.content import Content

from hatty.ui.graph.color_popup import _ANSI_MARKUP, ALL_PLOT_COLORS, swatch_markup


def test_every_offered_color_is_a_real_plotext_color():
    # Guards against the picker offering a color plotext would reject or the
    # explicit list drifting from plotext's palette.
    for color in ALL_PLOT_COLORS:
        assert color in color_codes, f"{color!r} is not a plotext named color"


def test_swatch_uses_the_plotext_ansi_code():
    # These three are the classic mismatches the old Rich table got wrong:
    # plotext "orange" is ANSI 3 (yellow), and gray/gray+ are easy to swap.
    assert swatch_markup("orange") == "[ansi_yellow]██████[/]"
    assert swatch_markup("gray") == "[ansi_bright_black]██████[/]"  # code 8
    assert swatch_markup("gray+") == "[ansi_white]██████[/]"  # code 7


def test_swatch_code_matches_color_codes_for_all_offered_colors():
    for color in ALL_PLOT_COLORS:
        assert swatch_markup(color) == f"[{_ANSI_MARKUP[color_codes[color]]}]██████[/]"


def test_swatch_markup_is_valid_textual_markup():
    # Regression: the swatch is consumed by an OptionList/Label, which parse it
    # as Textual markup (not Rich) — a bad dialect raised MarkupError before.
    for color in ALL_PLOT_COLORS:
        content = Content.from_markup(f"{swatch_markup(color)} {color}")
        assert content.plain == f"██████ {color}"


def test_swatch_falls_back_uncolored_for_unknown_color():
    assert swatch_markup("not-a-real-color") == "██████"


def test_magenta_stays_at_index_four():
    # test_saved_graphs.py drives the picker by numeric highlight index; keep the
    # ordering contract explicit so a reorder can't silently break that test.
    assert ALL_PLOT_COLORS[4] == "magenta"
