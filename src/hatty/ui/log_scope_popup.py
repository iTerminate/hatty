# hatty — MIT License. See LICENSE file for details.
"""`v` — preview-then-commit popup for the activity log's scope (issue #38),
replacing the old blind cycle. Lists every `LogScopeOption` the open session
offers (unresolvable ones, e.g. a cursor-scoped option with no selected row,
are simply omitted); highlighting a row resolves it — `LogbookController.
resolve` is pure, so this is side-effect-free — and renders the entities/
devices it would log into the preview pane below, with a summary line
noting any 200-entity/50-device cap. `Enter` applies the highlighted option
(`LogbookController.apply_option` — closes the popup, clears the panel,
refetches, and resyncs the live subscription); `Escape`/`q` cancel, leaving
the current scope untouched.

Scopes are resolved eagerly, once, in `__init__`, over every option — cheap:
a handful of registry passes bounded by the same caps that bound the fetch
itself. Entity/device *name* rendering is lazy, done per highlight, reusing
`LogbookController.display_names()`'s single precedence chain (passed in
rather than re-derived here)."""

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Footer, Label, OptionList, Static
from textual.widgets.option_list import Option

from hatty.controllers.keybindings import bindings_for
from hatty.controllers.logbook import LogScope, LogScopeOption
from hatty.ui.popup_base import PopupScreen


class LogScopePopup(PopupScreen[str | None]):
    DEFAULT_CSS = """
    LogScopePopup .popup-container {
        width: 72;
        height: 80%;
        max-height: 30;
    }
    LogScopePopup #log_scope_options {
        height: auto;
        max-height: 6;
    }
    LogScopePopup #log_scope_summary {
        margin-top: 1;
        color: $text-muted;
    }
    LogScopePopup #log_scope_preview {
        height: 1fr;
        border-top: solid $accent;
        margin-top: 1;
        padding-top: 1;
    }
    """

    BINDINGS = bindings_for("log_scope_popup")

    def __init__(
        self,
        resolved: list[tuple[LogScopeOption, "LogScope | None"]],
        active_option_id: str,
        entity_names: dict[str, str],
        device_names: dict[str, str],
    ) -> None:
        super().__init__()
        # Options that can't resolve right now (a cursor-scoped option with
        # no selected row) never show up as a row at all.
        self._resolved: list[tuple[LogScopeOption, LogScope]] = [
            (option, scope) for option, scope in resolved if scope is not None
        ]
        self._active_option_id = active_option_id
        self._entity_names = entity_names
        self._device_names = device_names

    def compose(self) -> ComposeResult:
        with Container(id="log_scope_container", classes="popup-container"):
            yield Label("Activity Log Scope", classes="popup-title")
            yield OptionList(id="log_scope_options", markup=False)
            yield Label("", id="log_scope_summary")
            with VerticalScroll(id="log_scope_preview"):
                yield Static(id="log_scope_preview_body", markup=False)
            yield Footer()

    def on_mount(self) -> None:
        options = self.query_one("#log_scope_options", OptionList)
        for option, scope in self._resolved:
            options.add_option(Option(self._row_label(option, scope), id=option.id))
        options.focus()
        index = next((i for i, (o, _) in enumerate(self._resolved) if o.id == self._active_option_id), 0)
        options.highlighted = index
        self._render_preview(index)

    @staticmethod
    def _row_label(option: LogScopeOption, scope: LogScope) -> str:
        if scope.device_ids or scope.device_total:
            count = scope.device_total or len(scope.device_ids)
            noun = "device" if count == 1 else "devices"
        else:
            count = scope.entity_total or len(scope.entity_ids)
            noun = "entity" if count == 1 else "entities"
        return f"{option.label} ({count} {noun})"

    def _render_preview(self, index: int) -> None:
        _option, scope = self._resolved[index]
        lines: list[str] = []
        if scope.device_ids:
            lines.append(f"Devices ({len(scope.device_ids)})")
            for device_id in scope.device_ids:
                lines.append(f"  {self._device_names.get(device_id, device_id)}")
            lines.append("")
        lines.append(f"Entities ({len(scope.entity_ids)})")
        for entity_id in scope.entity_ids:
            lines.append(f"  {self._entity_names.get(entity_id, entity_id)}   {entity_id}")
        self.query_one("#log_scope_preview_body", Static).update("\n".join(lines))

        summary = self.query_one("#log_scope_summary", Label)
        if scope.entity_total:
            summary.update(f"Showing the first {len(scope.entity_ids)} of {scope.entity_total} entities")
        elif scope.device_total:
            summary.update(f"Showing the first {len(scope.device_ids)} of {scope.device_total} devices")
        else:
            parts = [f"{len(scope.entity_ids)} entities"]
            if scope.device_ids:
                parts.append(f"{len(scope.device_ids)} devices")
            summary.update(" · ".join(parts))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_index is not None:
            self._render_preview(event.option_index)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index is not None:
            option, _scope = self._resolved[event.option_index]
            self.dismiss(option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
