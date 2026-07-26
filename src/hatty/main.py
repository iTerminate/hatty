# hatty — MIT License. See LICENSE file for details.
import asyncio
from datetime import datetime, timedelta, timezone

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header

from hatty import config, terminal_title
from hatty import storage as storage_module
from hatty.client import HAClient
from hatty.command_provider import HACommandProvider  # noqa: F401 (re-exported for tests)
from hatty.const import (
    CONFIG_KEY_COLUMNS,
    CONFIG_KEY_DASHBOARDS,
    CONFIG_KEY_DEFAULT_DASHBOARD,
    CONFIG_KEY_DEFAULT_LIST,
    CONFIG_KEY_ENTITY_NAMES,
    CONFIG_KEY_GRAPH_HOURS,
    CONFIG_KEY_GRAPH_TYPE,
    CONFIG_KEY_HOME_ASSISTANT,
    CONFIG_KEY_LISTS,
    CONFIG_KEY_LOG_HOURS,
    CONFIG_KEY_MANUAL_LISTS,
    CONFIG_KEY_SAVED_GRAPHS,
    CONFIG_KEY_TERMINAL_TITLE,
    CONFIG_KEY_TERMINAL_TITLE_ENABLED,
    CONFIG_KEY_THEME,
    CONFIG_KEY_TOKEN,
    CONFIG_KEY_URL,
    CONTROLLABLE_DOMAINS,
    DEFAULT_COLUMNS,
    DEFAULT_GRAPH_HOURS,
    DEFAULT_LOG_HOURS,
    DEFAULT_TERMINAL_TITLE,
    TOGGLABLE_DOMAINS,
)
from hatty.controllers.connection import ConnectionController
from hatty.controllers.dashboards import DashboardController
from hatty.controllers.graphs import GraphController, _trim_history  # noqa: F401 (_trim_history re-exported for tests)
from hatty.controllers.lists import ListController
from hatty.controllers.notifications import NotificationController
from hatty.service_calls import _CONTROL_SERVICE_BUILDERS
from hatty.types import Entity
from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.column_config_popup import ColumnConfigPopup
from hatty.ui.config_screen import ConfigScreen
from hatty.ui.confirm_popup import ConfirmPopup
from hatty.ui.controls.control_popup import EntityControlPopup
from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.entity_table import EntitiesTable, entity_matches, get_display_name
from hatty.ui.graph.entity_detail import EntityDetailPanel
from hatty.ui.help_popup import HelpPopup
from hatty.ui.list_selection_popup import ListSelectionPopup
from hatty.ui.rename_entity_popup import RenameEntityPopup
from hatty.ui.search_input import SearchInput

# In --demo mode the seeded DemoHAClient answers get_states almost instantly,
# so the splash would otherwise flash for a fraction of a second — never long
# enough to be seen (e.g. in the recorded demo screencast). Hold it visible for
# a moment on that first auto-dismiss only; real-HA boot is unaffected.
DEMO_SPLASH_SECONDS = 2.5


def _controller_proxy(controller_attr: str, target_attr: str) -> property:
    """A read/write property forwarding to ``self.<controller_attr>.<target_attr>``.

    Domain state lives on the controllers (``list_ctl``/``dash_ctl``/``graph_ctl``),
    but screens and tests read *and assign* these names on the app, so each stays a
    real ``property`` — assignment still routes through the setter, unchanged.
    """

    def getter(self):
        return getattr(getattr(self, controller_attr), target_attr)

    def setter(self, value):
        setattr(getattr(self, controller_attr), target_attr, value)

    return property(getter, setter)


