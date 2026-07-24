# hatty — MIT License. See LICENSE file for details.
"""Pure footprint/overlap helpers for dashboard slots with row/col spans.

A slot's footprint is rows [row, row+row_span) x cols [col, col+col_span);
the span keys are optional (absent = 1) so legacy slot dicts are untouched.
"""


def slot_span(slot: dict) -> tuple[int, int]:
    return (slot.get("row_span", 1), slot.get("col_span", 1))


def footprint(slot: dict) -> set[tuple[int, int]]:
    row_span, col_span = slot_span(slot)
    return {
        (r, c)
        for r in range(slot["row"], slot["row"] + row_span)
        for c in range(slot["col"], slot["col"] + col_span)
    }


def slot_covering(slots: list[dict], row: int, col: int) -> dict | None:
    """The slot whose footprint contains (row, col), if any."""
    return next((s for s in slots if (row, col) in footprint(s)), None)


def fits(slots: list[dict], candidate: dict, rows: int, cols: int) -> bool:
    """Whether `candidate` stays in bounds and doesn't overlap any *other* slot
    (a stored slot at the candidate's own anchor cell is treated as the candidate
    itself and ignored, so grow/shrink checks work in place)."""
    cells = footprint(candidate)
    if any(r < 0 or c < 0 or r >= rows or c >= cols for r, c in cells):
        return False
    for other in slots:
        if (other["row"], other["col"]) == (candidate["row"], candidate["col"]):
            continue
        if cells & footprint(other):
            return False
    return True


def exceeds_bounds(slot: dict, rows: int, cols: int) -> bool:
    row_span, col_span = slot_span(slot)
    return slot["row"] + row_span > rows or slot["col"] + col_span > cols
