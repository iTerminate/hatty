# hatty — MIT License. See LICENSE file for details.
"""DashboardScreen as a third LogbookController host (app.log_ctl), alongside
HACLI's docked panel and GraphPreviewScreen's — issue #38's "matter of
wiring" third host. Unlike GraphPreviewScreen, the dashboard log is live, so
the singleton WS subscription can be shared between the main screen's panel
(left `-visible` behind a pushed dashboard) and the dashboard's own."""

from textual.widgets import Label, Log, OptionList

from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.confirm_popup import ConfirmPopup
from hatty.ui.dashboard.slot_popup import DashboardSlotPopup
from hatty.ui.log_scope_popup import LogScopePopup
from tests.conftest import make_config

_DASHBOARD_CONFIG = {
    **make_config(),
    "lists": {},
    "dashboards": {
        "Main": {
            "rows": 1,
            "cols": 2,
            "slots": [
                {"row": 0, "col": 0, "widget_type": "switch", "entity_id": "switch.fan"},
                {
                    "row": 0,
                    "col": 1,
                    "widget_type": "panel",
                    "entity_id": None,
                    "entity_ids": ["light.living_room_lamp", "light.kitchen_light"],
                },
            ],
        }
    },
}


def _panel(app) -> ActivityLogPanel:
    return app.screen.query_one("#dashboard_log_panel", ActivityLogPanel)


async def test_a_with_no_entities_on_the_dashboard_notifies_and_stays_hidden(make_app, open_dashboard):
    config = {**make_config(), "lists": {}, "dashboards": {"Main": {"rows": 1, "cols": 1, "slots": []}}}
    app = make_app(config_data=config)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("a")
        await pilot.pause()
        assert not _panel(app).has_class("-visible")


async def test_a_opens_dashboard_log_scoped_to_the_whole_dashboard_and_a_again_closes_it(make_app, open_dashboard):
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("a")
        await pilot.pause()

        panel = _panel(app)
        assert panel.has_class("-visible")
        title = str(panel.query_one("#log_title", Label).content)
        assert "Main" in title
        # dashboard_entity_ids: the switch's own entity_id, plus the panel's entity_ids.
        assert app.client.logbook_calls[-1][0] == [
            "switch.fan",
            "light.living_room_lamp",
            "light.kitchen_light",
        ]

        await pilot.press("a")
        await pilot.pause()
        assert not panel.has_class("-visible")
        assert app.log_ctl.session_for(app.screen) is None


async def test_a_in_edit_mode_opens_the_slot_popup_not_the_log(make_app, open_dashboard):
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("E")  # edit mode
        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, DashboardSlotPopup)


async def test_entering_edit_mode_closes_an_open_log(make_app, open_dashboard):
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        screen = app.screen
        await pilot.press("a")
        await pilot.pause()
        assert app.log_ctl.is_open(screen)

        await pilot.press("E")
        await pilot.pause()
        assert not app.log_ctl.is_open(screen)
        assert not _panel(app).has_class("-visible")


async def test_v_opens_the_log_scope_popup_with_four_options(make_app, open_dashboard):
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("a", "v")
        await pilot.pause()
        assert isinstance(app.screen, LogScopePopup)
        options = app.screen.query_one("#log_scope_options", OptionList)
        assert options.option_count == 4


async def test_f_maximizes_then_arrows_page_instead_of_moving_the_grid_cursor(make_app, open_dashboard):
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        screen = app.screen
        cursor_before = (screen.cursor_row, screen.cursor_col)

        await pilot.press("a")
        await pilot.pause()
        session = app.log_ctl.session_for(screen)
        assert session.end is None

        await pilot.press("f")
        await pilot.pause()
        panel = _panel(app)
        assert panel.has_class("-maximized")

        await pilot.press("left")
        await pilot.press("left")
        await pilot.pause()
        paged_back_end = app.log_ctl.session_for(screen).end
        assert paged_back_end is not None
        assert (screen.cursor_row, screen.cursor_col) == cursor_before  # grid cursor untouched

        await pilot.press("right")
        await pilot.pause()
        assert app.log_ctl.session_for(screen).end > paged_back_end
        assert (screen.cursor_row, screen.cursor_col) == cursor_before


