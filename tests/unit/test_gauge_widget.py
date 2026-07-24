# hatty — MIT License. See LICENSE file for details.
from hatty.ui.dashboard.widgets.gauge import gauge_level_class, resolve_gauge_bounds


def test_bounds_default_to_percentage():
    assert resolve_gauge_bounds(None, None, {}) == (0.0, 100.0)


def test_bounds_from_entity_attrs():
    assert resolve_gauge_bounds(None, None, {"min": -10, "max": 10}) == (-10.0, 10.0)


def test_slot_override_beats_entity_attrs():
    assert resolve_gauge_bounds(5, 50, {"min": -10, "max": 10}) == (5.0, 50.0)


def test_partial_override_mixes_with_attrs():
    assert resolve_gauge_bounds(None, 50, {"min": 20}) == (20.0, 50.0)


def test_inverted_bounds_fall_back_to_default():
    assert resolve_gauge_bounds(100, 0, {}) == (0.0, 100.0)


def test_garbage_attr_bounds_fall_back_to_default():
    assert resolve_gauge_bounds(None, None, {"min": "low", "max": "high"}) == (0.0, 100.0)


def test_level_classes():
    assert gauge_level_class(10, 0, 100) == "-low"
    assert gauge_level_class(30, 0, 100) == "-mid"
    assert gauge_level_class(80, 0, 100) == "-high"
    assert gauge_level_class(-5, 0, 100) == "-low"  # clamped
    assert gauge_level_class(150, 0, 100) == "-high"  # clamped
