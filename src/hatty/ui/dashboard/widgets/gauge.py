# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label, Static

from hatty.types import Entity, EntityAttributes
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.dashboard.widgets.visuals import empty_bar, render_bar
from hatty.ui.entity_table import apply_pending_suffix, entity_unit, get_display_name_text

LOW_THRESHOLD = 0.2
MID_THRESHOLD = 0.5


def resolve_gauge_bounds(
    slot_min: float | None, slot_max: float | None, attrs: EntityAttributes
) -> tuple[float, float]:
    """Gauge bounds: explicit slot override > entity min/max attributes > 0-100."""
    min_v = slot_min if slot_min is not None else attrs.get("min")
    max_v = slot_max if slot_max is not None else attrs.get("max")
    try:
        min_v = float(min_v) if min_v is not None else 0.0
        max_v = float(max_v) if max_v is not None else 100.0
    except (TypeError, ValueError):
        return 0.0, 100.0
    if max_v <= min_v:
        return 0.0, 100.0
    return min_v, max_v


def gauge_level_class(value: float, min_v: float, max_v: float) -> str:
    frac = (value - min_v) / (max_v - min_v)
    frac = max(0.0, min(1.0, frac))
    if frac < LOW_THRESHOLD:
        return "-low"
    if frac < MID_THRESHOLD:
        return "-mid"
    return "-high"


class GaugeSlotWidget(EntitySlotWidget):
    """A numeric entity rendered as a min->max progress bar (e.g. battery %)."""

    DEFAULT_CSS = """
    GaugeSlotWidget {
        content-align: center middle;
    }
    GaugeSlotWidget #slot_name {
        text-style: bold;
    }
    GaugeSlotWidget #slot_value {
        text-style: bold;
    }
    GaugeSlotWidget #gauge_bar {
        color: $text-muted;
    }
    GaugeSlotWidget #gauge_bar.-low, GaugeSlotWidget #slot_value.-low {
        color: $error;
    }
    GaugeSlotWidget #gauge_bar.-mid, GaugeSlotWidget #slot_value.-mid {
        color: $warning;
    }
    GaugeSlotWidget #gauge_bar.-high, GaugeSlotWidget #slot_value.-high {
        color: $success;
    }
    """

    def __init__(
        self,
        entity_id: str | None,
        gauge_min: float | None = None,
        gauge_max: float | None = None,
        *,
        show_last_changed: bool = False,
    ):
        super().__init__(entity_id, show_last_changed=show_last_changed)
        self._gauge_min = gauge_min
        self._gauge_max = gauge_max

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        yield Label("", id="slot_value")
        yield Static("", id="gauge_bar")

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        value_label = self.query_one("#slot_value", Label)
        bar = self.query_one("#gauge_bar", Static)

        attrs = entity.get("attributes", {})
        unit = entity_unit(entity)
        state = entity.get("state", "")
        name_label.update(get_display_name_text(entity))

        try:
            value = float(state)
        except (TypeError, ValueError):
            value_label.update(apply_pending_suffix("—", pending))
            bar.update(empty_bar())
            value_label.set_classes("")
            bar.set_classes("")
            return

        min_v, max_v = resolve_gauge_bounds(self._gauge_min, self._gauge_max, attrs)
        level = gauge_level_class(value, min_v, max_v)
        value_label.update(apply_pending_suffix(f"{state}{unit}", pending))
        bar.update(render_bar(value, min_v, max_v))
        value_label.set_classes(level)
        bar.set_classes(level)
