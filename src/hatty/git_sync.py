# hatty — MIT License. See LICENSE file for details.
"""The git CLI layer for the Backup & Sync feature: pull-on-start and
commit/push-on-exit for the directory `backup.py` writes. Shells out to the
`git` binary — no library dependency — through a single chokepoint
(`_run_git`, mirroring `terminal_title._run_tmux`) so every invocation is
non-interactive and time-bounded: it must never prompt for credentials, open
an editor, or hang the TUI.

Every public function returns `(ok, message)` (or a `RepoInfo`) and never
raises — the `client.probe_connection` / `notifications.send_test_ntfy`
contract, so a config-screen status label or an exit-time overlay can just
display whatever comes back.
"""

import asyncio
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

#: Local, filesystem-only git operations (init, add, commit, status).
LOCAL_TIMEOUT = 10.0
#: Operations that talk to a remote (pull, push).
NETWORK_TIMEOUT = 60.0

#: Outside git's own return-code range, so they're unambiguous in _explain.
_RC_NO_GIT = -101
_RC_TIMEOUT = -102

# Applied to every invocation: core.editor=true makes an editor launch exit 0
# instantly instead of blocking on a TTY; commit.gpgsign=false stops a passphrase
# prompt from hanging the TUI; gc.auto=0 avoids a slow background gc mid-timing.
_GLOBAL_FLAGS = [
    "-c",
    "core.editor=true",
    "-c",
    "core.pager=cat",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "gc.auto=0",
]


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",  # no username/password TTY prompt; error instead
            "GIT_ASKPASS": "true",  # ...and no askpass fallback
            "SSH_ASKPASS": "true",
            "SSH_ASKPASS_REQUIRE": "never",
            "GIT_SSH_COMMAND": ("ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"),
            "GIT_PAGER": "cat",
            "GIT_OPTIONAL_LOCKS": "0",  # `status` won't block on index.lock
            "LC_ALL": "C",  # stable stderr strings for _explain()
        }
    )
    for var in ("DISPLAY", "WAYLAND_DISPLAY", "GIT_EDITOR", "EDITOR", "VISUAL"):
        env.pop(var, None)  # no GUI askpass window, no terminal editor
    return env


def _run_git(args: list[str], cwd: str, timeout: float = LOCAL_TIMEOUT) -> tuple[int, str, str]:
    """THE chokepoint every git invocation goes through. Unit tests monkeypatch
    this one function (cf. `terminal_title._run_tmux`) and assert on the
    recorded argument lists."""
    try:
        p = subprocess.run(
            ["git", *_GLOBAL_FLAGS, *args],
            cwd=cwd,
            env=_git_env(),
            stdin=subprocess.DEVNULL,  # git can never steal the TUI's stdin
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            start_new_session=True,  # own process group: no controlling TTY
        )
    except FileNotFoundError:
        return (_RC_NO_GIT, "", "git executable not found")
    except subprocess.TimeoutExpired:
        return (_RC_TIMEOUT, "", f"timed out after {timeout:g}s")
    except OSError as e:
        return (_RC_NO_GIT, "", str(e))
    return (p.returncode, p.stdout, p.stderr)


def _explain(op: str, rc: int, out: str, err: str) -> str:
    if rc == _RC_NO_GIT:
        return "git is not installed (or not on PATH)."
    if rc == _RC_TIMEOUT:
        return f"git {op} timed out."
    text = f"{out}\n{err}".lower()
    if "not a git repository" in text:
        return "Not a git repository."
    auth_markers = (
        "could not read username",
        "authentication failed",
        "permission denied (publickey",
        "terminal prompts disabled",
    )
    if any(s in text for s in auth_markers):
        return "git rejected the credentials, and hatty can't prompt. Set up an SSH key or a credential helper."
    if any(s in text for s in ("non-fast-forward", "updates were rejected", "fetch first")):
        return "The remote has commits you don't have. Pull first, or resolve it manually."
    if any(s in text for s in ("conflict", "automatic merge failed", "needs merge")):
        return "Merge conflict — resolve it with git, then sync again."
    if any(s in text for s in ("could not resolve host", "connection timed out", "network is unreachable")):
        return "Could not reach the remote."
    first_line = next((line for line in (*err.splitlines(), *out.splitlines()) if line.strip()), None)
    return (first_line or f"git {op} failed (exit {rc}).")[:200]


def default_commit_message(now: datetime | None = None) -> str:
    return f"hatty backup {(now or datetime.now()):%Y-%m-%d %H:%M:%S}"


def _current_branch(cwd: str) -> str:
    rc, out, _err = _run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd)
    if rc == 0:
        return out.strip()
    rc, out, _err = _run_git(["rev-parse", "--short", "HEAD"], cwd)
    return out.strip() if rc == 0 else ""


def _primary_remote(cwd: str) -> str:
    rc, out, _err = _run_git(["remote"], cwd)
    if rc != 0:
        return ""
    remotes = [r.strip() for r in out.splitlines() if r.strip()]
    if not remotes:
        return ""
    return "origin" if "origin" in remotes else remotes[0]


def _upstream(cwd: str) -> str:
    rc, out, _err = _run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd)
    return out.strip() if rc == 0 else ""


def _changed_count(cwd: str) -> int:
    rc, out, _err = _run_git(["status", "--porcelain", "--untracked-files=all"], cwd)
    if rc != 0:
        return 0
    return len([line for line in out.splitlines() if line.strip()])


