# hatty — MIT License. See LICENSE file for details.
from contextlib import contextmanager
from unittest.mock import patch

from rich.console import Console
from textual.widgets import Select, Static

from hatty.ui.config_screen import ConfigScreen
from tests.conftest import make_config


def _rendered_text(screen) -> str:
    console = Console(width=200)
    parts = []
    for widget in screen.query(Static):
        content = widget._Static__content
        with console.capture() as capture:
            console.print(content)
        parts.append(capture.get())
    return "\n".join(parts)


_CUSTOM_HOURS_CONFIG = {
    **make_config(),
    "lists": {},
    "graph_hours": 1.5,
}


async def test_config_screen_does_not_crash_with_custom_graph_hours(make_app, sample_entities):
    # Regression test: Select(..., value=1.5) used to raise InvalidSelectValueError
    # since 1.5 isn't one of the preset options, crashing the whole app on open.
    app = make_app(entities=sample_entities, config_data=_CUSTOM_HOURS_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        assert isinstance(app.screen, ConfigScreen)
        hours_select = app.screen.query_one("#cfg_graph_hours", Select)
        assert hours_select.is_blank()


async def test_saving_config_screen_preserves_custom_graph_hours(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CUSTOM_HOURS_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        # ctrl+s: a bare "s" would just move the auto-focused category ListView's
        # cursor (or type into a focused Input), so the binding is modifier-prefixed.
        await pilot.press("ctrl+s")
        await pilot.pause()

        assert app.app_config["graph_hours"] == 1.5


async def test_selecting_a_preset_in_config_screen_overrides_custom_value(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CUSTOM_HOURS_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        hours_select = app.screen.query_one("#cfg_graph_hours", Select)
        hours_select.value = 12
        await pilot.pause()

        await pilot.press("ctrl+s")
        await pilot.pause()

        assert app.app_config["graph_hours"] == 12


async def test_open_in_editor_does_not_raise_type_error(make_app, sample_entities):
    # Regression test: action_open_in_editor used `async with self.app.suspend()`,
    # but App.suspend is a sync contextmanager, raising TypeError on every press of "o".
    app = make_app(entities=sample_entities, config_data=_CUSTOM_HOURS_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        @contextmanager
        def fake_suspend(self):
            yield

        with patch.object(type(app), "suspend", fake_suspend), patch("hatty.ui.config_screen.subprocess.run") as run:
            app.screen.action_open_in_editor()
            await pilot.pause()

        assert run.called


async def test_editor_and_token_bindings_are_shown_in_footer(make_app, sample_entities):
    # ctrl+o (open in editor) and ctrl+v (show/hide token) must stay discoverable
    # in the footer. They're modifier-prefixed (not bare o/v) so they can't hijack
    # keystrokes once focus leaves the text Inputs (issue #192).
    app = make_app(entities=sample_entities, config_data=_CUSTOM_HOURS_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        # A focused Input can bind ctrl+v (paste) itself, shadowing the screen's
        # ctrl+v; clear focus so the screen-level bindings surface in the footer.
        app.screen.set_focus(None)
        await pilot.pause()
        shown_keys = {active.binding.key for active in app.screen.active_bindings.values() if active.binding.show}
        assert "ctrl+o" in shown_keys
        assert "ctrl+v" in shown_keys


async def test_config_screen_shows_saved_graphs_section(make_app, sample_entities):
    config_data = {
        **_CUSTOM_HOURS_CONFIG,
        "saved_graphs": {
            "Living Room Temp": {"entity_ids": ["sensor.living_room_temp"], "graph_type": "line", "hours": 4},
        },
    }
    app = make_app(entities=sample_entities, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        body_text = _rendered_text(app.screen)
        assert "Living Room Temp" in body_text
        assert "1 entity, line" in body_text


async def test_config_screen_shows_no_saved_graphs_note_when_empty(make_app, sample_entities):
    app = make_app(entities=sample_entities, config_data=_CUSTOM_HOURS_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_show_config()
        await pilot.pause()

        body_text = _rendered_text(app.screen)
        assert "No saved graphs defined." in body_text
