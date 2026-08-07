# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.widgets import Label, Static

from hatty.types import Entity, EntityAttributes
from hatty.ui.dashboard.widgets.base import EntitySlotWidget
from hatty.ui.dashboard.widgets.visuals import empty_bar, render_bar
from hatty.ui.entity_table import apply_pending_suffix, get_display_name_text

# Volume step per up/down nudge in widget mode.
VOLUME_STEP = 0.05

_STATE_ICONS = {"playing": "▶", "paused": "⏸", "idle": "⏹", "off": "⏹", "buffering": "⏳"}


class MediaPlayerSlotWidget(EntitySlotWidget):
    """Dashboard tile for a `media_player` entity: state glyph, now-playing
    title/artist, and a volume bar. up/down nudge volume and left/right skip
    tracks in widget mode; enter play/pauses. Full control (source, sound
    mode, shuffle/repeat) is available via expand (e)."""

    DEFAULT_CSS = """
    MediaPlayerSlotWidget {
        content-align: center middle;
    }
    MediaPlayerSlotWidget #slot_name {
        text-style: bold;
    }
    MediaPlayerSlotWidget #slot_state {
        color: $text-muted;
        text-style: bold;
    }
    MediaPlayerSlotWidget #slot_state.-playing {
        color: $success;
    }
    MediaPlayerSlotWidget #media_title {
        color: $text-muted;
    }
    MediaPlayerSlotWidget #media_volume {
        color: $text-muted;
    }
    MediaPlayerSlotWidget #media_volume.-playing {
        color: $success;
    }
    """

    def __init__(self, entity_id: str | None, *, show_last_changed: bool = False):
        super().__init__(entity_id, show_last_changed=show_last_changed)
        self._attrs: EntityAttributes = {}

    def compose(self) -> ComposeResult:
        yield Label("", id="slot_name")
        yield Label("", id="slot_state")
        yield Static("", id="media_title")
        yield Static("", id="media_volume")

    def _render_empty(self) -> None:
        super()._render_empty()
        self._attrs = {}

    def _render_entity(self, entity: Entity, pending: str | None) -> None:
        name_label = self.query_one("#slot_name", Label)
        state_label = self.query_one("#slot_state", Label)
        title_static = self.query_one("#media_title", Static)
        volume_static = self.query_one("#media_volume", Static)

        self._attrs = entity.get("attributes", {})
        state = entity.get("state", "")
        is_playing = state == "playing"

        name_label.update(get_display_name_text(entity))

        glyph = _STATE_ICONS.get(state, "◆")
        state_label.update(apply_pending_suffix(f"{glyph} {state}", pending))
        state_label.set_class(is_playing, "-playing")

        media_title = self._attrs.get("media_title")
        media_artist = self._attrs.get("media_artist")
        if media_title and media_artist:
            title_static.update(f"{media_title} — {media_artist}")
        elif media_title:
            title_static.update(media_title)
        else:
            title_static.update("—")

        volume = self._attrs.get("volume_level")
        volume_static.update(render_bar(volume * 100, 0, 100) if volume is not None else empty_bar())
        volume_static.set_class(is_playing, "-playing")

    def adjust_volume(self, direction: int) -> None:
        """Nudge volume by VOLUME_STEP when supported, else fall back to the
        stepped volume_up/volume_down services."""
        if not self.entity_id:
            return

        volume = self._attrs.get("volume_level")
        if volume is not None:
            new_volume = round(max(0.0, min(1.0, volume + direction * VOLUME_STEP)), 2)
            if new_volume == round(volume, 2):
                limit = "maximum" if direction > 0 else "minimum"
                self.app.notify(f"Already at {limit} volume.", severity="information")
                return
            self.app.dispatch_service_call(
                self.entity_id,
                "media_player",
                "volume_set",
                {"entity_id": self.entity_id, "volume_level": new_volume},
            )
            return

        service = "volume_up" if direction > 0 else "volume_down"
        self.app.dispatch_service_call(self.entity_id, "media_player", service, {"entity_id": self.entity_id})

    def previous_track(self) -> None:
        if not self.entity_id:
            return
        self.app.dispatch_service_call(
            self.entity_id, "media_player", "media_previous_track", {"entity_id": self.entity_id}
        )

    def next_track(self) -> None:
        if not self.entity_id:
            return
        self.app.dispatch_service_call(
            self.entity_id, "media_player", "media_next_track", {"entity_id": self.entity_id}
        )
