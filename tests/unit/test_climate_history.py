# hatty — MIT License. See LICENSE file for details.
from hatty.ui.graph.climate_history import hvac_action_runs

_HISTORY = [
    {"ts": "2024-01-01T08:00:00+00:00", "hvac_action": "heating"},
    {"ts": "2024-01-01T08:05:00+00:00", "hvac_action": "heating"},
    {"ts": "2024-01-01T08:10:00+00:00", "hvac_action": "idle"},
    {"ts": "2024-01-01T08:20:00+00:00", "hvac_action": "idle"},
    {"ts": "2024-01-01T08:30:00+00:00", "hvac_action": "cooling"},
    {"ts": "2024-01-01T08:40:00+00:00", "hvac_action": "cooling"},
    {"ts": "2024-01-01T08:50:00+00:00", "hvac_action": "cooling"},
]


def test_hvac_action_runs_collapses_contiguous_samples():
    runs = hvac_action_runs(_HISTORY)

    assert runs == [
        ("2024-01-01T08:00:00+00:00", "2024-01-01T08:10:00+00:00", "heating"),
        ("2024-01-01T08:30:00+00:00", "2024-01-01T08:50:00+00:00", "cooling"),
    ]


def test_hvac_action_runs_extends_to_final_sample_when_run_is_ongoing():
    history = _HISTORY[:2]  # only the heating samples, run never ends
    runs = hvac_action_runs(history)

    assert runs == [("2024-01-01T08:00:00+00:00", "2024-01-01T08:05:00+00:00", "heating")]


def test_hvac_action_runs_empty_for_no_heating_or_cooling():
    history = [
        {"ts": "2024-01-01T08:00:00+00:00", "hvac_action": "idle"},
        {"ts": "2024-01-01T08:05:00+00:00", "hvac_action": "idle"},
    ]
    assert hvac_action_runs(history) == []


def test_hvac_action_runs_empty_data():
    assert hvac_action_runs([]) == []
