# hatty — MIT License. See LICENSE file for details.
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Label, OptionList
from textual.widgets.option_list import Option

from hatty.controllers.keybindings import bindings_for
from hatty.ui.popup_base import PopupScreen

# plotext named color -> ANSI 0-15 code. plotext resolves colors through the
# terminal's own palette, so the swatch must go through the same codes or it lies
# about the plotted line. Imported from plotext's private _utility so it can
# never drift; falls back to an empty map if that internal module moves.
try:
    from plotext._utility import color_codes as _PLOTEXT_COLOR_CODES
except ImportError:  # pragma: no cover - defensive against plotext internals moving
    _PLOTEXT_COLOR_CODES = {}

# ANSI 0-15 -> Textual markup color name. `ansi_*` renders terminal-native
# (same 16-color palette plotext emits to), so a swatch and a plotted line
# share one palette on every theme. (Rich's `[color(N)]` isn't valid here.)
_ANSI_MARKUP = {
    0: "ansi_black",
    1: "ansi_red",
    2: "ansi_green",
    3: "ansi_yellow",
    4: "ansi_blue",
    5: "ansi_magenta",
    6: "ansi_cyan",
    7: "ansi_white",
    8: "ansi_bright_black",
    9: "ansi_bright_red",
    10: "ansi_bright_green",
    11: "ansi_bright_yellow",
    12: "ansi_bright_blue",
    13: "ansi_bright_magenta",
    14: "ansi_bright_cyan",
    15: "ansi_bright_white",
}

# Every plotext named color offered by the picker (`+` = plotext's bright variant).
# Order is deliberate and index-sensitive for tests; every entry must be a key
# of _PLOTEXT_COLOR_CODES (guarded by a test).
ALL_PLOT_COLORS = [
    "blue",
    "red",
    "green",
    "orange",
    "magenta",
    "cyan",
    "gray",
    "white",
    "blue+",
    "red+",
    "green+",
    "orange+",
    "magenta+",
    "cyan+",
    "gray+",
]


def swatch_markup(plotext_color: str) -> str:
    """Textual markup for a color swatch that resolves through the same terminal
    ANSI palette plotext uses to draw the line, so swatch and line always agree."""
    code = _PLOTEXT_COLOR_CODES.get(plotext_color)
    name = _ANSI_MARKUP.get(code) if code is not None else None
    if name is None:
        return "██████"
    return f"[{name}]██████[/]"


class GraphColorPopup(PopupScreen):
    """Pick a plotext color for one graph line; dismisses with the color name or None."""

    BINDINGS = bindings_for("graph_color")

    DEFAULT_CSS = """
    #graph_color_container {
        width: 40;
    }
    #graph_color_container Label {
        margin-bottom: 1;
        text-style: bold;
    }
    """

    def __init__(self, entity_name: str, current_color: str | None = None):
        super().__init__()
        self._entity_name = entity_name
        self._current_color = current_color

    def compose(self) -> ComposeResult:
        with Container(id="graph_color_container", classes="popup-container"):
            yield Label(f"Line color: {self._entity_name}")
            options = [Option(f"{swatch_markup(color)} {color}", id=color) for color in ALL_PLOT_COLORS]
            yield OptionList(*options, id="graph_color_list")
            yield Footer()

    def on_mount(self) -> None:
        option_list = self.query_one("#graph_color_list", OptionList)
        if self._current_color in ALL_PLOT_COLORS:
            option_list.highlighted = ALL_PLOT_COLORS.index(self._current_color)
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
