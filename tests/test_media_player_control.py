# hatty — MIT License. See LICENSE file for details.
from textual.widgets import Button, OptionList, Select, Static

from hatty.const import MEDIA_FEAT
from hatty.ui.controls import media_player_screen
from hatty.ui.controls.media_player_screen import MediaPlayerControlScreen
from hatty.ui.controls.percentage_slider import PercentageSlider
from hatty.ui.focus_nav import enclosing_row
from hatty.ui.help_popup import HelpPopup
from tests.conftest import make_config

_CONFIG = {
    **make_config(),
    "lists": {},
}

# All feature bits are distinct powers of two -> sum == bitwise OR of every flag.
_ALL_FEATURES = sum(MEDIA_FEAT.values())

_FULL_MEDIA_PLAYER = [
    {
        "entity_id": "media_player.living_room",
        "state": "playing",
        "attributes": {
            "friendly_name": "Living Room Speaker",
            "supported_features": _ALL_FEATURES,
            "volume_level": 0.6,
            "is_volume_muted": False,
            "media_title": "Song Title",
            "media_artist": "Artist Name",
            "source": "Spotify",
            "source_list": ["Spotify", "TV", "Radio"],
            "sound_mode": "Movie",
            "sound_mode_list": ["Movie", "Music", "Night"],
            "shuffle": False,
            "repeat": "off",
        },
        "last_changed": "",
    }
]

_VOLUME_ONLY_MEDIA_PLAYER = [
    {
        "entity_id": "media_player.bathroom",
        "state": "playing",
        "attributes": {
            "friendly_name": "Bathroom Speaker",
            "supported_features": MEDIA_FEAT["volume_set"],
            "volume_level": 0.3,
        },
        "last_changed": "",
    }
]

_NO_SOURCE_MEDIA_PLAYER = [
    {
        "entity_id": "media_player.kitchen",
        "state": "paused",
        "attributes": {
            "friendly_name": "Kitchen Speaker",
            "supported_features": (
                MEDIA_FEAT["play"]
                | MEDIA_FEAT["pause"]
                | MEDIA_FEAT["previous_track"]
                | MEDIA_FEAT["next_track"]
                | MEDIA_FEAT["stop"]
            ),
        },
        "last_changed": "",
    }
]

# Regression for the InvalidSelectValueError crash: source_list/sound_mode_list are
# populated (so the Source/Sound-Mode Selects are shown), but the entity's current
# source/sound_mode is absent — the blank fallback path Select(value=...) must not
# crash the screen on mount.
_BLANK_SOURCE_MEDIA_PLAYER = [
    {
        "entity_id": "media_player.office",
        "state": "playing",
        "attributes": {
            "friendly_name": "Office Speaker",
            "supported_features": MEDIA_FEAT["select_source"] | MEDIA_FEAT["select_sound_mode"],
            "source_list": ["Spotify", "TV", "Radio"],
            "sound_mode_list": ["Movie", "Music", "Night"],
        },
        "last_changed": "",
    }
]


async def _open(pilot, app) -> MediaPlayerControlScreen:
    await pilot.press("e")
    await pilot.pause()
    assert isinstance(app.screen, MediaPlayerControlScreen)
    return app.screen


async def test_full_featured_shows_every_control_and_now_playing(make_app):
    """e opening the screen, every control it should show for a fully-featured
    player, and the now-playing label are all read-only — one boot covers
    them (`_open`'s own assert already confirms the screen opens)."""
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        assert len(screen.query("#field_volume")) == 1
        assert len(screen.query("#btn_previous")) == 1
        assert len(screen.query("#btn_play_pause")) == 1
        assert len(screen.query("#btn_stop")) == 1
        assert len(screen.query("#btn_next")) == 1
        assert len(screen.query("#field_source")) == 1
        assert len(screen.query("#field_sound_mode")) == 1
        assert len(screen.query("#btn_shuffle")) == 1
        assert len(screen.query("#btn_repeat")) == 1
        assert str(screen.query_one("#now_playing", Static).render()) == "Song Title — Artist Name"
        assert screen.query_one("#field_volume", PercentageSlider).value == 60


