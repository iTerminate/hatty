# hatty — MIT License. See LICENSE file for details.
"""Unit tests for git_sync.py: the _run_git chokepoint, the _explain
classifier, and every public git operation, all driven through a fake
_run_git (cf. tests/unit/test_terminal_title.py's _run_tmux fakes) so no test
here shells out to a real git binary."""

import subprocess

import pytest

from hatty import git_sync

# tests/conftest.py's autouse _no_real_git_calls stubs git_sync._run_git for
# every test (so the acceptance suite never shells out to git); captured here
# at import time, before any monkeypatch has run, so the fixture below can
# restore it for this module, which needs the real chokepoint to exercise its
# own subprocess.run wiring and to let each test install its own fake.
_REAL_RUN_GIT = git_sync._run_git


@pytest.fixture(autouse=True)
def _use_real_run_git(monkeypatch):
    # A parent-conftest autouse fixture is instantiated before a same-scoped
    # one defined in the test module itself, so this runs after (and undoes)
    # tests/conftest.py's stub. Individual tests below still monkeypatch
    # _run_git or subprocess.run themselves as needed.
    monkeypatch.setattr(git_sync, "_run_git", _REAL_RUN_GIT)


# ── _git_env / _run_git ──────────────────────────────────────────────────────


def test_git_env_hardens_prompting_and_strips_editor_vars(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("EDITOR", "vim")
    env = git_sync._git_env()
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_ASKPASS"] == "true"
    assert env["SSH_ASKPASS_REQUIRE"] == "never"
    assert "BatchMode=yes" in env["GIT_SSH_COMMAND"]
    assert "DISPLAY" not in env
    assert "EDITOR" not in env


def test_run_git_missing_binary_returns_no_git_code(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc, out, err = git_sync._run_git(["status"], "/tmp")
    assert rc == git_sync._RC_NO_GIT
    assert out == ""


def test_run_git_timeout_returns_timeout_code(monkeypatch):
    def fake_run(*_args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc, _out, err = git_sync._run_git(["status"], "/tmp")
    assert rc == git_sync._RC_TIMEOUT
    assert "timed out" in err


def test_run_git_passes_hardening_flags_and_never_touches_stdin(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    git_sync._run_git(["status", "--porcelain"], "/tmp")

    assert captured["cmd"][0] == "git"
    assert "-c" in captured["cmd"] and "core.editor=true" in captured["cmd"]
    assert captured["cmd"][-2:] == ["status", "--porcelain"]
    assert captured["kwargs"]["stdin"] == subprocess.DEVNULL
    assert captured["kwargs"]["start_new_session"] is True
    assert captured["kwargs"]["cwd"] == "/tmp"


# ── _explain ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("rc", "out", "err", "expect_contains"),
    [
        (git_sync._RC_NO_GIT, "", "git executable not found", "not installed"),
        (git_sync._RC_TIMEOUT, "", "timed out after 10s", "timed out"),
        (128, "", "fatal: not a git repository (or any of the parent directories)", "Not a git repository"),
        (128, "", "fatal: could not read Username for 'https://example.com'", "credentials"),
        (128, "", "remote: Permission denied (publickey).", "credentials"),
        (1, "", "! [rejected] main -> main (non-fast-forward)", "commits you don't have"),
        (1, "", "CONFLICT (content): Merge conflict in x.json", "Merge conflict"),
        (128, "", "fatal: unable to access: Could not resolve host: example.com", "reach the remote"),
        (1, "", "some other failure line", "some other failure line"),
    ],
)
def test_explain_classifies_common_git_failures(rc, out, err, expect_contains):
    assert expect_contains in git_sync._explain("op", rc, out, err)


def test_explain_truncates_long_unclassified_output():
    err = "x" * 500
    assert len(git_sync._explain("op", 1, "", err)) <= 200


# ── fake _run_git dispatcher for the higher-level functions ────────────────────


class _FakeGit:
    """Dispatches on an args prefix; unmatched calls fail loudly so a test
    that forgets to stub a step doesn't silently pass."""

    def __init__(self, responses: dict[tuple, tuple[int, str, str]]):
        self.responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, args, cwd, timeout=git_sync.LOCAL_TIMEOUT):
        self.calls.append(args)
        for prefix, result in self.responses.items():
            n = len(prefix)
            # Anywhere in args, not just a leading prefix — commit_all prepends
            # -c user.name=... -c user.email=... ahead of "commit" itself.
            if any(tuple(args[i : i + n]) == prefix for i in range(len(args) - n + 1)):
                return result
        raise AssertionError(f"unstubbed git invocation: {args}")


def _install(monkeypatch, responses) -> _FakeGit:
    fake = _FakeGit(responses)
    monkeypatch.setattr(git_sync, "_run_git", fake)
    return fake


# ── repo_info ─────────────────────────────────────────────────────────────────


def test_repo_info_missing_directory():
    info = git_sync.repo_info("/does/not/exist")
    assert info.ok is False
    assert "does not exist" in info.message


def test_repo_info_not_yet_a_repo(monkeypatch, tmp_path):
    _install(monkeypatch, {("rev-parse", "--show-toplevel"): (128, "", "fatal: not a git repository")})
    info = git_sync.repo_info(str(tmp_path))
    assert info.ok is True
    assert info.is_repo is False


def test_repo_info_git_not_installed(monkeypatch, tmp_path):
    _install(monkeypatch, {("rev-parse", "--show-toplevel"): (git_sync._RC_NO_GIT, "", "git executable not found")})
    info = git_sync.repo_info(str(tmp_path))
    assert info.ok is False
    assert "not installed" in info.message


def test_repo_info_inside_another_repo(monkeypatch, tmp_path):
    outer = tmp_path.parent
    _install(monkeypatch, {("rev-parse", "--show-toplevel"): (0, f"{outer}\n", "")})
    info = git_sync.repo_info(str(tmp_path))
    assert info.ok is False
    assert info.is_repo is True
    assert "pick a dedicated directory" in info.message


def test_repo_info_healthy_repo(monkeypatch, tmp_path):
    fake = _install(
        monkeypatch,
        {
            ("rev-parse", "--show-toplevel"): (0, f"{tmp_path}\n", ""),
            ("symbolic-ref",): (0, "main\n", ""),
            ("remote",): (0, "origin\n", ""),
            ("rev-parse", "--abbrev-ref"): (0, "origin/main\n", ""),
            ("status",): (0, "?? untracked.txt\n", ""),
        },
    )
    info = git_sync.repo_info(str(tmp_path))
    assert info.ok is True
    assert info.is_repo is True
    assert info.branch == "main"
    assert info.remote == "origin"
    assert info.upstream == "origin/main"
    assert info.changed == 1
    assert fake.calls[0] == ["rev-parse", "--show-toplevel"]


def test_repo_info_prefers_origin_among_multiple_remotes(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        {
            ("rev-parse", "--show-toplevel"): (0, f"{tmp_path}\n", ""),
            ("symbolic-ref",): (0, "main\n", ""),
            ("remote",): (0, "upstream\norigin\n", ""),
            ("rev-parse", "--abbrev-ref"): (1, "", ""),
            ("status",): (0, "", ""),
        },
    )
    info = git_sync.repo_info(str(tmp_path))
    assert info.remote == "origin"


# ── init_repo ─────────────────────────────────────────────────────────────────


def test_init_repo_missing_directory():
    ok, msg = git_sync.init_repo("/does/not/exist")
    assert ok is False
    assert "does not exist" in msg


def test_init_repo_success(monkeypatch, tmp_path):
    fake = _install(monkeypatch, {("init",): (0, "Initialized empty Git repository", "")})
    ok, msg = git_sync.init_repo(str(tmp_path))
    assert ok is True
    assert "Initialized" in msg
    assert fake.calls[0][0] == "init"


def test_init_repo_falls_back_without_dash_b(monkeypatch, tmp_path):
    calls = []

    def fake(args, cwd, timeout=git_sync.LOCAL_TIMEOUT):
        calls.append(args)
        if "-b" in args:
            return (2, "", "error: unknown switch `b'")
        return (0, "Initialized empty Git repository", "")

    monkeypatch.setattr(git_sync, "_run_git", fake)
    ok, _msg = git_sync.init_repo(str(tmp_path))
    assert ok is True
    assert calls[0] == ["init", "-b", "main"]
    assert calls[1] == ["init"]


# ── commit_all ────────────────────────────────────────────────────────────────


def test_commit_all_nothing_staged_is_ok(monkeypatch, tmp_path):
    _install(monkeypatch, {("add",): (0, "", ""), ("diff",): (0, "", "")})
    ok, msg = git_sync.commit_all(str(tmp_path), "msg")
    assert ok is True
    assert "Nothing to commit" in msg


def test_commit_all_stages_and_commits(monkeypatch, tmp_path):
    fake = _install(
        monkeypatch,
        {
            ("add",): (0, "", ""),
            ("diff",): (1, "", ""),  # something staged
            ("config", "--get", "user.email"): (0, "me@example.com\n", ""),
            ("commit",): (0, "", ""),
        },
    )
    ok, msg = git_sync.commit_all(str(tmp_path), "my message")
    assert ok is True
    assert msg == "Committed."
    commit_call = next(c for c in fake.calls if c[0] == "commit")
    assert commit_call == ["commit", "--no-verify", "--no-gpg-sign", "-m", "my message"]


def test_commit_all_no_commits_yet_falls_back_to_status(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        {
            ("add",): (0, "", ""),
            ("diff",): (128, "", "fatal: ambiguous argument 'HEAD'"),
            ("status",): (0, "", ""),
        },
    )
    ok, msg = git_sync.commit_all(str(tmp_path), "msg")
    assert ok is True
    assert "Nothing to commit" in msg


def test_commit_all_supplies_identity_when_missing(monkeypatch, tmp_path):
    fake = _install(
        monkeypatch,
        {
            ("add",): (0, "", ""),
            ("diff",): (1, "", ""),
            ("config", "--get", "user.email"): (1, "", ""),
            ("commit",): (0, "", ""),
        },
    )
    ok, _msg = git_sync.commit_all(str(tmp_path), "msg")
    assert ok is True
    commit_call = next(c for c in fake.calls if "commit" in c)
    assert "-c" in commit_call and "user.email=hatty@localhost" in commit_call


def test_commit_all_add_failure_is_reported(monkeypatch, tmp_path):
    _install(monkeypatch, {("add",): (128, "", "fatal: pathspec broken")})
    ok, msg = git_sync.commit_all(str(tmp_path), "msg")
    assert ok is False
    assert msg


# ── pull ──────────────────────────────────────────────────────────────────────


def test_pull_no_remote_is_ok(monkeypatch, tmp_path):
    _install(monkeypatch, {("remote",): (0, "", "")})
    ok, msg = git_sync.pull(str(tmp_path))
    assert ok is True
    assert "No git remote" in msg


def test_pull_uses_ff_only_by_default(monkeypatch, tmp_path):
    fake = _install(
        monkeypatch,
        {
            ("remote",): (0, "origin\n", ""),
            ("rev-parse", "--abbrev-ref"): (0, "origin/main\n", ""),
            ("pull",): (0, "", ""),
        },
    )
    ok, _msg = git_sync.pull(str(tmp_path))
    assert ok is True
    pull_call = next(c for c in fake.calls if c[0] == "pull")
    assert "--ff-only" in pull_call
    assert "--rebase" not in pull_call


def test_pull_rebase_option(monkeypatch, tmp_path):
    fake = _install(
        monkeypatch,
        {
            ("remote",): (0, "origin\n", ""),
            ("rev-parse", "--abbrev-ref"): (0, "origin/main\n", ""),
            ("pull",): (0, "", ""),
        },
    )
    git_sync.pull(str(tmp_path), rebase=True)
    pull_call = next(c for c in fake.calls if c[0] == "pull")
    assert "--rebase" in pull_call
    assert "--autostash" in pull_call


def test_pull_without_upstream_passes_explicit_remote_and_branch(monkeypatch, tmp_path):
    fake = _install(
        monkeypatch,
        {
            ("remote",): (0, "origin\n", ""),
            ("rev-parse", "--abbrev-ref"): (1, "", ""),  # no upstream configured
            ("symbolic-ref",): (0, "main\n", ""),
            ("pull",): (0, "", ""),
        },
    )
    git_sync.pull(str(tmp_path))
    pull_call = next(c for c in fake.calls if c[0] == "pull")
    assert pull_call[-2:] == ["origin", "main"]


def test_pull_failure_is_explained(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        {
            ("remote",): (0, "origin\n", ""),
            ("rev-parse", "--abbrev-ref"): (0, "origin/main\n", ""),
            ("pull",): (1, "", "fatal: Could not resolve host: example.com"),
        },
    )
    ok, msg = git_sync.pull(str(tmp_path))
    assert ok is False
    assert "reach the remote" in msg


# ── push ──────────────────────────────────────────────────────────────────────


def test_push_no_remote_is_ok(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        {("remote",): (0, "", ""), ("symbolic-ref",): (0, "main\n", "")},
    )
    ok, msg = git_sync.push(str(tmp_path))
    assert ok is True
    assert "committed locally only" in msg


def test_push_no_commits_yet(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        {
            ("remote",): (0, "origin\n", ""),
            ("symbolic-ref",): (1, "", ""),
            ("rev-parse", "--short"): (1, "", ""),
        },
    )
    ok, msg = git_sync.push(str(tmp_path))
    assert ok is False
    assert "No commits yet" in msg


def test_push_adds_dash_u_when_no_upstream(monkeypatch, tmp_path):
    fake = _install(
        monkeypatch,
        {
            ("remote",): (0, "origin\n", ""),
            ("symbolic-ref",): (0, "main\n", ""),
            ("rev-parse", "--abbrev-ref"): (1, "", ""),
            ("push",): (0, "", ""),
        },
    )
    ok, _msg = git_sync.push(str(tmp_path))
    assert ok is True
    push_call = next(c for c in fake.calls if c[0] == "push")
    assert "-u" in push_call
    assert push_call[-2:] == ["origin", "HEAD:refs/heads/main"]


def test_push_omits_dash_u_when_upstream_tracked(monkeypatch, tmp_path):
    fake = _install(
        monkeypatch,
        {
            ("remote",): (0, "origin\n", ""),
            ("symbolic-ref",): (0, "main\n", ""),
            ("rev-parse", "--abbrev-ref"): (0, "origin/main\n", ""),
            ("push",): (0, "", ""),
        },
    )
    git_sync.push(str(tmp_path))
    push_call = next(c for c in fake.calls if c[0] == "push")
    assert "-u" not in push_call


def test_push_rejected_non_fast_forward(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        {
            ("remote",): (0, "origin\n", ""),
            ("symbolic-ref",): (0, "main\n", ""),
            ("rev-parse", "--abbrev-ref"): (0, "origin/main\n", ""),
            ("push",): (1, "", "! [rejected] main -> main (non-fast-forward)"),
        },
    )
    ok, msg = git_sync.push(str(tmp_path))
    assert ok is False
    assert "commits you don't have" in msg


# ── commit_and_push ───────────────────────────────────────────────────────────


def test_commit_and_push_stops_after_failed_commit(monkeypatch, tmp_path):
    fake = _install(monkeypatch, {("add",): (128, "", "fatal: broken")})
    ok, msg = git_sync.commit_and_push(str(tmp_path), "msg")
    assert ok is False
    assert msg
    assert not any(c[0] == "push" for c in fake.calls)


def test_commit_and_push_happy_path(monkeypatch, tmp_path):
    _install(
        monkeypatch,
        {
            ("add",): (0, "", ""),
            ("diff",): (1, "", ""),
            ("config", "--get", "user.email"): (0, "me@example.com\n", ""),
            ("commit",): (0, "", ""),
            ("remote",): (0, "origin\n", ""),
            ("symbolic-ref",): (0, "main\n", ""),
            ("rev-parse", "--abbrev-ref"): (0, "origin/main\n", ""),
            ("push",): (0, "", ""),
        },
    )
    ok, msg = git_sync.commit_and_push(str(tmp_path), "msg")
    assert ok is True
    assert "Pushed" in msg


def test_commit_and_push_never_pulls_first(monkeypatch, tmp_path):
    # A conflict at quit time is the worst possible moment; the next start's
    # pull handles a diverged remote instead.
    fake = _install(
        monkeypatch,
        {
            ("add",): (0, "", ""),
            ("diff",): (1, "", ""),
            ("config", "--get", "user.email"): (0, "me@example.com\n", ""),
            ("commit",): (0, "", ""),
            ("remote",): (0, "origin\n", ""),
            ("symbolic-ref",): (0, "main\n", ""),
            ("rev-parse", "--abbrev-ref"): (0, "origin/main\n", ""),
            ("push",): (0, "", ""),
        },
    )
    git_sync.commit_and_push(str(tmp_path), "msg")
    assert not any(c[0] == "pull" for c in fake.calls)


# ── default_commit_message ───────────────────────────────────────────────────


def test_default_commit_message_format():
    from datetime import datetime

    msg = git_sync.default_commit_message(datetime(2026, 8, 19, 14, 3, 11))
    assert msg == "hatty backup 2026-08-19 14:03:11"
