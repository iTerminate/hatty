# hatty — MIT License. See LICENSE file for details.
"""Set the terminal/tmux window title while hatty is running (issue: set tmux
title to hatty or pref). Two layers:

- An OSC 2 escape sequence, understood by essentially every terminal emulator
  and also picked up by tmux as the pane's `#{pane_title}`.
- When running inside tmux (`$TMUX` set), an explicit `tmux rename-window` call
  as well, since the status-bar *window name* tmux shows by default doesn't
  track the OSC title unless `automatic-rename` happens to be configured for
  it. tmux's `set-titles` session option also defaults to *off*, which means
  none of the above ever reaches the outer terminal emulator's actual tab/
  window title regardless of pane_title or window name — so apply() also
  turns `set-titles` on for the current session. `apply()` captures the
  window's prior name plus the `automatic-rename`/`set-titles` settings so
  `restore()` can put all three back on exit.

All tmux interaction is best-effort: a missing `tmux` binary, a timeout, or any
other subprocess failure is swallowed rather than raised, since a title cosmetic
must never break app startup or shutdown.
"""

import os
import subprocess
import sys

_TMUX_TIMEOUT = 1.0


def osc_title_sequence(title: str) -> str:
    """The OSC 2 'set window title' escape sequence for `title`."""
    return f"\033]2;{title}\007"


def _run_tmux(args: list[str]) -> str | None:
    """Run `tmux <args>`, returning stripped stdout, or None on any failure."""
    try:
        result = subprocess.run(
            ["tmux", *args],
            capture_output=True,
            text=True,
            timeout=_TMUX_TIMEOUT,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def apply(title: str) -> dict | None:
    """Set the terminal (and, if applicable, tmux) title to `title`. Returns a
    dict of prior tmux state for restore() to undo on exit, or None when not
    running inside tmux (or the prior state couldn't be captured)."""
    try:
        sys.stdout.write(osc_title_sequence(title))
        sys.stdout.flush()
    except Exception:
        pass

    if not os.environ.get("TMUX"):
        return None

    prior = _run_tmux(["display-message", "-p", "#{window_name}\n#{automatic-rename}\n#{set-titles}"])
    if prior is None:
        return None
    lines = prior.split("\n")
    if len(lines) < 3:
        return None
    prev_window_name, prev_automatic_rename, prev_set_titles = lines[0], lines[1], lines[2]

    # set-titles is what actually pushes a title out to the enclosing terminal
    # emulator's tab/window chrome; tmux defaults it to off, so without this the
    # rename-window below only ever shows up in tmux's own status line.
    _run_tmux(["set-option", "set-titles", "on"])
    _run_tmux(["rename-window", title])

    return {
        "window_name": prev_window_name,
        "automatic_rename": prev_automatic_rename,
        "set_titles": prev_set_titles,
    }


def restore(prev: dict | None) -> None:
    """Undo apply()'s tmux changes, restoring the window name, automatic-rename,
    and set-titles settings it captured. A no-op when `prev` is None (not in
    tmux, or nothing was captured)."""
    if prev is None or not os.environ.get("TMUX"):
        return
    window_name = prev.get("window_name")
    if window_name:
        _run_tmux(["rename-window", window_name])
    automatic_rename = prev.get("automatic_rename")
    if automatic_rename:
        _run_tmux(["set-window-option", "automatic-rename", automatic_rename])
    set_titles = prev.get("set_titles")
    if set_titles is not None:
        _run_tmux(["set-option", "set-titles", set_titles])
