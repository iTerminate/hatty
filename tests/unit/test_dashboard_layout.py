# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.layout import exceeds_bounds, fits, footprint, slot_covering, slot_span


def _slot(row, col, row_span=None, col_span=None, **extra):
    slot = {"row": row, "col": col, "widget_type": "sensor", "entity_id": "sensor.x", **extra}
    if row_span:
        slot["row_span"] = row_span
    if col_span:
        slot["col_span"] = col_span
    return slot


def test_slot_span_defaults_to_one():
    assert slot_span(_slot(0, 0)) == (1, 1)
    assert slot_span(_slot(0, 0, row_span=2, col_span=3)) == (2, 3)


def test_footprint_of_unspanned_slot_is_single_cell():
    assert footprint(_slot(1, 2)) == {(1, 2)}


def test_footprint_of_spanned_slot():
    assert footprint(_slot(0, 1, row_span=2, col_span=2)) == {(0, 1), (0, 2), (1, 1), (1, 2)}


def test_slot_covering_finds_slot_via_any_covered_cell():
    slots = [_slot(0, 0, row_span=2, col_span=2), _slot(2, 2)]
    assert slot_covering(slots, 1, 1) is slots[0]
    assert slot_covering(slots, 2, 2) is slots[1]
    assert slot_covering(slots, 0, 2) is None


def test_fits_rejects_out_of_bounds():
    assert not fits([], _slot(2, 2, col_span=2), rows=3, cols=3)
    assert not fits([], _slot(2, 2, row_span=2), rows=3, cols=3)
    assert fits([], _slot(1, 1, row_span=2, col_span=2), rows=3, cols=3)


def test_fits_rejects_overlap_with_other_slots():
    existing = [_slot(0, 2)]
    assert not fits(existing, _slot(0, 0, col_span=3), rows=3, cols=3)
    assert fits(existing, _slot(0, 0, col_span=2), rows=3, cols=3)


def test_fits_ignores_the_slot_at_its_own_anchor():
    stored = _slot(0, 0)
    assert fits([stored], _slot(0, 0, col_span=2), rows=3, cols=3)


def test_exceeds_bounds_accounts_for_spans():
    assert not exceeds_bounds(_slot(1, 1), rows=2, cols=2)
    assert exceeds_bounds(_slot(1, 1, col_span=2), rows=2, cols=2)
    assert exceeds_bounds(_slot(2, 0), rows=2, cols=2)
