# hatty — MIT License. See LICENSE file for details.
"""List (favorites) state and operations, extracted from HACLI."""

from hatty.ui.confirm_popup import ConfirmPopup
from hatty.ui.dashboard.screen import DashboardScreen

#: Bumped if the export payload shape ever changes incompatibly.
EXPORT_FORMAT_VERSION = 1


class ListController:
    """Owns the entity-list collections, selection, and undo/redo for
    membership toggles. UI plumbing (notify, popups, table refresh) goes
    through the app reference."""

    def __init__(self, app) -> None:
        self._app = app
        self.entity_lists: dict = {}
        self.list_names: list = []
        self.current_list_name: str | None = None
        self.last_list_name: str | None = None
        self.default_list_name: str | None = None
        self.manual_lists: set[str] = set()
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        # Transient (never persisted, #214): the one list currently unlocked for
        # removal. Every list starts locked; select_or_create re-locks it, so
        # unlocking never survives a switch away and back.
        self.unlocked_list: str | None = None

    def jump_target(self) -> str | None:
        """The list to jump back to: last shown, falling back to the default."""
        if self.last_list_name in self.list_names:
            return self.last_list_name
        if self.default_list_name in self.list_names:
            return self.default_list_name
        return None

    def reorder_lists(self, ordered_names: list[str]) -> None:
        """Reorder the lists collection (issue #212, mirrors column reordering).
        Persisted order is the *dict* insertion order of entity_lists, so this
        rebuilds the dict alongside list_names rather than just resequencing
        the name list."""
        order = [n for n in ordered_names if n in self.entity_lists]
        order += [n for n in self.list_names if n not in order]  # keep any omitted
        self.list_names = order
        self.entity_lists = {n: self.entity_lists[n] for n in order}
        self._app.persist("lists")

    def handle_popup_action(self, result: dict) -> None:
        app = self._app
        action = result.get("action")
        list_name = result.get("list_name")

        if action == "delete":
            if list_name not in self.entity_lists:
                return

            def _do_delete(confirmed, _name=list_name):
                if not confirmed:
                    return
                if _name not in self.entity_lists:
                    return
                del self.entity_lists[_name]
                self.list_names.remove(_name)
                self.manual_lists.discard(_name)
                app.notify_ctl.notify_lists.discard(_name)
                if self.unlocked_list == _name:
                    self.unlocked_list = None
                if self.current_list_name == _name:
                    self.current_list_name = None
                if self.default_list_name == _name:
                    self.default_list_name = None
                app.persist("lists", "manual_lists", "notify_lists", "default_list")
                app.notify(f"List '{_name}' deleted.", title="List Deleted")
                app._update_entities_display()
                app.refresh_table_log_scope()

            app.push_screen(ConfirmPopup(f"Delete list '{list_name}'?"), _do_delete)
        elif action == "set_default":
            self.default_list_name = list_name
            self.current_list_name = list_name
            self.last_list_name = list_name
            app.persist("default_list")
            app.notify(f"'{list_name}' set as default list.", title="Default List Set")
            app.set_title_based_on_focused_ui()
            app._update_entities_display()
            app.refresh_table_log_scope()
        elif action == "view_as_dashboard":
            if app.dash_ctl.preview_list_as_dashboard(list_name):
                app.push_screen(DashboardScreen(), lambda _: app.dash_ctl.cleanup_temp_dashboards())
        elif action == "rename":
            self.rename_list(list_name, result.get("new_name"))

    # ── Export / import ──────────────────────────────────────────────────────

    def to_export_payload(self, name: str) -> dict:
        """A JSON-serializable snapshot of list `name`, versioned so a future
        format change can be detected on import."""
        return {
            "hatty_list": EXPORT_FORMAT_VERSION,
            "name": name,
            "entities": list(self.entity_lists.get(name, [])),
            "manual": name in self.manual_lists,
            "notify": name in self._app.notify_ctl.notify_lists,
        }

    def import_from_payload(self, payload: dict) -> str:
        """Create a new list from a previously exported payload, deduplicating
        its name against the existing collection. Raises `ValueError` (with a
        user-facing message) if `payload` isn't a recognizable export. Returns
        the final list name."""
        if not isinstance(payload, dict) or payload.get("hatty_list") != EXPORT_FORMAT_VERSION:
            raise ValueError("Not a valid hatty list export file.")
        entities = payload.get("entities")
        if not isinstance(entities, list):
            raise ValueError("List export is missing its entities.")

        final = self._unique_name(str(payload.get("name") or "Imported"))
        self.entity_lists[final] = list(entities)
        self.list_names.append(final)
        if payload.get("manual"):
            self.manual_lists.add(final)
        if payload.get("notify"):
            self._app.notify_ctl.notify_lists.add(final)
        self._app.persist("lists", "manual_lists", "notify_lists")
        return final

    def _unique_name(self, name: str) -> str:
        """`name`, or `name (2)`, `name (3)`, ... if it's already taken."""
        final = name
        suffix = 2
        while final in self.entity_lists:
            final = f"{name} ({suffix})"
            suffix += 1
        return final

    def rename_list(self, old_name: str | None, new_name: str | None) -> None:
        app = self._app
        new_name = (new_name or "").strip()
        if not old_name or old_name not in self.entity_lists or not new_name or old_name == new_name:
            return
        if new_name in self.entity_lists:
            app.notify(f"A list named '{new_name}' already exists.", title="Rename Error", severity="error")
            return
        # Rebuild the dict in place (rather than pop+reinsert) so the renamed
        # list keeps its position — persisted order is entity_lists' dict order.
        self.entity_lists = {(new_name if n == old_name else n): v for n, v in self.entity_lists.items()}
        self.list_names = [new_name if n == old_name else n for n in self.list_names]
        if self.current_list_name == old_name:
            self.current_list_name = new_name
        if self.last_list_name == old_name:
            self.last_list_name = new_name
        if self.default_list_name == old_name:
            self.default_list_name = new_name
        if old_name in self.manual_lists:
            self.manual_lists.discard(old_name)
            self.manual_lists.add(new_name)
        if old_name in app.notify_ctl.notify_lists:
            app.notify_ctl.notify_lists.discard(old_name)
            app.notify_ctl.notify_lists.add(new_name)
        if self.unlocked_list == old_name:
            self.unlocked_list = new_name
        for entry in (*self.undo_stack, *self.redo_stack):
            if entry["list_name"] == old_name:
                entry["list_name"] = new_name
        app.persist("lists", "manual_lists", "notify_lists", "default_list")
        app.set_title_based_on_focused_ui()
        app._update_entities_display()
        app.refresh_table_log_scope()
        app.notify(f"Renamed list '{old_name}' to '{new_name}'.", title="List Renamed")

    def select_or_create(self, list_name: str) -> None:
        if list_name.lower() == "view all":
            self.current_list_name = None
        else:
            self.current_list_name = list_name
            self.last_list_name = list_name
            if list_name not in self.list_names:
                self.list_names.append(list_name)
                self.entity_lists[list_name] = []
            # An active free-text search takes priority in _currently_displayed_entities
            # and would otherwise keep showing stale results instead of the list (#211).
            self._app.search_term = ""
        # Every (re)entry into a list starts locked (issue #214) — unlocking
        # never survives switching away, even back to the same list.
        self.unlocked_list = None
        self._app.set_title_based_on_focused_ui()
        self._app._update_entities_display()
        self._app.refresh_table_log_scope()

    def is_locked(self, list_name: str) -> bool:
        """Whether removals from `list_name` currently require an unlock
        confirmation (issue #214). Transient — never persisted."""
        return list_name != self.unlocked_list

    def unlock(self, list_name: str) -> None:
        self.unlocked_list = list_name

    def lock(self, list_name: str) -> None:
        if self.unlocked_list == list_name:
            self.unlocked_list = None

    def apply_membership(self, list_name: str, entity_id: str, action: str) -> None:
        # `setdefault` re-creates a deleted list on undo rather than erroring; deleting
        # a list is out of scope for undo/redo, an accepted edge case, not a bug.
        current_list = self.entity_lists.setdefault(list_name, [])
        if action == "add" and entity_id not in current_list:
            current_list.append(entity_id)
        elif action == "remove" and entity_id in current_list:
            current_list.remove(entity_id)
        self._app.persist("lists")
        self._app._update_entities_display()
        if list_name == self.current_list_name:
            self._app.refresh_table_log_scope()

    def _freeze_visual_order(self, list_name: str, ordered_ids: list[str]) -> None:
        """Overwrite the stored list order with `ordered_ids` (the order currently
        on screen), keeping any member not currently displayed (e.g. its entity
        went offline) appended at the end so nothing is lost."""
        current = self.entity_lists.get(list_name, [])
        seen = set(ordered_ids)
        self.entity_lists[list_name] = list(ordered_ids) + [e for e in current if e not in seen]

    def set_manual(self, list_name: str) -> None:
        """Switch a list to manual sort, displaying whatever order is already
        stored (issue #213) — deliberately does *not* re-freeze from the
        current display. If it does, toggling a previously-curated list off
        (alphabetical) and back on would clobber the curated order with
        whatever was showing at that moment, which is alphabetical by
        definition since manual mode was off. Leaving the stored order alone
        means re-enabling always resumes exactly where it left off."""
        self.manual_lists.add(list_name)
        self._app.persist("manual_lists")
        self._app._update_entities_display()

    def disable_manual(self, list_name: str) -> None:
        """Switch a list back to alphabetical display (today's default). The
        stored order is left untouched — re-enabling manual mode (`set_manual`)
        resumes it."""
        self.manual_lists.discard(list_name)
        self._app.persist("manual_lists")
        self._app._update_entities_display()

    def reorder(self, list_name: str, ordered_ids: list[str], entity_id: str, delta: int) -> bool:
        """Move `entity_id` by `delta` positions within `ordered_ids` (the order
        currently on screen), freezing that as the list's new manual order —
        this is also how a list converts from alphabetical to manual on its
        first reorder. Returns False (no-op) at either edge or if `entity_id`
        isn't present."""
        if entity_id not in ordered_ids:
            return False
        i = ordered_ids.index(entity_id)
        j = i + delta
        if j < 0 or j >= len(ordered_ids):
            return False
        swapped = list(ordered_ids)
        swapped[i], swapped[j] = swapped[j], swapped[i]
        self._freeze_visual_order(list_name, swapped)
        self.manual_lists.add(list_name)
        self._app.persist("lists", "manual_lists")
        self._app._update_entities_display()
        return True

    def record_toggle(self, list_name: str, entity_id: str, action: str) -> None:
        self.undo_stack.append({"list_name": list_name, "entity_id": entity_id, "action": action})
        self.redo_stack.clear()

    def undo(self) -> None:
        if not self.undo_stack:
            self._app.notify("Nothing to undo.", title="Undo", severity="warning")
            return
        entry = self.undo_stack.pop()
        inverse = "add" if entry["action"] == "remove" else "remove"
        self.apply_membership(entry["list_name"], entry["entity_id"], inverse)
        self.redo_stack.append(entry)
        verb, prep = ("Restored", "to") if entry["action"] == "remove" else ("Removed", "from")
        self._app.notify(f"Undo: {verb} {entry['entity_id']} {prep} {entry['list_name']}", title="Undo")

    def redo(self) -> None:
        if not self.redo_stack:
            self._app.notify("Nothing to redo.", title="Redo", severity="warning")
            return
        entry = self.redo_stack.pop()
        self.apply_membership(entry["list_name"], entry["entity_id"], entry["action"])
        self.undo_stack.append(entry)
        verb, prep = ("Removed", "from") if entry["action"] == "remove" else ("Added", "to")
        self._app.notify(f"Redo: {verb} {entry['entity_id']} {prep} {entry['list_name']}", title="Redo")
