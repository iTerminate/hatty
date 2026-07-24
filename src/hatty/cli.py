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

    HACLI(config_path=args.config, demo=args.demo).run()


if __name__ == "__main__":
    main()
