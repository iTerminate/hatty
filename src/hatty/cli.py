# hatty — MIT License. See LICENSE file for details.
"""Console entry point for hatty.

Kept free of Textual imports at module top: the ``--debug`` flag has to set
``TEXTUAL_LOG`` *before* Textual is imported, since ``textual.constants`` reads
that env var into a module-level constant at import time. So the real app
(``hatty.main.HACLI``) is imported lazily inside ``main()``.
"""

import argparse


def main() -> None:
    from hatty import __version__

    parser = argparse.ArgumentParser(description="A Terminal User Interface for Home Assistant.")
    parser.add_argument("-c", "--config", help="Path to the configuration file.")
    parser.add_argument("-V", "--version", action="version", version=f"hatty {__version__}")
    parser.add_argument("--debug", action="store_true", help="Enable Textual debug logging to debug.log.")
    parser.add_argument(
        "--demo", action="store_true", help="Run offline against curated fake data (no Home Assistant needed)."
    )
    args = parser.parse_args()

    if args.debug:
        import os

        os.environ.setdefault("TEXTUAL_LOG", "debug.log")
        os.environ.setdefault("TEXTUAL_LOG_LEVEL", "DEBUG")

    from hatty.main import HACLI  # imported here so TEXTUAL_LOG is set first

    app = HACLI(config_path=args.config, demo=args.demo)
    try:
        app.run()
    finally:
        _flush_pending_exit_sync(app)


def _flush_pending_exit_sync(app) -> None:
    """Last-resort fallback for an exit path that skipped both
    HACLI.action_quit and HACLI._on_exit_app (a real SIGINT, or a panic) —
    runs after app.run() returns, with no event loop, so it calls git_sync's
    plain sync functions directly rather than through their asyncio.to_thread
    wrappers. A save task started just before this path may have been
    abandoned mid-flight, so the pushed data can be one save stale; that's
    unavoidable without an event loop here. Never raises — a failed backup
    sync must not turn into a crash on the way out."""
    if app._exit_sync_done or not app.backup_ctl.exit_sync_pending():
        return
    app._exit_sync_done = True

    from hatty import git_sync

    try:
        ok, msg = app.backup_ctl.export_now()
        if not ok:
            print(f"hatty: backup export failed: {msg}")
            return
        path = app.backup_ctl.prefs.get("path") or ""
        message = git_sync.default_commit_message()
        print("hatty: syncing backup with git…")
        op = git_sync.commit_and_push if app.backup_ctl.prefs.get("push_on_exit") else git_sync.commit_all
        ok, msg = op(path, message)
        print(f"hatty: {msg}")
    except Exception as e:
        print(f"hatty: backup sync failed: {e}")


if __name__ == "__main__":
    main()
