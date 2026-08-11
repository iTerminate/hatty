# hatty — MIT License. See LICENSE file for details.
"""Fullscreen graph screen, opened with `G`.

Mirrors `graph/entity_detail.py`'s numeric-vs-climate split. Takes a list of
`entity_ids` (a comparison graph shows several), a `colors` dict (`tab` picks
the active line, `c` cycles its color, `C` opens the full color picker), and
an optional `saved_graph_name` (adds the `u` update-in-place action alongside
`S` save-as).

`GraphWindow` (`window.py`) tracks the paging/live-anchor state: `None` end
means anchored to "now" with live refresh on incoming state changes; paging
away from live suppresses those refreshes until paging forward reaches the
original anchor again. `left`/`right` page by half a window (50% overlap for
visual continuity); `shift+left`/`shift+right` page by several full windows.
`+`/`-` zoom the visible span via a screen-local override of the global
`graph_hours` (never persisted, but carried into `S`/`u` saves); zooming
always freezes the window and a zoomed window never re-enters live mode when
paged forward — only `home` snaps back to live and clears the zoom.

`enter` toggles cursor/inspect mode: drops a marker at the selected sample and
swaps the stats line for every plotted entity's nearest value at that
timestamp, repurposing `left`/`right`/`shift+left`/`shift+right`/`home`/`end`
as marker moves instead of paging/zooming (unavailable for climate graphs).
Each repurposed key is a second `Binding` on the same key, gated by
`check_action` on `_cursor_mode` — exactly one twin is ever live, so the
Footer and help page always show the binding that matches what the key
currently does (`escape`/`q` similarly split three ways: exit inspect, close
the activity log, or back out of the screen).

`a` toggles a docked activity log for the plotted entities (issue #2),
fetched for the same window the graph is currently showing; paging/zooming
the graph (`left`/`right`/`shift+left`/`shift+right`/`+`/`-`/`home`) refetches
it to match. `v` opens a preview-then-commit scope popup (`LogScopePopup`,
issue #38, replacing the old blind cycle from #21): the plotted entities
alone, or widened to their devices' events too (issue #18, e.g. a zha_event
button press). `f` maximizes the panel to the full screen width and turns it
into a selectable list with an inline untruncated detail region (issue #22,
upgraded by #38 — no separate browse popup anymore); `a` always closes
outright even while maximized, while `escape`/`q` restore the normal width
first and only close on a further press.

`ALLOWED_APP_ACTIONS` is this screen's carve-out from `HACLI.check_action`'s
"pushed screen" lockdown — only the app-level keys that still do something on
top of a fullscreen graph (Dashboard/Device Tree/Saved Graphs/Duration/Quit)
stay live; everything else in `HACLI.BINDINGS` is main-table-only and denied.
`HELP_ALL_MODES` + `HELP_SECTIONS` (read by `HACLI.action_show_help`) make this
screen's help page always show every binding grouped by section — both a
paging key and its inspect-mode twin — rather than only whichever mode is
live when `?` is pressed.
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Label
from textual_plotext import PlotextPlot

from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.entity_table import entity_title, entity_unit, get_display_name
from hatty.ui.graph.binary_history import binary_stats, value_to_state
from hatty.ui.graph.plot_render import (
    DEFAULT_COLOR_PALETTE as _COLOR_PALETTE,
)
from hatty.ui.graph.plot_render import (
    PLOTEXT_MODES as _PLOT_MODES,
)
from hatty.ui.graph.plot_render import (
    numeric_stats_line,
    plot_width,
    render_binary,
    render_climate,
    render_numeric,
)
from hatty.ui.graph.plot_time import secs_since
from hatty.ui.graph.plot_time import ts_to_full as _ts_to_full
from hatty.ui.graph.window import GraphWindow

if TYPE_CHECKING:
    from hatty.main import HACLI
    from hatty.types import Entity


def _nearest_value(data: list[tuple[str, float]], target: datetime) -> float | None:
    if not data:
        return None
    return min(data, key=lambda p: abs((datetime.fromisoformat(p[0]) - target).total_seconds()))[1]


def _color_hint(color: str) -> str:
    """The 'tab: next line · c/C' stats-line hint, prefixed with a color swatch
    that resolves through plotext's terminal palette (see graph_color_popup)."""
    from hatty.ui.graph.color_popup import swatch_markup

    return f"{swatch_markup(color)} [tab: next line · c/C: {color}]"


