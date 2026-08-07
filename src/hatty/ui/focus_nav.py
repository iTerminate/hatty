# hatty — MIT License. See LICENSE file for details.
"""Shared row-aware focus navigation for modal screens with button rows (issue #36).

The convention (established by `light_screen.py`/`media_player_screen.py`, issues #88/#286):
left/right cycle within a `Horizontal` button row (wrapping) but hand off to a focused
widget's own native handling (a slider, an `Input`, an expanded `Select`'s overlay) when one
of those owns focus instead; up/down are a priority `Binding` that always steps focus one
field at a time, treating a button row as a single stop rather than one button at a time —
`check_action` is how each screen releases `nav_focus` while a widget with its own up/down
cursor (an `OptionList`, a `DataTable`, a `ListView`) is focused.
"""

from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button


def enclosing_row(widget: Widget | None, row_ids: tuple[str, ...]) -> Widget | None:
    """The `row_ids`-tagged `Horizontal` containing `widget`, if any."""
    if widget is None:
        return None
    for node in widget.ancestors_with_self:
        if isinstance(node, Widget) and node.id in row_ids:
            return node
    return None


def focus_within_row(row: Widget, focused: Widget, step: int) -> None:
    """Cycle focus among `row`'s buttons, wrapping at the ends. Skips buttons
    hidden via `.display` — light_screen/media_player_screen's rows never hide
    a composed button, but DashboardSlotPopup's `#btn_entity_first` can be."""
    buttons = [button for button in row.query(Button) if button.display]
    if not buttons:
        return
    index = next((i for i, button in enumerate(buttons) if button is focused), 0)
    buttons[(index + step) % len(buttons)].focus()


def focus_out_of_row(screen: Screen, row: Widget, step: int) -> None:
    """Move focus in `step`'s direction, skipping the whole row as one unit."""
    step_focus = screen.focus_next if step > 0 else screen.focus_previous
    for _ in range(len(screen.focus_chain)):
        landed = step_focus()
        if landed is None or row not in landed.ancestors_with_self:
            return


def nav_focus(screen: Screen, row_ids: tuple[str, ...], direction: int) -> None:
    """The shared `action_nav_focus` body: a focused row is skipped as a whole block;
    anything else just steps one field at a time."""
    row = enclosing_row(screen.focused, row_ids)
    if row is not None:
        focus_out_of_row(screen, row, direction)
    elif direction > 0:
        screen.focus_next()
    else:
        screen.focus_previous()
