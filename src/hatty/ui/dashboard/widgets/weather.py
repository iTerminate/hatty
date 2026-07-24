# hatty — MIT License. See LICENSE file for details.
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Static

from hatty.types import Entity
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.dashboard.widgets.visuals import WEATHER_CLASSES, weather_art, weather_label
from hatty.ui.entity_table import apply_pending_suffix, get_display_name_text


class WeatherSlotWidget(EntitySlotWidget):
    DEFAULT_CSS = """
    WeatherSlotWidget {
        content-align: center middle;
    }
    WeatherSlotWidget #slot_name {
        text-style: bold;
    }
    WeatherSlotWidget #weather_row {
        height: auto;
        align: center middle;
    }
    WeatherSlotWidget #weather_art {
        width: auto;
        margin-right: 2;
        color: $text-muted;
        text-style: bold;
    }
    WeatherSlotWidget #weather_art.-sunny {
        color: $warning;
    }
    WeatherSlotWidget #weather_art.-rainy, WeatherSlotWidget #weather_art.-storm {
        color: $primary;
    }
    WeatherSlotWidget #weather_art.-snowy {
        color: $text;
    }
    WeatherSlotWidget #weather_art.-cloudy, WeatherSlotWidget #weather_art.-night {
        color: $text-muted;
    }
    WeatherSlotWidget #weather_info {
        width: auto;
        height: auto;
    }
    WeatherSlotWidget #slot_temp {
        color: $accent;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        with Horizontal(id="weather_row"):
            yield Static("", id="weather_art")
            with Vertical(id="weather_info"):
                yield Label("", id="slot_condition")
                yield Label("", id="slot_temp")
                yield Label("", id="slot_detail")

    def _render_empty(self) -> None:
        super()._render_empty()
        self.query_one("#weather_art", Static).set_classes("")

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        art = self.query_one("#weather_art", Static)
        condition_label = self.query_one("#slot_condition", Label)
        temp_label = self.query_one("#slot_temp", Label)
        detail_label = self.query_one("#slot_detail", Label)

        condition = entity.get("state", "")
        attrs = entity.get("attributes", {})

        name_label.update(get_display_name_text(entity))
        art.update(weather_art(condition))
        art.set_classes(WEATHER_CLASSES.get(condition, ""))
        condition_label.update(Text(weather_label(condition)))

        temperature = attrs.get("temperature")
        temp_unit = attrs.get("temperature_unit") or ""
        temp_text = Text(f"{temperature}{temp_unit}" if temperature is not None else "—")
        temp_label.update(apply_pending_suffix(temp_text, pending))

        detail = Text()
        humidity = attrs.get("humidity")
        wind_speed = attrs.get("wind_speed")
        if humidity is not None:
            detail.append(f"💧 {humidity}%")
        if wind_speed is not None:
            if detail.plain:
                detail.append("  ")
            wind_unit = attrs.get("wind_speed_unit") or ""
            detail.append(f"🌬 {wind_speed}{f' {wind_unit}' if wind_unit else ''}")
        detail_label.update(detail)