_FAST_PAGE_MULTIPLIER = 6


class GraphPreviewScreen(Screen):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    DEFAULT_CSS = """
    GraphPreviewScreen {
        background: $surface;
    }
    GraphPreviewScreen #preview_title {
        text-style: bold;
        padding: 0 1;
        background: $panel;
    }
    GraphPreviewScreen #preview_plot {
        height: 1fr;
    }
    GraphPreviewScreen #preview_stats {
        padding: 0 1;
        background: $panel;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("t", "cycle_plot_type", "Graph Type"),
        Binding("left", "scroll_back", "Older"),
        Binding("left", "cursor_prev", "Prev Sample"),
        Binding("right", "scroll_forward", "Newer"),
        Binding("right", "cursor_next", "Next Sample"),
        Binding("shift+left", "scroll_back_fast", f"Older ×{_FAST_PAGE_MULTIPLIER}"),
        Binding("shift+left", "cursor_prev_fast", "Prev Sample ×10%"),
        Binding("shift+right", "scroll_forward_fast", f"Newer ×{_FAST_PAGE_MULTIPLIER}"),
        Binding("shift+right", "cursor_next_fast", "Next Sample ×10%"),
        Binding("plus", "zoom_in", "Zoom In"),
        Binding("minus", "zoom_out", "Zoom Out"),
        Binding("home", "snap_live", "Now"),
        Binding("home", "cursor_home", "Oldest Sample"),
        Binding("end", "cursor_end", "Newest Sample"),
        Binding("enter", "toggle_cursor_mode", "Inspect"),
        Binding("enter", "exit_cursor_mode", "Exit Inspect"),
        Binding("S", "save_graph", "Save As"),
        Binding("u", "update_graph", "Update"),
        Binding("tab", "next_entity", "Next Line", show=False),
        Binding("c", "cycle_color", "Color"),
        Binding("C", "pick_color", "Color Picker"),
        Binding("l", "show_list_popup", "Back to List", show=False),
        Binding("a", "toggle_event_log", "Activity Log"),
        Binding("v", "show_log_scope", "Log View"),
        Binding("f", "maximize_log", "Maximize Log", show=False),
        Binding("question_mark", "show_help", "Help"),
        Binding("escape", "exit_cursor_mode", "Exit Inspect"),
        Binding("escape", "close_event_log", "Close Log"),
        Binding("escape", "go_back", "Back"),
        Binding("q", "exit_cursor_mode", "Exit Inspect", show=False),
        Binding("q", "close_event_log", "Close Log", show=False),
        Binding("q", "go_back", "Back", show=False),
    ]

    # App-level actions that still make sense on top of this screen — everything
    # else in HACLI.BINDINGS is main-table-only and is denied by HACLI.check_action
    # (issue #7: `n`/`N` search, `L`/`u`/`ctrl+r` list editing, `G` full-graph-again,
    # etc. used to leak through and clutter the Graph help page).
    ALLOWED_APP_ACTIONS = frozenset(
        {"show_dashboard", "show_device_tree", "show_saved_graphs_popup", "show_graph_duration", "quit"}
    )

    # This screen's help page is always built from the full static BINDINGS
    # rather than whichever mode happens to be active (main.action_show_help),
    # grouped into these sections — otherwise the inspect-mode twin of every
    # paging key would never appear on the page unless help was opened from
    # inside inspect mode (issue #7).
    HELP_ALL_MODES = True
    HELP_SECTIONS = (
        (
            "Window",
            frozenset(
                {
                    "cycle_plot_type",
                    "scroll_back",
                    "scroll_forward",
                    "scroll_back_fast",
                    "scroll_forward_fast",
                    "zoom_in",
                    "zoom_out",
                    "snap_live",
                }
            ),
        ),
        (
            "Inspect mode (Enter)",
            frozenset(
                {
                    "toggle_cursor_mode",
                    "cursor_prev",
                    "cursor_next",
                    "cursor_prev_fast",
                    "cursor_next_fast",
                    "cursor_home",
                    "cursor_end",
                    "exit_cursor_mode",
                }
            ),
        ),
        ("Lines & Colors", frozenset({"next_entity", "cycle_color", "pick_color"})),
        ("Saving", frozenset({"save_graph", "update_graph"})),
        (
            "Activity log",
            frozenset(
                {"toggle_event_log", "show_log_scope", "maximize_log", "close_event_log"}
            ),
        ),
        ("Other", frozenset({"show_list_popup", "show_help", "go_back"})),
    )

    # LogHost hooks (LogbookController, issue #38) — see controllers/logbook.py.
    LOG_PANEL_ID: str = "preview_log_panel"
    LOG_SUPPORTS_LIVE: bool = False

    def __init__(
        self,
        entity_ids: list[str] | str,
        initial_graph_type: str | None = None,
        saved_graph_name: str | None = None,
        colors: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        self._entity_ids = entity_ids
        self._entity_id = entity_ids[0]  # primary for backwards compat
        self._mode_index = next(
            (i for i, (kind, _) in enumerate(_PLOT_MODES) if kind == (initial_graph_type or "line")), 0
        )
        self._data: list[tuple[str, float]] = []
        self._all_data: dict[str, list] = {}
        # Zoom/scroll/live-anchor state lives on a pure GraphWindow; the three
        # legacy attrs below are delegating properties over it so the rest of the
        # screen (and the tests) read/assign them unchanged.
        self._window = GraphWindow()
        self._is_climate = self._entity_id.split(".")[0] == "climate"
        # Comparison mixing is blocked upstream, so the primary decides for all lines.
        self._is_binary = self._entity_id.split(".")[0] == "binary_sensor"
        self._climate_data: list[dict] = []
        self._saved_graph_name = saved_graph_name
        colors = colors or {}
        self._colors: dict[str, str] = {
            eid: colors.get(eid, _COLOR_PALETTE[i % len(_COLOR_PALETTE)]) for i, eid in enumerate(entity_ids)
        }
        self._active_entity_index = 0
        self._cursor_mode = False
        self._cursor_index = 0

    # Delegating properties over the pure GraphWindow, so existing reads/writes
    # of these attrs across the screen and tests keep working unchanged.
    @property
    def _window_end(self) -> "datetime | None":
        return self._window.window_end

    @_window_end.setter
    def _window_end(self, value: "datetime | None") -> None:
        self._window.window_end = value

    @property
    def _live_anchor(self) -> "datetime | None":
        return self._window.live_anchor

    @_live_anchor.setter
    def _live_anchor(self, value: "datetime | None") -> None:
        self._window.live_anchor = value

    @property
    def _local_hours(self) -> float | None:
        return self._window.local_hours

    @_local_hours.setter
    def _local_hours(self, value: float | None) -> None:
        self._window.local_hours = value

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "update_graph":
            return self._saved_graph_name is not None
        if action == "cycle_plot_type":
            return not self._is_binary and not self._is_climate
        if action == "next_entity":
            return len(self._entity_ids) > 1
        if action in ("cycle_color", "pick_color"):
            return not self._is_climate
        if action == "toggle_cursor_mode":
            return not self._is_climate and not self._cursor_mode and bool(self._data)
        if action == "exit_cursor_mode":
            return self._cursor_mode
        if action in ("scroll_back", "scroll_forward", "scroll_back_fast", "scroll_forward_fast"):
            return not self._cursor_mode
        if action in ("cursor_prev", "cursor_next", "cursor_prev_fast", "cursor_next_fast", "cursor_home"):
            return self._cursor_mode
        if action == "cursor_end":
            return self._cursor_mode
        if action == "snap_live":
            return not self._cursor_mode and (self._window_end is not None or self._local_hours is not None)
        if action == "close_event_log":
            return not self._cursor_mode and self._log_visible()
        if action == "maximize_log":
            return self._log_visible()
        if action == "show_log_scope":
            return self._log_visible()
        if action == "go_back":
            return not self._cursor_mode and not self._log_visible()
        return True

    def _log_visible(self) -> bool:
        return self.app.log_ctl.is_open(self)

    def log_window(self, session) -> "tuple[float, datetime]":
        return self._window_hours(), self._window_end or datetime.now(timezone.utc)

    def log_title_suffix(self, session) -> str:
        return ""

    def compose(self) -> ComposeResult:
        yield Label("", id="preview_title")
        yield PlotextPlot(id="preview_plot")
        yield Label("", id="preview_stats")
        yield ActivityLogPanel(id="preview_log_panel")
        yield Footer()

    def on_mount(self) -> None:
        if self._is_climate:
            self.run_worker(self._load_climate_and_render(), exclusive=True)
        else:
            self.run_worker(self._load_and_render(), exclusive=True)

    def _window_hours(self) -> float:
        return self._window.window_hours(self.app.graph_hours)

    def _apply_live_window(self) -> None:
        """While live+zoomed, trim the screen's held numeric buffers to the last
        `_local_hours` ending now. No-op when paged-back or un-zoomed; the app's
        history store is never touched, only this screen's copy — so cursor and
        stats naturally describe just the visible window."""
        if self._window_end is not None or self._local_hours is None:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._local_hours)

        def _keep(ts: str) -> bool:
            return datetime.fromisoformat(ts) >= cutoff

        self._all_data = {eid: [(t, v) for t, v in data if _keep(t)] for eid, data in self._all_data.items()}
        self._data = self._all_data.get(self._entity_id, self._data)

    async def _load_and_render(self, preserve_zoom: bool = False) -> None:
        self._window.reset_live(preserve_zoom=preserve_zoom)
        if self._local_hours is not None and self._local_hours > self.app.graph_hours:
            # Zoomed out past the graph_hours store: fetch the wider window ending
            # now directly (still live; live ticks append to this held buffer).
            now = datetime.now(timezone.utc)
            self._all_data = {}
            for eid in self._entity_ids:
                values = await self.app.graph_ctl.history_fetcher(eid)(eid, hours=self._local_hours, end=now)
                # A wide-window REST fetch can fail or come back empty for a
                # single entity (HAClient swallows errors as None); don't blank
                # an otherwise-good line — fall back to the in-memory store's
                # recent buffer so it stays visible instead of vanishing (#179).
                self._all_data[eid] = values or list(self.app.entity_history.get(eid, []))
        else:
            for eid in self._entity_ids:
                await self.app.graph_ctl.ensure_entity_history(eid)
            self._all_data = {eid: list(self.app.entity_history.get(eid, [])) for eid in self._entity_ids}
        self._data = self._all_data.get(self._entity_id, [])
        self._apply_live_window()
        entity = self.app.find_entity(self._entity_id)
        self._update_display(entity)
        await self._refresh_events_if_open()

    async def _load_window(self, end: datetime) -> None:
        hours = self._window_hours()
        all_data = {}
        for eid in self._entity_ids:
            values = await self.app.graph_ctl.history_fetcher(eid)(eid, hours=hours, end=end)
            all_data[eid] = values or []
        self._all_data = all_data
        self._data = self._all_data.get(self._entity_id, [])
        entity = self.app.find_entity(self._entity_id)
        self._update_display(entity)
        await self._refresh_events_if_open()

    async def _load_climate_and_render(self, preserve_zoom: bool = False) -> None:
        self._window.reset_live(preserve_zoom=preserve_zoom)
        if self._local_hours is not None and self._local_hours > self.app.graph_hours:
            now = datetime.now(timezone.utc)
            values = await self.app.client.fetch_climate_history(self._entity_id, hours=self._local_hours, end=now)
            self._climate_data = values or []
        else:
            await self.app.graph_ctl.ensure_climate_history(self._entity_id)
            self._climate_data = list(self.app.climate_history.get(self._entity_id, []))
        self._apply_live_climate_window()
        self._update_climate_display()
        await self._refresh_events_if_open()

    def _apply_live_climate_window(self) -> None:
        """Climate analogue of `_apply_live_window` (keyed on the `"ts"` field)."""
        if self._window_end is not None or self._local_hours is None:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._local_hours)
        self._climate_data = [p for p in self._climate_data if datetime.fromisoformat(p["ts"]) >= cutoff]

    async def _load_climate_window(self, end: datetime) -> None:
        hours = self._window_hours()
        values = await self.app.client.fetch_climate_history(self._entity_id, hours=hours, end=end)
        self._climate_data = values or []
        self._update_climate_display()
        await self._refresh_events_if_open()

    def action_scroll_back(self) -> None:
        # Half-window strides keep 50% of the previous view on screen so the eye
        # can track continuity between pages; the fast variants cover distance.
        self._page_back(self._window_hours() / 2)

    def action_scroll_forward(self) -> None:
        self._page_forward(self._window_hours() / 2)

    def action_scroll_back_fast(self) -> None:
        self._page_back(self._window_hours() * _FAST_PAGE_MULTIPLIER)

    def action_scroll_forward_fast(self) -> None:
        self._page_forward(self._window_hours() * _FAST_PAGE_MULTIPLIER)

    def action_cursor_prev(self) -> None:
        self._move_cursor(-1)

    def action_cursor_next(self) -> None:
        self._move_cursor(1)

    def action_cursor_prev_fast(self) -> None:
        self._move_cursor(-self._fast_cursor_stride())

    def action_cursor_next_fast(self) -> None:
        self._move_cursor(self._fast_cursor_stride())

    def _plot_width(self) -> int:
        try:
            plot = self.query_one("#preview_plot", PlotextPlot)
        except Exception:
            return max(20, getattr(self.app.size, "width", 0) or 200)
        return plot_width(plot, fallback=getattr(self.app.size, "width", 0) or 200)

    def _fast_cursor_stride(self) -> int:
        """Cursor-mode fast step: at least 10% of the plotted samples so ~10 fast
        presses cross a dense (multi-thousand-point) window, never below the
        familiar small-plot step of _FAST_PAGE_MULTIPLIER."""
        return max(_FAST_PAGE_MULTIPLIER, round(len(self._data) * 0.10))

    def _page_back(self, hours: float) -> None:
        self._window.page_back(hours, datetime.now(timezone.utc))
        self._reload_window()

    def action_zoom_in(self) -> None:
        self._apply_zoom(max(0.25, self._window_hours() / 2))

    def action_zoom_out(self) -> None:
        self._apply_zoom(min(720.0, self._window_hours() * 2))

    def _apply_zoom(self, new_hours: float) -> None:
        signal = self._window.zoom(new_hours, self.app.graph_hours)
        if signal == "live":
            self._reload_live(preserve_zoom=True)
        elif signal == "window":
            self._reload_window()

    def action_snap_live(self) -> None:
        if not self._window.should_snap_live():
            return
        self._reload_live()

    def action_cursor_home(self) -> None:
        self._jump_cursor(0)

    def action_cursor_end(self) -> None:
        self._jump_cursor(len(self._data) - 1)

    def _jump_cursor(self, index: int) -> None:
        if not self._data:
            return
        self._cursor_index = max(0, min(len(self._data) - 1, index))
        entity = self.app.find_entity(self._entity_id)
        self._update_display(entity)

    def _page_forward(self, hours: float) -> None:
        # Re-entering live keeps any zoom level (issue #138); an un-zoomed window
        # simply returns to the base live view.
        signal = self._window.page_forward(hours)
        if signal == "live":
            self._reload_live(preserve_zoom=True)
        elif signal == "window":
            self._reload_window()

    def _reload_live(self, preserve_zoom: bool = False) -> None:
        if self._is_climate:
            self.run_worker(self._load_climate_and_render(preserve_zoom), exclusive=True)
        else:
            self.run_worker(self._load_and_render(preserve_zoom), exclusive=True)

    def reload(self) -> None:
        """Public: reload the live window from scratch (e.g. after the global
        graph duration changed)."""
        self._reload_live()

    def refresh_live_data(self, entity_id: str, history: list[tuple[str, float]]) -> None:
        """Public: redraw with fresh history for one plotted entity, but only
        while this screen is live-anchored — paged-back windows, climate
        graphs, and cursor/inspect mode must not be yanked around by live
        state changes."""
        if entity_id not in self._entity_ids:
            return
        if self._window_end is not None or self._is_climate or self._cursor_mode:
            return
        if self._local_hours is not None and self._local_hours > self.app.graph_hours:
            # Zoomed out past the store: `history` is only its recent tail, so a
            # wholesale replace would shrink the held wide window. Append just the
            # newest sample instead.
            buf = self._all_data.get(entity_id)
            if buf is not None and history and (not buf or history[-1][0] > buf[-1][0]):
                buf.append(history[-1])
                if entity_id == self._entity_id:
                    self._data = buf
        else:
            if entity_id in self._all_data:
                self._all_data[entity_id] = list(history)
            if entity_id == self._entity_id:
                self._data = list(history)
        self._apply_live_window()
        self._update_display(self.app.find_entity(self._entity_id))

    def _reload_window(self) -> None:
        end = self._window.window_end
        if end is None:
            return
        if self._is_climate:
            self.run_worker(self._load_climate_window(end), exclusive=True)
        else:
            self.run_worker(self._load_window(end), exclusive=True)

    def _window_status(self) -> str:
        """LIVE / zoom / paged-back badge for the title bar."""
        return self._window.status_badge()

    def _update_display(self, entity: "Entity | None") -> None:
        unit = self._render_title(entity)

        plot = self.query_one("#preview_plot", PlotextPlot)
        plot.plt.clear_data()
        plot.plt.clear_figure()
        if self._data:
            binary_end_iso = self._render_plot(plot.plt, entity)
            self.query_one("#preview_stats", Label).update(self._stats_text(entity, unit, binary_end_iso))
        else:
            self.query_one("#preview_stats", Label).update("No history data available.")
        plot.refresh()

    def _render_title(self, entity: "Entity | None") -> str:
        """Set the title line; returns the primary entity's unit for the stats."""
        _, mode_label = _PLOT_MODES[self._mode_index]
        unit = ""
        if self._data:
            window_suffix = f"  ({_ts_to_full(self._data[0][0])} – {_ts_to_full(self._data[-1][0])})"
        elif self._window_end is None:
            window_suffix = ""
        else:
            window_suffix = f"  (ending {_ts_to_full(self._window_end.isoformat())})"
        window_suffix += self._window_status()
        if entity:
            unit = entity_unit(entity)
            extra_count = len(self._entity_ids) - 1
            title = entity_title(entity, mode_label=mode_label, extra_count=extra_count)
            title.append(window_suffix)
            self.query_one("#preview_title", Label).update(title)
        else:
            self.query_one("#preview_title", Label).update(Text(f"{self._entity_id}  [{mode_label}]{window_suffix}"))
        return unit

    def _render_plot(self, plt, entity: "Entity | None") -> str | None:
        """Plot every series (primary, extras, cursor marker) for a non-empty
        window; returns the binary window-end ISO timestamp when applicable."""
        kind, _ = _PLOT_MODES[self._mode_index]
        primary_label = get_display_name(entity) if entity else self._entity_id

        if self._is_binary:
            # Step traces extend to the window edge so the current state reads
            # as a level, not a dangling point; render_binary drops any numeric
            # companion (can't sit on the 0/1 axis) and owns the shared draw.
            binary_end_iso = (self._window_end or datetime.now(timezone.utc)).isoformat()
            extras = []
            for eid in self._entity_ids[1:]:
                extra_entity = self.app.find_entity(eid)
                extra_name = get_display_name(extra_entity) if extra_entity else eid
                extras.append((extra_name, self._all_data.get(eid, []), self._colors.get(eid)))
            t0 = render_binary(
                plt,
                (primary_label, self._data, self._colors.get(self._entity_id)),
                extras,
                extend_to=binary_end_iso,
            )
            if self._cursor_mode:
                self._cursor_index = max(0, min(len(self._data) - 1, self._cursor_index))
                plt.vline(secs_since(t0)(self._data[self._cursor_index][0]), color="white")
            return binary_end_iso

        extras = []
        for eid in self._entity_ids[1:]:
            extra_entity = self.app.find_entity(eid)
            extra_name = get_display_name(extra_entity) if extra_entity else eid
            extras.append((extra_name, self._all_data.get(eid, []), self._colors.get(eid)))

        cursor_index = None
        if self._cursor_mode:
            self._cursor_index = max(0, min(len(self._data) - 1, self._cursor_index))
            cursor_index = self._cursor_index

        t0 = render_numeric(
            plt,
            kind,
            (primary_label, self._data, self._colors.get(self._entity_id)),
            extras,
            self._plot_width(),
            cursor_index=cursor_index,
        )
        return None

    def _stats_text(self, entity: "Entity | None", unit: str, binary_end_iso: str | None) -> str:
        if self._cursor_mode:
            cursor_ts, cursor_val = self._data[self._cursor_index]
            cursor_dt = datetime.fromisoformat(cursor_ts)
            primary_name = get_display_name(entity) if entity else self._entity_id

            def _fmt(value: float) -> str:
                if self._is_binary:
                    return value_to_state(value)
                return f"{value:.1f}"

            parts = [_ts_to_full(cursor_ts), f"{primary_name}: {_fmt(cursor_val)}{'' if self._is_binary else unit}"]
            for eid in self._entity_ids[1:]:
                nearest = _nearest_value(self._all_data.get(eid, []), cursor_dt)
                if nearest is not None:
                    extra_entity = self.app.find_entity(eid)
                    extra_name = get_display_name(extra_entity) if extra_entity else eid
                    parts.append(f"{extra_name}: {_fmt(nearest)}")
            parts.append(f"sample {self._cursor_index + 1}/{len(self._data)}")
            return "  |  ".join(parts)

        is_comparison = len(self._entity_ids) > 1
        active_eid = self._entity_ids[self._active_entity_index] if is_comparison else self._entity_id
        active_data = self._all_data.get(active_eid, []) if is_comparison else self._data

        if self._is_binary:
            stats_text = binary_stats(active_data, end_ts=binary_end_iso)
            if is_comparison:
                active_entity = self.app.find_entity(active_eid)
                active_name = get_display_name(active_entity) if active_entity else active_eid
                color = self._colors[active_eid]
                stats_text = f"{active_name} — {stats_text}   {_color_hint(color)}"
            return stats_text

        if not active_data:
            active_data = self._data
        active_entity = self.app.find_entity(active_eid) if is_comparison else entity
        active_unit = entity_unit(active_entity) if is_comparison and active_entity else unit
        active_values = [v for _, v in active_data]
        if not active_values:
            active_name = get_display_name(active_entity) if active_entity else active_eid
            return f"No data for {active_name}"
        stats_text = numeric_stats_line(active_values, active_unit)
        if is_comparison:
            active_name = get_display_name(active_entity) if active_entity else active_eid
            active_color = self._colors[active_eid]
            stats_text = f"{active_name} — {stats_text}   {_color_hint(active_color)}"
        return stats_text

    def action_save_graph(self) -> None:
        from hatty.ui.graph.saved_graphs_popup import SaveGraphNamePopup

        def callback(name: str | None) -> None:
            if not name:
                return
            self.app.graph_ctl.save_graph(
                name,
                list(self._entity_ids),
                _PLOT_MODES[self._mode_index][0],
                self._window_hours(),
                colors=dict(self._colors),
            )

        self.app.push_screen(SaveGraphNamePopup(initial_name=self._saved_graph_name), callback)

    def action_update_graph(self) -> None:
        if self._saved_graph_name is None:
            return
        self.app.graph_ctl.save_graph(
            self._saved_graph_name,
            list(self._entity_ids),
            _PLOT_MODES[self._mode_index][0],
            self._window_hours(),
            colors=dict(self._colors),
        )

    def action_cycle_plot_type(self) -> None:
        if self._is_climate or self._is_binary:
            return
        self._mode_index = (self._mode_index + 1) % len(_PLOT_MODES)
        entity = self.app.find_entity(self._entity_id)
        self._update_display(entity)

    def action_next_entity(self) -> None:
        if len(self._entity_ids) <= 1:
            return
        self._active_entity_index = (self._active_entity_index + 1) % len(self._entity_ids)
        entity = self.app.find_entity(self._entity_id)
        self._update_display(entity)

    def action_cycle_color(self) -> None:
        if self._is_climate:
            return
        active_eid = self._entity_ids[self._active_entity_index]
        current = self._colors.get(active_eid, _COLOR_PALETTE[0])
        next_index = (_COLOR_PALETTE.index(current) + 1) % len(_COLOR_PALETTE) if current in _COLOR_PALETTE else 0
        self._colors[active_eid] = _COLOR_PALETTE[next_index]
        entity = self.app.find_entity(self._entity_id)
        self._update_display(entity)

    def action_pick_color(self) -> None:
        if self._is_climate:
            return
        from hatty.ui.graph.color_popup import GraphColorPopup

        active_eid = self._entity_ids[self._active_entity_index]
        active_entity = self.app.find_entity(active_eid)
        active_name = get_display_name(active_entity) if active_entity else active_eid

        def callback(color: str | None) -> None:
            if not color:
                return
            self._colors[active_eid] = color
            entity = self.app.find_entity(self._entity_id)
            self._update_display(entity)

        self.app.push_screen(GraphColorPopup(active_name, self._colors.get(active_eid)), callback)

    def _set_cursor_mode(self, active: bool) -> None:
        self._cursor_mode = active
        if active:
            self._cursor_index = len(self._data) - 1
        entity = self.app.find_entity(self._entity_id)
        self._update_display(entity)
        self.refresh_bindings()

    def action_toggle_cursor_mode(self) -> None:
        self._set_cursor_mode(True)

    def action_exit_cursor_mode(self) -> None:
        self._set_cursor_mode(False)

    def action_show_help(self) -> None:
        self.app.action_show_help()

    def _close_event_log(self) -> None:
        self.app.log_ctl.close(self)
        self._redraw()

    _LOG_HINT = "v scope · f max · a close · ←/→ page with the graph"
    _LOG_HINT_MAXIMIZED = "↑/↓ select · f exit · a close · ←/→ page with the graph"

    def action_close_event_log(self) -> None:
        """escape/q — a further escape/toggle closes; a maximized panel gets
        un-maximized first, mirroring the main screen's action_go_back. `a`/`A`
        (action_toggle_event_log) close outright instead, bypassing this."""
        log_panel = self.query_one("#preview_log_panel", ActivityLogPanel)
        if log_panel.has_class("-maximized"):
            log_panel.set_hint(self._LOG_HINT)
            log_panel.set_maximized(False)
            # The screen itself isn't focusable, so self.focus() would no-op —
            # explicitly blur (Screen.set_focus(widget) is a no-op unless the
            # target is focusable, and there's no natural "home" widget here
            # the way the main table is for HACLI).
            self.set_focus(None)
            return
        self._close_event_log()

    def action_maximize_log(self) -> None:
        log_panel = self.query_one("#preview_log_panel", ActivityLogPanel)
        maximizing = not log_panel.has_class("-maximized")
        log_panel.set_hint(self._LOG_HINT_MAXIMIZED if maximizing else self._LOG_HINT)
        log_panel.set_maximized(maximizing)
        if not maximizing:
            # The screen itself isn't focusable, so self.focus() would no-op —
            # explicitly blur (Screen.set_focus(widget) is a no-op unless the
            # target is focusable, and there's no natural "home" widget here
            # the way the main table is for HACLI).
            self.set_focus(None)

    def action_go_back(self) -> None:
        self.dismiss()

    def _redraw(self) -> None:
        if self._is_climate:
            self._update_climate_display()
        else:
            entity = self.app.find_entity(self._entity_id)
            self._update_display(entity)

    def _open_event_log(self) -> None:
        label = self.app._log_label_for_ids(self._entity_ids)
        options = [
            self.app.log_ctl.base_option("entities", label, self._entity_ids, with_devices=False),
            self.app.log_ctl.base_option("entities_devices", label, self._entity_ids, with_devices=True),
        ]
        self.app.log_ctl.open(self, options=options, option_id="entities", hint=self._LOG_HINT)

    def action_toggle_event_log(self) -> None:
        if self.app.log_ctl.is_open(self):
            self._close_event_log()
            return
        self._open_event_log()

    def action_show_log_scope(self) -> None:
        """`v` — preview and pick the open log's scope (issue #38, replacing
        the old blind cycle from issue #21). A no-op while the log is closed
        (gated by check_action)."""
        from hatty.ui.log_scope_popup import LogScopePopup

        session = self.app.log_ctl.session_for(self)
        if session is None:
            return
        entity_names, device_names = self.app.log_ctl.display_names()
        resolved = self.app.log_ctl.resolved_options(self)

        def callback(result: str | None) -> None:
            self.app.log_ctl.handle_scope_popup_result(self, result)

        self.app.push_screen(LogScopePopup(resolved, session.option_id, entity_names, device_names), callback)

    async def _refresh_events_if_open(self) -> None:
        session = self.app.log_ctl.session_for(self)
        if session is not None:
            await self.app.log_ctl.load(session)

    def action_show_list_popup(self) -> None:
        # Mirror DashboardScreen: dismiss the fullscreen graph and jump straight back
        # to the last-shown (or default) list; only fall back to the full picker when
        # there is no list to return to.
        from hatty.ui.list_selection_popup import ListSelectionPopup

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

    def _move_cursor(self, direction: int) -> None:
        if not self._data:
            return
        self._cursor_index = max(0, min(len(self._data) - 1, self._cursor_index + direction))
        entity = self.app.find_entity(self._entity_id)
        self._update_display(entity)

    def _update_climate_display(self) -> None:
        if self._climate_data:
            start = _ts_to_full(self._climate_data[0]["ts"])
            end = _ts_to_full(self._climate_data[-1]["ts"])
            window_suffix = f"  ({start} – {end})"
        elif self._window_end is None:
            window_suffix = ""
        else:
            window_suffix = f"  (ending {_ts_to_full(self._window_end.isoformat())})"
        window_suffix += self._window_status()

        entity = self.app.find_entity(self._entity_id)
        name = get_display_name(entity) if entity else self._entity_id
        state = entity.get("state", "") if entity else ""
        self.query_one("#preview_title", Label).update(Text(f"{name} — {state}  [Current/Target]{window_suffix}"))

        plot = self.query_one("#preview_plot", PlotextPlot)
        plot.plt.clear_data()
        plot.plt.clear_figure()

        self.query_one("#preview_stats", Label).update(render_climate(plot.plt, self._climate_data))
        plot.refresh()
