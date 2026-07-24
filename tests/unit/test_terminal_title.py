# hatty — MIT License. See LICENSE file for details.
from hatty import terminal_title


def test_osc_title_sequence():
    assert terminal_title.osc_title_sequence("hatty") == "\033]2;hatty\007"


def test_apply_writes_escape_and_returns_none_outside_tmux(monkeypatch, capsys):
    monkeypatch.delenv("TMUX", raising=False)
    result = terminal_title.apply("hatty")
    assert result is None
    assert capsys.readouterr().out == "\033]2;hatty\007"


def test_apply_inside_tmux_captures_prior_state_and_renames(monkeypatch, capsys):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
    calls = []

    def fake_run_tmux(args):
        calls.append(args)
        if args[0] == "display-message":
            return "old-window\non\n0"
        return ""

    monkeypatch.setattr(terminal_title, "_run_tmux", fake_run_tmux)

    result = terminal_title.apply("hatty")

    assert result == {"window_name": "old-window", "automatic_rename": "on", "set_titles": "0"}
    assert calls == [
        ["display-message", "-p", "#{window_name}\n#{automatic-rename}\n#{set-titles}"],
        ["set-option", "set-titles", "on"],
        ["rename-window", "hatty"],
    ]
    assert capsys.readouterr().out == "\033]2;hatty\007"


def test_apply_inside_tmux_returns_none_when_capture_fails(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
    monkeypatch.setattr(terminal_title, "_run_tmux", lambda args: None)

    assert terminal_title.apply("hatty") is None


def test_restore_noop_when_prev_is_none(monkeypatch):
    calls = []
    monkeypatch.setattr(terminal_title, "_run_tmux", lambda args: calls.append(args))

    terminal_title.restore(None)

    assert calls == []


def test_restore_noop_outside_tmux(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    calls = []
    monkeypatch.setattr(terminal_title, "_run_tmux", lambda args: calls.append(args))

    terminal_title.restore({"window_name": "old-window", "automatic_rename": "on", "set_titles": "0"})

    assert calls == []


def test_restore_renames_and_resets_automatic_rename_and_set_titles(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,1234,0")
    calls = []
    monkeypatch.setattr(terminal_title, "_run_tmux", lambda args: calls.append(args))

    terminal_title.restore({"window_name": "old-window", "automatic_rename": "on", "set_titles": "0"})

    assert calls == [
        ["rename-window", "old-window"],
        ["set-window-option", "automatic-rename", "on"],
        ["set-option", "set-titles", "0"],
    ]


def test_run_tmux_swallows_missing_binary(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no tmux")

    monkeypatch.setattr(terminal_title.subprocess, "run", fake_run)

    assert terminal_title._run_tmux(["display-message", "-p", "x"]) is None


def test_apply_swallows_stdout_write_errors(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)

    class BrokenStdout:
        def write(self, _text):
            raise OSError("broken pipe")

        def flush(self):
            pass

    monkeypatch.setattr(terminal_title.sys, "stdout", BrokenStdout())

    # Must not raise.
    assert terminal_title.apply("hatty") is None
