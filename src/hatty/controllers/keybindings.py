# hatty — MIT License. See LICENSE file for details.
"""The single source of truth for every keybinding in hatty — backs the
Configuration > Keybindings category's custom-keybindings support — and the
app.keys_ctl controller that turns a user's overrides into a live Textual
keymap.

Two halves, like controllers/logbook.py pairs pure helpers with a stateful
controller:

  - **Pure registry** (`KeySpec`, `REGISTRY`, `BY_ID`, `BY_SCOPE`, `SCOPES`,
    `bindings_for`, `sanitize`, `resolve_keymap`, `validate`, `rebindable`).
    `REGISTRY` is imported at *class-definition* time by every screen —
    `BINDINGS = bindings_for("dashboard")` runs while `ui/dashboard/screen.py`
    is first imported — so this half must stay as cycle-safe as const.py/
    types.py: no imports from hatty.ui or hatty.main, only textual.binding and
    hatty.const. `display_key` is the one exception, and it lazy-imports its
    dependency for exactly that reason.

  - **`KeybindingController`** (`app.keys_ctl`), which owns the *live*
    overrides and pushes them onto the running App via `App.set_keymap`.

REGISTRY reproduces the 224 bindings that used to be hand-written across 25
screen modules (see the migration guard in tests/unit/test_keybindings.py,
checked against the pre-migration golden snapshot at
tests/unit/binding_snapshot.json) — one KeySpec per original Binding/tuple
entry, tagged with an `id` and the `scope` (screen) it belongs to. A single
`id` may label several KeySpec rows across different scopes when they are the
same conceptual action and should move together on rebind (e.g. `nav.back`
covers every screen's "leave/cancel" escape binding); every other row gets an
id unique to its own scope so it is never accidentally caught by another
id's rebind.

Only entries with a non-None `section` are user-rebindable via the config
screen's Keybindings category (`rebindable()`); everything else keeps its
default forever but still needs an id — see the next paragraph for why.

Three Textual behaviours (verified against textual 8.2.8's
`BindingsMap.apply_keymap`, textual/binding.py) shape this design:

1. Rebinding a key deletes *every* binding under the old key in that binding
   chain node, id'd or not, then re-adds only the ids present in the keymap
   passed to `apply_keymap`. `DashboardScreen` binds `a` to both
   `edit_slot` (Edit mode) and `toggle_activity_log` (Use mode); if only one
   had an id, the other would silently vanish the moment the id'd one moved.
   So *every* row gets an id, and `resolve_keymap()`/`KeybindingController.
   keymap()` always return the *complete* id -> key mapping (default or
   override) — never a delta — so every row in a touched scope survives the
   round trip.
2. Several bindings legitimately sharing one id (the `nav.back` case, or
   GraphPreviewScreen's three `escape` rows) make `apply_keymap` report a
   `clashed_bindings` false positive even when nothing is actually
   conflicting — see `HACLI.handle_bindings_clash`, which is a documented
   no-op for this reason; this module's own `validate()` is what gives the
   config UI a real conflict check.
3. `Binding.with_key()` (used by `KeybindingController.static_bindings`) is a
   `dataclasses.replace`, so `priority=`/`show=` survive rekeying for free.
"""

from typing import NamedTuple, cast

from textual.binding import Binding, BindingType

from hatty.const import CONFIG_KEY_KEYBINDINGS, FAST_PAGE_MULTIPLIER


class KeySpec(NamedTuple):
    id: str
    """Keymap id. Shared across rows (possibly in different scopes) that must
    move together when rebound; otherwise unique to this row."""
    scope: str
    """Which BINDINGS list (screen) this row belongs to — see SCOPES."""
    key: str
    """Default Textual key string."""
    action: str
    description: str
    show: bool = True
    priority: bool = False
    section: str | None = None
    """Config-UI grouping label. None = not user-rebindable."""
    label: str | None = None
    """Config-UI display label for a rebindable row; falls back to
    `description` when None (auto-generated, non-curated rows never set this,
    since they're never shown)."""


# Never assignable: ctrl+q is the unconditional quit hatch, ctrl+p opens the
# command palette, ctrl+c is the terminal interrupt (also KeyCapturePopup's cancel).
RESERVED_KEYS = frozenset({"ctrl+q", "ctrl+p", "ctrl+c"})

SECTION_ORDER = ("Navigation", "Entities & lists", "Activity log", "Graph")

