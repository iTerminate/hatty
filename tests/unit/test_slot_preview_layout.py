# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.slot_popup import MAIN_WIDTH, POPUP_CHROME, PREVIEW_GAP, PREVIEW_WIDTH, preview_fits


def test_preview_hidden_just_below_threshold():
    assert preview_fits(106) is False


def test_preview_shown_at_threshold():
    assert preview_fits(107) is True


def test_preview_hidden_at_zero_width():
    assert preview_fits(0) is False


def test_preview_shown_comfortably_wide():
    assert preview_fits(200) is True


def test_preview_fits_threshold_matches_the_widened_dialog_width():
    # _apply_preview_visibility (issue #36) sizes #dashboard_slot_container from these
    # same constants — preview_fits's threshold is exactly that widened width.
    assert MAIN_WIDTH + PREVIEW_GAP + PREVIEW_WIDTH + POPUP_CHROME == 107
