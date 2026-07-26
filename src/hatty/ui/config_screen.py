# hatty — MIT License. See LICENSE file for details.
import os
import subprocess
from typing import TYPE_CHECKING, cast

from rich.table import Table
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    SelectionList,
    Static,
)
from textual.widgets.selection_list import Selection

from hatty import config as config_module
from hatty import storage as storage_module
from hatty.client import probe_connection
from hatty.const import (
    CONFIG_KEY_COLUMNS,
    CONFIG_KEY_DASHBOARDS,
    CONFIG_KEY_ENTITY_NAMES,
    CONFIG_KEY_GRAPH_HOURS,
    CONFIG_KEY_GRAPH_TYPE,
    CONFIG_KEY_HOME_ASSISTANT,
    CONFIG_KEY_LISTS,
    CONFIG_KEY_NOTIFICATIONS,
    CONFIG_KEY_SAVED_GRAPHS,
    CONFIG_KEY_TERMINAL_TITLE,
    CONFIG_KEY_TERMINAL_TITLE_ENABLED,
    CONFIG_KEY_THEME,
    CONFIG_KEY_TOKEN,
    CONFIG_KEY_URL,
    DEFAULT_GRAPH_HOURS,
    DEFAULT_NOTIFICATIONS,
    DEFAULT_TERMINAL_TITLE,
    NOTIFY_LIST_NAME,
)
from hatty.controllers.notifications import send_test_ntfy
from hatty.ui.entity_table import COLUMNS

if TYPE_CHECKING:
    from hatty.main import HACLI

_GRAPH_OPTIONS = [
    ("Sparkline", "sparkline"),
    ("Line", "line"),
    ("Scatter", "scatter"),
]

_GRAPH_HOURS_OPTIONS = [
    ("1 hour", 1),
    ("4 hours", 4),
    ("12 hours", 12),
    ("24 hours", 24),
    ("48 hours", 48),
    ("1 week", 168),
]

# Notification channel toggles (issue #224), shown as a SelectionList mirroring
# the Visible Columns section below.
_NOTIFY_TOGGLES = [
    ("Enabled", "enabled"),
    ("Toast", "toast"),
    ("Beep", "beep"),
    ("Desktop (notify-send)", "desktop"),
    ("ntfy", "ntfy"),
    ("Highlight changed entity", "highlight"),
]

# Top-level category menu (issue #252). Each entry is (display name, pane id,
# one-line hint, first-focus widget id within the pane). "cat_menu" itself is
# the ContentSwitcher's built-in first pane and isn't listed here.
_CATEGORIES = [
    ("Home Assistant", "cat_home_assistant", "Connection URL, access token", "#cfg_url"),
    ("Appearance", "cat_appearance", "Theme, graph defaults, visible columns", "#cfg_theme"),
    ("Notifications", "cat_notifications", "Toast/beep/desktop/ntfy alerts", "#cfg_notify"),
    ("Data & Collections", "cat_data", "Lists, name overrides, dashboards, saved graphs", "#cat_data"),
]