# One row per original Binding/tuple across every migrated screen (config_screen.py
# excluded — its bindings stay fixed so it can never be rebound unreachable).
# Grouped by scope in file order, matching each screen's original BINDINGS list
# (guarded by test_keybindings.py against binding_snapshot.json).
REGISTRY: tuple[KeySpec, ...] = (
    KeySpec(
        id="nav.search",
        scope="app",
        key="/",
        action="toggle_search",
        description="Search",
        section="Navigation",
        label="Search",
    ),
    KeySpec(
        id="entity.expand",
        scope="app",
        key="e",
        action="expand_entity",
        description="Controls",
        section="Entities & lists",
        label="Controls",
    ),
    KeySpec(
        id="entity.toggle_list_membership",
        scope="app",
        key="space",
        action="toggle_list_membership",
        description="In List",
        section="Entities & lists",
        label="In List",
    ),
    KeySpec(
        id="entity.move_up",
        scope="app",
        key="shift+up",
        action="move_entity_in_list(-1)",
        description="Move Up",
        show=False,
        section="Entities & lists",
        label="Move Up",
    ),
    KeySpec(
        id="entity.move_down",
        scope="app",
        key="shift+down",
        action="move_entity_in_list(1)",
        description="Move Down",
        show=False,
        section="Entities & lists",
        label="Move Down",
    ),
    KeySpec(
        id="entity.sort",
        scope="app",
        key="o",
        action="toggle_list_sort",
        description="Sort Order",
        show=False,
        section="Entities & lists",
        label="Sort Order",
    ),
    KeySpec(
        id="entity.lock",
        scope="app",
        key="L",
        action="toggle_list_lock",
        description="Lock List",
        show=False,
        section="Entities & lists",
        label="Lock List",
    ),
    KeySpec(
        id="entity.rename",
        scope="app",
        key="r",
        action="rename_entity",
        description="Rename",
        show=False,
        section="Entities & lists",
        label="Rename",
    ),
    KeySpec(
        id="entity.undo",
        scope="app",
        key="u",
        action="undo",
        description="Undo",
        show=False,
        section="Entities & lists",
        label="Undo",
    ),
    KeySpec(
        id="entity.redo",
        scope="app",
        key="ctrl+r",
        action="redo",
        description="Redo",
        show=False,
        section="Entities & lists",
        label="Redo",
    ),
    KeySpec(
        id="entity.lists",
        scope="app",
        key="l",
        action="show_list_selection_popup",
        description="Lists",
        show=False,
        section="Entities & lists",
        label="Lists",
    ),
    KeySpec(
        id="entity.columns",
        scope="app",
        key="c",
        action="show_column_config",
        description="Columns",
        show=False,
        section="Entities & lists",
        label="Columns",
    ),
    KeySpec(
        id="log.toggle",
        scope="app",
        key="a",
        action="toggle_activity_log",
        description="Activity Log",
        show=False,
        section="Activity log",
        label="Toggle",
    ),
    KeySpec(
        id="log.entity",
        scope="app",
        key="i",
        action="toggle_entity_log",
        description="Entity Log",
        show=False,
        section="Activity log",
        label="Entity Log",
    ),
    KeySpec(
        id="log.scope",
        scope="app",
        key="v",
        action="show_log_scope",
        description="Log Scope",
        show=False,
        section="Activity log",
        label="Scope",
    ),
    KeySpec(
        id="log.maximize",
        scope="app",
        key="f",
        action="maximize_log",
        description="Maximize Log",
        show=False,
        section="Activity log",
        label="Maximize",
    ),
    KeySpec(
        id="log.older",
        scope="app",
        key="left",
        action="log_older",
        description="Older Events",
        show=False,
        priority=True,
        section="Activity log",
        label="Older Events",
    ),
    KeySpec(
        id="log.newer",
        scope="app",
        key="right",
        action="log_newer",
        description="Newer Events",
        show=False,
        priority=True,
        section="Activity log",
        label="Newer Events",
    ),
    KeySpec(
        id="graph.toggle",
        scope="app",
        key="g",
        action="toggle_graph",
        description="Graph",
        show=False,
        section="Graph",
        label="Toggle",
    ),
    KeySpec(
        id="graph.fullscreen",
        scope="app",
        key="G",
        action="graph_fullscreen",
        description="Full Graph",
        show=False,
        section="Graph",
        label="Fullscreen",
    ),
    KeySpec(
        id="graph.compare",
        scope="app",
        key="+",
        action="add_to_graph",
        description="Compare",
        show=False,
        section="Graph",
        label="Compare",
    ),
    KeySpec(
        id="nav.dashboard",
        scope="app",
        key="d",
        action="show_dashboard",
        description="Dashboard",
        show=False,
        section="Navigation",
        label="Dashboard",
    ),
    KeySpec(
        id="nav.device_tree",
        scope="app",
        key="D",
        action="show_device_tree",
        description="Device Tree",
        show=False,
        section="Navigation",
        label="Device Tree",
    ),
    KeySpec(
        id="nav.saved_graphs",
        scope="app",
        key="s",
        action="show_saved_graphs_popup",
        description="Saved Graphs",
        show=False,
        section="Navigation",
        label="Saved Graphs",
    ),
    KeySpec(
        id="graph.cycle_type",
        scope="app",
        key="t",
        action="cycle_graph_type",
        description="Graph Type",
        section="Graph",
        label="Cycle Type",
    ),
    KeySpec(
        id="graph.duration",
        scope="app",
        key="T",
        action="show_graph_duration",
        description="Duration",
        show=False,
        section="Graph",
        label="Duration",
    ),
    KeySpec(
        id="nav.search_next",
        scope="app",
        key="n",
        action="search_next",
        description="Next Match",
        show=False,
        section="Navigation",
        label="Next Match",
    ),
    KeySpec(
        id="nav.search_prev",
        scope="app",
        key="N",
        action="search_prev",
        description="Prev Match",
        show=False,
        section="Navigation",
        label="Prev Match",
    ),
    KeySpec(
        id="nav.help",
        scope="app",
        key="question_mark",
        action="show_help",
        description="Help",
        section="Navigation",
        label="Help",
    ),
    KeySpec(
        id="nav.back",
        scope="app",
        key="escape",
        action="go_back",
        description="Back/Clear",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="app.quit", scope="app", key="ctrl+q", action="quit", description="Quit", show=False),
    KeySpec(
        id="column_config.save_and_close",
        scope="column_config",
        key="escape",
        action="save_and_close",
        description="Save & Close",
    ),
    KeySpec(
        id="column_config.save_and_close__q",
        scope="column_config",
        key="q",
        action="save_and_close",
        description="Save & Close",
        show=False,
    ),
    KeySpec(
        id="column_config.save_and_close__enter",
        scope="column_config",
        key="enter",
        action="save_and_close",
        description="Save & Close",
        priority=True,
    ),
    KeySpec(
        id="column_config.move_up",
        scope="column_config",
        key="shift+up",
        action="move_up",
        description="Move Up",
        priority=True,
    ),
    KeySpec(
        id="column_config.move_down",
        scope="column_config",
        key="shift+down",
        action="move_down",
        description="Move Down",
        priority=True,
    ),
    KeySpec(id="confirm.confirm", scope="confirm", key="y", action="confirm", description="Yes"),
    KeySpec(id="confirm.cancel", scope="confirm", key="n", action="cancel", description="No"),
    KeySpec(
        id="nav.back",
        scope="confirm",
        key="escape",
        action="cancel",
        description="No",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="confirm.cancel__q", scope="confirm", key="q", action="cancel", description="No", show=False),
    KeySpec(
        id="nav.back",
        scope="control_popup",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="control_popup.cancel", scope="control_popup", key="q", action="cancel", description="Cancel", show=False
    ),
    KeySpec(id="control_popup.save", scope="control_popup", key="enter", action="save", description="Save"),
    KeySpec(
        id="nav.back",
        scope="entity_picker",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="entity_picker.cancel", scope="entity_picker", key="q", action="cancel", description="Cancel", show=False
    ),
    KeySpec(
        id="nav.back",
        scope="color_picker",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="color_picker.cancel", scope="color_picker", key="q", action="cancel", description="Cancel", show=False),
    KeySpec(
        id="nav.back",
        scope="light",
        key="escape",
        action="close",
        description="Close",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="light.close", scope="light", key="q", action="close", description="Close", show=False),
    KeySpec(
        id="light.toggle_power", scope="light", key="space", action="toggle_power", description="On/Off", priority=True
    ),
    KeySpec(id="light.white_preset", scope="light", key="1", action="white_preset(0)", description="Warm", show=False),
    KeySpec(
        id="light.white_preset__2", scope="light", key="2", action="white_preset(1)", description="Neutral", show=False
    ),
    KeySpec(
        id="light.white_preset__3", scope="light", key="3", action="white_preset(2)", description="Cool", show=False
    ),
    KeySpec(
        id="light.open_color_picker",
        scope="light",
        key="p",
        action="open_color_picker",
        description="Pick Color",
        show=False,
    ),
    KeySpec(id="light.cycle_tab", scope="light", key="t", action="cycle_tab", description="Next Tab"),
    KeySpec(
        id="light.nav_focus",
        scope="light",
        key="up",
        action="nav_focus(-1)",
        description="Focus Up",
        show=False,
        priority=True,
    ),
    KeySpec(
        id="light.nav_focus__down",
        scope="light",
        key="down",
        action="nav_focus(1)",
        description="Focus Down",
        show=False,
        priority=True,
    ),
    KeySpec(
        id="nav.help",
        scope="light",
        key="question_mark",
        action="show_help",
        description="Help",
        section="Navigation",
        label="Help",
    ),
    KeySpec(
        id="nav.back",
        scope="media_player",
        key="escape",
        action="close",
        description="Close",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="media_player.close", scope="media_player", key="q", action="close", description="Close", show=False),
    KeySpec(
        id="media_player.toggle_play_pause",
        scope="media_player",
        key="space",
        action="toggle_play_pause",
        description="Play/Pause",
        priority=True,
    ),
    KeySpec(
        id="media_player.stop_playback",
        scope="media_player",
        key="s",
        action="stop_playback",
        description="Stop",
        show=False,
    ),
    KeySpec(
        id="media_player.nav_focus",
        scope="media_player",
        key="up",
        action="nav_focus(-1)",
        description="Focus Up",
        show=False,
        priority=True,
    ),
    KeySpec(
        id="media_player.nav_focus__down",
        scope="media_player",
        key="down",
        action="nav_focus(1)",
        description="Focus Down",
        show=False,
        priority=True,
    ),
    KeySpec(
        id="nav.help",
        scope="media_player",
        key="question_mark",
        action="show_help",
        description="Help",
        section="Navigation",
        label="Help",
    ),
    KeySpec(
        id="nav.back",
        scope="panel_manage",
        key="escape",
        action="done",
        description="Done",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="panel_manage.done", scope="panel_manage", key="q", action="done", description="Done", show=False),
    KeySpec(id="panel_manage.move", scope="panel_manage", key="shift+up", action="move(-1)", description="Move up"),
    KeySpec(
        id="panel_manage.move__shift_down",
        scope="panel_manage",
        key="shift+down",
        action="move(1)",
        description="Move down",
    ),
    KeySpec(id="panel_manage.remove", scope="panel_manage", key="delete", action="remove", description="Remove"),
    KeySpec(id="panel_manage.remove__x", scope="panel_manage", key="x", action="remove", description="Remove"),
    KeySpec(id="panel_manage.add", scope="panel_manage", key="a", action="add", description="Add"),
    KeySpec(
        id="dashboard.move_cursor",
        scope="dashboard",
        key="up",
        action="move_cursor(-1, 0)",
        description="Up",
        show=False,
    ),
    KeySpec(
        id="dashboard.move_cursor__down",
        scope="dashboard",
        key="down",
        action="move_cursor(1, 0)",
        description="Down",
        show=False,
    ),
    KeySpec(
        id="dashboard.move_cursor__left",
        scope="dashboard",
        key="left",
        action="move_cursor(0, -1)",
        description="Left",
        show=False,
    ),
    KeySpec(
        id="dashboard.move_cursor__right",
        scope="dashboard",
        key="right",
        action="move_cursor(0, 1)",
        description="Right",
        show=False,
    ),
    KeySpec(id="dashboard.toggle_slot", scope="dashboard", key="enter", action="toggle_slot", description="Toggle"),
    KeySpec(id="dashboard.expand_slot", scope="dashboard", key="e", action="expand_slot", description="Controls"),
    KeySpec(id="dashboard.enter_edit", scope="dashboard", key="E", action="enter_edit", description="Edit"),
    KeySpec(
        id="dashboard.rename_slot_entity", scope="dashboard", key="r", action="rename_slot_entity", description="Rename"
    ),
    KeySpec(id="dashboard.edit_slot", scope="dashboard", key="a", action="edit_slot", description="Assign"),
    KeySpec(id="dashboard.clear_slot", scope="dashboard", key="delete", action="clear_slot", description="Clear Slot"),
    KeySpec(id="dashboard.grab_move", scope="dashboard", key="enter", action="grab_move", description="Move"),
    KeySpec(
        id="dashboard.resize_slot",
        scope="dashboard",
        key="ctrl+right",
        action="resize_slot(0, 1)",
        description="Wider",
        show=False,
    ),
    KeySpec(
        id="dashboard.resize_slot__ctrl_left",
        scope="dashboard",
        key="ctrl+left",
        action="resize_slot(0, -1)",
        description="Narrower",
        show=False,
    ),
    KeySpec(
        id="dashboard.resize_slot__ctrl_down",
        scope="dashboard",
        key="ctrl+down",
        action="resize_slot(1, 0)",
        description="Taller",
        show=False,
    ),
    KeySpec(
        id="dashboard.resize_slot__ctrl_up",
        scope="dashboard",
        key="ctrl+up",
        action="resize_slot(-1, 0)",
        description="Shorter",
        show=False,
    ),
    KeySpec(id="dashboard.split_slot", scope="dashboard", key="s", action="split_slot", description="Split"),
    KeySpec(
        id="dashboard.unsplit_slot",
        scope="dashboard",
        key="u",
        action="unsplit_slot",
        description="Unsplit",
        show=False,
    ),
    KeySpec(id="dashboard.fill_split", scope="dashboard", key="f", action="fill_split", description="Fill"),
    KeySpec(
        id="log.toggle",
        scope="dashboard",
        key="a",
        action="toggle_activity_log",
        description="Activity Log",
        show=False,
        section="Activity log",
        label="Toggle",
    ),
    KeySpec(
        id="log.scope",
        scope="dashboard",
        key="v",
        action="show_log_scope",
        description="Log Scope",
        show=False,
        section="Activity log",
        label="Scope",
    ),
    KeySpec(
        id="log.maximize",
        scope="dashboard",
        key="f",
        action="maximize_log",
        description="Maximize Log",
        show=False,
        section="Activity log",
        label="Maximize",
    ),
    KeySpec(
        id="dashboard.log_older",
        scope="dashboard",
        key="left_square_bracket",
        action="log_older",
        description="Older Events",
        show=False,
    ),
    KeySpec(
        id="dashboard.log_newer",
        scope="dashboard",
        key="right_square_bracket",
        action="log_newer",
        description="Newer Events",
        show=False,
    ),
    KeySpec(
        id="dashboard.show_list_popup",
        scope="dashboard",
        key="l",
        action="show_list_popup",
        description="Back to List",
        show=False,
    ),
    KeySpec(
        id="dashboard.manage_dashboards",
        scope="dashboard",
        key="d",
        action="manage_dashboards",
        description="Dashboards",
    ),
    KeySpec(
        id="nav.device_tree",
        scope="dashboard",
        key="D",
        action="show_device_tree",
        description="Device Tree",
        section="Navigation",
        label="Device Tree",
    ),
    KeySpec(
        id="graph.cycle_type",
        scope="dashboard",
        key="t",
        action="cycle_graph_type",
        description="Graph Type",
        show=False,
        section="Graph",
        label="Cycle Type",
    ),
    KeySpec(
        id="graph.fullscreen",
        scope="dashboard",
        key="G",
        action="graph_fullscreen",
        description="Full Graph",
        section="Graph",
        label="Fullscreen",
    ),
    KeySpec(
        id="nav.help",
        scope="dashboard",
        key="question_mark",
        action="show_help",
        description="Help",
        section="Navigation",
        label="Help",
    ),
    KeySpec(
        id="nav.back",
        scope="dashboard",
        key="escape",
        action="go_back",
        description="Back",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="dashboard_select.delete_dashboard",
        scope="dashboard_select",
        key="delete",
        action="delete_dashboard",
        description="Delete",
    ),
    KeySpec(
        id="dashboard_select.edit_dashboard",
        scope="dashboard_select",
        key="e",
        action="edit_dashboard",
        description="Edit",
    ),
    KeySpec(
        id="dashboard_select.set_default",
        scope="dashboard_select",
        key="d",
        action="set_default",
        description="Set as Default",
    ),
    KeySpec(
        id="dashboard_select.export_dashboard",
        scope="dashboard_select",
        key="x",
        action="export_dashboard",
        description="Export",
    ),
    KeySpec(
        id="dashboard_select.import_dashboard",
        scope="dashboard_select",
        key="i",
        action="import_dashboard",
        description="Import",
    ),
    KeySpec(
        id="nav.back",
        scope="dashboard_select",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="dashboard_select.cancel",
        scope="dashboard_select",
        key="q",
        action="cancel",
        description="Cancel",
        show=False,
    ),
    KeySpec(
        id="dashboard_select.move_up",
        scope="dashboard_select",
        key="shift+up",
        action="move_up",
        description="Move Up",
        priority=True,
    ),
    KeySpec(
        id="dashboard_select.move_down",
        scope="dashboard_select",
        key="shift+down",
        action="move_down",
        description="Move Down",
        priority=True,
    ),
    KeySpec(
        id="nav.back",
        scope="slot_popup",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="slot_popup.cancel", scope="slot_popup", key="q", action="cancel", description="Cancel", show=False),
    KeySpec(
        id="slot_popup.reorder_selected",
        scope="slot_popup",
        key="shift+up",
        action="reorder_selected(-1)",
        description="Move Up",
        show=False,
    ),
    KeySpec(
        id="slot_popup.reorder_selected__shift_down",
        scope="slot_popup",
        key="shift+down",
        action="reorder_selected(1)",
        description="Move Down",
        show=False,
    ),
    KeySpec(
        id="slot_popup.remove_selected",
        scope="slot_popup",
        key="delete",
        action="remove_selected",
        description="Remove",
        show=False,
    ),
    KeySpec(
        id="slot_popup.nav_focus",
        scope="slot_popup",
        key="up",
        action="nav_focus(-1)",
        description="Focus Up",
        show=False,
        priority=True,
    ),
    KeySpec(
        id="slot_popup.nav_focus__down",
        scope="slot_popup",
        key="down",
        action="nav_focus(1)",
        description="Focus Down",
        show=False,
        priority=True,
    ),
    KeySpec(id="split_slot.split", scope="split_slot", key="v", action="split('v')", description="Left/Right"),
    KeySpec(id="split_slot.split__h", scope="split_slot", key="h", action="split('h')", description="Top/Bottom"),
    KeySpec(id="split_slot.split__q", scope="split_slot", key="q", action="split('quad')", description="Quarters"),
    KeySpec(
        id="nav.back",
        scope="split_slot",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="nav.back",
        scope="area_name",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="area_name.cancel", scope="area_name", key="q", action="cancel", description="Cancel", show=False),
    KeySpec(
        id="nav.back",
        scope="area_picker",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="area_picker.cancel", scope="area_picker", key="q", action="cancel", description="Cancel", show=False),
    KeySpec(
        id="nav.back",
        scope="device_info",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="device_info.cancel", scope="device_info", key="i", action="cancel", description="Close"),
    KeySpec(
        id="device_info.cancel__q", scope="device_info", key="q", action="cancel", description="Cancel", show=False
    ),
    KeySpec(
        id="nav.search",
        scope="tree",
        key="/",
        action="toggle_search",
        description="Search",
        section="Navigation",
        label="Search",
    ),
    KeySpec(
        id="entity.expand",
        scope="tree",
        key="e",
        action="expand_entity",
        description="Controls",
        section="Entities & lists",
        label="Controls",
    ),
    KeySpec(
        id="graph.fullscreen",
        scope="tree",
        key="G",
        action="graph_fullscreen",
        description="Graph",
        section="Graph",
        label="Fullscreen",
    ),
    KeySpec(id="tree.cycle_mode", scope="tree", key="v", action="cycle_mode", description="View"),
    KeySpec(id="tree.move_device", scope="tree", key="m", action="move_device", description="Move to Area"),
    KeySpec(id="tree.device_info", scope="tree", key="i", action="device_info", description="Info"),
    KeySpec(id="tree.create_area", scope="tree", key="a", action="create_area", description="New Area"),
    KeySpec(id="tree.rename", scope="tree", key="r", action="rename", description="Rename"),
    KeySpec(id="tree.jump_to_list", scope="tree", key="l", action="jump_to_list", description="Lists"),
    KeySpec(id="tree.open_dashboard", scope="tree", key="d", action="open_dashboard", description="Dashboard"),
    KeySpec(
        id="tree.area_to_dashboard", scope="tree", key="n", action="area_to_dashboard", description="New Dashboard"
    ),
    KeySpec(id="tree.collapse_all", scope="tree", key="x", action="collapse_all", description="Collapse All"),
    KeySpec(id="tree.expand_all", scope="tree", key="X", action="expand_all", description="Expand All"),
    KeySpec(
        id="nav.help",
        scope="tree",
        key="question_mark",
        action="show_help",
        description="Help",
        section="Navigation",
        label="Help",
    ),
    KeySpec(
        id="entity.toggle_list_membership",
        scope="tree",
        key="space",
        action="toggle_list_membership",
        description="List",
        priority=True,
        section="Entities & lists",
        label="In List",
    ),
    KeySpec(
        id="tree.cycle_scope", scope="tree", key="ctrl+s", action="cycle_scope", description="Scope", priority=True
    ),
    KeySpec(
        id="nav.back",
        scope="tree",
        key="escape",
        action="go_back",
        description="Back",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="nav.back",
        scope="graph_color",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="graph_color.cancel", scope="graph_color", key="q", action="cancel", description="Cancel", show=False),
    KeySpec(
        id="nav.back",
        scope="graph_duration",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="graph_duration.cancel", scope="graph_duration", key="q", action="cancel", description="Cancel", show=False
    ),
    KeySpec(
        id="graph_duration.confirm",
        scope="graph_duration",
        key="enter",
        action="confirm",
        description="Select",
        priority=True,
    ),
    KeySpec(id="graph.cycle_plot_type", scope="graph", key="t", action="cycle_plot_type", description="Graph Type"),
    KeySpec(id="graph.scroll_back", scope="graph", key="left", action="scroll_back", description="Older"),
    KeySpec(id="graph.cursor_prev", scope="graph", key="left", action="cursor_prev", description="Prev Sample"),
    KeySpec(id="graph.scroll_forward", scope="graph", key="right", action="scroll_forward", description="Newer"),
    KeySpec(id="graph.cursor_next", scope="graph", key="right", action="cursor_next", description="Next Sample"),
    KeySpec(
        id="graph.scroll_back_fast",
        scope="graph",
        key="shift+left",
        action="scroll_back_fast",
        description=f"Older ×{FAST_PAGE_MULTIPLIER}",
    ),
    KeySpec(
        id="graph.cursor_prev_fast",
        scope="graph",
        key="shift+left",
        action="cursor_prev_fast",
        description="Prev Sample ×10%",
    ),
    KeySpec(
        id="graph.scroll_forward_fast",
        scope="graph",
        key="shift+right",
        action="scroll_forward_fast",
        description=f"Newer ×{FAST_PAGE_MULTIPLIER}",
    ),
    KeySpec(
        id="graph.cursor_next_fast",
        scope="graph",
        key="shift+right",
        action="cursor_next_fast",
        description="Next Sample ×10%",
    ),
    KeySpec(id="graph.zoom_in", scope="graph", key="plus", action="zoom_in", description="Zoom In"),
    KeySpec(id="graph.zoom_out", scope="graph", key="minus", action="zoom_out", description="Zoom Out"),
    KeySpec(id="graph.snap_live", scope="graph", key="home", action="snap_live", description="Now"),
    KeySpec(id="graph.cursor_home", scope="graph", key="home", action="cursor_home", description="Oldest Sample"),
    KeySpec(id="graph.cursor_end", scope="graph", key="end", action="cursor_end", description="Newest Sample"),
    KeySpec(
        id="graph.toggle_cursor_mode", scope="graph", key="enter", action="toggle_cursor_mode", description="Inspect"
    ),
    KeySpec(
        id="graph.exit_cursor_mode", scope="graph", key="enter", action="exit_cursor_mode", description="Exit Inspect"
    ),
    KeySpec(id="graph.save_graph", scope="graph", key="S", action="save_graph", description="Save As"),
    KeySpec(id="graph.update_graph", scope="graph", key="u", action="update_graph", description="Update"),
    KeySpec(
        id="graph.next_entity", scope="graph", key="tab", action="next_entity", description="Next Line", show=False
    ),
    KeySpec(id="graph.cycle_color", scope="graph", key="c", action="cycle_color", description="Color"),
    KeySpec(id="graph.pick_color", scope="graph", key="C", action="pick_color", description="Color Picker"),
    KeySpec(
        id="graph.show_list_popup",
        scope="graph",
        key="l",
        action="show_list_popup",
        description="Back to List",
        show=False,
    ),
    KeySpec(
        id="log.toggle",
        scope="graph",
        key="a",
        action="toggle_event_log",
        description="Activity Log",
        section="Activity log",
        label="Toggle",
    ),
    KeySpec(
        id="log.scope",
        scope="graph",
        key="v",
        action="show_log_scope",
        description="Log View",
        section="Activity log",
        label="Scope",
    ),
    KeySpec(
        id="log.maximize",
        scope="graph",
        key="f",
        action="maximize_log",
        description="Maximize Log",
        show=False,
        section="Activity log",
        label="Maximize",
    ),
    KeySpec(id="graph.show_help", scope="graph", key="question_mark", action="show_help", description="Help"),
    KeySpec(
        id="nav.back",
        scope="graph",
        key="escape",
        action="exit_cursor_mode",
        description="Exit Inspect",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="nav.back",
        scope="graph",
        key="escape",
        action="close_event_log",
        description="Close Log",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="nav.back",
        scope="graph",
        key="escape",
        action="go_back",
        description="Back",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="graph.exit_cursor_mode__q",
        scope="graph",
        key="q",
        action="exit_cursor_mode",
        description="Exit Inspect",
        show=False,
    ),
    KeySpec(
        id="graph.close_event_log",
        scope="graph",
        key="q",
        action="close_event_log",
        description="Close Log",
        show=False,
    ),
    KeySpec(id="graph.go_back", scope="graph", key="q", action="go_back", description="Back", show=False),
    KeySpec(
        id="nav.back",
        scope="save_graph_name",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="save_graph_name.cancel", scope="save_graph_name", key="q", action="cancel", description="Cancel", show=False
    ),
    KeySpec(
        id="saved_graphs_popup.rename_graph",
        scope="saved_graphs_popup",
        key="r",
        action="rename_graph",
        description="Rename",
    ),
    KeySpec(
        id="saved_graphs_popup.delete_graph",
        scope="saved_graphs_popup",
        key="delete",
        action="delete_graph",
        description="Delete",
    ),
    KeySpec(
        id="saved_graphs_popup.export_graph",
        scope="saved_graphs_popup",
        key="x",
        action="export_graph",
        description="Export",
    ),
    KeySpec(
        id="saved_graphs_popup.import_graph",
        scope="saved_graphs_popup",
        key="i",
        action="import_graph",
        description="Import",
    ),
    KeySpec(
        id="nav.back",
        scope="saved_graphs_popup",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="saved_graphs_popup.cancel",
        scope="saved_graphs_popup",
        key="q",
        action="cancel",
        description="Cancel",
        show=False,
    ),
    KeySpec(id="help_popup.prev_page", scope="help_popup", key="left", action="prev_page", description="Prev Page"),
    KeySpec(id="help_popup.next_page", scope="help_popup", key="right", action="next_page", description="Next Page"),
    KeySpec(id="help_popup.focus_filter", scope="help_popup", key="/", action="focus_filter", description="Search"),
    KeySpec(id="help_popup.toggle_all", scope="help_popup", key="a", action="toggle_all", description="Show All"),
    KeySpec(
        id="nav.back",
        scope="help_popup",
        key="escape",
        action="dismiss",
        description="Close",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="help_popup.dismiss",
        scope="help_popup",
        key="question_mark",
        action="dismiss",
        description="Close",
        show=False,
    ),
    KeySpec(id="help_popup.dismiss__q", scope="help_popup", key="q", action="dismiss", description="Close", show=False),
    KeySpec(
        id="list_popup.delete_list", scope="list_popup", key="delete", action="delete_list", description="Delete List"
    ),
    KeySpec(id="list_popup.rename_list", scope="list_popup", key="r", action="rename_list", description="Rename"),
    KeySpec(
        id="list_popup.set_default", scope="list_popup", key="d", action="set_default", description="Set as Default"
    ),
    KeySpec(id="list_popup.toggle_notify", scope="list_popup", key="n", action="toggle_notify", description="Notify"),
    KeySpec(
        id="list_popup.view_as_dashboard",
        scope="list_popup",
        key="v",
        action="view_as_dashboard",
        description="View as Dashboard",
    ),
    KeySpec(
        id="list_popup.export_list",
        scope="list_popup",
        key="x",
        action="export_list",
        description="Export",
    ),
    KeySpec(
        id="list_popup.import_list",
        scope="list_popup",
        key="i",
        action="import_list",
        description="Import",
    ),
    KeySpec(
        id="nav.back",
        scope="list_popup",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="list_popup.cancel", scope="list_popup", key="q", action="cancel", description="Cancel", show=False),
    KeySpec(
        id="nav.search",
        scope="list_popup",
        key="/",
        action="toggle_search",
        description="Search",
        section="Navigation",
        label="Search",
    ),
    KeySpec(
        id="list_popup.move_up",
        scope="list_popup",
        key="shift+up",
        action="move_up",
        description="Move Up",
        priority=True,
    ),
    KeySpec(
        id="list_popup.move_down",
        scope="list_popup",
        key="shift+down",
        action="move_down",
        description="Move Down",
        priority=True,
    ),
    KeySpec(
        id="nav.back",
        scope="log_scope_popup",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="log_scope_popup.cancel", scope="log_scope_popup", key="q", action="cancel", description="Cancel", show=False
    ),
    KeySpec(
        id="onboarding.test_connection",
        scope="onboarding",
        key="ctrl+t",
        action="test_connection",
        description="Test Connection",
    ),
    KeySpec(id="onboarding.save", scope="onboarding", key="ctrl+s", action="save", description="Save & Connect"),
    KeySpec(
        id="onboarding.toggle_token",
        scope="onboarding",
        key="ctrl+v",
        action="toggle_token",
        description="Show/Hide Token",
    ),
    KeySpec(
        id="nav.back",
        scope="onboarding",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(
        id="nav.back",
        scope="rename_popup",
        key="escape",
        action="cancel",
        description="Cancel",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="rename_popup.cancel", scope="rename_popup", key="q", action="cancel", description="Cancel", show=False),
    KeySpec(
        id="rename_popup.save_local", scope="rename_popup", key="enter", action="save_local", description="Save Locally"
    ),
    KeySpec(
        id="search_input.toggle_mode",
        scope="search_input",
        key="tab",
        action="toggle_mode",
        description="Toggle filter/jump",
        show=False,
    ),
    KeySpec(
        id="nav.back",
        scope="weather",
        key="escape",
        action="go_back",
        description="Back",
        section="Navigation",
        label="Back / Cancel",
    ),
    KeySpec(id="weather.cycle_type", scope="weather", key="t", action="cycle_type", description="Switch type"),
    KeySpec(
        id="nav.help",
        scope="weather",
        key="question_mark",
        action="show_help",
        description="Help",
        section="Navigation",
        label="Help",
    ),
)

SCOPES: tuple[str, ...] = tuple(dict.fromkeys(spec.scope for spec in REGISTRY))

BY_SCOPE: dict[str, tuple[KeySpec, ...]] = {
    scope: tuple(spec for spec in REGISTRY if spec.scope == scope) for scope in SCOPES
}

_by_id: dict[str, list[KeySpec]] = {}
for _spec in REGISTRY:
    _by_id.setdefault(_spec.id, []).append(_spec)
BY_ID: dict[str, tuple[KeySpec, ...]] = {spec_id: tuple(specs) for spec_id, specs in _by_id.items()}

# Distinct ids that default to the *same* key in the *same* scope — mode-gated
# twins check_action already keeps mutually exclusive (e.g. dashboard's Use-mode
# `log.toggle` and Edit-mode `dashboard.edit_slot`, both "a" by default).
# validate() must never flag these against each other: only one side of most such
# pairs is curated/rebindable, the other stays pinned at that shared default.
TWINS: dict[str, frozenset[str]] = {}
for _scope_specs in BY_SCOPE.values():
    _by_key: dict[str, set[str]] = {}
    for _spec in _scope_specs:
        _by_key.setdefault(_spec.key, set()).add(_spec.id)
    for _ids in _by_key.values():
        if len(_ids) > 1:
            for _id in _ids:
                TWINS[_id] = TWINS.get(_id, frozenset()) | (_ids - {_id})


def _binding_list(*scopes: str) -> list[Binding]:
    return [
        Binding(spec.key, spec.action, spec.description, show=spec.show, priority=spec.priority, id=spec.id)
        for scope in scopes
        for spec in BY_SCOPE.get(scope, ())
    ]


def bindings_for(*scopes: str) -> list[BindingType]:
    """The default (unrebound) `Binding` list for one or more scopes, in
    registry order — the replacement for a screen's old literal `BINDINGS`.
    Rebinding is applied later, per-node, by `App.set_keymap` (see
    `KeybindingController.apply`); this always returns defaults. Return type
    is `list[BindingType]` (not `list[Binding]`) only so it matches
    `DOMNode.BINDINGS`'s own invariant `list[BindingType]` declaration and
    `BINDINGS = bindings_for(...)` type-checks — every element actually
    constructed is a `Binding` (see `_binding_list`, used internally where
    that concrete type matters)."""
    return cast(list[BindingType], _binding_list(*scopes))


def display_key(key: str) -> str:
    """Friendly display text for a raw Textual key string, e.g. "escape" ->
    "Esc". Lazily imports help_popup — the one place this module reaches past
    const.py, since it's never needed at the class-definition time that makes
    the rest of this module import-cycle-sensitive (see module docstring)."""
    from hatty.ui.help_popup import display_key as _display_key

    return _display_key(key)


def sanitize(overrides: object) -> dict[str, str]:
    """Drop anything from a raw (possibly hand-edited) config value that isn't
    a valid, non-reserved override for a known id, and drop no-op overrides
    that just restate the default — so a stale/corrupt YAML can never break
    startup, and "keybindings:" in config.yaml only ever lists real
    customizations."""
    if not isinstance(overrides, dict):
        return {}
    clean: dict[str, str] = {}
    for spec_id, key in overrides.items():
        if not isinstance(spec_id, str) or spec_id not in BY_ID:
            continue
        if not isinstance(key, str) or not key or key in RESERVED_KEYS:
            continue
        if key == BY_ID[spec_id][0].key:
            continue
        clean[spec_id] = key
    return clean


def resolve_keymap(overrides: dict[str, str]) -> dict[str, str]:
    """The complete id -> key mapping: every registered id, override or
    default. Must be complete, never a delta (gotcha #1 in the module
    docstring) — this is what gets handed to `App.set_keymap`."""
    return {spec_id: overrides.get(spec_id, specs[0].key) for spec_id, specs in BY_ID.items()}


def validate(spec_id: str, key: str, overrides: dict[str, str]) -> str | None:
    """None if `key` is free to become spec_id's binding under `overrides`;
    otherwise an error naming the action that already owns it in a scope
    spec_id also occupies. Pure — the config screen calls this against its own
    uncommitted working copy of overrides before accepting a capture."""
    if spec_id not in BY_ID:
        raise KeyError(spec_id)
    if key in RESERVED_KEYS:
        return f"{display_key(key)} is reserved"
    resolved = resolve_keymap({**overrides, spec_id: key})
    target_scopes = {spec.scope for spec in BY_ID[spec_id]}
    twins = TWINS.get(spec_id, frozenset())
    for scope in target_scopes:
        for spec in BY_SCOPE[scope]:
            if spec.id == spec_id or spec.id in twins:
                continue
            if resolved[spec.id] == key:
                return f"{display_key(key)} is already used by {spec.label or spec.description}"
    return None


def rebindable() -> list[tuple[str, list[KeySpec]]]:
    """Curated ids grouped by section (Navigation / Entities & lists /
    Activity log / Graph), one representative KeySpec per id — the listing for
    the config screen's Keybindings category."""
    seen: set[str] = set()
    buckets: dict[str, list[KeySpec]] = {section: [] for section in SECTION_ORDER}
    for spec in REGISTRY:
        if spec.section is None or spec.id in seen:
            continue
        seen.add(spec.id)
        buckets[spec.section].append(spec)
    return [(section, buckets[section]) for section in SECTION_ORDER if buckets[section]]


class KeybindingController:
    """Owns the live keybinding overrides and pushes the resulting keymap onto
    the running App. `apply()` is called from HACLI._apply_config (boot, demo,
    and the post-onboarding restart) and again from _on_config_saved so a
    rebind in the config screen's Keybindings category takes effect without a
    restart."""

    def __init__(self, app) -> None:
        self._app = app
        self.overrides: dict[str, str] = {}

    def apply(self, cfg: dict) -> None:
        """Sanitize cfg[keybindings], store the result, and push the keymap
        onto the app. Also normalizes cfg in place so a save right afterwards
        writes back only the sanitized overrides."""
        self.overrides = sanitize(cfg.get(CONFIG_KEY_KEYBINDINGS) or {})
        cfg[CONFIG_KEY_KEYBINDINGS] = dict(self.overrides)
        self._app.set_keymap(resolve_keymap(self.overrides))

    def key_for(self, spec_id: str) -> str:
        specs = BY_ID.get(spec_id)
        if not specs:
            raise KeyError(spec_id)
        return self.overrides.get(spec_id, specs[0].key)

    def display(self, spec_id: str) -> str:
        return display_key(self.key_for(spec_id))

    def static_bindings(self, scope: str) -> list[Binding]:
        """`bindings_for(scope)` with the live keymap applied — for the help
        screen's pages for a screen that isn't the currently active one, whose
        `active_bindings` Textual can't give us directly."""
        keymap = resolve_keymap(self.overrides)
        return [binding.with_key(keymap[binding.id]) if binding.id else binding for binding in _binding_list(scope)]
