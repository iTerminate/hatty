# hatty — MIT License. See LICENSE file for details.
"""Unit tests for the keybinding registry (controllers/keybindings.py).

The migration-fidelity test is the safety net for issue #50's refactor: every
screen's old literal `BINDINGS` list became `bindings_for(scope)`, generated
from `tests/unit/binding_snapshot.json` — a golden snapshot of every
`BINDINGS` block captured *before* the migration. This test asserts
`bindings_for(scope)` reproduces that snapshot exactly, field for field, in
order, for every migrated scope, so a dropped `priority=True` or a typo'd
description fails loudly instead of silently changing app behavior.
"""

import json
from pathlib import Path

import pytest
from textual.binding import Binding

from hatty.controllers import keybindings as kb

SNAPSHOT_PATH = Path(__file__).parent / "binding_snapshot.json"

# class name -> registry scope key. ConfigScreen is intentionally absent: its
# BINDINGS stay a hand-written literal (see keybindings.py's module docstring)
# so the config screen can never be rebound into being unreachable.
SCOPE_MAP = {
    "HACLI": "app",
    "ColumnConfigPopup": "column_config",
    "ConfirmPopup": "confirm",
    "EntityControlPopup": "control_popup",
    "EntityPickerModal": "entity_picker",
    "ColorPickerModal": "color_picker",
    "LightControlScreen": "light",
    "MediaPlayerControlScreen": "media_player",
    "PanelManagePopup": "panel_manage",
    "DashboardScreen": "dashboard",
    "DashboardSelectionPopup": "dashboard_select",
    "DashboardSlotPopup": "slot_popup",
    "SplitSlotPopup": "split_slot",
    "AreaNamePopup": "area_name",
    "AreaPickerPopup": "area_picker",
    "DeviceInfoPopup": "device_info",
    "DeviceTreeScreen": "tree",
    "GraphColorPopup": "graph_color",
    "GraphDurationPopup": "graph_duration",
    "GraphPreviewScreen": "graph",
    "SaveGraphNamePopup": "save_graph_name",
    "SavedGraphsPopup": "saved_graphs_popup",
    "HelpPopup": "help_popup",
    "ListSelectionPopup": "list_popup",
    "LogScopePopup": "log_scope_popup",
    "OnboardingScreen": "onboarding",
    "RenameEntityPopup": "rename_popup",
    "SearchInput": "search_input",
    "WeatherForecastScreen": "weather",
}


def _snapshot_blocks():
    return json.loads(SNAPSHOT_PATH.read_text())


def _expected_row(entry: dict) -> tuple:
    desc = entry["description"]
    if isinstance(desc, dict) and "__expr__" in desc:
        # The two GraphPreviewScreen fast-page descriptions are f-strings
        # over FAST_PAGE_MULTIPLIER in the original source.
        from hatty.const import FAST_PAGE_MULTIPLIER

        desc = f"Older ×{FAST_PAGE_MULTIPLIER}" if "Older" in desc["__expr__"] else f"Newer ×{FAST_PAGE_MULTIPLIER}"
    show = True if entry.get("show") is None else entry["show"]
    priority = False if entry.get("priority") is None else entry["priority"]
    return (entry["key"], entry["action"], desc, show, priority)


def _actual_row(binding: Binding) -> tuple:
    return (binding.key, binding.action, binding.description, binding.show, binding.priority)


@pytest.mark.parametrize("block", _snapshot_blocks(), ids=lambda b: f"{b['class']}")
def test_bindings_for_reproduces_snapshot(block):
    scope = SCOPE_MAP.get(block["class"])
    if scope is None:
        pytest.skip(f"{block['class']} keeps a literal BINDINGS list, not migrated")
    expected = [_expected_row(e) for e in block["entries"]]
    # _binding_list (not the public bindings_for) so `b` is statically a
    # Binding, matching what this codebase actually constructs at every call
    # site — bindings_for's wider BindingType return only exists to satisfy
    # Textual's invariant `list[BindingType]` BINDINGS declaration.
    actual = [_actual_row(b) for b in kb._binding_list(scope)]
    assert actual == expected


