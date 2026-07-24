# hatty — MIT License. See LICENSE file for details.
from textual.widgets import Select

from hatty.ui.dashboard.screen import DashboardScreen
from hatty.ui.dashboard.slot_popup import DashboardSlotPopup
from hatty.ui.dashboard.widgets.media_player import MediaPlayerSlotWidget
from hatty.ui.entity_table import EntitiesTable
from tests.conftest import make_config

_HA = make_config(lists={})

_PLAYING_SPEAKER = {
    "entity_id": "media_player.living_room",
    "state": "playing",
    "attributes": {
        "friendly_name": "Living Room Speaker",
        "volume_level": 0.4,
        "media_title": "Song Title",
        "media_artist": "Artist Name",
    },
    "last_changed": "",
}

_NO_VOLUME_SPEAKER = {
    "entity_id": "media_player.kitchen",
    "state": "paused",
    "attributes": {"friendly_name": "Kitchen Speaker"},
    "last_changed": "",
}


def _cfg(entity_id):
    return {
        **_HA,
        "dashboards": {
            "Main": {
                "rows": 1,
                "cols": 1,
                "slots": [{"row": 0, "col": 0, "widget_type": "media_player", "entity_id": entity_id}],
            }
        },
    }


async def _open(pilot, app) -> DashboardScreen:
    await pilot.press("d")
    await pilot.pause()
    assert isinstance(app.screen, DashboardScreen)
    return app.screen


async def test_media_player_tile_renders_name_state_and_volume(make_app):
    app = make_app(entities=[_PLAYING_SPEAKER], config_data=_cfg("media_player.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        widget = screen.query_one(MediaPlayerSlotWidget)
        assert str(widget.query_one("#slot_name").content) == "Living Room Speaker"
        assert "playing" in str(widget.query_one("#slot_state").content)
        assert str(widget.query_one("#media_title").render()) == "Song Title — Artist Name"
        assert "█" in str(widget.query_one("#media_volume").render())


async def test_media_player_tile_shows_dash_when_no_title(make_app):
    app = make_app(entities=[_NO_VOLUME_SPEAKER], config_data=_cfg("media_player.kitchen"))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        widget = screen.query_one(MediaPlayerSlotWidget)
        assert str(widget.query_one("#media_title").render()) == "—"
        assert str(widget.query_one("#media_volume").render()) == "·" * 14


async def test_up_increases_volume_in_widget_mode(make_app):
    app = make_app(entities=[_PLAYING_SPEAKER], config_data=_cfg("media_player.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")  # enter widget mode
        await pilot.press("up")
        await pilot.pause()
        call = ("media_player", "volume_set", {"entity_id": "media_player.living_room", "volume_level": 0.45})
        assert call in app.client.call_service_calls


async def test_down_decreases_volume_in_widget_mode(make_app):
    app = make_app(entities=[_PLAYING_SPEAKER], config_data=_cfg("media_player.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")
        await pilot.press("down")
        await pilot.pause()
        call = ("media_player", "volume_set", {"entity_id": "media_player.living_room", "volume_level": 0.35})
        assert call in app.client.call_service_calls


async def test_left_right_skip_tracks_in_widget_mode(make_app):
    app = make_app(entities=[_PLAYING_SPEAKER], config_data=_cfg("media_player.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")  # enter widget mode
        await pilot.press("left")
        await pilot.press("right")
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("media_player", "media_previous_track", {"entity_id": "media_player.living_room"}) in calls
        assert ("media_player", "media_next_track", {"entity_id": "media_player.living_room"}) in calls


async def test_enter_in_widget_mode_play_pauses(make_app):
    app = make_app(entities=[_PLAYING_SPEAKER], config_data=_cfg("media_player.living_room"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")  # enter widget mode
        await pilot.press("enter")  # play/pause
        await pilot.pause()
        call = ("media_player", "media_play_pause", {"entity_id": "media_player.living_room"})
        assert call in app.client.call_service_calls


async def test_volume_up_service_used_when_no_volume_level(make_app):
    app = make_app(entities=[_NO_VOLUME_SPEAKER], config_data=_cfg("media_player.kitchen"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("enter")
        await pilot.press("up")
        await pilot.pause()
        call = ("media_player", "volume_up", {"entity_id": "media_player.kitchen"})
        assert call in app.client.call_service_calls


async def test_slot_popup_media_player_picker_lists_only_media_player_entities(
    make_app, sample_entities, open_dashboard
):
    app = make_app(entities=[*sample_entities, _PLAYING_SPEAKER, _NO_VOLUME_SPEAKER])
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # edit mode
        await pilot.press("a")
        await pilot.pause()
        popup = app.screen
        assert isinstance(popup, DashboardSlotPopup)

        popup.query_one("#widget_type_select", Select).value = "media_player"
        await pilot.pause()
        popup.query_one("#btn_next_step").press()
        await pilot.pause()

        table = popup.query_one("#entity_picker_table", EntitiesTable)
        row_keys = {key.value for key in table.rows}
        assert row_keys == {"", "media_player.living_room", "media_player.kitchen"}
