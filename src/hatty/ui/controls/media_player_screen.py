# hatty — MIT License. See LICENSE file for details.
from typing import TYPE_CHECKING

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Button, Footer, Label, OptionList, Select, Static

from hatty.const import media_supports
from hatty.ui.controls.light_screen import DEBOUNCE_SECONDS
from hatty.ui.controls.percentage_slider import PercentageSlider
from hatty.ui.entity_table import get_display_name

if TYPE_CHECKING:
    from hatty.main import HACLI
    from hatty.types import Entity

_STATE_ICONS = {"playing": "▶", "paused": "⏸", "idle": "⏹", "off": "⏹", "buffering": "⏳", "on": "▶"}

# Horizontal button rows where left/right should cycle within the row (wrapping) and
# up/down should jump out of the row as a block instead of stepping through each button
# individually (mirrors light_screen.py's #88/#286 patterns). Buttons without a dedicated
# hotkey (shuffle/repeat) are only reachable this way; the rest (transport) also have
# space/s/Enter shortcuts.
_BUTTON_ROW_IDS = ("transport_buttons", "toggle_buttons")

# HA repeat modes, in the order the repeat button cycles through them.
_REPEAT_MODES = ["off", "all", "one"]


class MediaPlayerControlScreen(ModalScreen):
    """Live-apply media_player control: continuous/selection fields debounce
    through dispatch_entity_control like LightControlScreen; discrete transport
    commands dispatch immediately via dispatch_service_call. No Save/Cancel —
    escape simply closes the screen."""

    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close", show=False),
        # priority so a focused Button doesn't swallow space (buttons still work via enter).
        Binding("space", "toggle_play_pause", "Play/Pause", priority=True),
        Binding("s", "stop_playback", "Stop", show=False),
        # Priority so up/down always move focus instead of being swallowed by a focused
        # volume slider's own value-adjust handling (issue #291, mirrors light_screen's
        # #286 fix) — left/right still adjust the slider in place. check_action releases
        # it while a Select's overlay is focused, so its own up/down keeps working.
        Binding("up", "nav_focus(-1)", "Focus Up", show=False, priority=True),
        Binding("down", "nav_focus(1)", "Focus Down", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    MediaPlayerControlScreen {
        align: center middle;
    }
    #media_container {
        width: 64;
        height: auto;
        max-height: 85%;
        background: $panel;
        border: heavy $accent;
        padding: 1 2;
    }
    #media_title {
        text-style: bold;
        margin-bottom: 1;
    }
    #media_title.-on {
        color: $success;
    }
    #now_playing {
        color: $text-muted;
        margin-bottom: 1;
    }
    #media_container Label.field-label {
        color: $text-muted;
    }
    #transport_buttons {
        height: 3;
        margin-top: 1;
        margin-bottom: 1;
    }
    #transport_buttons Button {
        min-width: 0;
        width: 1fr;
        margin: 0 1 0 0;
    }
    #media_container Select {
        margin-bottom: 1;
    }
    #toggle_buttons {
        height: 3;
        margin-top: 1;
    }
    #toggle_buttons Button {
        min-width: 0;
        width: 1fr;
        margin: 0 1 0 0;
    }
    """

    def __init__(self, entity: "Entity"):
        super().__init__()
        self._entity: "Entity" = entity
        self._entity_id = entity.get("entity_id", "")
        self._attrs = entity.get("attributes", {})
        self._pending: dict = {}
        self._debounce_timer: Timer | None = None

        features = self._attrs.get("supported_features")
        self.supports_volume = media_supports(features, "volume_set")
        self.supports_mute = media_supports(features, "volume_mute")
        self.supports_previous = media_supports(features, "previous_track")
        self.supports_next = media_supports(features, "next_track")
        self.supports_stop = media_supports(features, "stop")
        self.supports_play_pause = media_supports(features, "play") or media_supports(features, "pause")
        self.source_list: list[str] = list(self._attrs.get("source_list") or [])
        self.supports_source = media_supports(features, "select_source") and bool(self.source_list)
        self.sound_mode_list: list[str] = list(self._attrs.get("sound_mode_list") or [])
        self.supports_sound_mode = media_supports(features, "select_sound_mode") and bool(self.sound_mode_list)
        self.supports_shuffle = media_supports(features, "shuffle_set")
        self.supports_repeat = media_supports(features, "repeat_set")

        self._muted = bool(self._attrs.get("is_volume_muted", False))
        self._shuffle = bool(self._attrs.get("shuffle", False))
        self._repeat = self._attrs.get("repeat", "off")

        # Select posts a Changed message for its initial value on mount; these
        # guards skip that first event so opening the screen doesn't dispatch.
        self._source_select_ready = False
        self._sound_mode_select_ready = False

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="media_container"):
            yield Label("", id="media_title")
            yield Static("", id="now_playing")

            if self.supports_volume:
                volume = self._attrs.get("volume_level")
                percent = round(volume * 100) if volume is not None else 0
                yield Label("Volume", classes="field-label")
                yield PercentageSlider(value=percent, id="field_volume")

            if self.supports_previous or self.supports_play_pause or self.supports_stop or self.supports_next:
                with Horizontal(id="transport_buttons"):
                    if self.supports_previous:
                        yield Button("⏮ Prev", id="btn_previous")
                    if self.supports_play_pause:
                        yield Button(self._play_pause_label(), id="btn_play_pause")
                    if self.supports_stop:
                        yield Button("⏹ Stop", id="btn_stop")
                    if self.supports_next:
                        yield Button("Next ⏭", id="btn_next")

            if self.supports_source:
                yield Label("Source", classes="field-label")
                yield Select(
                    [(s, s) for s in self.source_list],
                    id="field_source",
                    allow_blank=True,
                    value=self._attrs.get("source") if self._attrs.get("source") in self.source_list else Select.NULL,
                )

            if self.supports_sound_mode:
                yield Label("Sound Mode", classes="field-label")
                sound_mode = self._attrs.get("sound_mode")
                yield Select(
                    [(s, s) for s in self.sound_mode_list],
                    id="field_sound_mode",
                    allow_blank=True,
                    value=sound_mode if sound_mode in self.sound_mode_list else Select.NULL,
                )

            if self.supports_shuffle or self.supports_repeat:
                with Horizontal(id="toggle_buttons"):
                    if self.supports_shuffle:
                        yield Button(self._shuffle_label(), id="btn_shuffle")
                    if self.supports_repeat:
                        yield Button(self._repeat_label(), id="btn_repeat")

            yield Footer()

    def on_mount(self) -> None:
        self._update_title()

    # ── Labels ────────────────────────────────────────────────────────────────

    def _play_pause_label(self) -> str:
        entity = self.app.find_entity(self._entity_id) or self._entity
        return "⏸ Pause" if entity.get("state") == "playing" else "▶ Play"

    def _shuffle_label(self) -> str:
        return f"🔀 Shuffle: {'on' if self._shuffle else 'off'}"

    def _repeat_label(self) -> str:
        return f"🔁 Repeat: {self._repeat}"

    # ── Live apply ────────────────────────────────────────────────────────────

    def _queue(self, **fields) -> None:
        self._pending.update(fields)
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        self._debounce_timer = self.set_timer(DEBOUNCE_SECONDS, self._flush)

    def _flush(self) -> None:
        self._debounce_timer = None
        if not self._pending:
            return
        fields, self._pending = self._pending, {}
        self.app.dispatch_entity_control(self._entity_id, "media_player", fields)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _update_title(self) -> None:
        entity = self.app.find_entity(self._entity_id) or self._entity
        state = entity.get("state", "")
        glyph = _STATE_ICONS.get(state, "◆")
        title = self.query_one("#media_title", Label)
        title.update(f"{glyph} {get_display_name(entity)} — {state}")
        title.set_class(state == "playing", "-on")

        attrs = entity.get("attributes", {})
        media_title = attrs.get("media_title")
        media_artist = attrs.get("media_artist")
        now_playing = self.query_one("#now_playing", Static)
        if media_title and media_artist:
            now_playing.update(f"{media_title} — {media_artist}")
        elif media_title:
            now_playing.update(media_title)
        else:
            now_playing.update("—")

    # ── Events ────────────────────────────────────────────────────────────────

    def on_percentage_slider_changed(self, event: PercentageSlider.Changed) -> None:
        if event.slider.has_focus:
            self._queue(volume_level=event.value / 100)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "field_source":
            if not self._source_select_ready:
                self._source_select_ready = True
                return
            if event.value is not Select.NULL:
                self.app.dispatch_entity_control(self._entity_id, "media_player", {"source": event.value})
        elif event.select.id == "field_sound_mode":
            if not self._sound_mode_select_ready:
                self._sound_mode_select_ready = True
                return
            if event.value is not Select.NULL:
                self.app.dispatch_entity_control(self._entity_id, "media_player", {"sound_mode": event.value})

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn_previous":
            self.action_previous_track()
        elif btn_id == "btn_play_pause":
            self.action_toggle_play_pause()
        elif btn_id == "btn_stop":
            self.action_stop_playback()
        elif btn_id == "btn_next":
            self.action_next_track()
        elif btn_id == "btn_shuffle":
            self._toggle_shuffle()
        elif btn_id == "btn_repeat":
            self._cycle_repeat()

    def on_key(self, event: events.Key) -> None:
        # Left/right walk the focus chain (row-aware — see _focus_within_row) unless the
        # volume slider or a Select's expanded overlay owns them (mirrors light_screen.py's
        # on_key hijack, issue #88). Up/down are handled as priority Bindings instead (see
        # nav_focus) so they always move focus rather than being swallowed by the slider.
        focused = self.focused
        if isinstance(focused, (PercentageSlider, OptionList)):
            return
        if event.key in ("left", "right"):
            row = self._enclosing_row(focused)
            if row is not None and focused is not None:
                self._focus_within_row(row, focused, 1 if event.key == "right" else -1)
            elif event.key == "left":
                self.focus_previous()
            else:
                self.focus_next()
            event.stop()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "toggle_play_pause":
            return self.supports_play_pause
        if action == "stop_playback":
            return self.supports_stop
        if action == "nav_focus":
            # Let an expanded Select's overlay (a SelectOverlay, an OptionList
            # subclass) keep its own up/down cursor movement.
            return not isinstance(self.focused, OptionList)
        return True

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_close(self) -> None:
        self._flush()
        self.dismiss(None)

    def action_nav_focus(self, direction: int) -> None:
        # A focused slider (or any other single widget) just steps one at a time; a
        # button row (transport/toggle) is skipped as a whole block (mirrors
        # light_screen.py's #286 pattern).
        row = self._enclosing_row(self.focused)
        if row is not None:
            self._focus_out_of_row(row, direction)
        elif direction > 0:
            self.focus_next()
        else:
            self.focus_previous()

    def _enclosing_row(self, widget: Widget | None) -> Widget | None:
        """The `#transport_buttons`/`#toggle_buttons` Horizontal row containing `widget`, if any."""
        if widget is None:
            return None
        for node in widget.ancestors_with_self:
            if isinstance(node, Widget) and node.id in _BUTTON_ROW_IDS:
                return node
        return None

    def _focus_within_row(self, row: Widget, focused: Widget, step: int) -> None:
        """Cycle focus among `row`'s buttons, wrapping at the ends."""
        buttons = list(row.query(Button))
        if not buttons:
            return
        index = next((i for i, button in enumerate(buttons) if button is focused), 0)
        buttons[(index + step) % len(buttons)].focus()

    def _focus_out_of_row(self, row: Widget, step: int) -> None:
        """Move focus in `step`'s direction, skipping the whole row as one unit."""
        step_focus = self.focus_next if step > 0 else self.focus_previous
        for _ in range(len(self.focus_chain)):
            landed = step_focus()
            if landed is None or row not in landed.ancestors_with_self:
                return

    def action_toggle_play_pause(self) -> None:
        if not self.supports_play_pause:
            return
        entity = self.app.find_entity(self._entity_id) or self._entity
        self.app.dispatch_service_call(
            self._entity_id, "media_player", "media_play_pause", {"entity_id": self._entity_id}
        )
        # Optimistically flip the header; the next state_changed confirms it.
        new_state = "paused" if entity.get("state") == "playing" else "playing"
        self._entity = {**entity, "state": new_state}
        self._update_title()
        buttons = self.query("#btn_play_pause")
        if buttons:
            buttons.first(Button).label = self._play_pause_label()

    def action_previous_track(self) -> None:
        if not self.supports_previous:
            return
        self.app.dispatch_service_call(
            self._entity_id, "media_player", "media_previous_track", {"entity_id": self._entity_id}
        )

    def action_next_track(self) -> None:
        if not self.supports_next:
            return
        self.app.dispatch_service_call(
            self._entity_id, "media_player", "media_next_track", {"entity_id": self._entity_id}
        )

    def action_stop_playback(self) -> None:
        if not self.supports_stop:
            return
        self.app.dispatch_service_call(self._entity_id, "media_player", "media_stop", {"entity_id": self._entity_id})

    def _toggle_shuffle(self) -> None:
        self._shuffle = not self._shuffle
        self.app.dispatch_entity_control(self._entity_id, "media_player", {"shuffle": self._shuffle})
        self.query_one("#btn_shuffle", Button).label = self._shuffle_label()

    def _cycle_repeat(self) -> None:
        index = _REPEAT_MODES.index(self._repeat) if self._repeat in _REPEAT_MODES else 0
        self._repeat = _REPEAT_MODES[(index + 1) % len(_REPEAT_MODES)]
        self.app.dispatch_entity_control(self._entity_id, "media_player", {"repeat": self._repeat})
        self.query_one("#btn_repeat", Button).label = self._repeat_label()