def test_snapshot_scope_map_is_exhaustive():
    """Every BINDINGS block in the golden snapshot is either mapped to a
    registry scope or explicitly (ConfigScreen) excluded — so a class renamed
    or added later can't silently fall out of coverage."""
    classes = {block["class"] for block in _snapshot_blocks()}
    assert classes - set(SCOPE_MAP) == {"ConfigScreen"}


def test_all_scopes_covered():
    assert set(kb.SCOPES) == set(SCOPE_MAP.values())


# ── Registry invariants ──────────────────────────────────────────────────────


def test_ids_have_a_consistent_default_key_across_scopes():
    """resolve_keymap()/KeybindingController.key_for() both pick BY_ID[id][0].key
    as *the* default — every row sharing an id must agree on it, or a shared
    id (e.g. nav.back) would resolve differently depending on which row was
    registered first."""
    for spec_id, specs in kb.BY_ID.items():
        keys = {spec.key for spec in specs}
        assert len(keys) == 1, f"{spec_id} has inconsistent default keys: {keys}"


def test_duplicate_ids_within_a_scope_are_only_deliberate_twins():
    """An id repeating within one scope is fine *only* when it's the
    deliberate "move together" pattern (e.g. GraphPreviewScreen's three
    `escape` rows all sharing `nav.back`) — each repeat must be a distinct
    action, never the same (key, action) pair registered twice."""
    for scope, specs in kb.BY_SCOPE.items():
        seen: dict[str, set[str]] = {}
        for spec in specs:
            actions = seen.setdefault(spec.id, set())
            assert spec.action not in actions, f"{spec.id} repeats action {spec.action!r} in scope {scope!r}"
            actions.add(spec.action)


def test_curated_ids_are_unique_and_labeled():
    sections = kb.rebindable()
    all_ids = [spec.id for _section, specs in sections for spec in specs]
    assert len(all_ids) == len(set(all_ids))
    for section, specs in sections:
        assert section in kb.SECTION_ORDER
        for spec in specs:
            assert spec.label


def test_reserved_keys_never_default_for_any_id():
    for spec in kb.REGISTRY:
        if spec.id != "app.quit":
            assert spec.key not in kb.RESERVED_KEYS


# ── resolve_keymap / sanitize / validate ─────────────────────────────────────


def test_resolve_keymap_is_complete():
    keymap = kb.resolve_keymap({})
    assert set(keymap) == set(kb.BY_ID)
    assert keymap["log.toggle"] == "a"


def test_resolve_keymap_applies_override():
    keymap = kb.resolve_keymap({"log.toggle": "A"})
    assert keymap["log.toggle"] == "A"
    # untouched ids keep their default
    assert keymap["nav.back"] == "escape"


def test_sanitize_drops_unknown_ids():
    assert kb.sanitize({"nonexistent.id": "x"}) == {}


def test_sanitize_drops_reserved_and_empty_keys():
    assert kb.sanitize({"log.toggle": "ctrl+q"}) == {}
    assert kb.sanitize({"log.toggle": ""}) == {}


def test_sanitize_drops_noop_overrides_restating_the_default():
    assert kb.sanitize({"log.toggle": "a"}) == {}


def test_sanitize_ignores_non_dict_input():
    assert kb.sanitize(None) == {}
    assert kb.sanitize(["a", "b"]) == {}


def test_validate_allows_a_free_key():
    assert kb.validate("log.toggle", "A", {}) is None


def test_validate_blocks_reserved_key():
    assert kb.validate("log.toggle", "ctrl+q", {}) is not None


def test_validate_blocks_conflict_in_a_shared_scope():
    # log.toggle and log.scope both live in {app, dashboard, graph}; log.scope
    # defaults to "v" — reassigning log.toggle to "v" collides in all three.
    error = kb.validate("log.toggle", "v", {})
    assert error is not None
    assert "Scope" in error


