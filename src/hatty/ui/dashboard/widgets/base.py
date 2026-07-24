# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Label, Static

from hatty.types import Entity

if TYPE_CHECKING:
    from hatty.main import HACLI


def slot_label(slot: dict | None) -> str:
    if not slot:
        return "Empty"
    label = slot["widget_type"].title()
    entity_id = slot.get("entity_id")
    return f"{label}\n{entity_id}" if entity_id else label


class EntitySlotWidget(Vertical):
    """Base for dashboard slot content that tracks one entity_id and refreshes in place."""

    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    DEFAULT_CSS = """
    EntitySlotWidget {
        height: 100%;
    }
    EntitySlotWidget.-alerted {
        background: $accent 30%;
        border: round $accent;
    }
    """

    def __init__(self, entity_id: str | None):
        super().__init__()
        self.entity_id = entity_id

    def on_mount(self) -> None:
        entity = self.app.find_entity(self.entity_id) if self.entity_id else None
        self.update_entity(entity)

    def update_entity(self, entity: Entity | None, pending: str | None = None) -> None:
        """Template method: owns the empty-slot guard once for every subclass and
        delegates the populated path to `_render_entity`. Subclasses implement
        `_render_entity` (and override `_render_empty` only if blanking needs more
        than the labels). Note: `_render` is reserved by Textual's Widget."""
        if not self.entity_id or entity is None:
            self._render_empty()
            return
        self._render_entity(entity, pending)

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        raise NotImplementedError

    def _render_empty(self) -> None:
        """Blank every text child and drop its state-modifier CSS classes, then
        mark the name slot 'No entity'. Subclasses whose empty state needs more —
        a plot reset, a cached-attrs reset — override this, usually calling super()."""
        for child in self.query(Static):  # Label subclasses Static; typed so .update resolves
            child.set_classes("")
            child.update("")
        self.query_one("#slot_name", Label).update("No entity")


# widget_type -> factory(slot) -> Widget. The imports stay inside the
# factories: the widget modules import EntitySlotWidget from this module, so a
# module-level import here would be circular.


def _single_entity_factory(module_name: str, class_name: str):
    def factory(slot: dict):
        import importlib

        cls = getattr(importlib.import_module(module_name), class_name)
        return cls(slot.get("entity_id"))

    return factory


def _gauge_factory(slot: dict) -> Widget:
    from hatty.ui.dashboard.widgets.gauge import GaugeSlotWidget

    return GaugeSlotWidget(slot.get("entity_id"), gauge_min=slot.get("gauge_min"), gauge_max=slot.get("gauge_max"))


def _panel_factory(slot: dict) -> Widget:
    from hatty.ui.dashboard.widgets.panel import PanelSlotWidget

    return PanelSlotWidget(slot.get("entity_ids") or [])


def _split_factory(slot: dict) -> Widget:
    from hatty.ui.dashboard.widgets.split import SplitSlotWidget

    # A split without a usable children fragment falls back to the label
    # placeholder instead of crashing on malformed config.
    if isinstance(slot.get("children"), dict):
        return SplitSlotWidget(slot)
    return Static(slot_label(slot))


WIDGET_FACTORIES = {
    "graph": _single_entity_factory("hatty.ui.dashboard.widgets.graph", "GraphSlotWidget"),
    "switch": _single_entity_factory("hatty.ui.dashboard.widgets.switch", "SwitchSlotWidget"),
    "light": _single_entity_factory("hatty.ui.dashboard.widgets.light", "LightSlotWidget"),
    "sensor": _single_entity_factory("hatty.ui.dashboard.widgets.text", "TextSlotWidget"),
    "binary_sensor": _single_entity_factory("hatty.ui.dashboard.widgets.binary_sensor", "BooleanSensorSlotWidget"),
    "thermostat": _single_entity_factory("hatty.ui.dashboard.widgets.thermostat", "ThermostatSlotWidget"),
    "cover": _single_entity_factory("hatty.ui.dashboard.widgets.cover", "CoverSlotWidget"),
    "lock": _single_entity_factory("hatty.ui.dashboard.widgets.lock", "LockSlotWidget"),
    "media_player": _single_entity_factory("hatty.ui.dashboard.widgets.media_player", "MediaPlayerSlotWidget"),
    "fan": _single_entity_factory("hatty.ui.dashboard.widgets.fan", "FanSlotWidget"),
    "weather": _single_entity_factory("hatty.ui.dashboard.widgets.weather", "WeatherSlotWidget"),
    "gauge": _gauge_factory,
    "panel": _panel_factory,
    "split": _split_factory,
}


def build_slot_content(slot: dict | None) -> Widget:
    if not slot:
        return Static("Empty", id="slot_empty")

    factory = WIDGET_FACTORIES.get(slot["widget_type"])
    if factory is None:
        return Static(slot_label(slot))
    return factory(slot)
