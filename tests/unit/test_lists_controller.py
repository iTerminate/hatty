# hatty — MIT License. See LICENSE file for details.
"""Unit tests for ListController: selection, membership, undo/redo (issue #169)."""

from hatty.controllers.lists import ListController


class _StubNotifyCtl:
    def __init__(self):
        self.notify_lists: set[str] = set()


class _StubApp:
    """Records the interactions ListController drives, so tests can assert on
    them without booting the Textual app."""

    def __init__(self):
        self.persist_calls = []
        self.notifications = []
        self.display_updates = 0
        self.title_updates = 0
        # For the delete branch: push_screen(screen, callback) — invoke the
        # callback immediately with whatever confirmation the test wants.
        self.confirm_result = True
        self.pushed = []
        self.search_term = ""
        self.notify_ctl = _StubNotifyCtl()
        self.log_scope_refreshes = 0

    def persist(self, *keys):
        self.persist_calls.append(keys)

    def notify(self, message, **kwargs):
        self.notifications.append((message, kwargs))

    def _update_entities_display(self):
        self.display_updates += 1

    def set_title_based_on_focused_ui(self):
        self.title_updates += 1

    def refresh_table_log_scope(self):
        self.log_scope_refreshes += 1

    def push_screen(self, screen, callback=None):
        self.pushed.append(screen)
        if callback is not None:
            callback(self.confirm_result)


def _controller() -> ListController:
    return ListController(_StubApp())


# ── jump_target ───────────────────────────────────────────────────────────────


def test_jump_target_prefers_last_shown():
    ctl = _controller()
    ctl.list_names = ["A", "B"]
    ctl.last_list_name = "B"
    ctl.default_list_name = "A"
    assert ctl.jump_target() == "B"


def test_jump_target_falls_back_to_default():
    ctl = _controller()
    ctl.list_names = ["A", "B"]
    ctl.last_list_name = "gone"
    ctl.default_list_name = "A"
    assert ctl.jump_target() == "A"


def test_jump_target_none_when_neither_present():
    ctl = _controller()
    ctl.list_names = ["A"]
    ctl.last_list_name = None
    ctl.default_list_name = None
    assert ctl.jump_target() is None


# ── select_or_create ──────────────────────────────────────────────────────────


def test_select_or_create_view_all_clears_current():
    ctl = _controller()
    ctl.current_list_name = "A"
    ctl.select_or_create("View All")  # case-insensitive
    assert ctl.current_list_name is None


def test_select_or_create_new_list_is_appended():
    ctl = _controller()
    ctl.select_or_create("Kitchen")
    assert ctl.current_list_name == "Kitchen"
    assert ctl.last_list_name == "Kitchen"
    assert ctl.list_names == ["Kitchen"]
    assert ctl.entity_lists["Kitchen"] == []


def test_select_or_create_existing_list_not_duplicated():
    ctl = _controller()
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": ["light.a"]}
    ctl.select_or_create("Kitchen")
    assert ctl.list_names == ["Kitchen"]
    assert ctl.entity_lists["Kitchen"] == ["light.a"]


def test_select_or_create_clears_active_search_term():
    # search_term otherwise wins over current_list_name in
    # _currently_displayed_entities, leaving the table stuck on stale search
    # results instead of the list just selected (issue #211).
    ctl = _controller()
    ctl._app.search_term = "temp"
    ctl.select_or_create("Kitchen")
    assert ctl.current_list_name == "Kitchen"
    assert ctl._app.search_term == ""


# ── apply_membership ──────────────────────────────────────────────────────────


def test_apply_membership_add_appends_and_persists():
    ctl = _controller()
    ctl.apply_membership("Kitchen", "light.a", "add")
    assert ctl.entity_lists["Kitchen"] == ["light.a"]
    assert ("lists",) in ctl._app.persist_calls


