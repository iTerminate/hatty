# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.screen import row_sizing


def test_explicit_row_height_always_wins():
    # Fits easily at 1fr, but an explicit row_height still forces fixed rows.
    assert row_sizing(avail=100, rows=3, min_height=8, row_height=12) == ("12", "auto")


def test_no_row_height_fills_viewport_when_it_fits():
    assert row_sizing(avail=30, rows=3, min_height=8, row_height=None) == ("1fr", "100%")


def test_no_row_height_pins_min_height_when_it_does_not_fit():
    assert row_sizing(avail=12, rows=3, min_height=8, row_height=None) == ("8", "auto")


def test_no_avail_falls_back_to_filling():
    # avail=0 (e.g. pre-layout) skips the fit check entirely.
    assert row_sizing(avail=0, rows=3, min_height=8, row_height=None) == ("1fr", "100%")


def test_zero_row_height_is_treated_as_unset():
    assert row_sizing(avail=30, rows=3, min_height=8, row_height=0) == ("1fr", "100%")
