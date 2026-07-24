# hatty — MIT License. See LICENSE file for details.
from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Log


class ActivityLogPanel(Widget):
    DEFAULT_CSS = """
    ActivityLogPanel {
        dock: right;
        width: 52;
        border-left: heavy $accent;
        background: $panel;
        padding: 0 1;
        display: none;
    }
    ActivityLogPanel.-visible {
        display: block;
    }
    ActivityLogPanel.-maximized {
        width: 100%;
    }
    ActivityLogPanel #log_title {
        text-style: bold;
        height: 1;
        color: $text;
    }
    ActivityLogPanel #log_widget {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Activity Log", id="log_title")
        yield Log(max_lines=2000, id="log_widget", auto_scroll=True)

    def set_title(self, text: str) -> None:
        self.query_one("#log_title", Label).update(text)

    def add_entry(self, name: str, state: str, when: str) -> None:
        self.query_one("#log_widget", Log).write_line(f"[{when}] {name} → {state}")

    def load_history(self, entries: list[dict]) -> None:
        log = self.query_one("#log_widget", Log)
        log.clear()
        if not entries:
            log.write_line("(no history available)")
            return
        lines = []
        for entry in entries:
            when = _format_log_time(entry.get("when", ""))
            name = entry.get("name") or entry.get("entity_id", "unknown")
            state = entry.get("state") or entry.get("message", "")
            lines.append(f"[{when}] {name} → {state}")
        log.write_lines(lines)

    def clear(self) -> None:
        self.query_one("#log_widget", Log).clear()


def _format_log_time(iso_str: str) -> str:
    if not iso_str:
        return "??:??:??"
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return iso_str[:8] if len(iso_str) >= 8 else "??:??:??"
