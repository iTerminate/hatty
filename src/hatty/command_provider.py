# hatty — MIT License. See LICENSE file for details.
"""The ``Ctrl+P`` command-palette provider for hatty.

Exposes three static entries regardless of how many lists/dashboards/saved
graphs exist; each dispatches to an ``action_*`` on the host ``HACLI`` app.
"""

from typing import TYPE_CHECKING

from textual.command import DiscoveryHit, Hit, Hits, Provider
from textual.types import IgnoreReturnCallbackType

if TYPE_CHECKING:
    from hatty.main import HACLI


class HACommandProvider(Provider):
    app: "HACLI"  # narrow Textual's inherited attr so the action_* dispatch type-checks

    def _candidates(self) -> list[tuple[str, str, IgnoreReturnCallbackType]]:
        app = self.app
        result: list[tuple[str, str, IgnoreReturnCallbackType]] = [
            ("Configuration", "Edit hatty settings", app.action_show_config),
        ]
        result.append(("Lists", "Switch to your last-used or default list", app.action_palette_switch_list))
        result.append(("Dashboard", "Open your last-used or default dashboard", app.action_show_dashboard))
        result.append(("Setup wizard", "Re-enter the Home Assistant URL and token", app.action_show_onboarding))
        return result

    async def discover(self) -> Hits:
        for text, help_text, command in self._candidates():
            yield DiscoveryHit(display=text, command=command, help=help_text)

    async def search(self, query: str) -> Hits:
        q = query.lower()
        for text, help_text, command in self._candidates():
            if not q or q in text.lower():
                yield Hit(score=1.0, match_display=text, command=command, help=help_text)
