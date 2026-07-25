# hatty — MIT License. See LICENSE file for details.
"""Two-step widget-type + entity picker for assigning a dashboard slot.

One `ModalScreen`, `self._step` is `"type"` or `"entity"`. Step 1 shows only
the widget-type `Select`; advancing switches to step 2, a live-filtered
entity picker (reusing `EntitiesTable` for its virtualized rendering) over
`self.parent.all_entities`, plus a synthetic "no entity" row. `escape` in step
2 returns to step 1 rather than dismissing the popup.

When the chosen type is `"panel"`, picking a row doesn't dismiss the popup —
it appends the entity to a running list and keeps the picker open ("pick one,
add, continue"); a separate done button finishes the flow and dismisses with
`entity_ids` instead of a single `entity_id`.
"""

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.events import Key
from textual.widgets import Button, DataTable, Footer, Input, Label, ListItem, ListView, Select

from hatty.const import WIDGET_TYPE_DOMAINS, WIDGET_TYPES
from hatty.ui.entity_table import EntitiesTable, entity_matches, get_display_name, is_numeric_state
from hatty.ui.popup_base import PopupScreen
from hatty.ui.search_input import SearchInput

if TYPE_CHECKING:
    from hatty.main import HACLI

NO_ENTITY_LABEL = "(no entity)"
NO_ENTITY_ROW = {"entity_id": "", "attributes": {"friendly_name": NO_ENTITY_LABEL}, "state": ""}


