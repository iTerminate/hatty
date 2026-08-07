# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.widgets.base import _wants_elapsed


def test_flag_off():
    assert _wants_elapsed({"widget_type": "sensor"}) is False


def test_flag_on_for_sensor():
    assert _wants_elapsed({"widget_type": "sensor", "show_last_changed": True}) is True


def test_flag_on_but_graph_excluded():
    assert _wants_elapsed({"widget_type": "graph", "show_last_changed": True}) is False


def test_flag_on_but_panel_excluded():
    assert _wants_elapsed({"widget_type": "panel", "show_last_changed": True}) is False
