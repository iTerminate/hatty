# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.slot_popup import preview_fits


def test_preview_hidden_just_below_threshold():
    assert preview_fits(106) is False


def test_preview_shown_at_threshold():
    assert preview_fits(107) is True


def test_preview_hidden_at_zero_width():
    assert preview_fits(0) is False


def test_preview_shown_comfortably_wide():
    assert preview_fits(200) is True