class DashboardSlotPopup(PopupScreen):
    parent: "HACLI"  # this popup's parent is always the app (annotation only, no runtime effect)

    AUTO_FOCUS = "#widget_type_select"

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel", show=False),
        # Panel/fill's accumulated-entities box (issue #254): reorder and remove
        # only apply while that box is focused (guarded in the actions below), so
        # these are plain (non-priority) bindings — a priority binding on "delete"
        # would intercept it ahead of Input's own delete_right while the search
        # box is focused, breaking forward-delete text editing there.
        Binding("shift+up", "reorder_selected(-1)", "Move Up", show=False),
        Binding("shift+down", "reorder_selected(1)", "Move Down", show=False),
        Binding("delete", "remove_selected", "Remove", show=False),
    ]

    DEFAULT_CSS = """
    #dashboard_slot_container {
        width: 70;
    }
    #dashboard_slot_container Label {
        margin-bottom: 1;
        text-style: bold;
    }
    #dashboard_slot_container Select {
        margin-bottom: 1;
    }
    #dashboard_slot_container SearchInput {
        margin-bottom: 1;
    }
    #entity_picker_table {
        height: 8;
        border: solid $accent;
    }
    #panel_added_hint {
        text-style: none;
        color: $text-muted;
    }
    #panel_added_list {
        height: 6;
        border: solid $accent;
        margin-bottom: 1;
    }
    #panel_added_list .panel-item-empty {
        color: $text-muted;
    }
    #gauge_bounds_row {
        height: 3;
        margin-bottom: 1;
    }
    #gauge_bounds_row Input {
        width: 1fr;
        margin-right: 1;
    }
    """

    def __init__(self, slot: dict | None, fill_mode: bool = False):
        super().__init__(id="dashboard_slot_popup")
        self._slot = slot
        self._fill_mode = fill_mode
        self._current_entity_id: str | None = slot.get("entity_id") if slot else None
        # Also doubles as the accumulated entity list in fill mode (issue #218).
        self._panel_entity_ids: list[str] = list(slot.get("entity_ids", [])) if slot else []
        self._gauge_min: float | None = slot.get("gauge_min") if slot else None
        self._gauge_max: float | None = slot.get("gauge_max") if slot else None
        self._step = "type"
        self._select_initialized = False

    def _type_choices(self) -> list[str]:
        # Fill mode packs one widget per entity into a fresh split; a "panel" is
        # itself a multi-entity container, so it doesn't make sense as the fill type.
        if self._fill_mode:
            return [wt for wt in WIDGET_TYPES if wt != "panel"]
        return WIDGET_TYPES

    def compose(self) -> ComposeResult:
        # Fall back to the default for types the popup can't assign (a split
        # pane's "split", or anything unrecognized) — the Select would raise
        # InvalidSelectValueError on a value outside WIDGET_TYPES.
        type_choices = self._type_choices()
        current_type = self._slot["widget_type"] if self._slot else type_choices[0]
        if current_type not in type_choices:
            current_type = type_choices[0]

        with Container(id="dashboard_slot_container", classes="popup-container"):
            yield Label("Configure Widget Slot" if not self._fill_mode else "Fill Pane — pick a type, then entities")
            yield Select(
                [(wt.replace("_", " ").title(), wt) for wt in type_choices],
                value=current_type,
                allow_blank=False,
                id="widget_type_select",
            )
            yield Button("Next", id="btn_next_step")
            yield SearchInput(id="entity_search_input")
            with Horizontal(id="gauge_bounds_row"):
                yield Input(placeholder="min (auto)", id="gauge_min_input")
                yield Input(placeholder="max (auto)", id="gauge_max_input")
            yield EntitiesTable(id="entity_picker_table", cursor_type="row")
            yield Label("Selected — Shift+↑/↓ reorder · Del remove", id="panel_added_hint")
            yield ListView(id="panel_added_list")
            yield Button("Done", id="btn_panel_done")
            yield Footer()

    def on_mount(self) -> None:
        self._rebuild_panel_added_list()
        self._show_step("type")

    def _show_step(self, step: str) -> None:
        self._step = step
        is_entity_step = step == "entity"
        self.query_one("#widget_type_select").display = not is_entity_step
        self.query_one("#btn_next_step").display = not is_entity_step
        self.query_one("#entity_search_input").display = is_entity_step
        self.query_one("#entity_picker_table").display = is_entity_step
        if is_entity_step:
            self._update_mode_visibility()
        else:
            self.query_one("#panel_added_hint").display = False
            self.query_one("#panel_added_list").display = False
            self.query_one("#btn_panel_done").display = False
            self.query_one("#gauge_bounds_row").display = False

    def _advance_to_entity_step(self) -> None:
        self._show_step("entity")
        self._update_entity_table()
        if self._current_entity_id:
            self.query_one("#entity_picker_table", EntitiesTable).jump_cursor_to_row_key(self._current_entity_id)
        self.query_one("#entity_search_input", SearchInput).action_focus_display()

    def _is_panel_mode(self) -> bool:
        return self.query_one("#widget_type_select", Select).value == "panel"

    def _is_gauge_mode(self) -> bool:
        return self.query_one("#widget_type_select", Select).value == "gauge"

    def _is_multi_add(self) -> bool:
        """True whenever the entity picker accumulates several entities instead
        of dismissing on the first pick: a real "panel" slot, or fill mode
        (issue #218), which packs one widget per entity into a fresh split."""
        return self._is_panel_mode() or self._fill_mode

    def _update_mode_visibility(self) -> None:
        is_multi = self._is_multi_add()
        # Gauge bounds are per-slot overrides; fill mode packs many entities under
        # one type, so there's no single min/max to offer.
        is_gauge = self._is_gauge_mode() and not self._fill_mode
        self.query_one("#panel_added_hint").display = is_multi
        self.query_one("#panel_added_list").display = is_multi
        self.query_one("#btn_panel_done").display = is_multi
        self.query_one("#gauge_bounds_row").display = is_gauge
        if is_gauge:
            if self._gauge_min is not None:
                self.query_one("#gauge_min_input", Input).value = f"{self._gauge_min:g}"
            if self._gauge_max is not None:
                self.query_one("#gauge_max_input", Input).value = f"{self._gauge_max:g}"

    def _relevant_entities(self) -> list[dict]:
        widget_type = self.query_one("#widget_type_select", Select).value
        entities = self.parent.all_entities
        if widget_type == "graph":
            # Binary sensors graph as 0/1 step timelines, so they qualify too.
            return [
                e for e in entities if is_numeric_state(e) or e.get("entity_id", "").startswith("binary_sensor.")
            ]
        if widget_type == "gauge":
            return [e for e in entities if is_numeric_state(e)]
        domain = WIDGET_TYPE_DOMAINS.get(cast(str, widget_type))
        if domain:
            return [e for e in entities if e.get("entity_id", "").split(".")[0] == domain]
        return entities

    def _update_entity_table(self) -> None:
        term = self.query_one("#entity_search_input", SearchInput).value.strip().lower()
        candidates = [NO_ENTITY_ROW, *self._relevant_entities()]
        if term:
            candidates = [e for e in candidates if entity_matches(e, term)]

        self.query_one("#entity_picker_table", EntitiesTable).update_table_data(
            entities_to_display=candidates,
            entity_lists={},
            current_list_name=None,
            columns=["name", "entity_id"],
        )

    def on_search_input_search_changed(self, event: SearchInput.SearchChanged) -> None:
        event.stop()
        self._update_entity_table()

    def on_search_input_search_submitted(self, event: SearchInput.SearchSubmitted) -> None:
        event.stop()
        self.query_one("#entity_picker_table", EntitiesTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "entity_picker_table":
            return
        entity_id = event.row_key.value or None
        if self._is_multi_add():
            self._add_panel_entity(entity_id)
        else:
            self._submit(entity_id)

    def _submit(self, entity_id: str | None) -> None:
        widget_type = self.query_one("#widget_type_select", Select).value
        result = {"widget_type": widget_type, "entity_id": entity_id}
        if widget_type == "gauge":
            # Blank inputs mean "auto" (entity min/max attrs, else 0-100); the keys
            # are only present when overridden so other slots' config shape is unchanged.
            for key, input_id in (("gauge_min", "#gauge_min_input"), ("gauge_max", "#gauge_max_input")):
                raw = self.query_one(input_id, Input).value.strip()
                if raw:
                    try:
                        result[key] = float(raw)
                    except ValueError:
                        pass
        self.dismiss(result)

    def _entity_label(self, entity_id: str) -> str:
        return get_display_name(self.parent.find_entity(entity_id) or {"entity_id": entity_id})

    def _empty_placeholder(self) -> ListItem:
        return ListItem(Label("(none yet)", classes="panel-item-empty"))

    def _rebuild_panel_added_list(self) -> None:
        """Full clear+repopulate of the accumulated-entities box (issue #254) —
        only used on mount, where there's no existing mounted rows to race
        against. Add/remove/reorder below mutate the ListView incrementally
        instead, since immediately setting `.index` right after a clear+append
        can post a Highlighted message for a not-yet-mounted child (see
        ListPopup._relabel's docstring for the same gotcha)."""
        list_view = self.query_one("#panel_added_list", ListView)
        list_view.clear()
        if not self._panel_entity_ids:
            list_view.append(self._empty_placeholder())
            return
        for eid in self._panel_entity_ids:
            list_view.append(ListItem(Label(self._entity_label(eid))))

    def _add_panel_entity(self, entity_id: str | None) -> None:
        if not entity_id:
            return
        list_view = self.query_one("#panel_added_list", ListView)
        if entity_id in self._panel_entity_ids:
            index = self._panel_entity_ids.index(entity_id)
            self._panel_entity_ids.remove(entity_id)
            list_view.pop(index)
            if not self._panel_entity_ids:
                list_view.append(self._empty_placeholder())
        else:
            if not self._panel_entity_ids:
                list_view.pop(0)  # drop the empty-state placeholder
            self._panel_entity_ids.append(entity_id)
            list_view.append(ListItem(Label(self._entity_label(entity_id))))
        self._update_entity_table()
        self.set_focus(self.query_one("#entity_picker_table"))

    def action_reorder_selected(self, delta: int) -> None:
        """Shift+↑/↓ (issue #254): reorder the highlighted row in the
        accumulated-entities box — order matters, a panel renders entities in
        list order and Fill creates one widget per entity in that order.
        Guarded to the box itself so it's a no-op with focus elsewhere."""
        list_view = self.query_one("#panel_added_list", ListView)
        if self.focused is not list_view or not self._panel_entity_ids:
            return
        index = list_view.index
        if index is None:
            return
        target = index + delta
        if not (0 <= target < len(self._panel_entity_ids)):
            return
        ids = self._panel_entity_ids
        ids[index], ids[target] = ids[target], ids[index]
        # Relabel existing rows in place rather than clear+append — no new rows
        # are mounted, so setting `.index` right after is safe.
        for item, eid in zip(list_view.children, ids):
            cast(Label, item.children[0]).update(self._entity_label(eid))
        list_view.index = target

    def action_remove_selected(self) -> None:
        """Del (issue #254): remove the highlighted row from the
        accumulated-entities box directly, instead of having to re-find and
        re-select the entity in the picker table."""
        list_view = self.query_one("#panel_added_list", ListView)
        if self.focused is not list_view or not self._panel_entity_ids:
            return
        index = list_view.index
        if index is None:
            return
        del self._panel_entity_ids[index]
        list_view.pop(index)
        if not self._panel_entity_ids:
            list_view.append(self._empty_placeholder())

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "widget_type_select":
            return
        # The Select posts a Changed for its initial value on mount; skip it so
        # AUTO_FOCUS keeps the type select focused when the popup opens.
        if not self._select_initialized:
            self._select_initialized = True
            return
        if self._step == "type":
            self.set_focus(self.query_one("#btn_next_step"))

    def on_key(self, event: Key) -> None:
        if self._step == "type":
            focused = self.focused
            if event.key == "right" and focused is self.query_one("#widget_type_select"):
                self.set_focus(self.query_one("#btn_next_step"))
                event.prevent_default()
            elif event.key == "left" and focused is self.query_one("#btn_next_step"):
                self.set_focus(self.query_one("#widget_type_select"))
                event.prevent_default()
        elif self._step == "entity" and self._is_multi_add():
            focused = self.focused
            if event.key == "right" and focused is self.query_one("#entity_search_input"):
                self.set_focus(self.query_one("#btn_panel_done"))
                event.prevent_default()
            elif event.key == "left" and focused is self.query_one("#btn_panel_done"):
                self.set_focus(self.query_one("#entity_search_input"))
                event.prevent_default()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_next_step":
            self._advance_to_entity_step()
        elif event.button.id == "btn_panel_done":
            widget_type = self.query_one("#widget_type_select", Select).value
            self.dismiss({"widget_type": widget_type, "entity_id": None, "entity_ids": list(self._panel_entity_ids)})

    def action_cancel(self) -> None:
        if self._step == "entity":
            search_input = self.query_one("#entity_search_input", SearchInput)
            if search_input.value:
                search_input.value = ""
                self._update_entity_table()
                return
            self._show_step("type")
            return
        self.dismiss(None)
