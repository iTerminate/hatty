# hatty — MIT License. See LICENSE file for details.
"""Guard against FakeHAClient drifting from the real HAClient.

Both are hand-maintained; without this check a signature change on HAClient
(parameter added/renamed, default changed, annotation changed) would silently
leave every Pilot test exercising a stale protocol."""

import inspect

from hatty.client import HAClient

# Every method the app calls on its client, i.e. the de-facto client protocol.
SHARED_METHODS = [
    "listen",
    "close",
    "call_service",
    "update_entity_registry",
    "update_device_registry",
    "create_area",
    "rename_area",
    "fetch_entity_registry",
    "fetch_device_registry",
    "fetch_area_registry",
    "fetch_history",
    "fetch_binary_history",
    "fetch_climate_history",
    "fetch_logbook",
    "fetch_forecast",
]


def _assert_signatures_match(stand_in, label: str) -> None:
    for name in SHARED_METHODS:
        real = inspect.signature(getattr(HAClient, name))
        other = inspect.signature(getattr(stand_in, name))
        real_params = list(real.parameters.values())
        other_params = list(other.parameters.values())
        assert [p.name for p in other_params] == [p.name for p in real_params], (
            f"{label}.{name}: parameter names diverged ({label} {other} vs real {real})"
        )
        assert [p.default for p in other_params] == [p.default for p in real_params], (
            f"{label}.{name}: parameter defaults diverged ({label} {other} vs real {real})"
        )
        assert [p.annotation for p in other_params] == [p.annotation for p in real_params], (
            f"{label}.{name}: parameter annotations diverged ({label} {other} vs real {real})"
        )


def test_fake_client_method_signatures_match_real_client(fake_client_class):
    _assert_signatures_match(fake_client_class, "FakeHAClient")


def test_demo_client_method_signatures_match_real_client():
    from hatty.demo.demo_client import DemoHAClient

    _assert_signatures_match(DemoHAClient, "DemoHAClient")
