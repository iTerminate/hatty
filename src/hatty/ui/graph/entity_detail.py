# hatty — MIT License. See LICENSE file for details.
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import cast

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Sparkline
from textual_plotext import PlotextPlot

from hatty.types import Entity
from hatty.ui.entity_table import entity_title, entity_unit, get_display_name
from hatty.ui.graph.plot_render import (
    PLOTEXT_MODES,
    numeric_stats_line,
    plot_width,
    render_binary,
    render_climate,
    render_numeric,
)

_SPARKLINE_MODES = [
    ("Max", max),
    ("Min", min),
    ("Mean", lambda data: sum(data) / len(data)),
]
_ALL_MODES = [("sparkline", label, fn) for label, fn in _SPARKLINE_MODES] + [
    ("plotext", label, kind) for kind, label in PLOTEXT_MODES
]


class EntityDetailPanel(Widget):
    DEFAULT_CSS = """
    EntityDetailPanel {
        height: 14;
        border-top: heavy $accent;
        background: $panel;
        padding: 0 1;
        display: none;
    }
    EntityDetailPanel.-visible {
        display: block;
    }
    EntityDetailPanel #detail_title {
        text-style: bold;
    }
    EntityDetailPanel #detail_sparkline {
        height: 3;
        margin: 0;
    }
    EntityDetailPanel #detail_sparkline > .sparkline--min-color {
        color: #0096ff;
    }
    EntityDetailPanel #detail_sparkline > .sparkline--max-color {
        color: #ff8c00;
    }
    EntityDetailPanel #detail_plot {
        height: 8;
        margin: 0;
        display: none;
    }
    EntityDetailPanel #detail_stats {
        color: $text-muted;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._mode_index = 0
        self._history: list[tuple[str, float]] = []
        self._extra_histories: dict[str, tuple[Entity | None, list]] = {}
        self._is_climate = False
        self._is_binary = False
        self._climate_data: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Label("", id="detail_title")
        yield Sparkline([], id="detail_sparkline", summary_function=_SPARKLINE_MODES[0][1])
        yield PlotextPlot(id="detail_plot")
        yield Label("", id="detail_stats")

    def apply_saved_graph_type(self, graph_type: str | None) -> None:
        self._mode_index = self._index_from_graph_type(graph_type or "line")

    @staticmethod
    def _graph_type_from_index(idx: int) -> str:
        kind, _, fn_or_type = _ALL_MODES[idx]
        return "sparkline" if kind == "sparkline" else fn_or_type

    @staticmethod
    def _index_from_graph_type(graph_type: str) -> int:
        for i in range(len(_ALL_MODES)):
            if EntityDetailPanel._graph_type_from_index(i) == graph_type:
                return i
        return 0

    def current_graph_type(self) -> str:
        return self._graph_type_from_index(self._mode_index)

    def _current_mode(self) -> tuple[str, str, object]:
        return _ALL_MODES[self._mode_index]

    def cycle_graph_type(self) -> None:
        if self._is_climate or self._is_binary:
            return
        self._mode_index = (self._mode_index + 1) % len(_ALL_MODES)
        self._render_current_mode()

    def _render_current_mode(self) -> None:
        kind, label, fn_or_type = self._current_mode()
        sparkline = self.query_one("#detail_sparkline", Sparkline)
        plot = self.query_one("#detail_plot", PlotextPlot)

        if kind == "sparkline":
            sparkline.display = True
            plot.display = False
            # In the sparkline branch fn_or_type is a summary callable (the mode
            # table stores it as object alongside plotext-mode strings).
            sparkline.summary_function = cast("Callable[[Sequence[float]], float]", fn_or_type)
            sparkline.data = [v for _, v in self._history]
        else:
            sparkline.display = False
            plot.display = True
            plot.plt.clear_data()
            plot.plt.clear_figure()
            if self._history:
                extras = [
                    (get_display_name(extra_entity) if extra_entity else _eid, extra_hist, None)
                    for _eid, (extra_entity, extra_hist) in self._extra_histories.items()
                ]
                # In this branch fn_or_type is a plotext-mode string, not a summary callable.
                kind = cast(str, fn_or_type)
                render_numeric(plot.plt, kind, (None, self._history, None), extras, plot_width(plot))
            plot.refresh()

    def update_multi(
        self,
        entity: Entity,
        history: list[tuple[str, float]] | None,
        extras: dict[str, tuple["Entity | None", list]],
    ) -> None:
        self._extra_histories = extras
        self.update(entity, history)

    def update_binary(
        self,
        entity: Entity,
        history: list[tuple[str, float]] | None,
        extras: dict[str, tuple["Entity | None", list]] | None = None,
    ) -> None:
        """Binary entities render a fixed off/on step trace instead of the numeric modes."""
        self._is_climate = False
        self._is_binary = True
        self._history = history or []
        self._extra_histories = extras or {}
        name = get_display_name(entity)
        state = entity.get("state", "")
        extra_count = len(self._extra_histories)
        extra_suffix = f" +{extra_count} more" if extra_count else ""
        self.query_one("#detail_title", Label).update(Text(f"{name}{extra_suffix} — {state}  [Timeline]"))
        self._render_binary_mode()

    def _render_binary_mode(self) -> None:
        from hatty.ui.graph.binary_history import binary_stats

        sparkline = self.query_one("#detail_sparkline", Sparkline)
        plot = self.query_one("#detail_plot", PlotextPlot)
        stats = self.query_one("#detail_stats", Label)
        sparkline.display = False
        plot.display = True
        plot.plt.clear_data()
        plot.plt.clear_figure()

        if not self._history:
            stats.update("Fetching history…")
            plot.refresh()
            return

        now_iso = datetime.now().astimezone().isoformat()
        # render_binary drops numeric companions (they can't sit on the 0/1 axis;
        # plotext crashes on a labelled series entirely outside ylim) and extends
        # each trace to "now".
        extras = [
            (get_display_name(extra_entity) if extra_entity else eid, extra_hist, None)
            for eid, (extra_entity, extra_hist) in self._extra_histories.items()
        ]
        render_binary(plot.plt, (None, self._history, None), extras, extend_to=now_iso)
        plot.refresh()
        stats.update(binary_stats(self._history, end_ts=now_iso))

    def update(self, entity: Entity, history: list[tuple[str, float]] | None) -> None:
        self._is_climate = False
        self._is_binary = False
        unit = entity_unit(entity)

        stats = self.query_one("#detail_stats", Label)
        _, mode_label, _ = self._current_mode()
        extra_count = len(self._extra_histories)
        self.query_one("#detail_title", Label).update(
            entity_title(entity, mode_label=mode_label, extra_count=extra_count)
        )

        if history is None:
            self._history = []
            self._render_current_mode()
            stats.update("Failed to load history.")
        elif len(history) >= 2:
            self._history = history
            self._render_current_mode()
            stats.update(numeric_stats_line([v for _, v in history], unit))
        else:
            self._history = history or []
            self._render_current_mode()
            stats.update("Fetching history…")

    def update_climate(self, entity: Entity, climate_data: list[dict] | None) -> None:
        self._is_climate = True
        self._is_binary = False
        self._climate_data = climate_data or []
        self.query_one("#detail_title", Label).update(
            entity_title(entity, mode_label="Current/Target", show_unit=False)
        )
        self._render_climate_mode()

    def _render_climate_mode(self) -> None:
        sparkline = self.query_one("#detail_sparkline", Sparkline)
        plot = self.query_one("#detail_plot", PlotextPlot)
        stats = self.query_one("#detail_stats", Label)
        sparkline.display = False
        plot.display = True
        plot.plt.clear_data()
        plot.plt.clear_figure()

        stats.update(render_climate(plot.plt, self._climate_data))
        plot.refresh()

    def update_unavailable(self, entity: Entity) -> None:
        self._is_climate = False
        self._is_binary = False
        self.query_one("#detail_title", Label).update(entity_title(entity))
        self._history = []
        self._render_current_mode()
        self.query_one("#detail_stats", Label).update("No graph data for this entity")