def _identity_flags(cwd: str) -> list[str]:
    """A fresh machine (or CI) with no git identity configured fails commit
    with "Please tell me who you are" — supply a fallback, but never override
    an identity the user already has."""
    rc, out, _err = _run_git(["config", "--get", "user.email"], cwd)
    if rc == 0 and out.strip():
        return []
    return ["-c", "user.name=hatty", "-c", "user.email=hatty@localhost"]


@dataclass(frozen=True)
class RepoInfo:
    ok: bool
    message: str
    installed: bool = False
    is_repo: bool = False
    root: str = ""
    branch: str = ""
    remote: str = ""
    upstream: str = ""
    changed: int = 0


def repo_info(path: str) -> RepoInfo:
    p = Path(path)
    if not p.is_dir():
        return RepoInfo(ok=False, message=f"{path} does not exist.")
    cwd = str(p)
    rc, out, err = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if rc == _RC_NO_GIT:
        return RepoInfo(ok=False, message=_explain("check", rc, out, err))
    if rc != 0:
        return RepoInfo(ok=True, installed=True, is_repo=False, message="Not a git repository yet.")

    root = out.strip()
    # --is-inside-work-tree would say True for a directory merely *inside* the
    # user's dotfiles repo, silently committing there — compare roots instead.
    if os.path.realpath(root) != os.path.realpath(cwd):
        return RepoInfo(
            ok=False,
            installed=True,
            is_repo=True,
            root=root,
            message=f"{path} is inside the repository at {root} — pick a dedicated directory.",
        )

    branch = _current_branch(cwd)
    remote = _primary_remote(cwd)
    upstream = _upstream(cwd)
    changed = _changed_count(cwd)
    summary = f"{branch or '(no commits yet)'} · {changed} changed" if branch or changed else "No commits yet."
    return RepoInfo(
        ok=True,
        installed=True,
        is_repo=True,
        root=root,
        branch=branch,
        remote=remote,
        upstream=upstream,
        changed=changed,
        message=summary,
    )


def init_repo(path: str) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_dir():
        return False, f"{path} does not exist."
    cwd = str(p)
    rc, out, err = _run_git(["init", "-b", "main"], cwd)
    if rc != 0:
        rc, out, err = _run_git(["init"], cwd)  # older git without -b
    if rc != 0:
        return False, _explain("init", rc, out, err)
    return True, f"Initialized a git repository in {path}."


def commit_all(path: str, message: str) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_dir():
        return False, f"{path} does not exist."
    cwd = str(p)

    rc, out, err = _run_git(["add", "-A", "--", "."], cwd)
    if rc != 0:
        return False, _explain("add", rc, out, err)

    rc, _out, _err = _run_git(["diff", "--cached", "--quiet", "--"], cwd)
    if rc == 0:
        return True, "Nothing to commit — export is already up to date."
    if rc not in (0, 1):
        # No commits yet (or another diff failure) — fall back to status.
        rc2, status_out, _err2 = _run_git(["status", "--porcelain"], cwd)
        if rc2 == 0 and not status_out.strip():
            return True, "Nothing to commit — export is already up to date."

    args = [*_identity_flags(cwd), "commit", "--no-verify", "--no-gpg-sign", "-m", message]
    rc, out, err = _run_git(args, cwd)
    if rc != 0:
        return False, _explain("commit", rc, out, err)
    return True, "Committed."


def pull(path: str, *, rebase: bool = False) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_dir():
        return False, f"{path} does not exist."
    cwd = str(p)

    remote = _primary_remote(cwd)
    if not remote:
        return True, "No git remote configured; nothing to pull."

    args = ["pull", "--rebase", "--autostash"] if rebase else ["pull", "--ff-only", "--no-edit"]
    args += ["--no-stat", "--no-tags"]
    if not _upstream(cwd):
        args += [remote, _current_branch(cwd) or "HEAD"]
    rc, out, err = _run_git(args, cwd, timeout=NETWORK_TIMEOUT)
    if rc != 0:
        return False, _explain("pull", rc, out, err)
    return True, "Pulled the latest changes."


def push(path: str) -> tuple[bool, str]:
    p = Path(path)
    if not p.is_dir():
        return False, f"{path} does not exist."
    cwd = str(p)

    remote = _primary_remote(cwd)
    if not remote:
        return True, "No git remote configured; committed locally only."
    branch = _current_branch(cwd)
    if not branch:
        return False, "No commits yet — nothing to push."

    args = ["push", "--porcelain"]
    if not _upstream(cwd):
        args.append("-u")
    args += [remote, f"HEAD:refs/heads/{branch}"]
    rc, out, err = _run_git(args, cwd, timeout=NETWORK_TIMEOUT)
    if rc != 0:
        return False, _explain("push", rc, out, err)
    return True, "Pushed to the remote."


def commit_and_push(path: str, message: str) -> tuple[bool, str]:
    # Deliberately no pull first — a conflict at quit time is the worst
    # possible moment; the next start's pull handles a diverged remote.
    ok, msg = commit_all(path, message)
    if not ok:
        return False, msg
    return push(path)


async def repo_info_async(path: str) -> RepoInfo:
    return await asyncio.to_thread(repo_info, path)


async def init_repo_async(path: str) -> tuple[bool, str]:
    return await asyncio.to_thread(init_repo, path)


async def commit_all_async(path: str, message: str) -> tuple[bool, str]:
    return await asyncio.to_thread(commit_all, path, message)


async def pull_async(path: str, *, rebase: bool = False) -> tuple[bool, str]:
    return await asyncio.to_thread(pull, path, rebase=rebase)


async def push_async(path: str) -> tuple[bool, str]:
    return await asyncio.to_thread(push, path)


async def commit_and_push_async(path: str, message: str) -> tuple[bool, str]:
    return await asyncio.to_thread(commit_and_push, path, message)
