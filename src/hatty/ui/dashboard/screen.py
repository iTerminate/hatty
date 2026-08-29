# hatty — MIT License. See LICENSE file for details.
"""Dashboard grid view, a full (non-modal) `Screen` pushed via `d`.

Renders a `Grid` of slot widgets for the current dashboard. Use mode: arrows
move a selection cursor (skipping a spanned slot's whole footprint), `enter`
toggles the slot's entity, `e` opens its controls, `E` enters layout Edit
mode. Edit mode: `a` assigns a slot's widget type + entity, `delete` clears
it, `ctrl+arrows` grow/shrink `col_span`/`row_span` (refused on overlap or
out-of-bounds), grab-move (`enter`) moves a slot's whole footprint and
refuses misfitting drops.

Some widgets repurpose these keys for in-widget interaction instead of grid
navigation: `ThermostatSlotWidget` takes `up`/`down` for setpoint, `FanSlotWidget`
for speed, `PanelSlotWidget` for its internal row cursor (+`enter` to toggle
the highlighted row), `MediaPlayerSlotWidget` takes `up`/`down` for volume
*and* `left`/`right` for prev/next track — the only widget that repurposes
horizontal movement too.

**Split panes**: `s` in edit mode splits the pane at the cursor into a nested
mini-grid (`SplitSlotPopup`: `v` left/right, `h` top/bottom, `q` quarters);
the existing widget moves into child (0,0). The cursor becomes a path
(`_cursor_path`) once inside a split; `enter` descends in Use mode, `a` on a
split descends in Edit mode (split isn't itself assignable), `escape` ascends
one level. A grab started outside a split can be carried across split
boundaries without releasing it (only a top-level `escape` releases a grab) —
dropping on an empty cell moves, on an occupied one swaps, across grids via
`DashboardController.move_slot_across`. Splits can't nest and can't land
inside a child grid. `u` in edit mode unsplits when at most one child is
occupied.

**Activity log** (Use mode only — `a` in Edit mode assigns a slot instead):
`a` opens the docked activity log, scoped to the whole dashboard by default;
`v` previews/picks a narrower scope (the dashboard, its devices, the cursor's
slot entity, or that entity's device); `f` maximizes it into a selectable
entry list. `[`/`]` page older/newer while docked; once maximized the grid is
hidden and `←`/`→` take over paging (mirroring the main screen and the
fullscreen graph). This is a third `LogbookController` host (`app.log_ctl`,
`controllers/logbook.py`) and, like the main screen, live — its live WS
subscription and the main screen's are handed off between whichever screen
is on top (`LogbookController.live_session`).
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Grid, VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Footer, Header, Static
from textual_fspicker import FileOpen, FileSave, Filters

from hatty.const import CONFIG_KEY_GRAPH_TYPE
from hatty.controllers.keybindings import bindings_for
from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.confirm_popup import ConfirmPopup
from hatty.ui.dashboard.cursor import GridCursor
from hatty.ui.dashboard.layout import exceeds_bounds, slot_covering, slot_span
from hatty.ui.dashboard.panel_manage_popup import PanelManagePopup
from hatty.ui.dashboard.selection_popup import DashboardSelectionPopup
from hatty.ui.dashboard.slot_popup import DashboardSlotPopup
from hatty.ui.dashboard.split_slot_popup import SplitSlotPopup
from hatty.ui.dashboard.widgets.base import EntitySlotWidget, build_slot_content
from hatty.ui.dashboard.widgets.fan import FanSlotWidget
from hatty.ui.dashboard.widgets.media_player import MediaPlayerSlotWidget
from hatty.ui.dashboard.widgets.panel import PanelSlotWidget
from hatty.ui.dashboard.widgets.split import SplitSlotWidget
from hatty.ui.dashboard.widgets.thermostat import ThermostatSlotWidget
from hatty.ui.list_selection_popup import ListSelectionPopup

if TYPE_CHECKING:
    from datetime import datetime

    from hatty.controllers.logbook import LogSession
    from hatty.main import HACLI
    from hatty.types import Entity


def _dashboard_json_filters() -> Filters:
    """Shared file filter for the export/import file-picker dialogs (issue #256)."""
    return Filters(
        ("Dashboard JSON", lambda p: p.suffix.lower() == ".json"),
        ("All files", lambda _p: True),
    )


class DashboardSlotWidget(Container):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    DEFAULT_CSS = """
    DashboardSlotWidget {
        height: 100%;
    }
    DashboardSlotWidget.-on {
        background: $success 12%;
    }
    DashboardSlotWidget.-selected {
        border: round $accent;
    }
    /* Container style while the cursor is descended into this split's mini-grid;
       the highlighted child cell carries the actual selection. */
    DashboardSlotWidget.-descended {
        border: round $accent 50%;
    }
    DashboardSlotWidget.-idle-featured {
        border: none;
    }
    /* In edit mode the slot borders switch to a dashed secondary accent so the
       mode is obvious at a glance; the picked-up (grabbed) cell stands out more. */
    DashboardScreen.-edit DashboardSlotWidget {
        border: dashed $secondary;
    }
    DashboardScreen.-edit DashboardSlotWidget.-selected {
        border: dashed $accent;
    }
    DashboardScreen.-edit DashboardSlotWidget.-grabbed {
        border: heavy $warning;
        background: $warning 20%;
    }
    """

    def __init__(self, slot: dict | None, row: int, col: int, nested: bool = False):
        super().__init__()
        self.slot = slot
        self.row = row
        self.col = col
        # Cells inside a SplitSlotWidget's mini-grid use child-relative coords, so
        # the screen's top-level cursor queries must skip them.
        self.nested = nested
        self.row_span, self.col_span = slot_span(slot) if slot else (1, 1)

    def covers(self, row: int, col: int) -> bool:
        return self.row <= row < self.row + self.row_span and self.col <= col < self.col + self.col_span

    def compose(self) -> ComposeResult:
        yield build_slot_content(self.slot)

    def on_mount(self) -> None:
        self._sync_on_state()

    def _sync_on_state(self, entity: "Entity | None" = None) -> None:
        children = list(self.children)
        if not children or not isinstance(children[0], EntitySlotWidget):
            return
        child = children[0]
        if not child.entity_id:
            return
        if entity is None:
            entity = self.app.find_entity(child.entity_id)
        state = entity.get("state", "") if entity else ""
        self.set_class(state in ("on", "playing", "paused"), "-on")


def row_sizing(avail: int, rows: int, min_height: int, row_height: int | None) -> tuple[str, str]:
    """Decide the grid's `grid_rows`/`height` styles. An explicit `row_height`
    always wins (fixed row height, grid grows to fit and the container scrolls
    past the viewport). Otherwise: fill the viewport when it fits at
    `min_height` or above, else pin rows to `min_height` and let the container
    scroll — today's adaptive fill-or-scroll behavior."""
    if row_height:
        return str(row_height), "auto"
    if avail and avail // rows < min_height:
        return str(min_height), "auto"
    return "1fr", "100%"


def populate_grid(grid: Grid, rows: int, cols: int, slots: list[dict], is_selected, is_grabbed, nested=False) -> None:
    """Row-major grid population shared by the top-level dashboard and a split
    slot's nested mini-grid. Covered cells are skipped so the grid's flow
    placement lands each (possibly spanned) widget in its intended cell; the
    two predicates take the freshly built DashboardSlotWidget."""
    grid.styles.grid_size_columns = cols
    grid.styles.grid_size_rows = rows
    grid.remove_children()
    for row in range(rows):
        for col in range(cols):
            slot = slot_covering(slots, row, col)
            if slot is not None and (slot["row"], slot["col"]) != (row, col):
                continue  # covered by a spanned slot mounted at its anchor
            widget = DashboardSlotWidget(slot, row, col, nested=nested)
            if widget.row_span > 1:
                widget.styles.row_span = widget.row_span
            if widget.col_span > 1:
                widget.styles.column_span = widget.col_span
            widget.set_class(is_selected(widget), "-selected")
            widget.set_class(is_grabbed(widget), "-grabbed")
            grid.mount(widget)


class DashboardScreen(Screen):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect
    parent: "HACLI"  # this screen's parent is always the app

    # Actions that only make sense while operating widgets (Use mode) vs. arranging
    # the layout (Edit mode). check_action() gates the rest by self.edit_mode.
    USE_ONLY_ACTIONS = frozenset({"toggle_slot", "enter_edit", "rename_slot_entity", "expand_slot"})
    EDIT_ONLY_ACTIONS = frozenset(
        {"grab_move", "edit_slot", "clear_slot", "resize_slot", "split_slot", "unsplit_slot", "fill_split"}
    )

    # LogHost identity (LogbookController) — see controllers/logbook.py; the
    # log_window/log_title_suffix hooks live below with the rest of the log actions.
    LOG_PANEL_ID: str = "dashboard_log_panel"
    LOG_SUPPORTS_LIVE: bool = True

    @property
    def _LOG_HINT(self) -> str:
        d = self.app.keys_ctl.display
        return (
            f"{d('log.scope')} scope · {d('log.maximize')} maximize · "
            f"{d('dashboard.log_older')}/{d('dashboard.log_newer')} older/newer · {d('log.toggle')} close"
        )

    @property
    def _LOG_HINT_MAXIMIZED(self) -> str:
        d = self.app.keys_ctl.display
        return (
            f"↑/↓ select · {d('log.maximize')} exit · "
            f"{d('dashboard.log_older')}/{d('dashboard.log_newer')} older/newer · {d('log.toggle')} close"
        )

    IDLE_TIMEOUT: float = 5.0

    # Minimum height a grid cell gets before the container scrolls instead of
    # squishing cells below readability.
    CELL_MIN_HEIGHT: int = 8

    BINDINGS = bindings_for("dashboard")

    # Groups the help page under the same Use/Edit split as the bindings above
    # (#7); unlike GraphPreviewScreen it still switches active/static rows normally.
    HELP_SECTIONS = (
        ("Use mode", USE_ONLY_ACTIONS),
        ("Edit mode", EDIT_ONLY_ACTIONS),
        (
            "Both modes",
            frozenset(
                {
                    "move_cursor",
                    "show_list_popup",
                    "manage_dashboards",
                    "show_device_tree",
                    "cycle_graph_type",
                    "graph_fullscreen",
                    "show_help",
                    "go_back",
                }
            ),
        ),
        (
            "Activity log",
            frozenset(
                {"toggle_activity_log", "show_log_scope", "maximize_log", "log_older", "log_newer"}
            ),
        ),
    )

    DEFAULT_CSS = """
    DashboardScreen #dashboard_mode_banner {
        height: 1;
        padding: 0 2;
        text-align: center;
        background: $panel;
        color: $text-muted;
    }
    DashboardScreen #dashboard_mode_banner.-mode-edit {
        background: $warning 20%;
        color: $warning;
        text-style: bold;
    }
    DashboardScreen #dashboard_mode_banner.-mode-grab {
        background: $error 20%;
        color: $error;
        text-style: bold;
    }
    DashboardScreen #dashboard_mode_banner.-mode-widget {
        background: $success 20%;
        color: $success;
        text-style: bold;
    }
    DashboardScreen #dashboard_scroll {
        height: 1fr;
    }
    DashboardScreen #dashboard_grid {
        grid-gutter: 1 2;
        padding: 1 2;
    }
    """

    edit_mode: reactive[bool] = reactive(False)

    def __init__(self):
        super().__init__()
        # Grid navigation lives on a pure GridCursor; _cursor_path/cursor_row/
        # cursor_col delegate to it so the rest of the screen reads/assigns unchanged.
        self._cursor = GridCursor()
        self._grabbed: tuple[int, int] | None = None
        # Anchor of the split the grab started in (None = top level); a grab can
        # only be dropped within the grid it was picked up in.
        self._grabbed_parent: tuple[int, int] | None = None
        self._widget_active = False
        self._idle_mode = False
        self._idle_timer: Timer | None = None
        self._log_cursor_timer: Timer | None = None

    @property
    def _cursor_path(self) -> list[tuple[int, int]]:
        return self._cursor.path

    @_cursor_path.setter
    def _cursor_path(self, value: list[tuple[int, int]]) -> None:
        self._cursor.path = value

    @property
    def cursor_row(self) -> int:
        return self._cursor.row

    @cursor_row.setter
    def cursor_row(self, value: int) -> None:
        self._cursor.row = value

    @property
    def cursor_col(self) -> int:
        return self._cursor.col

    @cursor_col.setter
    def cursor_col(self, value: int) -> None:
        self._cursor.col = value

    def _top_cell(self) -> tuple[int, int]:
        return self._cursor.top_cell()

    def _reset_cursor(self) -> None:
        self._cursor.reset()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="dashboard_mode_banner")
        # Not focusable: arrow keys must fall through to the screen's grid
        # navigation; scrolling is driven by scroll_visible() on cursor moves.
        with VerticalScroll(id="dashboard_scroll") as scroll:
            scroll.can_focus = False
            yield Grid(id="dashboard_grid")
        yield ActivityLogPanel(id="dashboard_log_panel")
        yield Footer()

    def on_mount(self) -> None:
        self.edit_mode = False
        self._grabbed = None
        self._widget_active = False
        self.render_dashboard()
        self._update_mode_banner()
        self._reset_idle_timer()

    def on_unmount(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.stop()
            self._idle_timer = None
        if self._log_cursor_timer is not None:
            self._log_cursor_timer.stop()
            self._log_cursor_timer = None
        # A session is only ever removed by close() — without this a dismissed
        # screen's live session could linger and, via id() reuse, alias a later host.
        self.app.log_ctl.close(self)

    def on_screen_resume(self, event) -> None:
        # Re-point the singleton WS logbook subscription at this screen's log (if
        # any) now that it's on top again, e.g. popping back from GraphPreviewScreen.
        if self.app.log_ctl.is_open(self):
            self.app.spawn(self.app.log_ctl.resync_subscription())

    def on_screen_suspend(self, event) -> None:
        # Mirror of on_screen_resume: hand the subscription to whatever live
        # session remains now that this screen is no longer on top.
        if self.app.log_ctl.is_open(self):
            self.app.spawn(self.app.log_ctl.resync_subscription())

    def watch_edit_mode(self, edit_mode: bool) -> None:
        self.set_class(edit_mode, "-edit")
        if edit_mode and self.app.log_ctl.is_open(self):
            # The log is a Use-mode affordance; closing it on entering Edit mode
            # also keeps the double-bound a/f keys unambiguous.
            self._close_log()
        self.refresh_bindings()
        # _update_mode_banner queries a widget, so guard against the initial pre-mount call.
        if self.is_mounted:
            self._update_mode_banner()

    def on_key(self, event) -> None:
        self._reset_idle_timer()
        # In edit mode, `r` on a panel opens the manage-entities popup (add/reorder/
        # remove in one place) instead of renaming the slot's single entity.
        if event.key == "r" and self.edit_mode:
            widget = self._content_widget_at_cursor()
            if isinstance(widget, PanelSlotWidget):
                self._open_panel_manage(widget)
                event.stop()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "toggle_activity_log":
            return not self.edit_mode
        if action in ("show_log_scope", "maximize_log", "log_older"):
            return not self.edit_mode and self.app.log_ctl.is_open(self)
        if action == "log_newer":
            return not self.edit_mode and self.app.log_ctl.is_open(self) and self.app.log_ctl.paged_back(self)
        if action in self.USE_ONLY_ACTIONS:
            return not self.edit_mode
        if action in self.EDIT_ONLY_ACTIONS:
            return self.edit_mode
        return True

    def action_show_help(self) -> None:
        self.app.action_show_help()

    def _update_mode_banner(self) -> None:
        banner = self.query_one("#dashboard_mode_banner", Static)
        for cls in ("-mode-edit", "-mode-grab", "-mode-widget"):
            banner.remove_class(cls)
        # Esc is the only key here that tracks the live keymap (nav.back); every
        # other key is a fixed, non-rebindable dashboard-local binding.
        back = self.app.keys_ctl.display("nav.back")
        if self._widget_active:
            banner.add_class("-mode-widget")
            banner.update(f"WIDGET · interacting — ↑↓: adjust  {back}: exit")
        elif not self.edit_mode:
            banner.update("USE · operate widgets — Enter: use  e: edit")
        elif self._grabbed is not None:
            banner.add_class("-mode-grab")
            banner.update("EDIT · moving widget — arrows to a cell, Enter to drop")
        else:
            banner.add_class("-mode-edit")
            banner.update(
                "EDIT · arrange — a: assign (enters a split)  Del: clear  Enter: move"
                f"  Ctrl+arrows: resize  s/u: split/unsplit  f: fill  r: manage panel  {back}: done"
            )

    def _reset_idle_timer(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.stop()
            self._idle_timer = None
        if self._idle_mode:
            self._exit_idle_mode()
        self._idle_timer = self.set_timer(self.IDLE_TIMEOUT, self._enter_idle_mode)

    def _enter_idle_mode(self) -> None:
        if self.app.screen is not self:
            return
        if self.edit_mode or self._widget_active or self._grabbed is not None:
            return
        self._idle_mode = True
        self.query_one(Footer).display = False
        self.query_one("#dashboard_mode_banner").display = False
        for widget in self._top_slot_widgets():
            if widget.covers(*self._top_cell()):
                widget.remove_class("-selected")
                widget.add_class("-idle-featured")

    def _exit_idle_mode(self) -> None:
        self._idle_mode = False
        self.query_one(Footer).display = True
        self.query_one("#dashboard_mode_banner").display = True
        for widget in self._top_slot_widgets():
            widget.remove_class("-idle-featured")
            if widget.covers(*self._top_cell()):
                widget.add_class("-selected")
        self._update_mode_banner()

    def _current_dashboard(self) -> dict:
        return self.parent.dashboards[self.parent.current_dashboard_name]

    def _top_slot_widgets(self) -> list[DashboardSlotWidget]:
        """Top-level grid cells only — a split slot's nested cells use
        child-relative coords and must not answer top-level cursor queries."""
        return [w for w in self.query(DashboardSlotWidget) if not w.nested]

    def render_dashboard(self) -> None:
        if self._idle_mode:
            self._exit_idle_mode()
        dashboard = self._current_dashboard()
        rows = dashboard["rows"]
        cols = dashboard["cols"]
        slots = dashboard["slots"]

        self._widget_active = False
        self._validate_cursor_path(rows, cols, slots)

        grid = self.query_one("#dashboard_grid", Grid)
        populate_grid(
            grid,
            rows,
            cols,
            slots,
            is_selected=lambda w: len(self._cursor_path) == 1 and w.covers(*self._top_cell()),
            is_grabbed=lambda w: self._grabbed == (w.row, w.col),
        )
        self._apply_cursor_highlight()
        self._apply_row_sizing()
        self._update_header()

    def _update_header(self) -> None:
        self.sub_title = f"Dashboard: {self.parent.current_dashboard_name}"

    def _validate_cursor_path(self, rows: int, cols: int, slots: list[dict]) -> None:
        self._cursor.validate(rows, cols, slots)

    def _split_widget_at(self, top_cell: tuple[int, int]) -> SplitSlotWidget | None:
        for widget in self._top_slot_widgets():
            if widget.covers(*top_cell):
                children = list(widget.children)
                content = children[0] if children else None
                return content if isinstance(content, SplitSlotWidget) else None
        return None

    def _apply_cursor_highlight(self) -> None:
        """Reflect the cursor path in the DOM: at depth 1 the top-level cell is
        selected; at depth 2 the split container gets a muted -descended style
        and the nested child cell carries the selection."""
        descended = len(self._cursor_path) > 1
        for widget in self._top_slot_widgets():
            on_cursor = widget.covers(*self._top_cell())
            widget.set_class(on_cursor and not descended, "-selected")
            widget.set_class(on_cursor and descended, "-descended")
        for split in self.query(SplitSlotWidget):
            owner = split.parent
            if (
                descended
                and isinstance(owner, DashboardSlotWidget)
                and not owner.nested
                and owner.covers(*self._top_cell())
            ):
                split.select_child(self._cursor_path[1])
            else:
                split.select_child(None)

    def _apply_row_sizing(self) -> None:
        """Fill the viewport when the grid fits; otherwise pin each row to a
        minimum height so the container scrolls instead of squishing cells.
        A dashboard's optional `row_height` overrides this entirely, forcing
        every row to that height (and thus scrolling whenever it doesn't fit)."""
        dashboard = self._current_dashboard()
        rows = dashboard["rows"]
        grid = self.query_one("#dashboard_grid", Grid)
        avail = self.query_one("#dashboard_scroll", VerticalScroll).content_size.height
        if not avail:
            # First render runs before layout settles; fall back to the screen
            # height minus the header/banner/footer chrome (on_resize re-runs later).
            avail = max(0, self.size.height - 3)
        grid_rows, height = row_sizing(avail, rows, self.CELL_MIN_HEIGHT, dashboard.get("row_height"))
        grid.styles.grid_rows = grid_rows
        grid.styles.height = height

    def on_resize(self, event) -> None:
        # Re-evaluate fill-vs-scroll on terminal resize without rebuilding the
        # grid (which would drop the user out of widget/reorder mode).
        if self.is_mounted:
            self._apply_row_sizing()

    def _enter_widget(self) -> None:
        self._widget_active = True
        for widget in self._top_slot_widgets():
            if widget.covers(*self._top_cell()):
                widget.add_class("-active")
        self._update_mode_banner()

    def _exit_widget(self) -> None:
        self._widget_active = False
        for widget in self._top_slot_widgets():
            widget.remove_class("-active")
        self._update_mode_banner()

    def _active_grid_ctx(self) -> tuple[int, int, list[dict]]:
        return self._cursor.active_grid_ctx(self._current_dashboard())

    def _move_selection(self, d_row: int, d_col: int) -> None:
        if self._widget_active:
            self._exit_widget()
        rows, cols, slots = self._cursor.active_grid_ctx(self._current_dashboard())
        # The step-past-footprint clamp lives on the cursor; it returns False when
        # the edge blocks the move, else settles the position — highlight/scroll here.
        if not self._cursor.move(d_row, d_col, rows, cols, slots):
            return
        self._apply_cursor_highlight()
        for widget in self._top_slot_widgets():
            if widget.covers(*self._top_cell()):
                widget.scroll_visible(animate=False)  # keep the cursor on-screen when scrolled
        self._schedule_log_follow()

    def _slot_at_cursor(self) -> dict | None:
        return self._cursor.slot_at(self._current_dashboard())

    def _content_widget_at_cursor(self) -> Widget | None:
        for widget in self._top_slot_widgets():
            if widget.covers(*self._top_cell()):
                children = list(widget.children)
                content = children[0] if children else None
                if len(self._cursor_path) > 1 and isinstance(content, SplitSlotWidget):
                    return content.child_widget_at(*self._cursor_path[1])
                return content
        return None

    def _descend_into_split(self) -> None:
        self._cursor.descend()
        self._apply_cursor_highlight()
        self._schedule_log_follow()

    def _ascend_from_split(self) -> None:
        self._cursor.ascend()
        self._apply_cursor_highlight()
        self._schedule_log_follow()

    def _split_anchor(self) -> tuple[int, int] | None:
        """Anchor of the split slot covering the cursor's top cell, if any."""
        return self._cursor.split_anchor(self._current_dashboard()["slots"])

    def _sync_split_selection(self, split: SplitSlotWidget) -> None:
        """Seed a freshly mounting SplitSlotWidget with the cursor's child cell —
        a full render rebuilds splits after _apply_cursor_highlight already ran."""
        owner = split.parent
        if (
            len(self._cursor_path) > 1
            and isinstance(owner, DashboardSlotWidget)
            and not owner.nested
            and owner.covers(*self._top_cell())
        ):
            split._selected = self._cursor_path[1]
        else:
            split._selected = None

    def action_move_cursor(self, d_row: int, d_col: int) -> None:
        # A maximized log hides the grid and gives the entry list focus (up/down);
        # left/right fall through here to page the log instead.
        if self._log_maximized():
            if d_col:
                self.app.log_ctl.page(self, d_col)
            return
        # Widget interaction (setpoint, panel cursor, …) only happens after entering
        # the widget with Enter/s; otherwise arrows navigate the grid. Edit mode always navigates.
        if self._widget_active and d_col == 0 and d_row != 0:
            widget = self._content_widget_at_cursor()
            if isinstance(widget, ThermostatSlotWidget):
                widget.adjust_setpoint(-d_row)
                return
            if isinstance(widget, FanSlotWidget):
                widget.adjust_speed(-d_row)
                return
            if isinstance(widget, PanelSlotWidget):
                widget.move_cursor(d_row)
                return
            if isinstance(widget, MediaPlayerSlotWidget):
                widget.adjust_volume(-d_row)
                return
        # An active media_player widget repurposes left/right for track skip instead.
        if self._widget_active and d_row == 0 and d_col != 0:
            widget = self._content_widget_at_cursor()
            if isinstance(widget, MediaPlayerSlotWidget):
                if d_col < 0:
                    widget.previous_track()
                else:
                    widget.next_track()
                return
        self._move_selection(d_row, d_col)

    def action_enter_edit(self) -> None:
        self.edit_mode = True

    def _in_split(self) -> bool:
        return self._cursor.in_split()

    def action_edit_slot(self) -> None:
        slot = self._slot_at_cursor()
        # `a` on a split pane descends into its mini-grid instead of opening the
        # popup — "split" isn't an assignable widget type; assignment targets a
        # child cell. `a` again on a child opens the popup for it (issue #89).
        if not self._in_split() and slot is not None and slot.get("widget_type") == "split":
            self._descend_into_split()
            return
        if self._grabbed is not None:
            return  # while moving a widget (issue #220), `a` only descends into a split
        parent = self._split_anchor() if self._in_split() else None
        if parent is not None:
            anchor_row, anchor_col = self._cursor_path[1]
        else:
            anchor_row, anchor_col = (slot["row"], slot["col"]) if slot else (self.cursor_row, self.cursor_col)

        def callback(result: dict | None) -> None:
            if result is None:
                return
            extra = {k: result[k] for k in ("gauge_min", "gauge_max", "show_last_changed") if k in result}
            # Reassigning a slot keeps its footprint (child cells never span).
            if slot and parent is None:
                for key in ("row_span", "col_span"):
                    if key in slot:
                        extra[key] = slot[key]
            self.app.dash_ctl.set_slot(
                self.parent.current_dashboard_name,
                anchor_row,
                anchor_col,
                result["widget_type"],
                result["entity_id"],
                result.get("entity_ids"),
                extra=extra,
                parent=parent,
            )
            self.render_dashboard()

        self.app.push_screen(DashboardSlotPopup(slot), callback)

    def action_clear_slot(self) -> None:
        if self._in_split():
            self.app.dash_ctl.clear_slot(
                self.parent.current_dashboard_name, *self._cursor_path[1], parent=self._split_anchor()
            )
            self.render_dashboard()
            return
        slot = self._slot_at_cursor()
        row, col = (slot["row"], slot["col"]) if slot else (self.cursor_row, self.cursor_col)
        self.app.dash_ctl.clear_slot(self.parent.current_dashboard_name, row, col)
        self.render_dashboard()

    def action_resize_slot(self, d_row: int, d_col: int) -> None:
        if self._in_split():
            self.app.notify("Child cells inside a split can't span.", severity="warning")
            return
        slot = self._slot_at_cursor()
        if slot is None:
            return
        row_span, col_span = slot_span(slot)
        new_spans = (max(1, row_span + d_row), max(1, col_span + d_col))
        if new_spans == (row_span, col_span):
            return
        if not self.app.dash_ctl.resize_slot(self.parent.current_dashboard_name, slot["row"], slot["col"], *new_spans):
            self.app.notify("No room to grow this widget there.", severity="warning")
            return
        self.render_dashboard()

    def action_split_slot(self) -> None:
        if self._in_split():
            self.app.notify("Splits can't nest further (one level max).", severity="warning")
            return
        slot = self._slot_at_cursor()
        if slot is not None and slot.get("widget_type") == "split":
            self.app.notify("Splits can't nest further (one level max).", severity="warning")
            return
        row, col = (slot["row"], slot["col"]) if slot else (self.cursor_row, self.cursor_col)

        def _split(direction: str | None) -> None:
            if not direction:
                return
            if self.app.dash_ctl.split_slot(self.parent.current_dashboard_name, row, col, direction):
                self.render_dashboard()

        self.app.push_screen(SplitSlotPopup(), _split)

    def action_unsplit_slot(self) -> None:
        slot = slot_covering(self._current_dashboard()["slots"], *self._top_cell())
        if slot is None or slot.get("widget_type") != "split":
            self.app.notify("Not a split pane.", severity="warning")
            return
        if not self.app.dash_ctl.unsplit_slot(self.parent.current_dashboard_name, slot["row"], slot["col"]):
            self.app.notify("Clear the split down to at most one widget before unsplitting.", severity="warning")
            return
        self._cursor_path = self._cursor_path[:1]
        self.render_dashboard()

    def action_fill_split(self) -> None:
        # Quick-fill (#218) always targets the top-level pane under the cursor — a
        # child cell can't itself become a split (one level max).
        row, col = self._top_cell()

        def callback(result: dict | None) -> None:
            if not result or not result.get("entity_ids"):
                return
            if self.app.dash_ctl.fill_split(
                self.parent.current_dashboard_name, row, col, result["widget_type"], result["entity_ids"]
            ):
                self._cursor_path = self._cursor_path[:1]  # drop any prior descent
                self.render_dashboard()

        self.app.push_screen(DashboardSlotPopup(None, fill_mode=True), callback)

    def action_grab_move(self) -> None:
        # Two-step move: Enter grabs the cell at the cursor, Enter on a destination
        # swaps contents (Enter on the grabbed cell cancels). Works across grids too
        # (#220) — a widget can be carried into/out of a split via a/escape while
        # grabbed; a split itself can never land in a child grid (refused by the controller).
        grab_parent = self._split_anchor() if self._in_split() else None
        cursor_cell = self._cursor_path[-1]
        if self._grabbed is None:
            slot = self._slot_at_cursor()
            if slot is None:
                return
            self._grabbed = (slot["row"], slot["col"])
            self._grabbed_parent = grab_parent
            self._apply_grabbed_class()
            self._update_mode_banner()
            return

        same_grid = grab_parent == self._grabbed_parent
        target = self._slot_at_cursor()
        cell = (target["row"], target["col"]) if target else cursor_cell
        if same_grid and cell == self._grabbed:
            self._release_grab()
            return

        r1, c1 = self._grabbed
        name = self.parent.current_dashboard_name
        if same_grid:
            ok = self.app.dash_ctl.swap_slots(name, r1, c1, *cell, parent=grab_parent)
        else:
            ok = self.app.dash_ctl.move_slot_across(name, r1, c1, self._grabbed_parent, cell[0], cell[1], grab_parent)
        if not ok:
            self.app.notify("The widget doesn't fit there.", severity="warning")
            return
        self._grabbed = None
        self._grabbed_parent = None
        self.render_dashboard()
        self._update_mode_banner()

    def _apply_grabbed_class(self) -> None:
        top_grab = self._grabbed if self._grabbed_parent is None else None
        for widget in self._top_slot_widgets():
            widget.set_class(top_grab == (widget.row, widget.col), "-grabbed")
        for split in self.query(SplitSlotWidget):
            owner = split.parent
            owner_slot = owner.slot if isinstance(owner, DashboardSlotWidget) else None
            anchor = (owner_slot["row"], owner_slot["col"]) if owner_slot else None
            in_this_split = self._grabbed_parent is not None and anchor == self._grabbed_parent
            for child in split.query(DashboardSlotWidget):
                child.set_class(in_this_split and self._grabbed == (child.row, child.col), "-grabbed")

    def _release_grab(self) -> None:
        self._grabbed = None
        self._grabbed_parent = None
        self._apply_grabbed_class()
        self._update_mode_banner()

    def action_toggle_slot(self) -> None:
        widget = self._content_widget_at_cursor()

        if self._widget_active:
            # In active mode: panel toggles its selected row; a fan toggles its own
            # power (up/down having adjusted speed); thermostat has no toggle.
            if isinstance(widget, PanelSlotWidget):
                widget.toggle_selected()
            elif isinstance(widget, (FanSlotWidget, MediaPlayerSlotWidget)):
                slot = self._slot_at_cursor()
                if slot and slot.get("entity_id"):
                    self.parent.toggle_entity(slot["entity_id"])
            return

        # Enter on a split container descends into its mini-grid; escape ascends.
        if isinstance(widget, SplitSlotWidget):
            self._descend_into_split()
            return

        # Thermostat, fan, panel and media_player enter an interactive mode instead
        # of toggling directly.
        if isinstance(widget, (ThermostatSlotWidget, FanSlotWidget, PanelSlotWidget, MediaPlayerSlotWidget)):
            self._enter_widget()
            return

        slot = self._slot_at_cursor()
        if slot and slot.get("entity_id"):
            self.parent.toggle_entity(slot["entity_id"])

    def action_expand_slot(self) -> None:
        # Open the entity's full control UI (light screen / control popup / graph),
        # reusing the same routing as the entity table's expand key.
        entity_id = self._entity_at_cursor()
        if entity_id:
            self.parent.open_entity_controls(entity_id)

    def action_rename_slot_entity(self) -> None:
        slot = self._slot_at_cursor()
        if not slot or not slot.get("entity_id"):
            return
        self.parent.open_rename_for_entity(slot["entity_id"])

    def refresh_entity(self, entity_id: str, entity: "Entity | None", pending: str | None = None) -> None:
        for widget in self.query(EntitySlotWidget):
            if widget.entity_id == entity_id:
                widget.update_entity(entity, pending)
                widget.set_class(self.parent.notify_ctl.is_alerted(entity_id), "-alerted")
                if isinstance(widget.parent, DashboardSlotWidget):
                    widget.parent._sync_on_state(entity)
        for widget in self.query(PanelSlotWidget):
            if entity_id in widget.entity_ids:
                widget.update_entity_state(entity_id, entity, pending)

    def action_cycle_graph_type(self) -> None:
        from hatty.ui.dashboard.widgets.graph import GraphSlotWidget

        widget = self._content_widget_at_cursor()
        if isinstance(widget, GraphSlotWidget):
            widget.cycle_plot_type()
            self.app.app_config[CONFIG_KEY_GRAPH_TYPE] = widget.current_graph_type()
            self.app.persist()

    def action_graph_fullscreen(self) -> None:
        from hatty.ui.graph.preview_screen import GraphPreviewScreen

        entity_id = self._entity_at_cursor()
        if not entity_id:
            return
        entity = self.app.find_entity(entity_id)
        if not entity or not self.app.graph_ctl.is_graphable(entity):
            self.app.notify("No graph available for this entity type.", severity="warning")
            return
        self.app.push_screen(
            GraphPreviewScreen(
                entity_id,
                initial_graph_type=self.app.app_config.get(CONFIG_KEY_GRAPH_TYPE),
            )
        )

    def _entity_at_cursor(self) -> str | None:
        """The entity the slot under the cursor acts on: a panel uses its
        highlighted row; every other widget uses its own entity_id. Shared by the
        fullscreen graph (G) and the expand-controls (o) actions. Returns None
        when there is no entity."""
        widget = self._content_widget_at_cursor()
        if isinstance(widget, PanelSlotWidget):
            if not widget.entity_ids:
                return None
            index = max(0, min(len(widget.entity_ids) - 1, widget.cursor_index))
            return widget.entity_ids[index]
        slot = self._slot_at_cursor()
        return slot.get("entity_id") if slot else None

    def action_show_list_popup(self) -> None:
        # Jump straight back to the last-shown (or default) list; only fall back to
        # the full picker when there is no list to return to.
        target = self.app.list_ctl.jump_target()
        if target:
            self.dismiss()
            self.app.list_ctl.select_or_create(target)
            return

        def callback(result) -> None:
            if result is not None:
                self.dismiss()
            if isinstance(result, dict):
                self.app.list_ctl.handle_popup_action(result)
            elif isinstance(result, str):
                self.app.list_ctl.select_or_create(result)

        self.app.push_screen(ListSelectionPopup(), callback)

    def action_manage_dashboards(self) -> None:
        def callback(result: dict | None) -> None:
            if not result:
                return
            action = result["action"]
            if action == "select":
                self.app.dash_ctl.switch(result["name"])
                self._reset_cursor()
                self.render_dashboard()
            elif action == "create":
                self.app.dash_ctl.create(result["name"], result["rows"], result["cols"], result.get("row_height"))
                self._reset_cursor()
                self.render_dashboard()
            elif action == "rename":
                self.app.dash_ctl.rename(result["old_name"], result["new_name"])
                self.render_dashboard()
            elif action == "set_default":
                self.app.dash_ctl.set_default(result["name"])
                self._reset_cursor()
                self.render_dashboard()
            elif action == "resize":
                self.app.dash_ctl.resize(result["name"], result["rows"], result["cols"])
                self.render_dashboard()
            elif action == "edit":
                old_name = result["old_name"]
                new_name = result["new_name"]
                rows, cols = result["rows"], result["cols"]
                row_height = result.get("row_height")
                dashboard = self.parent.dashboards.get(old_name, {})
                dropped = [s for s in dashboard.get("slots", []) if exceeds_bounds(s, rows, cols)]

                def _apply_edit(confirmed, _old=old_name, _new=new_name, _r=rows, _c=cols, _h=row_height):
                    if not confirmed:
                        return
                    if _new != _old:
                        self.app.dash_ctl.rename(_old, _new)
                    self.app.dash_ctl.resize(_new, _r, _c)
                    self.app.dash_ctl.set_row_height(_new, _h)
                    self.render_dashboard()

                if dropped:
                    self.app.push_screen(
                        ConfirmPopup(f"Resize will remove {len(dropped)} slot(s). Continue?"),
                        _apply_edit,
                    )
                else:
                    _apply_edit(True)
            elif action == "delete":
                name = result["name"]

                def _do_delete(confirmed, _name=name):
                    if not confirmed:
                        return
                    self.app.dash_ctl.delete(_name)
                    self._reset_cursor()
                    self.render_dashboard()

                self.app.push_screen(ConfirmPopup(f"Delete dashboard '{name}'?"), _do_delete)
            elif action == "export":
                self._export_dashboard(result["name"])
            elif action == "import":
                self._import_dashboard()

        self.app.push_screen(DashboardSelectionPopup(), callback)

    def _export_dashboard(self, name: str) -> None:
        slug = name.strip().lower().replace(" ", "-") or "dashboard"

        def _do_export(path: Path | None) -> None:
            if path is None:
                return
            payload = self.app.dash_ctl.to_export_payload(name)
            try:
                path.expanduser().write_text(json.dumps(payload, indent=2))
            except OSError as exc:
                self.app.notify(f"Could not write '{path}': {exc}", title="Export Failed", severity="error")
                return
            self.app.notify(f"Exported '{name}' to {path}.", title="Dashboard Exported")

        self.app.push_screen(
            FileSave(
                location=str(Path.home()),
                title="Export dashboard",
                save_button="Export",
                cancel_button="Cancel",
                default_file=f"{slug}.dashboard.json",
                filters=_dashboard_json_filters(),
            ),
            _do_export,
        )

    def _import_dashboard(self) -> None:
        def _do_import(path: Path | None) -> None:
            if path is None:
                return
            try:
                payload = json.loads(path.expanduser().read_text())
            except (OSError, ValueError) as exc:
                self.app.notify(f"Could not read '{path}': {exc}", title="Import Failed", severity="error")
                return
            try:
                final = self.app.dash_ctl.import_from_payload(payload)
            except ValueError as exc:
                self.app.notify(str(exc), title="Import Failed", severity="error")
                return
            self.app.dash_ctl.switch(final)
            self._reset_cursor()
            self.render_dashboard()
            self.app.notify(f"Imported dashboard '{final}' from {path}.", title="Dashboard Imported")

        self.app.push_screen(
            FileOpen(
                location=str(Path.home()),
                title="Import dashboard",
                open_button="Import",
                cancel_button="Cancel",
                filters=_dashboard_json_filters(),
            ),
            _do_import,
        )

    def action_show_device_tree(self) -> None:
        self.app.action_show_device_tree()

    # ── Activity log (a third LogbookController host — controllers/logbook.py) ──

    def log_window(self, session: "LogSession") -> "tuple[float, datetime | None]":
        return self.app.log_hours, session.end

    def log_title_suffix(self, session: "LogSession") -> str:
        return self.app.log_ctl.range_suffix(session)

    def _log_maximized(self) -> bool:
        return self.query_one("#dashboard_log_panel", ActivityLogPanel).has_class("-maximized")

    def action_toggle_activity_log(self) -> None:
        if self.app.log_ctl.is_open(self):
            self._close_log()
            return

        name = self.app.current_dashboard_name
        entity_ids = self.app.dash_ctl.dashboard_entity_ids(name) if name else []
        if not entity_ids:
            self.app.notify("No entities on this dashboard to log.", severity="warning")
            return

        log_ctl = self.app.log_ctl
        options = [
            log_ctl.base_option("dashboard", name, entity_ids, with_devices=False),
            log_ctl.base_option("dashboard_devices", name, entity_ids, with_devices=True),
            log_ctl.cursor_option("cursor", self._entity_at_cursor, with_device=False),
            log_ctl.cursor_option("cursor_device", self._entity_at_cursor, with_device=True),
        ]
        log_ctl.open(self, options=options, option_id="dashboard", hint=self._LOG_HINT)

    def _close_log(self) -> None:
        panel = self.query_one("#dashboard_log_panel", ActivityLogPanel)
        if panel.has_class("-maximized"):
            panel.set_maximized(False)
            # The grid isn't focusable the way the main table is — explicitly blur.
            self.set_focus(None)
        self.app.log_ctl.close(self)

    def action_show_log_scope(self) -> None:
        """`v` — preview and pick the open log's scope. A no-op while the log
        is closed (gated by check_action)."""
        from hatty.ui.log_scope_popup import LogScopePopup

        session = self.app.log_ctl.session_for(self)
        if session is None:
            return
        entity_names, device_names = self.app.log_ctl.display_names()
        resolved = self.app.log_ctl.resolved_options(self)

        def callback(result: str | None) -> None:
            self.app.log_ctl.handle_scope_popup_result(self, result)

        self.app.push_screen(LogScopePopup(resolved, session.option_id, entity_names, device_names), callback)

    def action_maximize_log(self) -> None:
        panel = self.query_one("#dashboard_log_panel", ActivityLogPanel)
        maximizing = not panel.has_class("-maximized")
        panel.set_hint(self._LOG_HINT_MAXIMIZED if maximizing else self._LOG_HINT)
        panel.set_maximized(maximizing)
        if not maximizing:
            self.set_focus(None)

    def action_log_older(self) -> None:
        self.app.log_ctl.page(self, -1)

    def action_log_newer(self) -> None:
        self.app.log_ctl.page(self, 1)

    _LOG_CURSOR_DEBOUNCE = 0.3  # coalesces held arrow-key repeats before a cursor-scoped log refetches

    def _schedule_log_follow(self) -> None:
        if not self.app.log_ctl.is_open(self):
            return
        if self._log_cursor_timer is not None:
            self._log_cursor_timer.stop()
        self._log_cursor_timer = self.set_timer(
            self._LOG_CURSOR_DEBOUNCE, lambda: self.app.log_ctl.follow_cursor(self)
        )

    def action_go_back(self) -> None:
        # Esc backs out one level: un-maximize log, exit widget, drop grab, ascend
        # out of a split, leave Edit mode, close log, then dismiss. A grabbed widget
        # ascends out of a split first, carrying the grab along (#220).
        if self._log_maximized():
            self.action_maximize_log()
            return
        if self._grabbed is not None:
            if len(self._cursor_path) > 1:
                self._ascend_from_split()
                return
            self._release_grab()
            return
        if self._widget_active:
            self._exit_widget()
            return
        if len(self._cursor_path) > 1:
            self._ascend_from_split()
            return
        if self.edit_mode:
            self.edit_mode = False
            return
        if self.app.log_ctl.is_open(self):
            self._close_log()
            return

        def _do_leave(confirmed: bool | None) -> None:
            if confirmed:
                self.dismiss()

        self.app.push_screen(ConfirmPopup("Leave dashboard?"), _do_leave)

    def _open_panel_manage(self, widget: PanelSlotWidget) -> None:
        parent = self._split_anchor() if self._in_split() else None
        slot = self._slot_at_cursor()
        row, col = (slot["row"], slot["col"]) if slot else self._cursor_path[-1]

        def _done(entity_ids: list[str] | None) -> None:
            if entity_ids is None:
                return  # dismissed untouched
            self.app.dash_ctl.update_panel_entity_ids(
                self.parent.current_dashboard_name, row, col, entity_ids, parent=parent
            )
            self.render_dashboard()

        self.app.push_screen(PanelManagePopup(widget.entity_ids), _done)
