# hatty — MIT License. See LICENSE file for details.
"""`WeatherForecastScreen` — a fullscreen multi-day forecast view for a
`weather` entity, opened by `e`/`enter` via `HACLI.open_entity_controls`'s
`weather` branch (dashboard slot, device tree, and main table all route
through it). Modeled on `graph/preview_screen.py`'s fullscreen `Screen`
pattern (opaque background, `Footer`, `escape` dismisses).

Forecast data is fetched on demand via `HAClient.fetch_forecast` (the
`weather.get_forecasts` service, issue #283) rather than read off the entity's
`forecast` attribute — modern Home Assistant no longer keeps that attribute
populated, so a static attribute read silently rendered "No forecast data
available" against a real instance. When the entity's `supported_features`
bitmask advertises more than one forecast type (`daily`/`twice_daily`/`hourly`),
a `Tabs` bar renders them across the top so the available types and the active
one are visible at a glance (e.g. a National Weather Service entity only
supports twice_daily/hourly, no daily) — `t`, native left/right, or clicking a
tab all switch the active type via `on_tabs_tab_activated`. A single-type
entity gets no bar at all. A fetch that comes back empty falls back to the
legacy inline `forecast` attribute, so older integrations and the demo dataset
keep working."""

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Label, Static, Tab, Tabs

from hatty.const import supported_forecast_types
from hatty.ui.dashboard.widgets.visuals import build_forecast_columns
from hatty.ui.entity_table import get_display_name

if TYPE_CHECKING:
    from hatty.main import HACLI
    from hatty.types import Entity

_TYPE_LABELS = {"daily": "Daily", "twice_daily": "Twice daily", "hourly": "Hourly"}


class WeatherForecastScreen(Screen):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    DEFAULT_CSS = """
    WeatherForecastScreen {
        background: $surface;
    }
    WeatherForecastScreen #forecast_title {
        text-style: bold;
        padding: 0 1;
        background: $panel;
    }
    WeatherForecastScreen Tabs {
        margin-top: 1;
    }
    WeatherForecastScreen #forecast_content {
        height: 1fr;
    }
    WeatherForecastScreen #forecast_row {
        height: 1fr;
        align: center middle;
        align-vertical: top;
    }
    WeatherForecastScreen .forecast_day {
        width: auto;
        height: auto;
        margin: 0 2;
        align: center top;
    }
    WeatherForecastScreen .forecast_day_label {
        text-style: bold;
    }
    WeatherForecastScreen .forecast_art {
        width: auto;
        margin: 1 0;
        text-align: center;
        color: $text-muted;
    }
    WeatherForecastScreen .forecast_art.-sunny {
        color: $warning;
    }
    WeatherForecastScreen .forecast_art.-rainy, WeatherForecastScreen .forecast_art.-storm {
        color: $primary;
    }
    WeatherForecastScreen .forecast_art.-snowy {
        color: $text;
    }
    WeatherForecastScreen .forecast_art.-cloudy, WeatherForecastScreen .forecast_art.-night {
        color: $text-muted;
    }
    WeatherForecastScreen #forecast_status {
        width: 100%;
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("t", "cycle_type", "Switch type"),
    ]

    def __init__(self, entity: "Entity") -> None:
        super().__init__()
        self._entity = entity
        self._entity_id = entity.get("entity_id", "")
        self._attrs = entity.get("attributes", {})
        # Which weather.get_forecasts `type`s to offer: whatever the entity's
        # supported_features bitmask advertises, or a bare ["daily"] guess
        # (still worth trying, then falling back to the attribute) when the
        # entity carries no supported_features at all.
        self._types = supported_forecast_types(self._attrs.get("supported_features")) or ["daily"]
        self._type_index = 0
        self._forecast: list[dict] | None = None
        self._active_type = self._types[0]

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "cycle_type":
            return len(self._types) > 1
        return True

    def compose(self) -> ComposeResult:
        yield Label(f"{get_display_name(self._entity)} Forecast", id="forecast_title")
        if len(self._types) > 1:
            yield Tabs(
                *(Tab(_TYPE_LABELS.get(t, t.title()), id=f"type_{t}") for t in self._types),
                id="forecast_tabs",
            )
        with Container(id="forecast_content"):
            yield Label("Loading forecast…", id="forecast_status")
        yield Footer()

    def on_mount(self) -> None:
        if len(self._types) > 1:
            self.query_one("#forecast_tabs", Tabs).focus()
        self.run_worker(self._load_forecast(), exclusive=True)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        type_key = (event.tab.id or "").removeprefix("type_")
        if type_key not in self._types:
            return
        index = self._types.index(type_key)
        if index == self._type_index:
            # The initial activation Textual posts on mount for the first tab —
            # _load_forecast already covers that fetch, so don't double it.
            return
        self._type_index = index
        self.run_worker(self._show_loading_then_load(), exclusive=True)

    async def _load_forecast(self) -> None:
        requested_type = self._types[self._type_index]
        forecast = await self.app.client.fetch_forecast(self._entity_id, requested_type)
        if forecast:
            self._active_type = requested_type
        else:
            forecast = self._attrs.get("forecast")
            self._active_type = "daily"
        self._forecast = forecast
        await self._render_forecast()

    def action_cycle_type(self) -> None:
        if len(self._types) <= 1:
            return
        next_index = (self._type_index + 1) % len(self._types)
        self.query_one("#forecast_tabs", Tabs).active = f"type_{self._types[next_index]}"

    async def _show_loading_then_load(self) -> None:
        content = self.query_one("#forecast_content", Container)
        await content.remove_children()
        await content.mount(Label("Loading forecast…", id="forecast_status"))
        await self._load_forecast()

    async def _render_forecast(self) -> None:
        temp_unit = self._attrs.get("temperature_unit") or ""
        columns = build_forecast_columns(self._forecast, temp_unit, forecast_type=self._active_type)

        content = self.query_one("#forecast_content", Container)
        await content.remove_children()
        if not columns:
            await content.mount(Label("No forecast data available", id="forecast_status"))
            return

        days = []
        for column in columns:
            art = Static(column.art, classes="forecast_art")
            if column.css_class:
                art.add_class(column.css_class)
            day_children = [
                Label(column.label, classes="forecast_day_label"),
                art,
                Label(column.condition_label, classes="forecast_condition"),
                Label(column.temp_range, classes="forecast_temp"),
            ]
            if column.extra:
                day_children.append(Label(column.extra, classes="forecast_extra"))
            days.append(Vertical(*day_children, classes="forecast_day"))
        await content.mount(Horizontal(*days, id="forecast_row"))

    def action_go_back(self) -> None:
        self.dismiss()