async def test_volume_only_hides_transport_and_selects(make_app):
    app = make_app(entities=_VOLUME_ONLY_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        assert len(screen.query("#field_volume")) == 1
        assert len(screen.query("#transport_buttons")) == 0
        assert len(screen.query("#field_source")) == 0
        assert len(screen.query("#field_sound_mode")) == 0
        assert len(screen.query("#toggle_buttons")) == 0


async def test_volume_change_live_dispatches_after_debounce(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        slider = screen.query_one("#field_volume", PercentageSlider)
        slider.focus()
        slider.value = 80
        await pilot.pause(delay=0.5)  # let the 0.3s debounce fire

        calls = [c for c in app.client.call_service_calls if c[1] == "volume_set"]
        assert any(abs(c[2].get("volume_level") - 0.8) < 1e-9 for c in calls)


async def test_space_toggles_play_pause(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)

        await pilot.press("space")
        await pilot.pause()

        assert ("media_player", "media_play_pause", {"entity_id": "media_player.living_room"}) in (
            app.client.call_service_calls
        )


async def test_left_right_navigate_transport_row_instead_of_dispatching(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        screen.query_one("#btn_previous", Button).focus()
        await pilot.pause()

        await pilot.press("right")
        await pilot.pause()
        assert app.focused is screen.query_one("#btn_play_pause", Button)

        await pilot.press("left")
        await pilot.pause()
        assert app.focused is screen.query_one("#btn_previous", Button)

        # wraps at the left edge of the row
        await pilot.press("left")
        await pilot.pause()
        assert app.focused is screen.query_one("#btn_next", Button)

        assert app.client.call_service_calls == []


async def test_stop_key_dispatches(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)

        await pilot.press("s")
        await pilot.pause()

        calls = app.client.call_service_calls
        assert ("media_player", "media_stop", {"entity_id": "media_player.living_room"}) in calls


async def test_left_right_never_dispatch_previous_or_next(make_app):
    # left/right are pure focus navigation now (no previous_track/next_track bindings) —
    # on a volume-only player they just adjust the slider (see
    # test_left_right_still_adjust_volume_slider_value), never a prev/next service call.
    app = make_app(entities=_VOLUME_ONLY_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        screen.query_one("#field_volume", PercentageSlider).focus()
        await pilot.pause()

        await pilot.press("left")
        await pilot.press("right")
        await pilot.pause()

        assert app.client.call_service_calls == []


async def test_source_select_dispatches_select_source(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        screen.query_one("#field_source", Select).value = "TV"
        await pilot.pause()

        assert ("media_player", "select_source", {"entity_id": "media_player.living_room", "source": "TV"}) in (
            app.client.call_service_calls
        )


async def test_sound_mode_select_dispatches_select_sound_mode(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        screen.query_one("#field_sound_mode", Select).value = "Night"
        await pilot.pause()

        calls = app.client.call_service_calls
        assert (
            "media_player",
            "select_sound_mode",
            {"entity_id": "media_player.living_room", "sound_mode": "Night"},
        ) in calls


async def test_shuffle_button_toggles_and_dispatches(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        screen.query_one("#btn_shuffle", Button).press()
        await pilot.pause()

        assert ("media_player", "shuffle_set", {"entity_id": "media_player.living_room", "shuffle": True}) in (
            app.client.call_service_calls
        )
        assert "on" in str(screen.query_one("#btn_shuffle", Button).label)


async def test_repeat_button_cycles_off_all_one(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        screen.query_one("#btn_repeat", Button).press()
        await pilot.pause()
        assert ("media_player", "repeat_set", {"entity_id": "media_player.living_room", "repeat": "all"}) in (
            app.client.call_service_calls
        )

        screen.query_one("#btn_repeat", Button).press()
        await pilot.pause()
        assert ("media_player", "repeat_set", {"entity_id": "media_player.living_room", "repeat": "one"}) in (
            app.client.call_service_calls
        )


async def test_escape_closes_without_dispatching(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, MediaPlayerControlScreen)
        assert app.client.call_service_calls == []


async def test_no_source_player_hides_select_fields(make_app):
    app = make_app(entities=_NO_SOURCE_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        assert len(screen.query("#field_source")) == 0
        assert len(screen.query("#field_sound_mode")) == 0
        assert len(screen.query("#field_volume")) == 0


# ── regression: blank Source/Sound-Mode must not crash the screen on mount ─────────
# `Select.BLANK is False` in the pinned textual version, so passing it as `value=`
# used to raise InvalidSelectValueError as soon as the entity had no current
# source/sound_mode. Fixed by using `Select.NULL` instead.


async def test_missing_source_does_not_crash_shows_blank_select_and_does_not_dispatch(make_app):
    app = make_app(entities=_BLANK_SOURCE_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)

        assert len(screen.query("#field_source")) == 1
        assert len(screen.query("#field_sound_mode")) == 1
        assert screen.query_one("#field_source", Select).value is Select.NULL
        assert screen.query_one("#field_sound_mode", Select).value is Select.NULL
        assert app.client.call_service_calls == []


# ── issue #291: up/down focus navigation (mirrors #286 on light_screen) ────────────


async def test_down_from_volume_slider_navigates_instead_of_adjusting(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        slider = screen.query_one("#field_volume", PercentageSlider)
        slider.focus()
        await pilot.pause()
        start = slider.value

        await pilot.press("down")
        await pilot.pause()

        assert slider.value == start  # unchanged
        assert app.focused is not slider


async def test_left_right_still_adjust_volume_slider_value(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        slider = screen.query_one("#field_volume", PercentageSlider)
        slider.focus()
        await pilot.pause()
        start = slider.value

        await pilot.press("right")
        await pilot.pause()

        assert slider.value == start + 1
        assert app.focused is slider  # left/right never move focus off the slider


async def test_down_enters_transport_row_at_first_button(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        screen.query_one("#field_volume", PercentageSlider).focus()
        await pilot.pause()

        await pilot.press("down")
        await pilot.pause()

        assert app.focused is screen.query_one("#btn_previous", Button)


async def test_down_skips_rest_of_transport_row_as_a_block(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        screen.query_one("#btn_stop", Button).focus()  # a middle button in the row
        await pilot.pause()

        await pilot.press("down")
        await pilot.pause()

        assert enclosing_row(app.focused, media_player_screen._BUTTON_ROW_IDS) is None
        assert app.focused is screen.query_one("#field_source", Select)


async def test_down_enters_toggle_row_at_shuffle_then_skips_out_on_repeat(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        screen.query_one("#field_sound_mode", Select).focus()
        await pilot.pause()

        await pilot.press("down")  # enters the row at the first button
        await pilot.pause()
        assert app.focused is screen.query_one("#btn_shuffle", Button)

        await pilot.press("down")  # already inside the row -> skip the whole block
        await pilot.pause()
        assert enclosing_row(app.focused, media_player_screen._BUTTON_ROW_IDS) is None


async def test_up_from_toggle_row_reaches_field_sound_mode(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        screen.query_one("#btn_repeat", Button).focus()  # last button in the row
        await pilot.pause()

        await pilot.press("up")
        await pilot.pause()

        assert app.focused is screen.query_one("#field_sound_mode", Select)


async def test_source_select_overlay_keeps_its_own_up_down_navigation(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        select = screen.query_one("#field_source", Select)
        select.expanded = True
        await pilot.pause()
        overlay = select.query_one(OptionList)
        assert app.focused is overlay
        start = overlay.highlighted

        await pilot.press("down")
        await pilot.pause()

        assert overlay.highlighted == start + 1  # cursor moved within the overlay
        assert app.focused is overlay  # nav_focus didn't steal focus


async def test_left_right_from_field_source_walks_focus_chain(make_app):
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _open(pilot, app)
        screen.query_one("#field_source", Select).focus()
        await pilot.pause()

        await pilot.press("right")
        await pilot.pause()

        assert app.focused is screen.query_one("#field_sound_mode", Select)
        assert app.client.call_service_calls == []


async def test_question_mark_opens_help_on_media_player_screen(make_app):
    """Issue #7: MediaPlayerControlScreen is a ModalScreen, so the app-level
    `?` binding never reached it — it needed its own question_mark binding."""
    app = make_app(entities=_FULL_MEDIA_PLAYER, config_data=_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open(pilot, app)
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpPopup)
        assert app.screen._pages[app.screen._active_index][0] == "Media Player"
        descriptions = [desc for _, desc in app.screen._binding_rows]
        assert "Close" in descriptions
        assert "Play/Pause" in descriptions