class HACLI(App):
    COMMANDS = App.COMMANDS | {HACommandProvider}

    PENDING_TIMEOUT_SECONDS = 10  # class attribute so tests can override it per-instance

    BINDINGS = [
        Binding("/", "toggle_search", "Search"),
        Binding("e", "expand_entity", "Controls"),
        Binding("space", "toggle_list_membership", "In List"),
        Binding("shift+up", "move_entity_in_list(-1)", "Move Up", show=False),
        Binding("shift+down", "move_entity_in_list(1)", "Move Down", show=False),
        Binding("o", "toggle_list_sort", "Sort Order", show=False),
        Binding("L", "toggle_list_lock", "Lock List", show=False),
        Binding("r", "rename_entity", "Rename", show=False),
        Binding("u", "undo", "Undo", show=False),
        Binding("ctrl+r", "redo", "Redo", show=False),
        Binding("l", "show_list_selection_popup", "Lists", show=False),
        Binding("c", "show_column_config", "Columns", show=False),
        Binding("a", "toggle_activity_log", "Activity Log", show=False),
        Binding("A", "toggle_device_log", "Device Log", show=False),
        Binding("i", "toggle_entity_log", "Entity Log", show=False),
        Binding("f", "maximize_log", "Maximize Log", show=False),
        Binding("left", "log_older", "Older Events", show=False, priority=True),
        Binding("right", "log_newer", "Newer Events", show=False, priority=True),
        Binding("g", "toggle_graph", "Graph", show=False),
        Binding("G", "graph_fullscreen", "Full Graph", show=False),
        Binding("+", "add_to_graph", "Compare", show=False),
        Binding("d", "show_dashboard", "Dashboard", show=False),
        Binding("D", "show_device_tree", "Device Tree", show=False),
        Binding("s", "show_saved_graphs_popup", "Saved Graphs", show=False),
        Binding("t", "cycle_graph_type", "Graph Type"),
        Binding("T", "show_graph_duration", "Duration", show=False),
        Binding("n", "search_next", "Next Match", show=False),
        Binding("N", "search_prev", "Prev Match", show=False),
        Binding("question_mark", "show_help", "Help"),
        Binding("escape", "go_back", "Back/Clear"),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    def __init__(self, config_path: str | None = None, demo: bool = False):
        super().__init__()
        self.config_path = config_path
        self._demo = demo
        self._demo_splash_held = False
        self._client_factory = HAClient
        if demo:
            from hatty.demo import demo_client_factory

            self._client_factory = demo_client_factory()
        self.storage: storage_module.Storage | None = None
        # Prior tmux window state captured by terminal_title.apply(), for
        # terminal_title.restore() to put back on exit / config change.
        self._title_restore: dict | None = None

        self.list_ctl = ListController(self)
        self.dash_ctl = DashboardController(self)
        self.graph_ctl = GraphController(self)
        self.conn_ctl = ConnectionController(self)
        self.notify_ctl = NotificationController(self)

        self.all_entities: list = []
        self.entity_registry: list = []
        self.device_registry: list = []
        self.area_registry: list = []
        self.entity_names: dict[str, str] = {}
        self.search_term = ""
        self.vi_search_term = ""
        self.vi_search_matches: list[str] = []
        self.vi_search_index = -1
        self.columns = list(DEFAULT_COLUMNS)
        self.ha_url = ""
        self.current_view = "entities"
        self._log_entity_ids: set[str] = set()
        self._log_query_ids: list[str] = []
        self._log_generation: int = 0
        self._log_mode: str = "list"
        self._log_title_base: str = ""
        self._log_end: datetime | None = None
        self._update_pending = False
        self.pending_call_status: dict[str, str] = {}
        self._pending_call_timers: dict[str, Timer] = {}
        # Fire-and-forget tasks hold a reference here so asyncio can't GC them
        # mid-flight; done tasks remove themselves.
        self._bg_tasks: set[asyncio.Task] = set()

    # Config key -> the app attribute that is its in-memory working copy, derived
    # from storage.PERSISTED so there is one source of truth (issue #168).
    _PERSIST_ATTRS = {key: attr for key, (attr, _dest) in storage_module.PERSISTED.items()}

    def spawn(self, coro) -> asyncio.Task:
        """create_task with the reference tracked in _bg_tasks."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def persist(self, *keys: str) -> None:
        """Mirror the named collections from their app attributes into
        app_config and schedule an async save. With no keys, just schedules
        the save (for scalar values written straight into app_config)."""
        for key in keys:
            self.app_config[key] = getattr(self, self._PERSIST_ATTRS[key])
        self.spawn(self._save_config_async())

    @property
    def graph_hours(self) -> float:
        return self.app_config.get(CONFIG_KEY_GRAPH_HOURS, DEFAULT_GRAPH_HOURS)

    @property
    def log_hours(self) -> float:
        return self.app_config.get(CONFIG_KEY_LOG_HOURS, DEFAULT_LOG_HOURS)

    # ── Domain state lives on the controllers; these proxies preserve the app's
    #    historical surface — screens and tests read *and assign* these directly.
    #    Each is a real property, so assignment still routes to the controller. ──

    # List state (ListController)
    entity_lists = _controller_proxy("list_ctl", "entity_lists")
    list_names = _controller_proxy("list_ctl", "list_names")
    current_list_name = _controller_proxy("list_ctl", "current_list_name")
    _last_list_name = _controller_proxy("list_ctl", "last_list_name")
    default_list_name = _controller_proxy("list_ctl", "default_list_name")
    manual_lists = _controller_proxy("list_ctl", "manual_lists")
    _undo_stack = _controller_proxy("list_ctl", "undo_stack")
    _redo_stack = _controller_proxy("list_ctl", "redo_stack")

    # Dashboard state (DashboardController)
    dashboards = _controller_proxy("dash_ctl", "dashboards")
    dashboard_names = _controller_proxy("dash_ctl", "dashboard_names")
    default_dashboard_name = _controller_proxy("dash_ctl", "default_dashboard_name")
    current_dashboard_name = _controller_proxy("dash_ctl", "current_dashboard_name")
    _temp_dashboard_names = _controller_proxy("dash_ctl", "temp_dashboard_names")

    # Graph/history state (GraphController)
    entity_history = _controller_proxy("graph_ctl", "entity_history")
    climate_history = _controller_proxy("graph_ctl", "climate_history")
    _detail_entity_id = _controller_proxy("graph_ctl", "detail_entity_id")
    _graph_extra_ids = _controller_proxy("graph_ctl", "graph_extra_ids")
    saved_graphs = _controller_proxy("graph_ctl", "saved_graphs")

    def compose(self) -> ComposeResult:
        yield Header()
        yield SearchInput(id="search_input")
        yield EntitiesTable(id="entities_table")
        yield EntityDetailPanel(id="detail_panel")
        yield ActivityLogPanel(id="activity_log_panel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search_input", SearchInput).display = False
        self.query_one("#entities_table", EntitiesTable).focus()

        if self._demo:
            self._start_demo()
            return

        self.app_config = config.load_config(self.config_path)

        # First run (or copied-but-unedited example): walk the user through
        # entering a URL + token instead of dead-ending on an error sub_title.
        if config.needs_onboarding(self.app_config):
            self._launch_onboarding()
            return

        if self.app_config.get("error"):
            self.sub_title = f"Error: {self.app_config['error']}"
            return

        self._apply_config(self.app_config)

        if not self.ha_url or not self._token:
            self.sub_title = "Error: URL or token not found in config"
            return

        self._show_splash()
        self._start_client()

    def on_unmount(self) -> None:
        try:
            terminal_title.restore(self._title_restore)
        except Exception as e:
            self.log.error(f"Error restoring terminal title: {e}")
        if self.storage is not None:
            try:
                self.storage.close()
            except Exception as e:
                self.log.error(f"Error closing storage: {e}")

    def _storage_db_path(self):
        from pathlib import Path

        if self.config_path:
            return Path(self.config_path).parent / "hatty.db"
        import os

        data_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "hatty"
        return data_dir / "hatty.db"

    def _start_demo(self) -> None:
        """Boot straight into demo mode: no config file, no onboarding, no disk.
        The demo client is already wired at _client_factory (see __init__); here we
        just supply the seeded config and reuse the normal apply/start seam."""
        from hatty.demo import demo_config

        self.app_config = demo_config()
        self._apply_config(self.app_config)
        self.title = "hatty — DEMO"
        self._show_splash()
        self._start_client()

    def _open_storage(self, cfg: dict) -> None:
        """Open the SQLite collections DB, importing the collections from the YAML
        config exactly once (first run on this DB), then load them back so the DB
        is the authoritative source for lists/dashboards/saved graphs/etc."""
        if self._demo:
            # Demo mode is disk-free: keep the seeded collections in app_config only.
            self.storage = None
            return
        try:
            self.storage = storage_module.Storage(self._storage_db_path())
            self.storage.connect()
            if self.storage.is_empty():
                # One-time migration from a legacy all-in-YAML config.
                self.storage.save_all({key: cfg.get(key) for key in storage_module.COLLECTION_KEYS})
            loaded = self.storage.load_all()
            cfg.update(loaded)
        except Exception as e:
            # A broken DB must not stop the app; fall back to the YAML collections.
            self.log.error(f"Storage unavailable, using config-file collections: {e}")
            self.storage = None

    def _apply_config(self, cfg: dict) -> None:
        """Populate app state from a (valid) config dict. Shared by on_mount and
        the post-onboarding restart so neither path diverges."""
        self._open_storage(cfg)
        self.entity_lists = cfg.get(CONFIG_KEY_LISTS, {})
        self.list_names = list(self.entity_lists.keys())
        self.default_list_name = cfg.get(CONFIG_KEY_DEFAULT_LIST)
        self.manual_lists = set(cfg.get(CONFIG_KEY_MANUAL_LISTS) or [])
        self.columns = cfg.get(CONFIG_KEY_COLUMNS, list(DEFAULT_COLUMNS))
        self.entity_names = cfg.get(CONFIG_KEY_ENTITY_NAMES, {})
        self.dashboards = cfg.get(CONFIG_KEY_DASHBOARDS, {})
        self.dashboard_names = list(self.dashboards.keys())
        self.default_dashboard_name = cfg.get(CONFIG_KEY_DEFAULT_DASHBOARD)
        self.saved_graphs = cfg.get(CONFIG_KEY_SAVED_GRAPHS, {})
        # Seeds entity_lists[NOTIFY_LIST_NAME] if missing and shows/hides it in
        # list_names per the "enabled" pref — must run before the auto-select
        # fallback below so a freshly-seeded reserved list is never picked.
        self.notify_ctl.sync()

        saved_theme = cfg.get(CONFIG_KEY_THEME)
        if saved_theme and saved_theme in self.available_themes:
            self.theme = saved_theme

        self._apply_terminal_title(cfg)

        self.query_one("#detail_panel", EntityDetailPanel).apply_saved_graph_type(cfg.get(CONFIG_KEY_GRAPH_TYPE))

        selectable = [n for n in self.list_names if n != self.notify_ctl.list_name]
        if self.default_list_name and self.default_list_name in self.entity_lists:
            self.current_list_name = self.default_list_name
        elif selectable:
            self.current_list_name = selectable[0]
        self._last_list_name = self.current_list_name

        ha_config = cfg.get(CONFIG_KEY_HOME_ASSISTANT, {})
        self.ha_url = ha_config.get(CONFIG_KEY_URL)
        self._token = ha_config.get(CONFIG_KEY_TOKEN)

    def _apply_terminal_title(self, cfg: dict) -> None:
        """Set the terminal/tmux window title per the "terminal_title_enabled"/
        "terminal_title" prefs (default: on, "hatty"). Best-effort — a cosmetic
        title must never affect startup."""
        if not cfg.get(CONFIG_KEY_TERMINAL_TITLE_ENABLED, True):
            return
        title = cfg.get(CONFIG_KEY_TERMINAL_TITLE) or DEFAULT_TERMINAL_TITLE
        try:
            self._title_restore = terminal_title.apply(title)
        except Exception as e:
            self.log.error(f"Error setting terminal title: {e}")

    def _start_client(self) -> None:
        self.set_title_based_on_focused_ui()
        # Re-running the setup wizard replaces the client; retire the old one's
        # reconnect loop so it doesn't linger with stale credentials.
        old_client = getattr(self, "client", None)
        if old_client is not None:
            self.spawn(old_client.close())
        self.client = self._client_factory(self.ha_url, self._token, self.handle_ha_message, self.log)
        # The entity registry is (re)fetched on each ha_connected, not here, so a
        # first connect that has to retry (or any reconnect) still loads it.
        self.spawn(self.client.listen())

    def _show_splash(self, status: str | None = None) -> None:
        from hatty.ui.splash_screen import SplashScreen

        if self._splash_screen() is not None:
            return  # already showing — don't stack a second one
        self.push_screen(SplashScreen(status) if status else SplashScreen())

    def _splash_screen(self):
        """The splash iff it's still the top of the screen stack, else None — so
        status updates and the auto-dismiss can't touch a screen the user opened
        after dismissing the splash themselves. Reads the stack via the
        non-raising `screen_stack` snapshot (rather than `self.screen`) since
        the demo splash hold's deferred timer (see DEMO_SPLASH_SECONDS) can
        fire after the app has already exited, when there's no screen at all."""
        from hatty.ui.splash_screen import SplashScreen

        stack = self.screen_stack
        return stack[-1] if stack and isinstance(stack[-1], SplashScreen) else None

    def _dismiss_splash(self) -> None:
        splash = self._splash_screen()
        if splash is None:
            return
        # Demo mode: hold the splash up for a moment on its first auto-dismiss
        # (see DEMO_SPLASH_SECONDS) so it's actually visible instead of a
        # single-frame flash. A keypress (SplashScreen.on_key) can still skip
        # it early — the deferred call below just no-ops if that happened.
        if self._demo and not self._demo_splash_held:
            self._demo_splash_held = True
            self.set_timer(DEMO_SPLASH_SECONDS, self._dismiss_splash)
            return
        self.pop_screen()

    def _launch_onboarding(self) -> None:
        from hatty.ui.onboarding_screen import OnboardingScreen

        ha = self.app_config.get(CONFIG_KEY_HOME_ASSISTANT) or {}
        self.sub_title = "Setup required"
        self.push_screen(
            OnboardingScreen(url=ha.get(CONFIG_KEY_URL, ""), token=ha.get(CONFIG_KEY_TOKEN, "")),
            self._on_onboarding_done,
        )

    def _on_onboarding_done(self, result: dict | None) -> None:
        if not result:
            # User cancelled without configuring; leave the informative sub_title.
            self.sub_title = "Setup incomplete — configure the URL and token to connect"
            return
        # Seed a full config skeleton if there wasn't a usable one, then write the
        # entered credentials and start connecting — no restart needed.
        base = self.app_config if not self.app_config.get("error") else config.default_config()
        merged = {**config.default_config(), **base}
        merged[CONFIG_KEY_HOME_ASSISTANT] = {
            CONFIG_KEY_URL: result["url"],
            CONFIG_KEY_TOKEN: result["token"],
        }
        config.save_config(merged, self.config_path)
        self.app_config = merged
        self._apply_config(merged)
        self._start_client()

    def set_title_based_on_focused_ui(self) -> None:
        if self.current_list_name:
            glyph = "🔐" if self.list_ctl.is_locked(self.current_list_name) else "🔓"
            base = f"List: {self.current_list_name} {glyph}"
        else:
            base = f"Connected to {self.ha_url}..."
        if self.search_term:
            visible = len(self._currently_displayed_entities())
            total = len(self.all_entities)
            self.sub_title = f"{base} — search: '{self.search_term}' — {visible}/{total}"
        else:
            self.sub_title = base

    def _list_context_label(self) -> str:
        return f"List: {self.current_list_name}" if self.current_list_name else "View All"

    # ── List management ──────────────────────────────────────────────────────

    def pop_to_base_screen(self) -> None:
        while len(self.screen_stack) > 1:
            self.pop_screen()

    def action_palette_switch_list(self) -> None:
        target = self.list_ctl.jump_target()
        if target:
            self.pop_to_base_screen()
            self.select_or_create_list(target)

    def action_show_list_selection_popup(self) -> None:
        if self.current_list_name is not None and self.search_term:
            # A list is already active but hidden behind a search filter —
            # just clear the search and return to it, rather than making the
            # user re-pick the same list from the popup (issue #211).
            self.pop_to_base_screen()
            self.search_term = ""
            self.set_title_based_on_focused_ui()
            self._update_entities_display()
            return
        if self.current_list_name is None:
            target = self.list_ctl.jump_target()
            if target:
                self.pop_to_base_screen()
                self.select_or_create_list(target)
                return

        def callback(result) -> None:
            if isinstance(result, dict):
                self.list_ctl.handle_popup_action(result)
            elif isinstance(result, str):
                self.select_or_create_list(result)

        self.push_screen(ListSelectionPopup(), callback)

    def select_or_create_list(self, list_name: str) -> None:
        self.list_ctl.select_or_create(list_name)

    def action_toggle_list_membership(self) -> None:
        entities_table = self.query_one("#entities_table", EntitiesTable)
        if not entities_table.row_count:
            self.notify("Toggle membership attempted on empty table", title="Warning", severity="warning")
            return

        if not self.current_list_name:
            self.notify("No list selected.", title="Warning", severity="warning")
            return

        entity_id = self._selected_entity_id()
        if not entity_id:
            return

        current_list = self.entity_lists.get(self.current_list_name, [])
        action = "remove" if entity_id in current_list else "add"
        list_name = self.current_list_name

        # Removing while viewing a locked list requires an unlock confirmation
        # (issue #214) — but only in pure list-view; an active search is the
        # "filter list for adding items" path the issue exempts, since there
        # every displayed entity isn't necessarily a list member.
        if action == "remove" and not self.search_term and self.list_ctl.is_locked(list_name):

            def _unlock_and_remove(confirmed: bool | None, _name: str = list_name, _eid: str = entity_id) -> None:
                if not confirmed:
                    return
                self.list_ctl.unlock(_name)
                self._apply_membership_toggle(_name, _eid, "remove")

            self.push_screen(ConfirmPopup(f"Unlock '{list_name}' to remove items?"), _unlock_and_remove)
            return

        self._apply_membership_toggle(list_name, entity_id, action)

    def _apply_membership_toggle(self, list_name: str, entity_id: str, action: str) -> None:
        entities_table = self.query_one("#entities_table", EntitiesTable)
        cursor_row = entities_table.cursor_row
        self.list_ctl.apply_membership(list_name, entity_id, action)
        self.list_ctl.record_toggle(list_name, entity_id, action)

        verb, prep = ("Removed", "from") if action == "remove" else ("Added", "to")
        self.notify(f"{verb} {entity_id} {prep} {list_name}", title="List Updated")

        # Keep the cursor at the same visual row rather than chasing the entity to its new sorted position.
        if entities_table.row_count > 0:
            entities_table.move_cursor(row=min(cursor_row, entities_table.row_count - 1), animate=False)

    def action_move_entity_in_list(self, delta: int) -> None:
        """Shift+up/down: move the highlighted entity within the active list
        (issue #213). Freezes the visible order as the list's manual order."""
        if not self.current_list_name:
            self.notify("Select a list to reorder.", title="Warning", severity="warning")
            return
        if self.search_term:
            self.notify("Clear search to reorder.", title="Warning", severity="warning")
            return

        entity_id = self._selected_entity_id()
        if not entity_id:
            return

        entities_table = self.query_one("#entities_table", EntitiesTable)
        ordered = entities_table.ordered_entity_ids()
        if self.list_ctl.reorder(self.current_list_name, ordered, entity_id, delta):
            entities_table.jump_cursor_to_row_key(entity_id)

    def action_toggle_list_sort(self) -> None:
        """`o`: toggle the active list between manual order and alphabetical
        (today's default, issue #213)."""
        if not self.current_list_name:
            self.notify("Select a list to change its sort order.", title="Warning", severity="warning")
            return

        if self.current_list_name in self.manual_lists:
            self.list_ctl.disable_manual(self.current_list_name)
            self.notify(f"'{self.current_list_name}' sorted alphabetically.", title="Sort Order")
        else:
            self.list_ctl.set_manual(self.current_list_name)
            self.notify(f"'{self.current_list_name}' set to manual order.", title="Sort Order")

    def action_toggle_list_lock(self) -> None:
        """`L`: manually lock/unlock the active list against removal (issue
        #214) without going through the remove-triggered confirmation popup.
        Like the unlock-via-popup path, this is transient and re-locks the
        next time the list is (re)entered."""
        if not self.current_list_name:
            self.notify("Select a list to lock/unlock.", title="Warning", severity="warning")
            return

        if self.list_ctl.is_locked(self.current_list_name):
            self.list_ctl.unlock(self.current_list_name)
            self.notify(f"'{self.current_list_name}' unlocked.", title="List Lock")
        else:
            self.list_ctl.lock(self.current_list_name)
            self.notify(f"'{self.current_list_name}' locked.", title="List Lock")
        self.set_title_based_on_focused_ui()

    def action_undo(self) -> None:
        self.list_ctl.undo()

    def action_redo(self) -> None:
        self.list_ctl.redo()

    # ── Column configuration ─────────────────────────────────────────────────

    def action_show_column_config(self) -> None:
        def callback(result) -> None:
            if result is not None:
                self.columns = result
                self.persist("columns")
                self._update_entities_display()

        self.push_screen(ColumnConfigPopup(list(self.columns)), callback)

    # ── Help ──────────────────────────────────────────────────────────────────

    def action_show_help(self) -> None:
        from hatty.ui.controls.light_screen import LightControlScreen
        from hatty.ui.controls.media_player_screen import MediaPlayerControlScreen
        from hatty.ui.device_tree_screen import DeviceTreeScreen
        from hatty.ui.graph.preview_screen import GraphPreviewScreen
        from hatty.ui.help_popup import action_name, binding_entries, sectioned_rows

        def page_rows(screen_cls: type | None, is_active: bool) -> list[tuple[str, str]]:
            # A screen opting into HELP_ALL_MODES (GraphPreviewScreen) always builds
            # from its full static BINDINGS plus an app-level "From anywhere" section,
            # regardless of which mode is active — its help page groups both modes'
            # bindings side by side instead of only showing whichever is live (#7).
            if screen_cls is not None and getattr(screen_cls, "HELP_ALL_MODES", False):
                rows = sectioned_rows(binding_entries(screen_cls.BINDINGS), screen_cls.HELP_SECTIONS)
                allowed = screen_cls.ALLOWED_APP_ACTIONS
                app_rows = [(key, desc) for key, desc, action in binding_entries(self.BINDINGS) if action in allowed]
                if app_rows:
                    rows = [*rows, ("", "From anywhere"), *app_rows]
                return rows

            if is_active:
                entries = [
                    (active.binding.key, active.binding.description, action_name(active.binding.action))
                    for active in self.screen.active_bindings.values()
                    if active.binding.description
                ]
            else:
                static_bindings = self.BINDINGS if screen_cls is None else screen_cls.BINDINGS
                entries = binding_entries(static_bindings)

            sections = getattr(screen_cls, "HELP_SECTIONS", None) if screen_cls is not None else None
            if sections:
                return sectioned_rows(entries, sections)
            return [(key, desc) for key, desc, _ in entries]

        # `None` marks the base (main-table) screen, which isn't a dedicated
        # Screen subclass — the app composes its widgets straight onto the
        # auto-created screen at the bottom of the stack.
        page_defs: list[tuple[str, type | None]] = [
            ("Main", None),
            ("Dashboard", DashboardScreen),
            ("Device Tree", DeviceTreeScreen),
            ("Graph", GraphPreviewScreen),
            ("Light Control", LightControlScreen),
            ("Media Player", MediaPlayerControlScreen),
        ]

        pages: list[tuple[str, list[tuple[str, str]]]] = []
        active_index = 0
        for i, (title, screen_cls) in enumerate(page_defs):
            is_active = (
                self.screen is self.screen_stack[0] if screen_cls is None else isinstance(self.screen, screen_cls)
            )
            if is_active:
                active_index = i
            pages.append((title, page_rows(screen_cls, is_active)))

        self.push_screen(HelpPopup(pages, active_index))

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def action_show_dashboard(self) -> None:
        if not self.dashboard_names:
            self.dash_ctl.create("Main", rows=3, cols=3)
        elif self.current_dashboard_name not in self.dashboards:
            target = self.default_dashboard_name if self.default_dashboard_name in self.dashboards else None
            self.current_dashboard_name = target or self.dashboard_names[0]
        self.pop_to_base_screen()
        self.push_screen(DashboardScreen())

    # ── Device / area tree ────────────────────────────────────────────────────

    def action_show_device_tree(self) -> None:
        from hatty.ui.device_tree_screen import DeviceTreeScreen

        self.pop_to_base_screen()
        # Carry the table's selection into the tree, and take it back on close so
        # the cursor follows the entity both ways (issue #153).
        entity_id = self._selected_entity_id()
        self.push_screen(DeviceTreeScreen(entity_id), self._on_device_tree_closed)

    def _on_device_tree_closed(self, entity_id: str | None) -> None:
        if entity_id:
            self.query_one("#entities_table", EntitiesTable).jump_cursor_to_row_key(entity_id)

    def _refresh_device_tree(self) -> None:
        """Rebuild the device tree if it's the active screen (e.g. a registry
        just (re)loaded or a device moved area)."""
        from hatty.ui.device_tree_screen import DeviceTreeScreen

        if isinstance(self.screen, DeviceTreeScreen):
            self.screen.rebuild()

    def _refresh_device_tree_entity(self, entity_id: str) -> None:
        """Update a single entity's leaf label in the device tree if it's active
        (cheap live update, no full rebuild)."""
        from hatty.ui.device_tree_screen import DeviceTreeScreen

        if isinstance(self.screen, DeviceTreeScreen):
            self.screen.refresh_entity(entity_id)

    def _resize_dashboard(self, name: str, rows: int, cols: int) -> None:
        self.dash_ctl.resize(name, rows, cols)

    def _set_dashboard_slot(self, *args, **kwargs) -> None:
        self.dash_ctl.set_slot(*args, **kwargs)

    # ── Graph panel ──────────────────────────────────────────────────────────

    def action_toggle_graph(self) -> None:
        panel = self.query_one("#detail_panel", EntityDetailPanel)
        if panel.has_class("-visible"):
            self.graph_ctl.close_panel()
            return

        entity_id = self._selected_entity_id()
        if not entity_id:
            return

        entity = self.find_entity(entity_id)
        if not entity:
            return

        if not self.graph_ctl.is_graphable(entity):
            self.notify("No graph available for this entity type.", severity="warning")
            return

        log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)
        if log_panel.has_class("-visible"):
            log_panel.remove_class("-visible")
            self._log_entity_ids.clear()

        self.graph_ctl.open_graph_for(entity_id, entity)

    def action_add_to_graph(self) -> None:
        panel = self.query_one("#detail_panel", EntityDetailPanel)
        if not panel.has_class("-visible"):
            return

        entity_id = self._selected_entity_id()
        if not entity_id or entity_id in self._graph_extra_ids:
            return

        entity = self.find_entity(entity_id)
        if not entity:
            return

        if not self.graph_ctl.is_graphable(entity):
            self.notify("No graph available for this entity type.", severity="warning")
            return

        detail_is_climate = self._detail_entity_id and self.graph_ctl.is_climate_entity(self._detail_entity_id)
        if self.graph_ctl.is_climate_entity(entity_id) or detail_is_climate:
            self.notify("Climate entities can't be combined with comparison graphs.", severity="warning")
            return

        # The detail entity follows the cursor, so check the whole graphed set
        # (current detail + extras) when refusing binary/numeric mixing.
        graph_ids = [eid for eid in [self._detail_entity_id, *self._graph_extra_ids] if eid]
        candidate_is_binary = self.graph_ctl.is_binary_entity(entity_id)
        if any(self.graph_ctl.is_binary_entity(eid) != candidate_is_binary for eid in graph_ids):
            self.notify("Binary sensors can only be compared with other binary sensors.", severity="warning")
            return

        self._graph_extra_ids.append(entity_id)

        async def _load_and_refresh() -> None:
            await self.graph_ctl.ensure_entity_history(entity_id)
            self.graph_ctl.refresh_detail_panel()

        self.spawn(_load_and_refresh())

    def _close_log_panel(self) -> None:
        log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)
        log_panel.remove_class("-visible")
        log_panel.remove_class("-maximized")
        self._log_entity_ids.clear()
        self._log_query_ids = []
        self._log_mode = "list"
        self._log_end = None
        self.refresh_bindings()

    def action_maximize_log(self) -> None:
        log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)
        if not log_panel.has_class("-visible"):
            return
        log_panel.toggle_class("-maximized")

    _LOG_HINT = "f maximize · ←/→ older/newer · T timeframe · a/A/i close"

    @staticmethod
    def _format_log_hours(hours: float) -> str:
        return f"{int(hours)}h" if hours == int(hours) else f"{hours:.1f}h"

    def _log_range_suffix(self) -> str:
        """`(last Xh)` while live, or the paged-back window's full start–end
        range — mirrors the fullscreen graph's window-status suffix."""
        from hatty.ui.graph.plot_time import ts_to_full

        if self._log_end is None:
            return f"  (last {self._format_log_hours(self.log_hours)})"
        end = self._log_end
        start = end - timedelta(hours=self.log_hours)
        return f"  ({ts_to_full(start.isoformat())} – {ts_to_full(end.isoformat())})"

    def _set_log_title(self) -> None:
        log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)
        log_panel.set_title(self._log_title_base + self._log_range_suffix())

    def _open_log_panel(self, entity_ids: list[str], title: str) -> None:
        log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)
        self._log_entity_ids = set(entity_ids)
        self._log_query_ids = list(entity_ids)
        self._log_end = None
        self._log_title_base = title
        log_panel.set_hint(self._LOG_HINT)
        log_panel.clear()
        log_panel.remove_class("-maximized")
        log_panel.add_class("-visible")
        self.refresh_bindings()
        self._reload_log()

    def _reload_log(self) -> None:
        self._log_generation += 1
        current_gen = self._log_generation
        self._set_log_title()
        self.spawn(self._load_activity_log(self._log_query_ids, current_gen))

    def action_log_older(self) -> None:
        now = datetime.now(timezone.utc)
        self._log_end = (self._log_end or now) - timedelta(hours=self.log_hours)
        self._reload_log()

    def action_log_newer(self) -> None:
        if self._log_end is None:
            return
        now = datetime.now(timezone.utc)
        new_end = self._log_end + timedelta(hours=self.log_hours)
        self._log_end = None if new_end >= now else new_end
        self._reload_log()

    # A device log covering a whole list can expand to many sibling entities; cap
    # the set so a single logbook GET's entity_id= param can't blow up.
    _DEVICE_LOG_MAX_ENTITIES = 200

    def _get_device_entity_ids(self, entity_id: str) -> tuple[list[str], str, bool]:
        entity = self.find_entity(entity_id)
        label = get_display_name(entity) if entity else entity_id

        reg_entry = next((e for e in self.entity_registry if e.get("entity_id") == entity_id), None)
        device_id = reg_entry.get("device_id") if reg_entry else None

        if not device_id:
            return ([entity_id], label, False)

        siblings = [
            e["entity_id"] for e in self.entity_registry if e.get("device_id") == device_id and e.get("entity_id")
        ]
        if not siblings:
            siblings = [entity_id]

        return (siblings, label, True)

    def _device_index(self) -> dict[str, list[str]]:
        """device_id -> its registered entity_ids, built once per call."""
        index: dict[str, list[str]] = {}
        for entry in self.entity_registry:
            device_id = entry.get("device_id")
            entity_id = entry.get("entity_id")
            if device_id and entity_id:
                index.setdefault(device_id, []).append(entity_id)
        return index

    def _expand_to_device_entity_ids(self, entity_ids: list[str]) -> tuple[list[str], int]:
        """Every entity of every device backing any of entity_ids. Entities with
        no registry entry / no device pass through as themselves. Returns the
        deduped, order-preserving expansion plus the number of distinct devices."""
        index = self._device_index()
        reg_device = {e.get("entity_id"): e.get("device_id") for e in self.entity_registry}

        expanded: list[str] = []
        seen: set[str] = set()
        devices: set[str] = set()

        def _add(eid: str) -> None:
            if eid and eid not in seen:
                seen.add(eid)
                expanded.append(eid)

        for entity_id in entity_ids:
            device_id = reg_device.get(entity_id)
            if device_id and device_id in index:
                devices.add(device_id)
                for sibling in index[device_id]:
                    _add(sibling)
            else:
                _add(entity_id)

        return (expanded, len(devices))

    def action_toggle_activity_log(self) -> None:
        log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)

        if log_panel.has_class("-visible"):
            self._close_log_panel()
            return

        if self.query_one("#detail_panel", EntityDetailPanel).has_class("-visible"):
            self.graph_ctl.close_panel()

        if self.current_list_name:
            entity_ids = list(self.entity_lists.get(self.current_list_name, []))
            title = f"Activity Log — {self.current_list_name}"
        else:
            entity_ids = [e["entity_id"] for e in self.all_entities]
            if len(entity_ids) > 50:
                entity_ids = entity_ids[:50]
                self.notify(
                    "Showing log for first 50 entities. Select a list for a focused view.",
                    title="Activity Log",
                )
            title = "Activity Log — All Entities" if entity_ids else "Activity Log"

        if not entity_ids:
            self.notify("No entities to log. Select a list or add entities.", severity="warning")
            return

        self._log_mode = "list"
        self._open_log_panel(entity_ids, title)

    def action_toggle_device_log(self) -> None:
        log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)

        if log_panel.has_class("-visible"):
            self._close_log_panel()
            return

        if self.query_one("#detail_panel", EntityDetailPanel).has_class("-visible"):
            self.graph_ctl.close_panel()

        self._log_mode = "device"

        # With a list active, the device log covers every device backing every
        # entity in the list (all sibling channels), not just the selected row.
        if self.current_list_name:
            list_ids = list(self.entity_lists.get(self.current_list_name, []))
            if not list_ids:
                self.notify("No entities in this list to log.", title="Device Log", severity="warning")
                return
            entity_ids, device_count = self._expand_to_device_entity_ids(list_ids)
            if len(entity_ids) > self._DEVICE_LOG_MAX_ENTITIES:
                entity_ids = entity_ids[: self._DEVICE_LOG_MAX_ENTITIES]
                self.notify(
                    f"Showing device log for the first {self._DEVICE_LOG_MAX_ENTITIES} entities.",
                    title="Device Log",
                )
            self._open_log_panel(entity_ids, f"Device Log — {self.current_list_name} ({device_count} devices)")
            return

        # No list active: log the selected entity's device (expanding a View-All
        # of ~everything would be a useless whole-instance logbook query).
        entity_id = self._selected_entity_id()
        if not entity_id:
            self.notify("No entity selected.", title="Device Log", severity="warning")
            return

        entity_ids, label, device_found = self._get_device_entity_ids(entity_id)

        if not device_found:
            self.notify(
                f"No device found for {entity_id}. Showing single entity log.",
                title="Device Log",
            )

        self._open_log_panel(entity_ids, f"Device Log — {label}")

    def action_toggle_entity_log(self) -> None:
        log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)

        if log_panel.has_class("-visible"):
            self._close_log_panel()
            return

        if self.query_one("#detail_panel", EntityDetailPanel).has_class("-visible"):
            self.graph_ctl.close_panel()

        entity_id = self._selected_entity_id()
        if not entity_id:
            self.notify("No entity selected.", title="Activity Log", severity="warning")
            return

        entity = self.find_entity(entity_id)
        label = get_display_name(entity) if entity else entity_id

        self._log_mode = "entity"
        self._open_log_panel([entity_id], f"Activity Log — {label}")

    def on_data_table_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        if self._detail_entity_id is None:
            return

        entity_id = event.cell_key.row_key.value
        if not entity_id or entity_id == self._detail_entity_id:
            return

        entity = self.find_entity(entity_id)
        if not entity:
            return

        self.graph_ctl.follow_cursor(entity_id, entity)

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        # Enter on the entities table toggles the selected entity (mirrors the dashboard's Enter).
        # The focused DataTable owns the `enter` key, so this is wired via its CellSelected message
        # rather than an app-level binding.
        if event.data_table.id != "entities_table":
            return
        entity_id = self._selected_entity_id()
        if entity_id:
            self.toggle_or_open_controls(entity_id)

    async def _load_activity_log(self, entity_ids: list[str], generation: int) -> None:
        entries = await self.client.fetch_logbook(entity_ids, hours=self.log_hours, end=self._log_end)
        panel = self.query_one("#activity_log_panel", ActivityLogPanel)
        if not panel.has_class("-visible") or self._log_generation != generation:
            return
        if entries is None:
            self.notify("Failed to load activity log from Home Assistant.", title="Activity Log", severity="error")
            panel.load_history([])
        else:
            panel.load_history(entries)

    def action_cycle_graph_type(self) -> None:
        panel = self.query_one("#detail_panel", EntityDetailPanel)
        panel.cycle_graph_type()
        self.graph_ctl.refresh_detail_panel()
        self.app_config[CONFIG_KEY_GRAPH_TYPE] = panel.current_graph_type()
        self.persist()

    def action_show_graph_duration(self) -> None:
        from hatty.ui.graph.duration_popup import GraphDurationPopup

        # The two panels are mutually exclusive (opening either closes the
        # other), so `T` unambiguously targets whichever is open — the
        # activity log's timeframe when it's visible, the graph's otherwise.
        if self.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible"):
            self._show_log_duration_popup()
            return

        current = self.graph_hours

        def callback(hours: float | None) -> None:
            if hours is None:
                return
            self.app_config[CONFIG_KEY_GRAPH_HOURS] = hours
            self.persist()
            self._on_graph_hours_changed()

        self.push_screen(GraphDurationPopup(current), callback)

    def _show_log_duration_popup(self) -> None:
        from hatty.ui.graph.duration_popup import GraphDurationPopup

        current = self.log_hours

        def callback(hours: float | None) -> None:
            if hours is None:
                return
            self.app_config[CONFIG_KEY_LOG_HOURS] = hours
            self.persist()
            self._reload_log()

        self.push_screen(GraphDurationPopup(current, title="Activity Log Timeframe"), callback)

    def _on_graph_hours_changed(self) -> None:
        self.graph_ctl.on_graph_hours_changed()

    def action_graph_fullscreen(self) -> None:
        from hatty.ui.graph.preview_screen import GraphPreviewScreen

        if isinstance(self.screen, GraphPreviewScreen):
            return
        entity_id = self._detail_entity_id or self._selected_entity_id()
        if not entity_id:
            return
        entity = self.find_entity(entity_id)
        if entity and not self.graph_ctl.is_graphable(entity):
            self.notify("No graph available for this entity type.", severity="warning")
            return
        entity_ids = [entity_id] + [e for e in self._graph_extra_ids if e != entity_id]
        self.push_screen(
            GraphPreviewScreen(
                entity_ids,
                initial_graph_type=self.app_config.get(CONFIG_KEY_GRAPH_TYPE),
            )
        )

    # ── Saved graphs ─────────────────────────────────────────────────────────

    def action_show_saved_graphs_popup(self) -> None:
        from hatty.ui.graph.saved_graphs_popup import SavedGraphsPopup

        def callback(result) -> None:
            if isinstance(result, dict):
                self.graph_ctl.handle_saved_graphs_popup_action(result)

        self.push_screen(SavedGraphsPopup(), callback)

    # ── Config persistence ───────────────────────────────────────────────────

    def watch_theme(self, theme: str) -> None:
        if not hasattr(self, "app_config") or self.app_config.get(CONFIG_KEY_THEME) == theme:
            return
        self.app_config[CONFIG_KEY_THEME] = theme
        self.persist()

    def _collections_snapshot(self) -> dict:
        """The collection values to persist, with in-session temp dashboards
        excluded (they must never reach either the DB or the YAML)."""
        dashboards = self.app_config.get(CONFIG_KEY_DASHBOARDS) or {}
        if self._temp_dashboard_names:
            dashboards = {k: v for k, v in dashboards.items() if k not in self._temp_dashboard_names}
        snapshot = {
            CONFIG_KEY_LISTS: self.app_config.get(CONFIG_KEY_LISTS) or {},
            CONFIG_KEY_ENTITY_NAMES: self.app_config.get(CONFIG_KEY_ENTITY_NAMES) or {},
            CONFIG_KEY_DASHBOARDS: dashboards,
            CONFIG_KEY_SAVED_GRAPHS: self.app_config.get(CONFIG_KEY_SAVED_GRAPHS) or {},
            CONFIG_KEY_MANUAL_LISTS: self.app_config.get(CONFIG_KEY_MANUAL_LISTS) or set(),
            CONFIG_KEY_DEFAULT_LIST: self.app_config.get(CONFIG_KEY_DEFAULT_LIST),
            CONFIG_KEY_DEFAULT_DASHBOARD: self.app_config.get(CONFIG_KEY_DEFAULT_DASHBOARD),
        }
        # Guard the SSOT: every sqlite collection key must be snapshotted here, and
        # nothing extra (issue #168; the temp-dashboard/scalar handling above is why
        # this stays explicit rather than a generic loop).
        assert set(snapshot) == set(storage_module.COLLECTION_KEYS)
        return snapshot

    async def _save_config_async(self) -> None:
        if self._demo:
            # Demo mode is disk-free: interactions mutate in-memory state only and
            # must never overwrite the user's real config/DB.
            return
        collections = self._collections_snapshot()
        # Collections live in SQLite now; keep them out of the lean YAML, which
        # only carries connection settings + display preferences.
        to_save = {k: v for k, v in self.app_config.items() if k not in storage_module.COLLECTION_KEYS}
        try:
            config.save_config(to_save, self.config_path)
        except Exception as e:
            self.log.error(f"Error saving configuration: {e}")
            self.notify(f"Error saving configuration: {e}", title="Save Error", severity="error")
        if self.storage is not None:
            try:
                await asyncio.to_thread(self.storage.save_all, collections)
            except Exception as e:
                self.log.error(f"Error saving collections to storage: {e}")
                self.notify(f"Error saving data: {e}", title="Save Error", severity="error")

    # ── Navigation / back ────────────────────────────────────────────────────

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if isinstance(self.screen, DashboardScreen):
            return action in ("quit", "show_saved_graphs_popup")
        from hatty.ui.device_tree_screen import DeviceTreeScreen

        if isinstance(self.screen, DeviceTreeScreen):
            return action == "quit"
        from hatty.ui.graph.preview_screen import GraphPreviewScreen

        if isinstance(self.screen, GraphPreviewScreen):
            return action in GraphPreviewScreen.ALLOWED_APP_ACTIONS
        # Any other pushed screen (ConfigScreen, LightControlScreen, popups, …)
        # must not leak main-table bindings to the hidden base table (#187), but
        # Textual's own tab focus navigation (app.focus_next/previous) operates on
        # the pushed screen and must stay live so Tab works inside it (#202).
        if self.screen is not self.screen_stack[0] and not isinstance(
            self.screen, (DashboardScreen, DeviceTreeScreen, GraphPreviewScreen)
        ):
            return action in ("quit", "focus_next", "focus_previous")
        if action == "go_back":
            if self.query_one("#activity_log_panel", ActivityLogPanel).has_class("-maximized"):
                return True
            search_input = self.query_one("#search_input", SearchInput)
            if not search_input.display and not self.search_term and self.current_list_name is None:
                return None
        elif action == "expand_entity":
            entity_id = self._selected_entity_id()
            if not entity_id:
                return False
            entity = self.find_entity(entity_id)
            if not entity:
                return False
            domain = entity_id.split(".")[0]
            # "weather" is neither controllable nor graphable but still routes to
            # WeatherForecastScreen in open_entity_controls (issue #275) — without
            # this carve-out the binding (and its footer hint) never appears on the
            # main table for a weather entity, even though the dashboard/device tree
            # paths reach the same screen fine via their own check_action (#283).
            return domain in CONTROLLABLE_DOMAINS or domain == "weather" or self.graph_ctl.is_graphable(entity)
        elif action == "cycle_graph_type":
            return self._detail_entity_id is not None
        elif action == "graph_fullscreen":
            if self._detail_entity_id is not None:
                return True
            entity_id = self._selected_entity_id()
            entity = self.find_entity(entity_id) if entity_id else None
            return entity is not None and self.graph_ctl.is_graphable(entity)
        elif action == "add_to_graph":
            panel = self.query_one("#detail_panel", EntityDetailPanel)
            return panel.has_class("-visible")
        elif action == "maximize_log":
            return self.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible")
        elif action == "log_older":
            return self.query_one("#activity_log_panel", ActivityLogPanel).has_class("-visible")
        elif action == "log_newer":
            log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)
            return log_panel.has_class("-visible") and self._log_end is not None
        elif action == "toggle_graph":
            panel = self.query_one("#detail_panel", EntityDetailPanel)
            if panel.has_class("-visible"):
                return True  # allow g to close an open panel from any row
            entity_id = self._selected_entity_id()
            entity = self.find_entity(entity_id) if entity_id else None
            return entity is not None and self.graph_ctl.is_graphable(entity)
        elif action in (
            "toggle_list_membership",
            "rename_entity",
            "toggle_device_log",
            "toggle_entity_log",
        ):
            entity_id = self._selected_entity_id()
            entity = self.find_entity(entity_id) if entity_id else None
            if not entity:
                return False
        return True

    def action_go_back(self) -> None:
        log_panel = self.query_one("#activity_log_panel", ActivityLogPanel)
        if log_panel.has_class("-maximized"):
            # First escape restores the normal-width panel; a further escape/toggle closes it.
            log_panel.remove_class("-maximized")
            return

        search_input = self.query_one("#search_input", SearchInput)

        if search_input.display:
            was_vi_mode = search_input.vi_mode
            search_input.action_hide_display()
            if was_vi_mode:
                self.vi_search_term = ""
                self.vi_search_matches = []
                self.vi_search_index = -1
                self._update_entities_display()
            else:
                self.search_term = ""
                self._update_entities_display()
            self.set_title_based_on_focused_ui()
            self.query_one("#entities_table", EntitiesTable).focus()
        elif self.search_term:
            self.search_term = ""
            self._update_entities_display()
            self.set_title_based_on_focused_ui()
        elif self.current_list_name is not None:

            def _do_leave_list(confirmed: bool | None, _name: str = self.current_list_name) -> None:
                if not confirmed:
                    return
                self.current_list_name = None
                self._update_entities_display()
                self.set_title_based_on_focused_ui()

            self.push_screen(ConfirmPopup(f"Leave list '{self.current_list_name}'?"), _do_leave_list)

    def action_toggle_search(self) -> None:
        search_input = self.query_one("#search_input", SearchInput)
        search_input.action_focus_display()

    def on_search_input_search_submitted(self, event: SearchInput.SearchSubmitted) -> None:
        search_input = self.query_one("#search_input", SearchInput)
        if not search_input.vi_mode:
            self.search_term = event.value.lower()
            self._update_entities_display()
        search_input.action_hide_display()
        self.set_title_based_on_focused_ui()
        self.query_one("#entities_table", EntitiesTable).focus()

    def on_search_input_search_changed(self, event: SearchInput.SearchChanged) -> None:
        search_input = self.query_one("#search_input", SearchInput)
        if search_input.vi_mode:
            self._update_vi_search(event.value)
        else:
            self.search_term = event.value.lower()
            self._update_entities_display()
            self.set_title_based_on_focused_ui()

    # ── Vi-style jump search ─────────────────────────────────────────────────

    def _update_vi_search(self, raw_term: str) -> None:
        self.vi_search_term = raw_term.lower()
        if not self.vi_search_term:
            self.vi_search_matches = []
            self.vi_search_index = -1
            self.sub_title = f"{self._list_context_label()} — jump: (type to search)"
            return

        displayed = self._currently_displayed_entities()
        self.vi_search_matches = [e["entity_id"] for e in displayed if entity_matches(e, self.vi_search_term)]
        self.vi_search_index = 0 if self.vi_search_matches else -1
        self._jump_to_vi_match()
        self._update_vi_subtitle()

    def _jump_to_vi_match(self) -> None:
        if self.vi_search_index < 0:
            return
        self.query_one("#entities_table", EntitiesTable).jump_cursor_to_row_key(
            self.vi_search_matches[self.vi_search_index]
        )

    def _update_vi_subtitle(self) -> None:
        base = self._list_context_label()
        if not self.vi_search_matches:
            self.sub_title = f"{base} — jump: '{self.vi_search_term}' (no matches)"
        else:
            self.sub_title = (
                f"{base} — jump: '{self.vi_search_term}' ({self.vi_search_index + 1}/{len(self.vi_search_matches)})"
            )

    def action_search_next(self) -> None:
        self._cycle_vi_search(1)

    def action_search_prev(self) -> None:
        self._cycle_vi_search(-1)

    def _cycle_vi_search(self, direction: int) -> None:
        if not self.vi_search_matches:
            return
        self.vi_search_index = (self.vi_search_index + direction) % len(self.vi_search_matches)
        self._jump_to_vi_match()
        self._update_vi_subtitle()

    # ── HA message handling ──────────────────────────────────────────────────

    def handle_ha_message(self, msg: dict) -> None:
        # Public message-callback seam: the client factory is handed this bound
        # method; the pump itself lives on the ConnectionController.
        self.conn_ctl.handle_ha_message(msg)

    def _apply_name_override(self, entity: Entity) -> None:
        entity_id = entity.get("entity_id", "")
        entity["_local_name_override"] = self.entity_names.get(entity_id, "")

    # ── Pending service-call tracking ────────────────────────────────────────

    def dispatch_service_call(self, entity_id: str, domain: str, service: str, service_data: dict) -> None:
        existing = self._pending_call_timers.pop(entity_id, None)
        if existing:
            existing.stop()
        self.pending_call_status[entity_id] = "pending"
        self._pending_call_timers[entity_id] = self.set_timer(
            self.PENDING_TIMEOUT_SECONDS, lambda: self._mark_call_stalled(entity_id)
        )
        self.spawn(self.client.call_service(domain, service, service_data, entity_id))
        self._update_entities_display()
        self._refresh_dashboard_widgets(entity_id)

    def _mark_call_stalled(self, entity_id: str) -> None:
        self._pending_call_timers.pop(entity_id, None)
        if self.pending_call_status.get(entity_id) == "pending":
            self.pending_call_status[entity_id] = "stalled"
            self.notify(f"No response from Home Assistant for {entity_id}", title="Unresponsive", severity="warning")
            self._update_entities_display()
            self._refresh_dashboard_widgets(entity_id)

    def _refresh_dashboard_widgets(self, entity_id: str) -> None:
        entity = self.find_entity(entity_id)
        pending = self.pending_call_status.get(entity_id)
        for screen in self.screen_stack:
            if isinstance(screen, DashboardScreen):
                screen.refresh_entity(entity_id, entity, pending)

    def _clear_pending_call(self, entity_id: str) -> None:
        timer = self._pending_call_timers.pop(entity_id, None)
        if timer:
            timer.stop()
        self.pending_call_status.pop(entity_id, None)

    # ── Display update ───────────────────────────────────────────────────────

    def _schedule_display_update(self) -> None:
        if not self._update_pending:
            self._update_pending = True
            self.call_later(self._run_pending_display_update)

    def _run_pending_display_update(self) -> None:
        self._update_pending = False
        self._update_entities_display()

    def _currently_displayed_entities(self) -> list:
        display_entities = self.all_entities

        if self.search_term:
            display_entities = [e for e in display_entities if entity_matches(e, self.search_term)]
        elif self.current_list_name:
            current_list = self.entity_lists.get(self.current_list_name, [])
            display_entities = [e for e in display_entities if e.get("entity_id") in current_list]

        return display_entities

    def _update_entities_display(self) -> None:
        self.query_one("#entities_table", EntitiesTable).update_table_data(
            entities_to_display=self._currently_displayed_entities(),
            entity_lists=self.entity_lists,
            current_list_name=self.current_list_name,
            columns=self.columns,
            pending_status=self.pending_call_status,
            manual_lists=self.manual_lists,
            alerted_ids=self.notify_ctl.alerted,
        )

    # ── Entity toggle (enter on the entities table) ─────────────────────────

    def toggle_entity(self, entity_id: str) -> None:
        domain = entity_id.split(".")[0]
        if domain not in TOGGLABLE_DOMAINS:
            return

        if domain == "media_player":
            # media_player state is playing/paused/idle, not on/off, so it
            # can't use the generic on/off branch below — quick play/pause instead.
            self.dispatch_service_call(entity_id, "media_player", "media_play_pause", {"entity_id": entity_id})
            return

        entity = self.find_entity(entity_id)
        current_state = entity.get("state") if entity else None
        if current_state == "on":
            service = "turn_off"
        elif current_state == "off":
            service = "turn_on"
        else:
            return

        self.dispatch_service_call(entity_id, domain, service, {"entity_id": entity_id})

    def toggle_or_open_controls(self, entity_id: str, *, fullscreen_graph_fallback: bool = False) -> None:
        """`enter` behavior shared by the entity table and device tree (issue #150):
        toggle togglable entities, otherwise fall back to the `e` open-controls
        behavior so `enter` on a sensor isn't a dead key. `fullscreen_graph_fallback`
        is forwarded to `open_entity_controls` (the tree wants the fullscreen graph
        since its detail panel is hidden behind the pushed screen)."""
        domain = entity_id.split(".")[0]
        if domain in TOGGLABLE_DOMAINS:
            self.toggle_entity(entity_id)
        else:
            self.open_entity_controls(entity_id, fullscreen_graph_fallback=fullscreen_graph_fallback)

    # ── Entity expand (e key) ────────────────────────────────────────────────

    def action_expand_entity(self) -> None:
        entities_table = self.query_one("#entities_table", EntitiesTable)
        if not entities_table.row_count:
            return

        entity_id = self._selected_entity_id()
        if not entity_id:
            return

        self.open_entity_controls(entity_id)

    def open_entity_controls(self, entity_id: str, *, fullscreen_graph_fallback: bool = False) -> None:
        """Open the full control UI for an entity: the live-apply LightControlScreen
        for lights, the live-apply MediaPlayerControlScreen for media players, the
        Save/Cancel EntityControlPopup for other controllable domains, or the graph
        for anything else graphable. Shared by the entity
        table's expand (e), the dashboard's expand key, and the device tree.
        `fullscreen_graph_fallback` makes the graphable fallback push the
        fullscreen GraphPreviewScreen instead of the main table's detail panel —
        the panel is invisible behind a pushed screen like the device tree."""
        entity = self.find_entity(entity_id)
        if not entity:
            return

        domain = entity_id.split(".")[0]
        if domain == "light":
            # Lights get the dedicated live-apply screen; no result callback since
            # every change dispatches immediately.
            from hatty.ui.controls.light_screen import LightControlScreen

            self.push_screen(LightControlScreen(entity))
        elif domain == "media_player":
            # Same live-apply model as light: no result callback, every change
            # dispatches immediately.
            from hatty.ui.controls.media_player_screen import MediaPlayerControlScreen

            self.push_screen(MediaPlayerControlScreen(entity))
        elif domain in CONTROLLABLE_DOMAINS:

            def callback(result: dict | None) -> None:
                if result:
                    self.dispatch_entity_control(entity_id, domain, result)

            self.push_screen(EntityControlPopup(entity), callback)
        elif domain == "weather":
            # Fullscreen forecast view (issue #275); a weather entity's state is a
            # condition slug, not numeric, so it's neither togglable nor graphable
            # and would otherwise dead-end here.
            from hatty.ui.weather_forecast_screen import WeatherForecastScreen

            self.push_screen(WeatherForecastScreen(entity))
        elif self.graph_ctl.is_graphable(entity):
            if fullscreen_graph_fallback:
                from hatty.ui.graph.preview_screen import GraphPreviewScreen

                self.push_screen(
                    GraphPreviewScreen(
                        [entity_id],
                        initial_graph_type=self.app_config.get(CONFIG_KEY_GRAPH_TYPE),
                    )
                )
            else:
                self.graph_ctl.open_graph_for(entity_id, entity)

    def dispatch_entity_control(self, entity_id: str, domain: str, fields: dict) -> None:
        builder = _CONTROL_SERVICE_BUILDERS.get(domain)
        if builder is None:
            return
        try:
            calls = builder(entity_id, fields)
        except ValueError:
            self.notify("Invalid value entered.", title="Control Error", severity="error")
            return
        for call_domain, service, service_data in calls:
            self.dispatch_service_call(entity_id, call_domain, service, service_data)

    # ── Entity rename (r key) ────────────────────────────────────────────────

    def action_rename_entity(self) -> None:
        entity_id = self._selected_entity_id()
        if not entity_id:
            return
        self.open_rename_for_entity(entity_id)

    def open_rename_for_entity(self, entity_id: str) -> None:
        entity = self.find_entity(entity_id)
        if not entity:
            return

        def callback(result: dict | None) -> None:
            if not result:
                return
            if result["scope"] == "local":
                self._set_local_entity_name(entity_id, result["name"])
            elif result["scope"] == "ha":
                self._dispatch_rename_to_ha(entity_id, result["name"])

        has_override = bool(self.entity_names.get(entity_id))
        self.push_screen(RenameEntityPopup(entity_id, get_display_name(entity), has_override), callback)

    def _set_local_entity_name(self, entity_id: str, new_name: str | None) -> None:
        if new_name:
            self.entity_names[entity_id] = new_name
        else:
            self.entity_names.pop(entity_id, None)
        self.persist("entity_names")

        entity = self.find_entity(entity_id)
        if entity:
            self._apply_name_override(entity)
        self._update_entities_display()
        self._refresh_device_tree_entity(entity_id)
        if self._detail_entity_id == entity_id:
            self.graph_ctl.refresh_detail_panel()

        if new_name:
            self.notify(f"Renamed {entity_id} locally to '{new_name}'", title="Renamed")
        else:
            self.notify(f"Cleared local name for {entity_id}", title="Renamed")

    def _dispatch_rename_to_ha(self, entity_id: str, name: str | None) -> None:
        self.spawn(self.client.update_entity_registry(entity_id, name))

    # ── Configuration screen ─────────────────────────────────────────────────

    def action_show_config(self) -> None:
        # Pass the live in-memory config: the YAML no longer carries collections
        # (they're in SQLite now), so a fresh load_config would show empty
        # lists/dashboards/graphs and its save would drop them.
        self.push_screen(ConfigScreen(dict(self.app_config), self.config_path), self._on_config_saved)

    def action_show_onboarding(self) -> None:
        self.pop_to_base_screen()
        self._launch_onboarding()

    def _on_config_saved(self, result: dict | None) -> None:
        if result is None:
            return
        old_graph_hours = self.graph_hours
        self.app_config = result
        self.columns = result.get(CONFIG_KEY_COLUMNS, list(DEFAULT_COLUMNS))
        self.entity_names = result.get(CONFIG_KEY_ENTITY_NAMES, {})
        # Show/hide the reserved notifications list per the (possibly just-toggled)
        # "enabled" pref, and refresh the title/table in case current_list_name
        # was reset by sync() (e.g. the user disabled notifications while viewing it).
        self.notify_ctl.sync()
        self.set_title_based_on_focused_ui()
        new_graph_type = result.get(CONFIG_KEY_GRAPH_TYPE)
        self.query_one("#detail_panel", EntityDetailPanel).apply_saved_graph_type(new_graph_type)
        new_theme = result.get(CONFIG_KEY_THEME)
        if new_theme and new_theme in self.available_themes:
            self.theme = new_theme
        try:
            terminal_title.restore(self._title_restore)
        except Exception as e:
            self.log.error(f"Error restoring terminal title: {e}")
        self._title_restore = None
        self._apply_terminal_title(result)
        ha_config = result.get(CONFIG_KEY_HOME_ASSISTANT, {})
        new_url = ha_config.get(CONFIG_KEY_URL, "")
        new_token = ha_config.get(CONFIG_KEY_TOKEN, "")
        if new_url != self.ha_url or new_token != self._token:
            # Reconnect live through the same seam onboarding uses — no restart.
            self.ha_url = new_url
            self._token = new_token
            self._start_client()
            self.notify("Reconnecting with new connection settings…", title="Config Saved")
        else:
            self.notify("Configuration saved.", title="Config Saved")
        self._update_entities_display()
        if result.get(CONFIG_KEY_GRAPH_HOURS, DEFAULT_GRAPH_HOURS) != old_graph_hours:
            self._on_graph_hours_changed()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def find_entity(self, entity_id: str) -> Entity | None:
        return next((e for e in self.all_entities if e["entity_id"] == entity_id), None)

    def _selected_entity_id(self) -> str | None:
        entities_table = self.query_one("#entities_table", EntitiesTable)
        if not entities_table.row_count:
            return None
        cell_key = entities_table.coordinate_to_cell_key(Coordinate(entities_table.cursor_row, 0))
        return cell_key.row_key.value if cell_key else None
