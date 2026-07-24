# hatty — MIT License. See LICENSE file for details.
"""Unit tests for the pure GridCursor dashboard-navigation math (issue #171).

GridCursor holds only the cursor path and the step/clamp/descend arithmetic over
plain dashboard dicts, so these tests need no running screen.
"""

from hatty.ui.dashboard.cursor import GridCursor, find_slot


def _slot(row, col, row_span=None, col_span=None, **extra):
    slot = {"row": row, "col": col, "widget_type": "sensor", "entity_id": "sensor.x", **extra}
    if row_span:
        slot["row_span"] = row_span
    if col_span:
        slot["col_span"] = col_span
    return slot


def _split(row, col, child_rows, child_cols, child_slots):
    return {
        "row": row,
        "col": col,
        "widget_type": "split",
        "entity_id": None,
        "children": {"rows": child_rows, "cols": child_cols, "slots": child_slots},
    }


def _dashboard(rows, cols, slots):
    return {"rows": rows, "cols": cols, "slots": slots}


# ── path tail properties ──────────────────────────────────────────────────────


def test_row_col_read_and_write_the_tail():
    c = GridCursor()
    c.row, c.col = 2, 3
    assert (c.row, c.col) == (2, 3)
    assert c.path == [(2, 3)]


def test_top_cell_reads_the_head_even_when_descended():
    c = GridCursor()
    c.path = [(1, 1), (0, 1)]
    assert c.top_cell() == (1, 1)
    assert (c.row, c.col) == (0, 1)  # tail is the child cell


def test_reset_and_in_split():
    c = GridCursor()
    c.descend()
    assert c.in_split() is True
    assert c.path == [(0, 0), (0, 0)]
    c.reset()
    assert c.in_split() is False
    assert c.path == [(0, 0)]


def test_descend_then_ascend():
    c = GridCursor()
    c.path = [(0, 1)]
    c.descend()
    assert c.path == [(0, 1), (0, 0)]
    c.ascend()
    assert c.path == [(0, 1)]


# ── move: step / clamp / footprint ────────────────────────────────────────────


def test_move_steps_one_cell():
    c = GridCursor()
    slots = [_slot(0, 0), _slot(0, 1)]
    assert c.move(0, 1, rows=1, cols=2, slots=slots) is True
    assert (c.row, c.col) == (0, 1)


def test_move_on_empty_cell_clamped_at_edge_still_settles():
    c = GridCursor()  # at (0,0), an empty cell (no slots)
    # Stepping up from the top row: clamped, no real move, but the cell has no
    # footprint, so it's not the footprint early-out — returns True so the screen
    # still refreshes highlight.
    assert c.move(-1, 0, rows=2, cols=1, slots=[]) is True
    assert (c.row, c.col) == (0, 0)


def test_move_on_slot_clamped_at_edge_refused():
    c = GridCursor()  # at (0,0), sitting on its own single-cell slot
    # Clamped at the top edge while still inside the slot's footprint → the
    # footprint-edge early-out: unchanged, no highlight refresh.
    assert c.move(-1, 0, rows=2, cols=1, slots=[_slot(0, 0)]) is False
    assert (c.row, c.col) == (0, 0)


def test_move_steps_past_a_spanned_footprint():
    c = GridCursor()  # at (0,0), on a 2x2 span
    slots = [_slot(0, 0, row_span=2, col_span=2), _slot(0, 2)]
    assert c.move(0, 1, rows=2, cols=3, slots=slots) is True
    assert (c.row, c.col) == (0, 2)  # skipped the whole 2-wide footprint


def test_move_refused_when_footprint_reaches_the_edge():
    c = GridCursor()
    c.row, c.col = 0, 1  # inside a span that runs to the right edge
    slots = [_slot(0, 1, col_span=2)]
    assert c.move(0, 1, rows=1, cols=3, slots=slots) is False
    assert (c.row, c.col) == (0, 1)  # unchanged; nothing beyond the footprint


# ── validate ──────────────────────────────────────────────────────────────────


def test_validate_clamps_out_of_range_top_cell():
    c = GridCursor()
    c.path = [(9, 9)]
    c.validate(rows=3, cols=3, slots=[])
    assert c.path == [(2, 2)]


def test_validate_drops_descent_when_top_no_longer_a_split():
    c = GridCursor()
    c.path = [(0, 0), (0, 1)]
    c.validate(rows=2, cols=2, slots=[_slot(0, 0)])  # a plain slot, not a split
    assert c.path == [(0, 0)]


def test_validate_clamps_child_cell_within_child_grid():
    c = GridCursor()
    c.path = [(0, 0), (5, 5)]
    split = _split(0, 0, 1, 2, [_slot(0, 0), _slot(0, 1)])
    c.validate(rows=1, cols=1, slots=[split])
    assert c.path == [(0, 0), (0, 1)]  # clamped to the 1x2 child grid


# ── active_grid_ctx ───────────────────────────────────────────────────────────


def test_active_grid_ctx_returns_dashboard_grid_when_not_descended():
    c = GridCursor()
    dash = _dashboard(3, 4, [_slot(0, 0)])
    assert c.active_grid_ctx(dash) == (3, 4, dash["slots"])


def test_active_grid_ctx_returns_child_grid_when_descended_into_split():
    c = GridCursor()
    c.path = [(0, 0), (0, 0)]
    child_slots = [_slot(0, 0), _slot(0, 1)]
    split = _split(0, 0, 1, 2, child_slots)
    dash = _dashboard(2, 2, [split])
    rows, cols, slots = c.active_grid_ctx(dash)
    assert (rows, cols) == (1, 2)
    assert slots == child_slots


def test_active_grid_ctx_prunes_stale_descent():
    c = GridCursor()
    c.path = [(0, 0), (0, 0)]
    dash = _dashboard(2, 2, [_slot(0, 0)])  # top cell holds a plain slot now
    assert c.active_grid_ctx(dash) == (2, 2, dash["slots"])
    assert c.path == [(0, 0)]  # descent dropped


# ── slot_at ───────────────────────────────────────────────────────────────────


def test_slot_at_top_level_returns_covering_slot():
    c = GridCursor()
    c.row, c.col = 1, 1
    span = _slot(0, 0, row_span=2, col_span=2)
    dash = _dashboard(3, 3, [span])
    assert c.slot_at(dash) is span


def test_slot_at_descended_returns_child_slot():
    c = GridCursor()
    c.path = [(0, 0), (0, 1)]
    child = _slot(0, 1)
    split = _split(0, 0, 1, 2, [_slot(0, 0), child])
    dash = _dashboard(2, 2, [split])
    assert c.slot_at(dash) is child


def test_slot_at_descended_returns_none_when_top_not_split():
    c = GridCursor()
    c.path = [(0, 0), (0, 0)]
    dash = _dashboard(2, 2, [_slot(0, 0)])
    assert c.slot_at(dash) is None


# ── split_anchor & find_slot ──────────────────────────────────────────────────


def test_split_anchor_returns_anchor_of_covering_split():
    c = GridCursor()
    c.row, c.col = 0, 1
    split = _split(0, 0, 1, 2, [_slot(0, 0), _slot(0, 1)])
    split["col_span"] = 2
    assert c.split_anchor([split]) == (0, 0)


def test_split_anchor_none_when_not_on_a_split():
    c = GridCursor()
    assert c.split_anchor([_slot(0, 0)]) is None


def test_find_slot_matches_anchor_exactly():
    slots = [_slot(0, 0), _slot(0, 1)]
    assert find_slot(slots, 0, 1) is slots[1]
    assert find_slot(slots, 1, 1) is None
