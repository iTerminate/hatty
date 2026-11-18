# hatty — MIT License. See LICENSE file for details.
"""The collections snapshot handed to the storage save worker must be detached
from the app's live state: save_all runs in an asyncio.to_thread worker, so a
shallow snapshot had it iterating the very dicts the UI mutates —
"dictionary changed size during iteration" (see HACLI._save_config_async)."""

from hatty.main import HACLI


def _app() -> tuple[HACLI, dict]:
    app = HACLI()
    config = {
        "lists": {"living": ["light.a"]},
        "entity_names": {"light.a": "Lamp"},
        "dashboards": {
            "Main": {
                "rows": 1,
                "cols": 1,
                "slots": [
                    {
                        "row": 0,
                        "col": 0,
                        "widget_type": "split",
                        "entity_id": None,
                        "children": {"rows": 1, "cols": 1, "slots": []},
                    }
                ],
            }
        },
        "saved_graphs": {
            "Trend": {
                "entity_ids": ["light.a"],
                "graph_type": "line",
                "hours": 1,
                "colors": {"light.a": "red"},
            }
        },
        "manual_lists": {"living"},
        "notify_lists": {"living"},
        "default_list": "living",
        "default_dashboard": "Main",
    }
    app.app_config = config
    # _apply_config hands the controllers these very objects, and persist()
    # mirrors them back, so the snapshot must copy them — not alias them.
    app.entity_lists = config["lists"]
    app.entity_names = config["entity_names"]
    app.dashboards = config["dashboards"]
    app.saved_graphs = config["saved_graphs"]
    app.manual_lists = config["manual_lists"]
    app.notify_lists = config["notify_lists"]
    return app, config


def test_collections_snapshot_is_detached_from_live_state():
    app, _config = _app()
    snapshot = app._collections_snapshot()

    # Every mutation below is one the UI/controllers can make while a save runs.
    app.entity_lists["added"] = []
    app.entity_lists["living"].append("light.b")
    app.entity_names["light.a"] = "Renamed"
    app.dashboards["Other"] = {"rows": 1, "cols": 1, "slots": []}
    app.dashboards["Main"]["slots"][0]["children"]["slots"].append(
        {"row": 0, "col": 0, "widget_type": "sensor", "entity_id": "sensor.x"}
    )
    app.saved_graphs["Trend"]["colors"]["light.a"] = "blue"
    app.saved_graphs["Other"] = {"entity_ids": []}
    app.manual_lists.add("added")
    app.notify_lists.clear()

    assert snapshot == {
        "lists": {"living": ["light.a"]},
        "entity_names": {"light.a": "Lamp"},
        "dashboards": {
            "Main": {
                "rows": 1,
                "cols": 1,
                "slots": [
                    {
                        "row": 0,
                        "col": 0,
                        "widget_type": "split",
                        "entity_id": None,
                        "children": {"rows": 1, "cols": 1, "slots": []},
                    }
                ],
            }
        },
        "saved_graphs": {
            "Trend": {
                "entity_ids": ["light.a"],
                "graph_type": "line",
                "hours": 1,
                "colors": {"light.a": "red"},
            }
        },
        "manual_lists": {"living"},
        "notify_lists": {"living"},
        "default_list": "living",
        "default_dashboard": "Main",
    }


def test_collections_snapshot_still_drops_temp_dashboards():
    app, _config = _app()
    app.dashboards["living (preview)"] = {"rows": 1, "cols": 1, "slots": []}
    app._temp_dashboard_names.add("living (preview)")

    snapshot = app._collections_snapshot()

    assert set(snapshot["dashboards"]) == {"Main"}
