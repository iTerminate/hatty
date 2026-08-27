# hatty — MIT License. See LICENSE file for details.
from datetime import datetime, timezone
from typing import cast

from rich.text import Text
from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.widgets.data_table import CellDoesNotExist, RowDoesNotExist

from hatty.const import DEFAULT_COLUMNS
from hatty.types import Entity
from hatty.ui.dashboard.widgets.visuals import entity_glyph

# States that mean the entity is dead/unreachable; rendered dimmed on both the
# entity table and the device tree so dead devices are scannable at a glance.
DEAD_STATES = {"unavailable", "unknown"}


def is_dead(entity: Entity) -> bool:
    return entity.get("state") in DEAD_STATES


def format_relative(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return iso_str

    seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _is_in_list(entity: Entity, lists, current_list_name) -> bool:
    return entity.get("entity_id") in (lists.get(current_list_name) or [])


def entity_matches(entity: Entity, term: str) -> bool:
    # Multi-word terms match "skip words" (#241): each word just has to appear
    # somewhere in the haystack, in any order — "living lamp" matches "Living Room Lamp".
    haystack = " ".join(
        (
            str(entity.get("entity_id", "")),
            str(entity.get("state", "")),
            get_display_name(entity),
        )
    ).lower()
    return all(word in haystack for word in term.lower().split())


def apply_pending_suffix(value: str | Text, pending: str | None) -> Text:
    # Always return a Text: a raw str would be parsed as Rich markup by Textual, so
    # an HA-derived state like "[red]" restyles the UI or crashes rendering (#157).
    # A plain-str base gets escaped; an already-styled Text base is preserved.
    base = value if isinstance(value, Text) else Text(str(value))
    if pending == "pending":
        out = base.copy()
        out.append(" ⏳")
        out.stylize("dim italic")
        return out
    if pending == "stalled":
        out = base.copy()
        out.append(" ⚠ unresponsive")
        out.stylize("bold red")
        return out
    return base


def _format_state(entity: Entity, pending: str | None) -> Text:
    return apply_pending_suffix(entity.get("state", ""), pending)


def _format_value(entity: Entity, pending: str | None) -> Text:
    state = entity.get("state", "")
    return apply_pending_suffix(f"{state}{entity_unit(entity)}", pending)


def is_numeric_state(entity: Entity) -> bool:
    try:
        float(entity.get("state", ""))
    except (ValueError, TypeError):
        return False
    return True


def get_display_name(entity: Entity) -> str:
    override = entity.get("_local_name_override")
    return override or entity.get("attributes", {}).get("friendly_name") or entity.get("entity_id", "")


def get_display_name_text(entity: Entity) -> Text:
    """get_display_name wrapped in a markup-safe Text for direct rendering by
    Textual widgets (the plain str is kept for search/sort). See #157: an HA
    friendly_name containing Rich markup would otherwise restyle or crash the UI."""
    return Text(get_display_name(entity))


def entity_unit(entity: Entity) -> str:
    """The entity's unit_of_measurement, or "" when absent — the one-liner that
    used to be repeated at ~10 call sites (#164)."""
    return entity.get("attributes", {}).get("unit_of_measurement") or ""


def entity_title(
    entity: Entity, *, mode_label: str | None = None, extra_count: int = 0, show_unit: bool = True
) -> Text:
    """The shared `name (+N more) — state{unit}  [mode]` header line, as a
    markup-safe Text (centralizes the #157 sanitization). Callers append their own
    trailing context (e.g. a graph window badge) to the returned Text."""
    text = Text(get_display_name(entity))
    if extra_count:
        text.append(f" +{extra_count} more")
    text.append(" — ")
    text.append(entity.get("state", ""))
    if show_unit:
        text.append(entity_unit(entity))
    if mode_label:
        text.append(f"  [{mode_label}]")
    return text


# key -> (header label, extractor(entity, entity_lists, current_list_name, pending_status))
COLUMNS = {
    "icon": ("Icon", lambda e, lists, cur, pending: entity_glyph(e)),
    "name": ("Friendly Name", lambda e, lists, cur, pending: get_display_name(e)),
    "state": ("State", lambda e, lists, cur, pending: _format_state(e, pending)),
    "unit": ("Unit", lambda e, lists, cur, pending: entity_unit(e)),
    "value": ("Value", lambda e, lists, cur, pending: _format_value(e, pending)),
    "entity_id": ("Entity ID", lambda e, lists, cur, pending: e.get("entity_id", "")),
    "device_class": ("Class", lambda e, lists, cur, pending: e.get("attributes", {}).get("device_class") or ""),
    "last_changed": ("Changed", lambda e, lists, cur, pending: format_relative(e.get("last_changed", ""))),
    "in_list": ("✓", lambda e, lists, cur, pending: "✓" if _is_in_list(e, lists, cur) else ""),
}


class EntitiesTable(DataTable):
    DEFAULT_CSS = """
    EntitiesTable {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entity_lists: dict = {}
        self.current_list_name: str | None = None
        self._manual_lists: set[str] = set()
        self._columns: list[str] = []
        self.pending_status: dict[str, str] = {}
        self._last_row_keys: list[str] = []
        self._alerted_ids: set[str] = set()

    def update_table_data(
        self,
        entities_to_display: list,
        entity_lists: dict,
        current_list_name: str | None,
        columns: list[str] | None = None,
        pending_status: dict[str, str] | None = None,
        manual_lists: set[str] | None = None,
        alerted_ids: set[str] | None = None,
    ):
        self.entity_lists = entity_lists
        self.current_list_name = current_list_name
        self._manual_lists = manual_lists or set()
        self._columns = list(columns or DEFAULT_COLUMNS)
        self.pending_status = pending_status or {}
        self._alerted_ids = alerted_ids or set()

        self._update_table_rows(self._get_sorted_entities(entities_to_display))

    def ordered_entity_ids(self) -> list[str]:
        """The entity_ids currently displayed, top to bottom — what a reorder
        action should treat as "the visible order" (issue #213)."""
        return list(self._last_row_keys)

    def _get_sorted_entities(self, entities: list) -> list:
        current_list = self.entity_lists.get(self.current_list_name) or []
        in_list = [e for e in entities if e.get("entity_id") in current_list]
        others = [e for e in entities if e.get("entity_id") not in current_list]

        def sort_key(entity):
            return get_display_name(entity).lower()

        if self.current_list_name and self.current_list_name in self._manual_lists:
            position = {entity_id: i for i, entity_id in enumerate(current_list)}
            in_list.sort(key=lambda e: position.get(e.get("entity_id"), len(position)))
        else:
            in_list.sort(key=sort_key)
        others.sort(key=sort_key)
        return in_list + others

    @staticmethod
    def _style_cell(value: str | Text, dead: bool, alerted: bool = False) -> Text:
        """Return the cell value as a Text (escaping any Rich markup in HA-derived
        strings — #157), dimmed when the entity is dead and reverse-video while it's
        in its post-change alert highlight window (issue #224 — a plain, theme-agnostic
        way to make a row stand out that still combines with the dim treatment)."""
        if isinstance(value, Text):
            text = value.copy()
            if dead:
                text.stylize("dim")
        else:
            text = Text(str(value), style="dim" if dead else "")
        if alerted:
            text.stylize("reverse")
        return text

    def _update_table_rows(self, entities: list):
        valid_entities = [e for e in entities if isinstance(e, dict) and "entity_id" in e]
        new_keys = [e["entity_id"] for e in valid_entities]

        if new_keys == self._last_row_keys and list(self.columns.keys()) == self._columns:
            for entity in valid_entities:
                pending = self.pending_status.get(entity["entity_id"])
                dead = is_dead(cast(Entity, entity))
                alerted = entity["entity_id"] in self._alerted_ids
                for key in self._columns:
                    if key not in COLUMNS:
                        continue
                    value = COLUMNS[key][1](entity, self.entity_lists, self.current_list_name, pending)
                    self.update_cell(entity["entity_id"], key, self._style_cell(value, dead, alerted))
            return

        selected_entity_id = None
        selected_column = 0
        if self.row_count > 0:
            try:
                cell_key = self.coordinate_to_cell_key(Coordinate(self.cursor_row, 0))
                selected_entity_id = cell_key.row_key.value
                selected_column = self.cursor_column
            except CellDoesNotExist:
                pass

        self.clear(columns=True)
        for key in self._columns:
            header, _ = COLUMNS.get(key, (key, None))
            self.add_column(header, key=key)

        for entity in valid_entities:
            pending = self.pending_status.get(entity["entity_id"])
            dead = is_dead(cast(Entity, entity))
            alerted = entity["entity_id"] in self._alerted_ids
            row = [
                self._style_cell(
                    COLUMNS[key][1](entity, self.entity_lists, self.current_list_name, pending), dead, alerted
                )
                for key in self._columns
                if key in COLUMNS
            ]
            self.add_row(*row, key=entity["entity_id"])

        if self.row_count > 0 and selected_entity_id:
            try:
                target_row = self.get_row_index(selected_entity_id)
                self.move_cursor(row=target_row, column=selected_column, animate=False)
            except RowDoesNotExist:
                self.move_cursor(row=0, column=0, animate=False)

        self._last_row_keys = new_keys

    def jump_cursor_to_row_key(self, row_key: str) -> bool:
        try:
            target_row = self.get_row_index(row_key)
        except RowDoesNotExist:
            return False
        self.move_cursor(row=target_row, column=self.cursor_column, animate=False)
        return True
