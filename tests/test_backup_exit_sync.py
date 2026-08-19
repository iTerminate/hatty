# hatty — MIT License. See LICENSE file for details.
"""Acceptance tests for the exit-time git sync (HACLI.action_quit +
ExitSyncScreen): quitting with commit_on_exit set runs the export + git
commit before the app actually exits, quitting with no backup configured
never touches git, and escape on the overlay skips a slow sync instead of
trapping the user."""

import asyncio

import pytest

from hatty import git_sync
from hatty.ui.exit_sync_screen import ExitSyncScreen
from tests.conftest import make_config


@pytest.fixture
def git_spy(monkeypatch):
    """Overrides tests/conftest.py's blanket _no_real_git_calls stub with one
    that also records every invocation, so these tests can assert on it."""
    calls = []

    def fake(args, cwd, timeout=None):
        calls.append(args)
        if args[:3] == ["diff", "--cached", "--quiet"]:
            return (1, "", "")  # rc 1 = something staged, so commit_all proceeds
        if args[0] == "remote":
            return (0, "origin\n", "")  # a configured remote, so push actually runs
        if args[:2] == ["symbolic-ref", "--quiet"]:
            return (0, "main\n", "")
        return (0, "", "")

    monkeypatch.setattr(git_sync, "_run_git", fake)
    return calls


def _backup_config(path, **overrides):
    return {
        **make_config(),
        "backup": {
            "path": str(path),
            "git_enabled": True,
            "sections": ["lists"],
            **overrides,
        },
    }


async def test_commit_on_exit_runs_git_before_quitting(make_app, git_spy, tmp_path):
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    app = make_app(config_data=_backup_config(backup_dir, commit_on_exit=True))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        await pilot.pause()

    assert any(c[0] == "add" for c in git_spy)
    assert any("commit" in c for c in git_spy)
    assert not any(c[0] == "push" for c in git_spy)  # commit_on_exit alone never pushes
    assert app._exit_sync_done is True
    assert app._exit is True


async def test_push_on_exit_also_pushes(make_app, git_spy, tmp_path):
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    app = make_app(config_data=_backup_config(backup_dir, push_on_exit=True))

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        await pilot.pause()

    assert any("commit" in c for c in git_spy)
    assert any(c[0] == "push" for c in git_spy)


async def test_no_backup_configured_quits_without_touching_git(make_app, git_spy):
    app = make_app(config_data=make_config())

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()

    assert git_spy == []
    assert app._exit is True


async def test_escape_skips_a_slow_sync_and_quits_immediately(make_app, tmp_path, monkeypatch):
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    app = make_app(config_data=_backup_config(backup_dir, commit_on_exit=True))

    async def _slow_sync(timeout=75.0):
        await asyncio.sleep(10)
        return True, "done"

    async with app.run_test() as pilot:
        await pilot.pause()
        monkeypatch.setattr(app.backup_ctl, "sync_on_exit", _slow_sync)

        await pilot.press("ctrl+q")
        await pilot.pause()
        assert isinstance(app.screen, ExitSyncScreen)

        await pilot.press("escape")
        await pilot.pause()

    # Reaching here (well under the 10s sync) proves escape didn't wait for it.
    assert app._exit is True