class ConfigScreen(Screen):
    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    AUTO_FOCUS = "#cfg_category_list"

    # All bindings are modifier-prefixed (mirroring OnboardingScreen). A bare
    # single-letter binding here would hijack keystrokes the moment focus tabs
    # onto a non-Input widget (Select/SelectionList/Button) — e.g. a stray "s"
    # would fire save_and_close and dismiss the screen (issue #192).
    BINDINGS = [
        Binding("ctrl+s", "save_and_close", "Save"),
        Binding("escape", "cancel", "Back/Cancel"),
        Binding("ctrl+o", "open_in_editor", "Editor"),
        Binding("ctrl+v", "toggle_token", "Show/Hide Token"),
        # "?" is punctuation, not a bare letter, so it doesn't hijack typing the
        # way the comment above warns about; a focused Input still consumes it
        # as a keystroke rather than letting it reach this binding.
        Binding("question_mark", "show_help", "Help"),
    ]

    HELP_TITLE = "Config"

    DEFAULT_CSS = """
    ConfigScreen {
        background: $background;
    }
    #cfg_breadcrumb {
        padding: 0 2;
        text-style: bold;
        color: $accent;
        background: $panel;
        height: 1;
    }
    #cfg_switcher {
        height: 1fr;
    }
    .config-pane {
        padding: 1 2;
        height: 1fr;
    }
    #cfg_category_list {
        height: auto;
        margin-top: 1;
        border: round $panel-lighten-1;
    }
    .section-title {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    .field-label {
        color: $text-muted;
        margin-top: 1;
    }
    .read-only-note {
        color: $text-disabled;
        text-style: italic;
    }
    ConfigScreen SelectionList {
        height: auto;
        max-height: 10;
        border: round $panel-lighten-1;
    }
    #cfg_conn_status {
        margin-top: 1;
        color: $text;
    }
    #cfg_conn_status.-ok {
        color: $success;
    }
    #cfg_conn_status.-error {
        color: $error;
    }
    #cfg_conn_buttons {
        height: auto;
        margin-top: 1;
    }
    #cfg_conn_buttons Button {
        margin-right: 2;
    }
    #cfg_ntfy_status {
        margin-top: 1;
        color: $text;
    }
    #cfg_ntfy_status.-ok {
        color: $success;
    }
    #cfg_ntfy_status.-error {
        color: $error;
    }
    """

    def __init__(self, raw_config: dict, config_path: str | None):
        super().__init__()
        self._raw_config = raw_config
        self._config_path = config_path
        self._token_visible = False

    @staticmethod
    def _lists_summary(lists: dict) -> str | Table:
        """The Lists section's summary renderable — factored out so the
        "Clear watched entities" button (issue #224) can refresh it in place
        instead of leaving it showing the stale pre-clear count."""
        if not lists:
            return "No lists defined."
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold", no_wrap=True)
        t.add_column(style="dim")
        for name, entities in lists.items():
            t.add_row(name, f"{len(entities)} entit{'y' if len(entities) == 1 else 'ies'}")
        return t

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Configuration", id="cfg_breadcrumb")

        ha = self._raw_config.get(CONFIG_KEY_HOME_ASSISTANT, {})
        url = ha.get(CONFIG_KEY_URL, "")
        token = ha.get(CONFIG_KEY_TOKEN, "")
        current_theme = self._raw_config.get(CONFIG_KEY_THEME) or ""
        current_graph_type = self._raw_config.get(CONFIG_KEY_GRAPH_TYPE) or "line"
        # Guard against a stale persisted type no longer in the option list (e.g. the
        # removed "bar" mode) — Select raises InvalidSelectValueError on an unknown value.
        if current_graph_type not in {value for _, value in _GRAPH_OPTIONS}:
            current_graph_type = "line"
        current_graph_hours = self._raw_config.get(CONFIG_KEY_GRAPH_HOURS, DEFAULT_GRAPH_HOURS)
        current_columns = self._raw_config.get(CONFIG_KEY_COLUMNS, [])
        title_enabled = self._raw_config.get(CONFIG_KEY_TERMINAL_TITLE_ENABLED, True)
        title_text = self._raw_config.get(CONFIG_KEY_TERMINAL_TITLE) or DEFAULT_TERMINAL_TITLE
        lists = self._raw_config.get(CONFIG_KEY_LISTS, {})
        notify_prefs = {**DEFAULT_NOTIFICATIONS, **(self._raw_config.get(CONFIG_KEY_NOTIFICATIONS) or {})}
        watched_count = len(lists.get(NOTIFY_LIST_NAME) or [])
        entity_names = self._raw_config.get(CONFIG_KEY_ENTITY_NAMES, {})
        dashboards = self._raw_config.get(CONFIG_KEY_DASHBOARDS, {})
        saved_graphs = self._raw_config.get(CONFIG_KEY_SAVED_GRAPHS, {})

        themes = sorted(self.app.available_themes)
        theme_kwargs: dict = {"allow_blank": True}
        if current_theme in themes:
            theme_kwargs["value"] = current_theme

        graph_hours_kwargs: dict = {}
        if current_graph_hours in {h for h, _ in _GRAPH_HOURS_OPTIONS}:
            graph_hours_kwargs["value"] = current_graph_hours

        with ContentSwitcher(initial="cat_menu", id="cfg_switcher"):
            with VerticalScroll(id="cat_menu", classes="config-pane"):
                yield ListView(
                    *(
                        ListItem(Label(f"{name}\n[dim]{hint}[/dim]", markup=True), id=f"li_{pane_id}")
                        for name, pane_id, hint, _first_focus in _CATEGORIES
                    ),
                    id="cfg_category_list",
                )

            with VerticalScroll(id="cat_home_assistant", classes="config-pane"):
                yield Label("Home Assistant URL", classes="field-label")
                yield Input(value=url, id="cfg_url", placeholder="http://homeassistant.local:8123")
                yield Label("Access Token  [dim](ctrl+v: show/hide)[/dim]", classes="field-label", markup=True)
                yield Input(value=token, id="cfg_token", password=True, placeholder="long-lived access token")
                yield Label("", id="cfg_conn_status")
                with Horizontal(id="cfg_conn_buttons"):
                    yield Button("Test connection", id="cfg_test")
                    yield Button("Save", variant="primary", id="cfg_save")
                    yield Button("Cancel", id="cfg_cancel")

            with VerticalScroll(id="cat_appearance", classes="config-pane"):
                yield Label("Theme", classes="field-label")
                yield Select([(t, t) for t in themes], id="cfg_theme", **theme_kwargs)
                yield Label("Default Graph Type", classes="field-label")
                yield Select(_GRAPH_OPTIONS, id="cfg_graph_type", value=current_graph_type)
                yield Label("Graph Timeframe", classes="field-label")
                yield Select(_GRAPH_HOURS_OPTIONS, id="cfg_graph_hours", **graph_hours_kwargs)

                yield Label("Terminal / tmux Title", classes="field-label")
                yield SelectionList(
                    Selection("Set terminal / tmux title", "enabled", title_enabled),
                    id="cfg_terminal_title_enabled",
                )
                yield Input(value=title_text, id="cfg_terminal_title", placeholder=DEFAULT_TERMINAL_TITLE)

                yield Label("Visible Columns", classes="section-title")
                col_selections = [
                    Selection(header, key, key in current_columns) for key, (header, _) in COLUMNS.items()
                ]
                yield SelectionList(*col_selections, id="cfg_columns")

            with VerticalScroll(id="cat_notifications", classes="config-pane"):
                notify_selections = [Selection(label, key, notify_prefs[key]) for label, key in _NOTIFY_TOGGLES]
                yield SelectionList(*notify_selections, id="cfg_notify")
                yield Label("ntfy Server URL", classes="field-label")
                yield Input(value=notify_prefs["ntfy_url"], id="cfg_ntfy_url", placeholder="https://ntfy.sh")
                yield Label("ntfy Topic", classes="field-label")
                yield Input(value=notify_prefs["ntfy_topic"], id="cfg_ntfy_topic", placeholder="my-hatty-alerts")
                yield Label("ntfy Username", classes="field-label")
                yield Input(value=notify_prefs["ntfy_username"], id="cfg_ntfy_username", placeholder="(optional)")
                yield Label("ntfy Password", classes="field-label")
                yield Input(
                    value=notify_prefs["ntfy_password"],
                    id="cfg_ntfy_password",
                    password=True,
                    placeholder="(optional)",
                )
                yield Label("", id="cfg_ntfy_status")
                yield Button("Send test notification", id="cfg_ntfy_test")
                yield Static(
                    f"{watched_count} entit{'y' if watched_count == 1 else 'ies'} watched.", id="cfg_notify_count"
                )
                yield Button("Clear watched entities", id="cfg_notify_clear")

            with VerticalScroll(id="cat_data", classes="config-pane"):
                yield Label("Lists", classes="section-title")
                lists_summary = Static(self._lists_summary(lists), id="cfg_lists_summary")
                lists_summary.set_class(not lists, "read-only-note")
                yield lists_summary
                yield Label("Use [bold]l[/bold] to manage lists", classes="read-only-note", markup=True)

                yield Label("Entity Name Overrides", classes="section-title")
                count = len(entity_names)
                yield Static(f"{count} override{'s' if count != 1 else ''} defined.")
                yield Label("Use [bold]r[/bold] to rename entities", classes="read-only-note", markup=True)

                yield Label("Dashboards", classes="section-title")
                if dashboards:
                    t = Table.grid(padding=(0, 2))
                    t.add_column(style="bold", no_wrap=True)
                    t.add_column(style="dim")
                    for name, dash in dashboards.items():
                        t.add_row(name, f"{dash['rows']}×{dash['cols']}")
                    yield Static(t)
                else:
                    yield Static("No dashboards defined.", classes="read-only-note")
                yield Label("Use [bold]d[/bold] to manage dashboards", classes="read-only-note", markup=True)

                yield Label("Saved Graphs", classes="section-title")
                if saved_graphs:
                    t = Table.grid(padding=(0, 2))
                    t.add_column(style="bold", no_wrap=True)
                    t.add_column(style="dim")
                    for name, graph in saved_graphs.items():
                        entity_ids = graph.get("entity_ids", [])
                        count = len(entity_ids)
                        t.add_row(
                            name, f"{count} entit{'y' if count == 1 else 'ies'}, {graph.get('graph_type', 'line')}"
                        )
                    yield Static(t)
                else:
                    yield Static("No saved graphs defined.", classes="read-only-note")
                yield Label("Use [bold]s[/bold] to manage saved graphs", classes="read-only-note", markup=True)

        yield Footer()

    def show_category(self, pane_id: str) -> None:
        """Drill into a category pane ("cat_menu" to go back to the top-level
        menu), updating the breadcrumb and focusing that pane's primary field."""
        switcher = self.query_one("#cfg_switcher", ContentSwitcher)
        switcher.current = pane_id

        breadcrumb = self.query_one("#cfg_breadcrumb", Label)
        if pane_id == "cat_menu":
            breadcrumb.update("Configuration")
            self.query_one("#cfg_category_list", ListView).focus()
            return

        name, _pane_id, _hint, first_focus = next(c for c in _CATEGORIES if c[1] == pane_id)
        breadcrumb.update(f"Configuration ▸ {name}")
        self.query_one(first_focus).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "cfg_category_list":
            return
        event.stop()
        pane_id = (event.item.id or "").removeprefix("li_")
        self.show_category(pane_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cfg_test":
            self.action_test_connection()
        elif event.button.id == "cfg_save":
            self.action_save_and_close()
        elif event.button.id == "cfg_cancel":
            # Unconditional dismiss (unlike the back-aware escape binding below) —
            # the on-screen Cancel button means "abandon changes and close", not
            # "go back a level", even when pressed from inside a category pane.
            self.dismiss(None)
        elif event.button.id == "cfg_notify_clear":
            self.action_clear_watched_entities()
        elif event.button.id == "cfg_ntfy_test":
            self.action_test_ntfy()

    def action_clear_watched_entities(self) -> None:
        # A live write (like the l/d/s popups edit their own collections directly)
        # rather than something staged until Save — there's no "undo" expected here.
        self.app.notify_ctl.clear_entities()
        lists_now = dict(self.app.entity_lists)
        self._raw_config[CONFIG_KEY_LISTS] = lists_now
        self.query_one("#cfg_notify_count", Static).update("0 entities watched.")
        lists_summary = self.query_one("#cfg_lists_summary", Static)
        lists_summary.update(self._lists_summary(lists_now))
        lists_summary.set_class(not lists_now, "read-only-note")
        self.notify("Cleared the watched-entities list.", title="Notifications")

    def _set_status(self, text: str, ok: bool | None = None) -> None:
        status = self.query_one("#cfg_conn_status", Label)
        status.update(text)
        status.set_class(ok is True, "-ok")
        status.set_class(ok is False, "-error")

    def action_test_connection(self) -> None:
        url = self.query_one("#cfg_url", Input).value.strip()
        token = self.query_one("#cfg_token", Input).value.strip()
        if not url or not token:
            self._set_status("Enter both a URL and a token first.", ok=False)
            return
        self._set_status("Testing connection…")
        self.run_worker(self._do_test(url, token), exclusive=True)

    async def _do_test(self, url: str, token: str) -> None:
        ok, message = await probe_connection(url, token)
        self._set_status(message, ok=ok)

    def _set_ntfy_status(self, text: str, ok: bool | None = None) -> None:
        status = self.query_one("#cfg_ntfy_status", Label)
        status.update(text)
        status.set_class(ok is True, "-ok")
        status.set_class(ok is False, "-error")

    def action_test_ntfy(self) -> None:
        # Uses the currently entered (unsaved) fields, like action_test_connection,
        # so the user can verify ntfy config before committing to Save (issue #248).
        prefs = {
            "ntfy_url": self.query_one("#cfg_ntfy_url", Input).value.strip(),
            "ntfy_topic": self.query_one("#cfg_ntfy_topic", Input).value.strip(),
            "ntfy_username": self.query_one("#cfg_ntfy_username", Input).value.strip(),
            "ntfy_password": self.query_one("#cfg_ntfy_password", Input).value,
        }
        self._set_ntfy_status("Sending test notification…")
        self.run_worker(self._do_test_ntfy(prefs), exclusive=True)

    async def _do_test_ntfy(self, prefs: dict) -> None:
        ok, message = await send_test_ntfy(prefs, "hatty", "🔔 Test notification from hatty")
        self._set_ntfy_status(message, ok=ok)

    def action_save_and_close(self) -> None:
        url = self.query_one("#cfg_url", Input).value.strip()
        token = self.query_one("#cfg_token", Input).value.strip()

        theme_select = self.query_one("#cfg_theme", Select)
        theme = None if theme_select.is_blank() else str(theme_select.value)

        graph_select = self.query_one("#cfg_graph_type", Select)
        graph_type = None if graph_select.is_blank() else str(graph_select.value)

        hours_select = self.query_one("#cfg_graph_hours", Select)
        if hours_select.is_blank():
            existing_graph_hours = self._raw_config.get(CONFIG_KEY_GRAPH_HOURS, DEFAULT_GRAPH_HOURS)
            preset_hours = {h for h, _ in _GRAPH_HOURS_OPTIONS}
            graph_hours = existing_graph_hours if existing_graph_hours not in preset_hours else DEFAULT_GRAPH_HOURS
        else:
            graph_hours = int(cast(float, hours_select.value))

        title_enabled = "enabled" in self.query_one("#cfg_terminal_title_enabled", SelectionList).selected
        title_text = self.query_one("#cfg_terminal_title", Input).value.strip() or DEFAULT_TERMINAL_TITLE

        selected_cols = list(self.query_one("#cfg_columns", SelectionList).selected)
        existing = self._raw_config.get(CONFIG_KEY_COLUMNS, [])
        columns = [k for k in existing if k in selected_cols]
        columns += [k for k in selected_cols if k not in columns]

        selected_notify = set(self.query_one("#cfg_notify", SelectionList).selected)
        notifications: dict[str, bool | str] = {key: key in selected_notify for _label, key in _NOTIFY_TOGGLES}
        notifications["ntfy_url"] = self.query_one("#cfg_ntfy_url", Input).value.strip()
        notifications["ntfy_topic"] = self.query_one("#cfg_ntfy_topic", Input).value.strip()
        notifications["ntfy_username"] = self.query_one("#cfg_ntfy_username", Input).value.strip()
        notifications["ntfy_password"] = self.query_one("#cfg_ntfy_password", Input).value

        new_config = {**self._raw_config}
        new_config[CONFIG_KEY_HOME_ASSISTANT] = {
            **self._raw_config.get(CONFIG_KEY_HOME_ASSISTANT, {}),
            CONFIG_KEY_URL: url,
            CONFIG_KEY_TOKEN: token,
        }
        new_config[CONFIG_KEY_THEME] = theme
        new_config[CONFIG_KEY_GRAPH_TYPE] = graph_type
        new_config[CONFIG_KEY_GRAPH_HOURS] = graph_hours
        new_config[CONFIG_KEY_TERMINAL_TITLE_ENABLED] = title_enabled
        new_config[CONFIG_KEY_TERMINAL_TITLE] = title_text
        new_config[CONFIG_KEY_COLUMNS] = columns if columns else existing
        new_config[CONFIG_KEY_NOTIFICATIONS] = notifications

        # Collections live in SQLite; this screen only edits connection settings +
        # display preferences, so keep them out of the lean YAML it writes. The
        # dismissed dict still carries them so the app's in-memory state is intact.
        to_save = {k: v for k, v in new_config.items() if k not in storage_module.COLLECTION_KEYS}

        try:
            config_module.save_config(to_save, self._config_path)
        except Exception as e:
            self.notify(f"Error saving config: {e}", title="Save Error", severity="error")
            return

        self.dismiss(new_config)

    def action_cancel(self) -> None:
        # Back-aware (issue #252): escape/Cancel from inside a category returns
        # to the top-level menu first; only dismisses the screen from there.
        switcher = self.query_one("#cfg_switcher", ContentSwitcher)
        if switcher.current != "cat_menu":
            self.show_category("cat_menu")
            return
        self.dismiss(None)

    def action_open_in_editor(self) -> None:
        config_path = self._config_path or str(config_module.get_config_path() or "")
        if not config_path:
            self.notify("No config file path found.", severity="warning")
            return
        editor = os.environ.get("EDITOR", "nano")
        with self.app.suspend():
            subprocess.run([editor, config_path])

    def action_toggle_token(self) -> None:
        self._token_visible = not self._token_visible
        self.query_one("#cfg_token", Input).password = not self._token_visible
        self.query_one("#cfg_ntfy_password", Input).password = not self._token_visible

    def action_show_help(self) -> None:
        self.app.action_show_help()
