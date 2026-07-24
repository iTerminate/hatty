# hatty — MIT License. See LICENSE file for details.
"""First-run onboarding wizard (issue #72)."""

import yaml

from hatty.main import HACLI
from hatty.ui.entity_table import EntitiesTable
from hatty.ui.onboarding_screen import OnboardingScreen


def _make_app_with_path(tmp_path, fake_client_factory, config_data, filename="config.yaml"):
    config_path = tmp_path / filename
    if config_data is not None:
        config_path.write_text(yaml.safe_dump(config_data))

    app = HACLI(config_path=str(config_path))
    app._client_factory = fake_client_factory()
    return app, config_path


async def test_wizard_shown_when_no_config_file(tmp_path, fake_client_factory):
    app, _ = _make_app_with_path(tmp_path, fake_client_factory, config_data=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, OnboardingScreen)


async def test_wizard_shown_for_placeholder_token(tmp_path, fake_client_factory):
    config_data = {
        "home_assistant": {"url": "http://homeassistant.local:8123", "token": "YOUR_LONG_LIVED_ACCESS_TOKEN"},
        "lists": {},
    }
    app, _ = _make_app_with_path(tmp_path, fake_client_factory, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, OnboardingScreen)


async def test_wizard_not_shown_for_valid_config(tmp_path, fake_client_factory, sample_entities):
    config_data = {
        "home_assistant": {"url": "http://fake.ha.local:8123", "token": "real_token"},
        "lists": {},
    }
    app, _ = _make_app_with_path(tmp_path, fake_client_factory, config_data=config_data)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, OnboardingScreen)
        assert app.query_one(EntitiesTable).row_count == len(sample_entities)


async def test_wizard_save_writes_config_and_starts_client(tmp_path, fake_client_factory, sample_entities):
    app, config_path = _make_app_with_path(tmp_path, fake_client_factory, config_data=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, OnboardingScreen)

        screen.query_one("#onboarding_url").value = "http://myha.local:8123"
        screen.query_one("#onboarding_token").value = "tok123"
        await pilot.pause()
        screen.action_save()
        await pilot.pause()
        await pilot.pause()

        # Config written with a full skeleton + entered credentials.
        saved = yaml.safe_load(config_path.read_text())
        assert saved["home_assistant"] == {"url": "http://myha.local:8123", "token": "tok123"}
        assert "columns" in saved and "dashboards" in saved

        # Client started and the main table is populated.
        assert not isinstance(app.screen, OnboardingScreen)
        assert app.ha_url == "http://myha.local:8123"
        assert app.query_one(EntitiesTable).row_count == len(sample_entities)


async def test_wizard_cancel_leaves_setup_incomplete(tmp_path, fake_client_factory):
    app, config_path = _make_app_with_path(tmp_path, fake_client_factory, config_data=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, OnboardingScreen)
        app.screen.action_cancel()
        await pilot.pause()
        assert not isinstance(app.screen, OnboardingScreen)
        assert "incomplete" in app.sub_title.lower()
        # Nothing was written.
        assert not config_path.exists()


async def test_wizard_save_requires_both_fields(tmp_path, fake_client_factory):
    app, _ = _make_app_with_path(tmp_path, fake_client_factory, config_data=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#onboarding_url").value = "http://myha.local:8123"
        screen.query_one("#onboarding_token").value = ""  # missing
        await pilot.pause()
        screen.action_save()
        await pilot.pause()
        # Still on the wizard; a validation message is shown.
        assert isinstance(app.screen, OnboardingScreen)
        status = str(screen.query_one("#onboarding_status").content)
        assert "token" in status.lower() or "both" in status.lower()


async def test_tab_cycles_fields_without_stopping_on_container(tmp_path, fake_client_factory):
    """Tab should walk url → token → test → save and wrap back to url, never
    landing on the scroll container (#202)."""
    app, _ = _make_app_with_path(tmp_path, fake_client_factory, config_data=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, OnboardingScreen)
        screen.query_one("#onboarding_url").focus()
        await pilot.pause()

        expected = ["onboarding_token", "onboarding_test", "onboarding_save", "onboarding_url"]
        for want in expected:
            await pilot.press("tab")
            await pilot.pause()
            assert app.focused is not None and app.focused.id == want


async def test_enter_in_url_advances_to_token(tmp_path, fake_client_factory):
    """Enter in the URL field moves focus to the token field (#202)."""
    app, _ = _make_app_with_path(tmp_path, fake_client_factory, config_data=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#onboarding_url").focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "onboarding_token"