def test_apply_membership_add_is_idempotent():
    ctl = _controller()
    ctl.entity_lists = {"Kitchen": ["light.a"]}
    ctl.apply_membership("Kitchen", "light.a", "add")
    assert ctl.entity_lists["Kitchen"] == ["light.a"]


def test_apply_membership_remove_guarded():
    ctl = _controller()
    ctl.entity_lists = {"Kitchen": []}
    ctl.apply_membership("Kitchen", "light.a", "remove")  # not present -> no error
    assert ctl.entity_lists["Kitchen"] == []


# ── undo / redo ───────────────────────────────────────────────────────────────


def test_record_toggle_clears_redo_stack():
    ctl = _controller()
    ctl.redo_stack = [{"list_name": "K", "entity_id": "x", "action": "add"}]
    ctl.record_toggle("Kitchen", "light.a", "add")
    assert ctl.undo_stack == [{"list_name": "Kitchen", "entity_id": "light.a", "action": "add"}]
    assert ctl.redo_stack == []


def test_undo_applies_inverse_action():
    ctl = _controller()
    ctl.entity_lists = {"Kitchen": ["light.a"]}
    ctl.record_toggle("Kitchen", "light.a", "add")
    ctl.undo()
    # Inverse of "add" is "remove".
    assert ctl.entity_lists["Kitchen"] == []
    assert ctl.redo_stack[-1]["action"] == "add"


def test_undo_redo_round_trip_restores_membership():
    ctl = _controller()
    ctl.entity_lists = {"Kitchen": ["light.a"]}
    ctl.record_toggle("Kitchen", "light.a", "add")
    ctl.undo()
    assert ctl.entity_lists["Kitchen"] == []
    ctl.redo()
    assert ctl.entity_lists["Kitchen"] == ["light.a"]
    assert ctl.undo_stack[-1]["action"] == "add"


def test_undo_empty_stack_warns_and_does_nothing():
    ctl = _controller()
    ctl.undo()
    assert ctl.undo_stack == []
    assert ctl._app.notifications[-1][1].get("severity") == "warning"


def test_redo_empty_stack_warns_and_does_nothing():
    ctl = _controller()
    ctl.redo()
    assert ctl.redo_stack == []
    assert ctl._app.notifications[-1][1].get("severity") == "warning"


# ── handle_popup_action ───────────────────────────────────────────────────────


def test_handle_popup_set_default():
    ctl = _controller()
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": []}
    ctl.handle_popup_action({"action": "set_default", "list_name": "Kitchen"})
    assert ctl.default_list_name == "Kitchen"
    assert ctl.current_list_name == "Kitchen"
    assert ctl.last_list_name == "Kitchen"


def test_handle_popup_delete_confirmed_removes_list():
    ctl = _controller()
    ctl._app.confirm_result = True
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": ["light.a"]}
    ctl.current_list_name = "Kitchen"
    ctl.default_list_name = "Kitchen"
    ctl.handle_popup_action({"action": "delete", "list_name": "Kitchen"})
    assert "Kitchen" not in ctl.entity_lists
    assert ctl.list_names == []
    assert ctl.current_list_name is None
    assert ctl.default_list_name is None


def test_handle_popup_delete_cancelled_is_noop():
    ctl = _controller()
    ctl._app.confirm_result = False
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": ["light.a"]}
    ctl.handle_popup_action({"action": "delete", "list_name": "Kitchen"})
    assert ctl.entity_lists == {"Kitchen": ["light.a"]}
    assert ctl.list_names == ["Kitchen"]


def test_handle_popup_delete_unknown_list_returns_early():
    ctl = _controller()
    ctl.handle_popup_action({"action": "delete", "list_name": "Ghost"})
    # Never even reached the confirm popup.
    assert ctl._app.pushed == []


