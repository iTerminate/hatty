# hatty — MIT License. See LICENSE file for details.
"""A handful of git_sync.py tests against a *real* git binary and a local
bare remote — the unit tests in tests/unit/test_git_sync.py fake _run_git and
prove the argument lists are right; these prove the hardening flags actually
work against real git (identity fallback, ff-only rejection, a genuine
clone-back round trip)."""

import os
import shutil
import subprocess

import pytest

from hatty import git_sync

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.fixture(autouse=True)
def _isolated_git_config(monkeypatch):
    # Never let the developer's (or CI runner's) ~/.gitconfig — commit.gpgsign,
    # pull.rebase, init.defaultBranch, credential.helper — decide the outcome.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)


def _git(*args, cwd) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_init_export_commit_push_clone_back(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    work.mkdir()
    _git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    ok, msg = git_sync.init_repo(str(work))
    assert ok, msg

    (work / "hatty-backup.json").write_text('{"hatty_backup": 1}')
    _git("remote", "add", "origin", str(remote), cwd=work)

    ok, msg = git_sync.commit_and_push(str(work), "initial backup")
    assert ok, msg

    clone = tmp_path / "clone"
    _git("clone", str(remote), str(clone), cwd=tmp_path)
    assert (clone / "hatty-backup.json").exists()


def test_second_push_with_no_changes_is_a_noop(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    work.mkdir()
    _git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git_sync.init_repo(str(work))
    (work / "hatty-backup.json").write_text('{"hatty_backup": 1}')
    _git("remote", "add", "origin", str(remote), cwd=work)
    ok, msg = git_sync.commit_and_push(str(work), "initial")
    assert ok, msg

    log = subprocess.run(["git", "log", "--oneline"], cwd=work, capture_output=True, text=True, check=True)
    commit_count_before = len(log.stdout.splitlines())

    # commit_all itself reports "Nothing to commit" (checked at the unit-test
    # level); at this level what matters is that no *new* commit was created
    # and the push (of an already up-to-date branch) still succeeds.
    ok, msg = git_sync.commit_and_push(str(work), "no changes")
    assert ok, msg

    log = subprocess.run(["git", "log", "--oneline"], cwd=work, capture_output=True, text=True, check=True)
    assert len(log.stdout.splitlines()) == commit_count_before


def test_push_rejected_when_remote_has_diverged(tmp_path):
    remote = tmp_path / "remote.git"
    work_a = tmp_path / "work_a"
    work_b = tmp_path / "work_b"
    work_a.mkdir()
    work_b.mkdir()
    _git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    for work in (work_a, work_b):
        git_sync.init_repo(str(work))
        _git("remote", "add", "origin", str(remote), cwd=work)

    (work_a / "hatty-backup.json").write_text('{"hatty_backup": 1}')
    ok, msg = git_sync.commit_and_push(str(work_a), "first")
    assert ok, msg

    # work_b never pulled work_a's commit -> its push is rejected non-ff.
    (work_b / "other.json").write_text('{"x": 1}')
    ok, msg = git_sync.commit_and_push(str(work_b), "second")
    assert ok is False
    assert msg


def test_commit_succeeds_with_no_identity_configured(tmp_path, monkeypatch):
    # A fresh machine (or CI) may have no git identity at all — commit_all's
    # fallback (-c user.name=hatty -c user.email=...) must still succeed.
    for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(var, raising=False)

    work = tmp_path / "work"
    work.mkdir()
    git_sync.init_repo(str(work))
    (work / "hatty-backup.json").write_text('{"hatty_backup": 1}')

    ok, msg = git_sync.commit_all(str(work), "no identity")
    assert ok, msg
    assert msg == "Committed."


def test_pull_ff_only_success(tmp_path):
    remote = tmp_path / "remote.git"
    work_a = tmp_path / "work_a"
    work_b = tmp_path / "work_b"
    work_a.mkdir()
    _git("init", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    git_sync.init_repo(str(work_a))
    _git("remote", "add", "origin", str(remote), cwd=work_a)
    (work_a / "hatty-backup.json").write_text('{"hatty_backup": 1}')
    ok, msg = git_sync.commit_and_push(str(work_a), "first")
    assert ok, msg

    _git("clone", str(remote), str(work_b), cwd=tmp_path)

    (work_a / "hatty-backup.json").write_text('{"hatty_backup": 2}')
    ok, msg = git_sync.commit_and_push(str(work_a), "second")
    assert ok, msg

    ok, msg = git_sync.pull(str(work_b))
    assert ok, msg
    assert '"hatty_backup": 2' in (work_b / "hatty-backup.json").read_text()
