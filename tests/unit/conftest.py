# hatty — MIT License. See LICENSE file for details.
import pytest


@pytest.fixture(autouse=True)
def _no_terminal_title_side_effects():
    """Override the acceptance-suite stub of the same name (tests/conftest.py):
    tests/unit/test_terminal_title.py exercises hatty.terminal_title directly and
    must not have its functions replaced with no-ops."""
    yield