def test_handle_popup_delete_drops_notify_designation():
    # issue #24: any list can be a notification source, so deleting one must
    # also clear its designation rather than leaving a dangling name.
    ctl = _controller()
    ctl._app.confirm_result = True
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": ["switch.fan"]}
    ctl._app.notify_ctl.notify_lists = {"Kitchen"}
    ctl.handle_popup_action({"action": "delete", "list_name": "Kitchen"})
    assert "Kitchen" not in ctl.entity_lists
    assert ctl._app.notify_ctl.notify_lists == set()
    assert ("lists", "manual_lists", "notify_lists", "default_list") in ctl._app.persist_calls


# ── rename_list ───────────────────────────────────────────────────────────────


def test_rename_list_preserves_position_and_membership():
    ctl = _controller()
    ctl.list_names = ["Kitchen", "Office", "Garage"]
    ctl.entity_lists = {"Kitchen": ["light.a"], "Office": ["light.b"], "Garage": ["light.c"]}
    ctl.rename_list("Office", "Study")
    assert ctl.list_names == ["Kitchen", "Study", "Garage"]
    assert list(ctl.entity_lists.keys()) == ["Kitchen", "Study", "Garage"]
    assert ctl.entity_lists["Study"] == ["light.b"]
    assert ("lists", "manual_lists", "notify_lists", "default_list") in ctl._app.persist_calls


def test_rename_list_updates_current_last_and_default():
    ctl = _controller()
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": []}
    ctl.current_list_name = "Kitchen"
    ctl.last_list_name = "Kitchen"
    ctl.default_list_name = "Kitchen"
    ctl.rename_list("Kitchen", "Living Room")
    assert ctl.current_list_name == "Living Room"
    assert ctl.last_list_name == "Living Room"
    assert ctl.default_list_name == "Living Room"


def test_rename_list_carries_manual_lock_and_undo_state():
    ctl = _controller()
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": ["light.a"]}
    ctl.manual_lists = {"Kitchen"}
    ctl.unlocked_list = "Kitchen"
    ctl.undo_stack = [{"list_name": "Kitchen", "entity_id": "light.a", "action": "add"}]
    ctl.redo_stack = [{"list_name": "Kitchen", "entity_id": "light.a", "action": "remove"}]
    ctl.rename_list("Kitchen", "Study")
    assert ctl.manual_lists == {"Study"}
    assert ctl.unlocked_list == "Study"
    assert ctl.undo_stack[0]["list_name"] == "Study"
    assert ctl.redo_stack[0]["list_name"] == "Study"


def test_rename_list_carries_notify_designation():
    ctl = _controller()
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": ["light.a"]}
    ctl._app.notify_ctl.notify_lists = {"Kitchen"}
    ctl.rename_list("Kitchen", "Study")
    assert ctl._app.notify_ctl.notify_lists == {"Study"}


def test_rename_list_refuses_collision():
    ctl = _controller()
    ctl.list_names = ["Kitchen", "Office"]
    ctl.entity_lists = {"Kitchen": ["light.a"], "Office": []}
    ctl.rename_list("Kitchen", "Office")
    assert ctl.list_names == ["Kitchen", "Office"]
    assert ctl.entity_lists["Kitchen"] == ["light.a"]
    assert ctl._app.notifications[-1][1].get("severity") == "error"


def test_rename_list_unknown_name_is_noop():
    ctl = _controller()
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": []}
    ctl.rename_list("Ghost", "New")
    assert ctl.list_names == ["Kitchen"]
    assert ctl._app.persist_calls == []


def test_rename_list_unchanged_name_is_noop():
    ctl = _controller()
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": []}
    ctl.rename_list("Kitchen", "Kitchen")
    assert ctl._app.persist_calls == []


def test_rename_list_blank_new_name_is_noop():
    ctl = _controller()
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": []}
    ctl.rename_list("Kitchen", "   ")
    assert ctl.list_names == ["Kitchen"]


def test_handle_popup_rename_routes_to_rename_list():
    ctl = _controller()
    ctl.list_names = ["Kitchen"]
    ctl.entity_lists = {"Kitchen": []}
    ctl.handle_popup_action({"action": "rename", "list_name": "Kitchen", "new_name": "Study"})
    assert ctl.list_names == ["Study"]