async def test_bracket_keys_page_while_docked_and_leave_the_cursor_alone(make_app, open_dashboard):
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        screen = app.screen
        await pilot.press("right")  # move the grid cursor onto the panel slot
        await pilot.pause()
        cursor_before = (screen.cursor_row, screen.cursor_col)
        assert cursor_before == (0, 1)

        await pilot.press("a")
        await pilot.pause()
        assert app.log_ctl.session_for(screen).end is None

        await pilot.press("[")
        await pilot.press("[")
        await pilot.pause()
        paged_back_end = app.log_ctl.session_for(screen).end
        assert paged_back_end is not None
        assert (screen.cursor_row, screen.cursor_col) == cursor_before  # not moved by paging

        await pilot.press("]")
        await pilot.pause()
        assert app.log_ctl.session_for(screen).end > paged_back_end
        assert (screen.cursor_row, screen.cursor_col) == cursor_before


async def test_escape_ladder_unmaximizes_then_closes_the_log_then_confirms_leaving(make_app, open_dashboard):
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        screen = app.screen
        await pilot.press("a")
        await pilot.press("f")
        await pilot.pause()
        panel = _panel(app)
        assert panel.has_class("-maximized")

        await pilot.press("escape")
        await pilot.pause()
        # Still open, just restored to normal width — mirrors the main screen/graph.
        assert app.screen is screen
        assert panel.has_class("-visible")
        assert not panel.has_class("-maximized")

        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is screen
        assert not app.log_ctl.is_open(screen)

        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmPopup)


async def test_live_logbook_event_appends_while_dashboard_log_open(make_app, open_dashboard):
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        await pilot.press("a")
        await pilot.pause()

        log_widget = _panel(app).query_one("#log_widget", Log)
        count_before = log_widget.line_count

        app.client.inject_logbook_event(
            [{"when": "2024-01-15T10:32:00+00:00", "name": "Fan Switch", "state": "off"}]
        )
        await pilot.pause()
        assert log_widget.line_count > count_before


async def test_dashboard_log_takes_over_the_live_subscription_and_hands_it_back(make_app, open_dashboard):
    """Pushing the dashboard doesn't close the main screen's log — both stay
    `-visible` — so the singleton WS subscription must follow whichever is
    on top, and come back when the dashboard's log closes."""
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")  # main screen's activity log
        await pilot.pause()
        main_session = app.log_ctl.session_for(app)
        assert app.client.subscribe_logbook_calls[-1][0] == main_session.query_ids

        await open_dashboard(pilot)
        screen = app.screen
        await pilot.press("a")  # dashboard's own log
        await pilot.pause()
        dash_session = app.log_ctl.session_for(screen)
        assert app.client.subscribe_logbook_calls[-1][0] == dash_session.query_ids
        assert app.log_ctl.live_session() is dash_session

        await pilot.press("a")  # close the dashboard's log
        await pilot.pause()
        assert app.client.subscribe_logbook_calls[-1][0] == main_session.query_ids
        assert app.log_ctl.live_session() is main_session


async def test_leaving_the_dashboard_closes_its_log_and_releases_the_subscription(make_app, open_dashboard):
    app = make_app(config_data=_DASHBOARD_CONFIG)
    async with app.run_test() as pilot:
        await open_dashboard(pilot)
        screen = app.screen
        await pilot.press("a")
        await pilot.pause()
        assert app.log_ctl.is_open(screen)
        assert app.client.logbook_subscription_id is not None

        await pilot.press("escape")  # closes the log (docked, not maximized)
        await pilot.pause()
        await pilot.press("escape")  # "Leave dashboard?" confirm
        await pilot.pause()
        assert isinstance(app.screen, ConfirmPopup)
        await pilot.press("y")
        await pilot.pause()

        assert app.log_ctl.is_open(screen) is False
        assert app.client.logbook_subscription_id is None
