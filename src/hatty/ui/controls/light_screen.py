# hatty — MIT License. See LICENSE file for details.
"""Dedicated light control screen, pushed by `e` on a light entity.

Live-apply model: every change is queued and dispatched through
`HACLI.dispatch_entity_control` after a debounce — there is no Save/Cancel,
`escape` flushes and closes. Since only the touched field is queued, white and
color edits never send a conflicting `kelvin` + `rgb_color` pair in the same
call.

Layout: title with power state (`space` toggles), a live color/brightness
preview bar, an always-visible brightness slider, then a `TabbedContent` with
only the tabs the light supports — White (kelvin slider + presets), Color
(swatches + picker), Effects (filtered list). Capability detection reads
`supported_color_modes`, a fixed attribute present even while the light is
off — unlike `brightness`/`color_temp`, which only appear once it's on — so
the available tabs don't flicker based on current power state.

`t` cycles tabs; `left`/`right` adjust a focused slider or cycle within a
button row when the row itself is focused, but hand off to `Tabs`'/`Input`'s
own native handling when one of those is focused instead. `up`/`down` are a
priority binding that always moves focus one step (or one row-block) rather
than being swallowed by a slider's own arrow handling.
"""

from typing import TYPE_CHECKING

from textual import events
from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Button, Footer, Input, Label, OptionList, Static, TabbedContent, TabPane, Tabs
from textual.widgets.option_list import Option
from textual_colorpicker import ColorPicker

from hatty.controllers.keybindings import bindings_for
from hatty.ui.controls.kelvin_slider import KelvinSlider
from hatty.ui.controls.percentage_slider import PercentageSlider
from hatty.ui.entity_table import get_display_name
from hatty.ui.focus_nav import enclosing_row, focus_within_row, nav_focus
from hatty.ui.popup_base import PopupScreen

if TYPE_CHECKING:
    from hatty.main import HACLI
    from hatty.types import Entity

_COLOR_PICKER_MODES = {"hs", "rgb", "xy", "rgbw", "rgbww"}

# Warm/Neutral/Cool white preset color temperatures (Kelvin), on keys 1/2/3.
WHITE_PRESETS = [("Warm", 2700), ("Neutral", 4000), ("Cool", 6500)]

# Quick-pick color swatches: (id-suffix, label, hex).
COLOR_SWATCHES = [
    ("red", "Red", "#ff0000"),
    ("orange", "Orange", "#ff8000"),
    ("yellow", "Yellow", "#ffff00"),
    ("green", "Green", "#00ff00"),
    ("cyan", "Cyan", "#00ffff"),
    ("blue", "Blue", "#0000ff"),
    ("purple", "Purple", "#8000ff"),
    ("white", "White", "#ffffff"),
]

DEBOUNCE_SECONDS = 0.3

# Horizontal button rows where left/right should cycle within the row (wrapping) instead of
# walking the whole screen's focus chain, and up/down should jump out of the row as a block.
_BUTTON_ROW_IDS = ("color_swatches", "white_presets")


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    """h 0-360, s 0-100, v 0-100 → r,g,b 0-255."""
    s /= 100.0
    v /= 100.0
    if s == 0:
        c = round(v * 255)
        return (c, c, c)
    h = h % 360
    h6 = h / 60.0
    i = int(h6)
    f = h6 - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    rgb_map = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]
    r, g, b = rgb_map[i % 6]
    return (round(r * 255), round(g * 255), round(b * 255))


class ColorPickerModal(PopupScreen):
    BINDINGS = bindings_for("color_picker")

    # Centering + the panel box come from PopupScreen's `.popup-container`; only the
    # auto width (to fit the ColorPicker) and the button row differ.
    DEFAULT_CSS = """
    ColorPickerModal #color_picker_container {
        width: auto;
    }
    #picker_button_row {
        margin-top: 1;
        height: 3;
        align-horizontal: right;
    }
    """

    def __init__(self, color: Color):
        super().__init__()
        self._initial_color = color

    def compose(self) -> ComposeResult:
        with Container(id="color_picker_container", classes="popup-container"):
            yield ColorPicker(self._initial_color, id="the_picker")
            with Horizontal(id="picker_button_row"):
                yield Button("Pick", variant="primary", id="btn_pick")
                yield Button("Cancel", id="btn_cancel_pick")
            yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_pick":
            self.dismiss(self.query_one("#the_picker", ColorPicker).color)
        elif event.button.id == "btn_cancel_pick":
            self.dismiss(None)


