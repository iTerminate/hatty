# hatty — MIT License. See LICENSE file for details.
"""Unit tests for the pure device_info_rows helper (issue #151)."""

from hatty.ui.device_tree_screen import device_info_rows

AREAS = [{"area_id": "lr", "name": "Living Room"}]
DEVICES = [
    {
        "id": "hub",
        "name": "Hub",
        "manufacturer": "Acme",
        "model": "H1",
    },
    {
        "id": "dev_lamp",
        "name": "Lamp",
        "name_by_user": "Reading Lamp",
        "manufacturer": "Acme",
        "model": "L100",
        "sw_version": "1.2.3",
        "hw_version": "rev-B",
        "area_id": "lr",
        "via_device_id": "hub",
    },
]


def _rows_dict(rows):
    return dict(rows)


def test_full_device_all_fields_present():
    rows = device_info_rows(DEVICES[1], AREAS, DEVICES, entity_count=3)
    d = _rows_dict(rows)
    assert d["Name"] == "Reading Lamp (was: Lamp)"
    assert d["Manufacturer"] == "Acme"
    assert d["Model"] == "L100"
    assert d["SW version"] == "1.2.3"
    assert d["HW version"] == "rev-B"
    assert d["Area"] == "Living Room"
    assert d["Entities"] == "3"
    assert d["Via device"] == "Hub"


def test_sparse_device_omits_empty_rows():
    sparse = {"id": "d", "name": "Bare"}
    rows = device_info_rows(sparse, AREAS, DEVICES, entity_count=0)
    labels = [label for label, _ in rows]
    # Only Name and the always-present Entities count survive.
    assert labels == ["Name", "Entities"]
    assert _rows_dict(rows)["Name"] == "Bare"


def test_name_without_rename_shows_plain_name():
    rows = device_info_rows(DEVICES[0], AREAS, DEVICES, entity_count=1)
    assert _rows_dict(rows)["Name"] == "Hub"
    # No via_device / area for the hub.
    assert "Via device" not in _rows_dict(rows)
    assert "Area" not in _rows_dict(rows)


def test_unknown_via_device_id_is_omitted():
    dev = {"id": "x", "name": "X", "via_device_id": "ghost"}
    rows = device_info_rows(dev, AREAS, DEVICES, entity_count=0)
    assert "Via device" not in _rows_dict(rows)
