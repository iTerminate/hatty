# hatty — MIT License. See LICENSE file for details.
"""Demo mode: run hatty fully offline against curated fake data.

Enabled by ``uv run hatty --demo``. The client-side stand-in lives in
``demo_client`` and the dataset/generators in ``demo_data``; ``main.py`` swaps
the demo client in at the ``_client_factory`` seam and boots from
``demo_config()`` instead of loading the user's real config/DB.
"""

from hatty.demo.demo_client import DemoHAClient, demo_client_factory
from hatty.demo.demo_data import demo_collections

__all__ = ["DemoHAClient", "demo_client_factory", "demo_collections", "demo_config"]


def demo_config() -> dict:
    """A full config dict for a demo session: the documented skeleton plus the
    seeded lists/dashboards/saved graphs and dummy (ignored) credentials."""
    from hatty import const
    from hatty.config import default_config

    cfg = default_config()
    cfg["home_assistant"] = {"url": "demo://home-assistant", "token": "demo"}
    cfg["graph_type"] = "line"  # dashboard Graph widgets render as a line, not the block sparkline
    cfg.update(demo_collections())
    # Enable change-alert notifications (#224) — the "Security" list is
    # pre-designated (#24) so it shows up already in use; ntfy stays off (offline).
    cfg[const.CONFIG_KEY_NOTIFICATIONS] = {**const.DEFAULT_NOTIFICATIONS}
    return cfg
