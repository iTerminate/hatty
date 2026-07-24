# hatty — MIT License. See LICENSE file for details.
"""Unit tests for DashboardController.create_populated (issue #133)."""

from hatty.controllers.dashboards import DashboardController


class _StubApp:
    def __init__(self):
        self.persist_calls = []

    def persist(self, *keys):
        self.persist_calls.append(keys)


def _controller() -> DashboardController:
    return DashboardController(_StubApp())


def test_create_populated_builds_square_grid():
    ctl = _controller()
    name = ctl.create_populated("Office", [f"sensor.s{i}" for i in range(5)])
    assert name == "Office"
    dashboard = ctl.dashboards["Office"]
    # 5 entities -> round(sqrt(5))=2 cols, 3 rows.
    assert (dashboard["rows"], dashboard["cols"]) == (3, 2)
    assert [(s["row"], s["col"]) for s in dashboard["slots"]] == [
        (0, 0), (0, 1), (1, 0), (1, 1), (2, 0),
    ]
    assert ctl.current_dashboard_name == "Office"
    assert ctl._app.persist_calls == [("dashboards",)]


def test_create_populated_maps_widget_types_by_domain():
    ctl = _controller()
    ctl.create_populated("Mixed", ["light.a", "switch.b", "climate.c", "sensor.d"])
    assert [s["widget_type"] for s in ctl.dashboards["Mixed"]["slots"]] == [
        "light",
        "switch",
        "thermostat",
        "sensor",
    ]


def test_create_populated_suffixes_on_collision():
    ctl = _controller()
    assert ctl.create_populated("Office", ["sensor.a"]) == "Office"
    assert ctl.create_populated("Office", ["sensor.b"]) == "Office (2)"
    assert ctl.create_populated("Office", ["sensor.c"]) == "Office (3)"
    assert ctl.dashboards["Office"]["slots"][0]["entity_id"] == "sensor.a"
    assert ctl.dashboard_names == ["Office", "Office (2)", "Office (3)"]
