# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label, Sparkline
from textual_plotext import PlotextPlot

from hatty.const import CONFIG_KEY_GRAPH_TYPE
from hatty.types import Entity
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.entity_table import entity_title
from hatty.ui.graph.plot_render import PLOTEXT_MODES, plot_numeric_series, plot_width
from hatty.ui.graph.plot_time import ts_to_hhmm as _ts_to_hhmm

_PLOT_MODES = [("sparkline", "Spark")] + PLOTEXT_MODES


class GraphSlotWidget(EntitySlotWidget):
    DEFAULT_CSS = """
    GraphSlotWidget #slot_title {
        text-style: bold;
    }
    GraphSlotWidget #slot_sparkline {
        height: 1fr;
        margin: 0;
    }
    GraphSlotWidget #slot_sparkline > .sparkline--min-color {
        color: #0096ff;
    }
    GraphSlotWidget #slot_sparkline > .sparkline--max-color {
        color: #ff8c00;
    }
    GraphSlotWidget #slot_plot {
        height: 1fr;
        margin: 0;
        display: none;
    }
    """

    def __init__(self, entity_id: str | None, *, show_last_changed: bool = False):
        super().__init__(entity_id, show_last_changed=show_last_changed)
        self._data: list[tuple[str, float]] = []
        self._mode_index = 0

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_title")
        yield Sparkline([], id="slot_sparkline")
        yield PlotextPlot(id="slot_plot")

    def on_mount(self) -> None:
        saved = self.app.app_config.get(CONFIG_KEY_GRAPH_TYPE) or "sparkline"
        self._mode_index = next((i for i, (kind, _) in enumerate(_PLOT_MODES) if kind == saved), 0)
        super().on_mount()
        if self.entity_id:
            self.run_worker(self._load_history(), exclusive=True)

    def current_graph_type(self) -> str:
        return _PLOT_MODES[self._mode_index][0]

    async def _load_history(self) -> None:
        if not self.entity_id:
            return
        await self.app.graph_ctl.ensure_entity_history(self.entity_id)
        self.update_entity(self.app.find_entity(self.entity_id))

    def reload_history(self) -> None:
        if self.entity_id:
            self.run_worker(self._load_history(), exclusive=True)

    def cycle_plot_type(self) -> None:
        self._mode_index = (self._mode_index + 1) % len(_PLOT_MODES)
        self._render_plot()

    def _render_plot(self) -> None:
        kind, _ = _PLOT_MODES[self._mode_index]
        sparkline = self.query_one("#slot_sparkline", Sparkline)
        plot = self.query_one("#slot_plot", PlotextPlot)

        if kind == "sparkline":
            sparkline.display = True
            plot.display = False
            sparkline.data = [v for _, v in self._data]
        else:
            sparkline.display = False
            plot.display = True
            plot.plt.clear_data()
            plot.plt.clear_figure()
            if self._data:
                n = len(self._data)
                values = [v for _, v in self._data]
                indices = list(range(n))
                step = max(1, n // 5)
                tick_pos = indices[::step]
                tick_labels = [_ts_to_hhmm(self._data[i][0]) for i in tick_pos]
                plot.plt.xticks([float(p) for p in tick_pos], tick_labels)
                width = plot_width(plot)
                if kind in ("line", "scatter"):
                    plot_numeric_series(plot.plt, kind, [float(i) for i in indices], values, width)
            plot.refresh()

    def _render_empty(self) -> None:
        # Structural outlier: a titled sparkline, not the label stack the base
        # blanks — reset the plot and title directly.
        self.query_one("#slot_title", Label).update("No entity")
        self._data = []
        self._render_plot()

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        self.query_one("#slot_title", Label).update(entity_title(entity))
        self._data = list(self.app.entity_history.get(self.entity_id, []))
        self._render_plot()