def test_validate_allows_resetting_to_default_despite_a_baseline_twin_overlap():
    # dashboard.edit_slot (Edit-mode "a", never rebindable) and log.toggle
    # (Use-mode "a", curated) share "a" by default in the dashboard scope —
    # a deliberate, check_action-gated overlap (TWINS), not a real conflict.
    # Resetting log.toggle back to "a" must not trip validate() against it.
    assert kb.validate("log.toggle", "a", {"log.toggle": "A"}) is None


def test_twins_pairs_ids_sharing_a_scope_and_key_by_default():
    assert "dashboard.edit_slot" in kb.TWINS.get("log.toggle", frozenset())
    assert "log.toggle" in kb.TWINS.get("dashboard.edit_slot", frozenset())
    # nav.back's three GraphPreviewScreen rows all share one *id*, not three
    # distinct ids colliding on a key — never a TWINS entry.
    assert "nav.back" not in kb.TWINS


def test_validate_allows_reusing_a_key_in_a_disjoint_scope():
    # dashboard.rename_slot_entity ("r") only lives in the dashboard scope;
    # entity.rename ("r", app-only) rebinding elsewhere doesn't touch it, and
    # rebinding entity.rename to some other dashboard-only key is fine since
    # entity.rename never appears in the dashboard scope.
    assert kb.validate("entity.rename", "E", {}) is None


def test_validate_considers_hypothetical_override_not_just_current():
    # Rebind log.scope away from "v" first; now "v" should be free for
    # log.toggle when validating against that hypothetical state.
    overrides = {"log.scope": "V"}
    assert kb.validate("log.toggle", "v", overrides) is None


def test_validate_unknown_id_raises():
    with pytest.raises(KeyError):
        kb.validate("nonexistent.id", "x", {})


# ── bindings_for / display_key ───────────────────────────────────────────────


def test_bindings_for_unknown_scope_is_empty():
    assert kb.bindings_for("nonexistent-scope") == []


def test_bindings_for_multiple_scopes_concatenates_in_order():
    combined = kb._binding_list("confirm", "control_popup")
    assert [b.key for b in combined[:4]] == ["y", "n", "escape", "q"]


def test_display_key_uses_help_popup_mapping():
    assert kb.display_key("escape") == "Esc"
    assert kb.display_key("a") == "a"


# ── KeybindingController ─────────────────────────────────────────────────────


class _FakeApp:
    def __init__(self):
        self.keymap = None

    def set_keymap(self, keymap):
        self.keymap = keymap


def test_controller_apply_sanitizes_and_pushes_keymap():
    app = _FakeApp()
    ctl = kb.KeybindingController(app)
    cfg = {"keybindings": {"log.toggle": "A", "bogus.id": "z"}}
    ctl.apply(cfg)
    assert ctl.overrides == {"log.toggle": "A"}
    assert cfg["keybindings"] == {"log.toggle": "A"}
    assert app.keymap == kb.resolve_keymap({"log.toggle": "A"})


def test_controller_key_for_and_display():
    app = _FakeApp()
    ctl = kb.KeybindingController(app)
    ctl.apply({"keybindings": {"log.toggle": "A"}})
    assert ctl.key_for("log.toggle") == "A"
    assert ctl.key_for("nav.back") == "escape"
    assert ctl.display("nav.back") == "Esc"


def test_controller_static_bindings_reflects_overrides():
    app = _FakeApp()
    ctl = kb.KeybindingController(app)
    ctl.apply({"keybindings": {"log.toggle": "A"}})
    dashboard_bindings = ctl.static_bindings("dashboard")
    log_toggle = next(b for b in dashboard_bindings if b.id == "log.toggle")
    assert log_toggle.key == "A"
    # a sibling binding at the *old* default key must be untouched — this is
    # the gotcha #1 regression: dashboard's Edit-mode "a" (edit_slot) must
    # survive log.toggle moving off of "a".
    edit_slot = next(b for b in dashboard_bindings if b.id == "dashboard.edit_slot")
    assert edit_slot.key == "a"