class LightControlScreen(ModalScreen):
    """Live-apply light control: every change is sent to HA after a short debounce,
    so there is no Save/Cancel — escape simply closes the screen."""

    app: "HACLI"  # narrow Textual's inherited attr for type-checkers; annotation only, no runtime effect

    # space is priority so a focused Button doesn't swallow it (released while the
    # effect filter Input is focused). up/down are priority so they move focus
    # instead of being swallowed by a slider's value-adjust (#286) — left/right
    # still adjust in place; released while the effects OptionList is focused.
    BINDINGS = bindings_for("light")

    DEFAULT_CSS = """
    LightControlScreen {
        align: center middle;
    }
    #light_container {
        width: 64;
        height: auto;
        max-height: 85%;
        background: $panel;
        border: heavy $accent;
        padding: 1 2;
    }
    #light_title {
        text-style: bold;
        margin-bottom: 1;
    }
    #light_title.-on {
        color: $success;
    }
    #color_preview {
        height: 1;
        margin-bottom: 1;
    }
    #light_container Label.field-label {
        color: $text-muted;
    }
    #white_presets, #color_swatches {
        height: 3;
        margin-top: 1;
    }
    #white_presets Button, #color_swatches Button {
        min-width: 0;
        width: 1fr;
        margin: 0 1 0 0;
    }
    #color_hex_display {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
    }
    #effect_filter {
        margin-bottom: 1;
    }
    #effect_options {
        height: 8;
        border: solid $accent;
    }
    LightControlScreen TabbedContent {
        margin-top: 1;
    }
    """

    def __init__(self, entity: "Entity"):
        super().__init__()
        self._entity: "Entity" = entity
        self._entity_id = entity.get("entity_id", "")
        self._attrs = entity.get("attributes", {})
        self._effect_list: list[str] = list(self._attrs.get("effect_list") or [])
        self._light_color: Color | None = None
        self._pending: dict = {}
        self._debounce_timer: Timer | None = None

        color_modes = self._attrs.get("supported_color_modes")
        self.supports_brightness = True if color_modes is None else any(m != "onoff" for m in color_modes)
        self.supports_color_temp = True if color_modes is None else "color_temp" in color_modes
        self.supports_color = color_modes is not None and any(m in _COLOR_PICKER_MODES for m in color_modes)

        rgb_color = self._attrs.get("rgb_color")
        hs_color = self._attrs.get("hs_color")
        if rgb_color:
            r, g, b = (int(x) for x in rgb_color)
            self._light_color = Color(r, g, b)
        elif hs_color:
            hue, sat = hs_color
            self._light_color = Color(*hsv_to_rgb(hue, sat, 100))

    # ── Capability helpers ────────────────────────────────────────────────────

    def _read_kelvin(self) -> int | None:
        """Current color temperature in Kelvin, tolerating legacy mireds-only configs."""
        kelvin = self._attrs.get("color_temp_kelvin")
        if kelvin is not None:
            return int(kelvin)
        mireds = self._attrs.get("color_temp")
        if mireds:
            return round(1_000_000 / mireds)
        return None

    def _read_kelvin_range(self) -> tuple[int, int]:
        min_k = self._attrs.get("min_color_temp_kelvin")
        max_k = self._attrs.get("max_color_temp_kelvin")
        if min_k is not None and max_k is not None:
            return int(min_k), int(max_k)
        min_mireds = self._attrs.get("min_mireds")
        max_mireds = self._attrs.get("max_mireds")
        if min_mireds and max_mireds:
            # Larger mireds == warmer (lower Kelvin), so max_mireds maps to the minimum K.
            return round(1_000_000 / max_mireds), round(1_000_000 / min_mireds)
        return 2000, 6500

    def _initial_tab(self) -> str:
        color_mode = self._attrs.get("color_mode")
        if color_mode == "color_temp" and self.supports_color_temp:
            return "tab_white"
        if color_mode in _COLOR_PICKER_MODES and self.supports_color:
            return "tab_color"
        if self.supports_color_temp:
            return "tab_white"
        if self.supports_color:
            return "tab_color"
        return "tab_effects"

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="light_container"):
            yield Label("", id="light_title")
            yield Static("", id="color_preview")

            if self.supports_brightness:
                brightness = self._attrs.get("brightness")
                percent = round(int(brightness) / 255 * 100) if brightness is not None else 0
                yield Label("Brightness", classes="field-label")
                yield PercentageSlider(value=percent, id="field_brightness")

            if self.supports_color_temp or self.supports_color or self._effect_list:
                with TabbedContent(initial=self._initial_tab()):
                    if self.supports_color_temp:
                        with TabPane("White", id="tab_white"):
                            min_k, max_k = self._read_kelvin_range()
                            current = self._read_kelvin()
                            yield Label("Color Temp (1/2/3 presets)", classes="field-label")
                            yield KelvinSlider(
                                value=current if current is not None else min_k,
                                min_value=min_k,
                                max_value=max_k,
                                id="field_kelvin",
                            )
                            with Horizontal(id="white_presets"):
                                for label, _kelvin in WHITE_PRESETS:
                                    yield Button(label, id=f"btn_preset_{label.lower()}")
                    if self.supports_color:
                        with TabPane("Color", id="tab_color"):
                            with Horizontal(id="color_swatches"):
                                for suffix, label, hex_str in COLOR_SWATCHES:
                                    btn = Button("", id=f"btn_swatch_{suffix}")
                                    btn.styles.background = hex_str
                                    btn.tooltip = label
                                    yield btn
                            yield Static(self._light_color.hex if self._light_color else "—", id="color_hex_display")
                            yield Button("Pick color… (p)", id="btn_pick_color")
                    if self._effect_list:
                        with TabPane("Effects", id="tab_effects"):
                            yield Input(placeholder="filter effects…", id="effect_filter")
                            yield OptionList(*self._effect_options(), id="effect_options")
            yield Footer()

    def _effect_options(self, term: str = "") -> list[Option]:
        term = term.strip().lower()
        effects = [e for e in self._effect_list if term in e.lower()] if term else self._effect_list
        current = self._attrs.get("effect")
        return [Option(f"● {e}" if e == current else f"  {e}", id=e) for e in effects]

    def on_mount(self) -> None:
        self._update_title()
        self._update_preview()
        sliders = self.query("#field_brightness")
        if sliders:
            sliders.first().focus()

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
        self.app.dispatch_entity_control(self._entity_id, "light", fields)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _update_title(self) -> None:
        entity = self.app.find_entity(self._entity_id) or self._entity
        state = entity.get("state", "")
        glyph = "💡" if state == "on" else "○"
        title = self.query_one("#light_title", Label)
        title.update(f"{glyph} {get_display_name(entity)} — {state}  (space: on/off)")
        title.set_class(state == "on", "-on")

    def _current_brightness_percent(self) -> int:
        sliders = self.query("#field_brightness")
        if sliders:
            return sliders.first(PercentageSlider).value
        return 100

    def _update_preview(self) -> None:
        brightness = self._current_brightness_percent()
        if self._light_color is not None:
            r, g, b = self._light_color.r, self._light_color.g, self._light_color.b
            factor = brightness / 100
            r, g, b = round(r * factor), round(g * factor), round(b * factor)
        else:
            r = g = b = round(brightness * 255 / 100)
        self.query_one("#color_preview", Static).update(
            f"[on #{r:02x}{g:02x}{b:02x}]{' ' * 58}[/on #{r:02x}{g:02x}{b:02x}]"
        )

    def _set_color(self, color: Color) -> None:
        self._light_color = color
        hex_q = self.query("#color_hex_display")
        if hex_q:
            hex_q.first(Static).update(color.hex)
        self._update_preview()
        self._queue(rgb_hex=color.hex)

    # ── Events ────────────────────────────────────────────────────────────────

    def on_percentage_slider_changed(self, event: PercentageSlider.Changed) -> None:
        self._update_preview()
        if event.slider.has_focus:
            self._queue(brightness=round(event.value / 100 * 255))

    def on_kelvin_slider_changed(self, event: KelvinSlider.Changed) -> None:
        if event.slider.has_focus:
            self._queue(kelvin=event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "effect_filter":
            options = self.query_one("#effect_options", OptionList)
            options.clear_options()
            options.add_options(self._effect_options(event.value))
            if options.option_count:
                options.highlighted = 0
            event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "effect_filter":
            self.query_one("#effect_options", OptionList).focus()
            event.stop()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "effect_options" and event.option.id:
            self._queue(effect=event.option.id)
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("btn_preset_"):
            name = btn_id.removeprefix("btn_preset_")
            kelvin = next((k for label, k in WHITE_PRESETS if label.lower() == name), None)
            if kelvin is not None:
                self._apply_kelvin(kelvin)
            event.stop()
        elif btn_id.startswith("btn_swatch_"):
            suffix = btn_id.removeprefix("btn_swatch_")
            hex_str = next((h for s, _, h in COLOR_SWATCHES if s == suffix), None)
            if hex_str is not None:
                self._set_color(Color.parse(hex_str))
            event.stop()
        elif btn_id == "btn_pick_color":
            self.action_open_color_picker()
            event.stop()

    def on_key(self, event: events.Key) -> None:
        # Left/right walk the focus chain unless a slider/input/tab bar owns them
        # (#88). Up/down are priority Bindings instead (see nav_focus).
        focused = self.focused
        if isinstance(focused, (Input, PercentageSlider, KelvinSlider, Tabs)):
            return
        if event.key in ("left", "right"):
            row = enclosing_row(focused, _BUTTON_ROW_IDS)
            if row is not None and focused is not None:
                focus_within_row(row, focused, 1 if event.key == "right" else -1)
            elif event.key == "left":
                self.focus_previous()
            else:
                self.focus_next()
            event.stop()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # Don't steal space/digits/p/t while typing in the effect filter.
        if action in ("toggle_power", "white_preset", "open_color_picker", "cycle_tab") and isinstance(
            self.focused, Input
        ):
            return False
        if action == "white_preset":
            return self.supports_color_temp
        if action == "open_color_picker":
            return self.supports_color
        if action == "cycle_tab":
            # Only offer the cycle when there is more than one pane to cycle.
            panes = (self.supports_color_temp, self.supports_color, bool(self._effect_list))
            return sum(panes) > 1
        if action == "nav_focus":
            # Let the effects OptionList keep its own up/down cursor movement.
            return not isinstance(self.focused, OptionList)
        return True

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_close(self) -> None:
        self._flush()
        self.dismiss(None)

    def action_show_help(self) -> None:
        self.app.action_show_help()

    def action_nav_focus(self, direction: int) -> None:
        # A focused slider (or any single widget) steps one at a time; a row
        # (swatches/presets) is skipped as a whole block (#286).
        nav_focus(self, _BUTTON_ROW_IDS, direction)

    def action_toggle_power(self) -> None:
        entity = self.app.find_entity(self._entity_id) or self._entity
        service = "turn_off" if entity.get("state") == "on" else "turn_on"
        self.app.dispatch_service_call(self._entity_id, "light", service, {"entity_id": self._entity_id})
        # Optimistically flip the header; the next state_changed confirms it.
        self._entity = {**entity, "state": "off" if service == "turn_off" else "on"}
        self._update_title()

    def action_cycle_tab(self) -> None:
        tabs = self.query(TabbedContent)
        if not tabs:
            return
        tc = tabs.first(TabbedContent)
        panes = [pane.id for pane in tc.query(TabPane) if pane.id]
        if len(panes) < 2:
            return
        # Deliberately no auto-focus of the effect filter here: `t` must keep
        # cycling on the next press instead of typing into the filter.
        tc.active = panes[(panes.index(tc.active) + 1) % len(panes)]

    def action_white_preset(self, index: int) -> None:
        if not self.supports_color_temp:
            return
        self._apply_kelvin(WHITE_PRESETS[index][1])

    def _apply_kelvin(self, kelvin: int) -> None:
        slider = self.query_one("#field_kelvin", KelvinSlider)
        slider.value = kelvin  # KelvinSlider clamps to its supported range
        self._queue(kelvin=slider.value)

    def action_open_color_picker(self) -> None:
        if not self.supports_color:
            return
        initial = self._light_color or Color(255, 255, 255)

        def _on_picked(color: Color | None) -> None:
            if color is not None:
                self._set_color(color)

        self.app.push_screen(ColorPickerModal(initial), _on_picked)
