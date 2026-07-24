# hatty — MIT License. See LICENSE file for details.
"""Pure zoom/scroll/live-anchor state machine for the fullscreen graph
(`graph/preview_screen.py`), extracted so the windowing math is unit-testable
without booting a Textual screen (issue #171).

The screen owns a `GraphWindow`, mutates it in response to key actions, and then
dispatches the async history reload the returned signal asks for. This class
never touches widgets, workers, or `self.app` — it only holds the three window
attributes and the arithmetic over them.

Window state:
- `window_end`  — the window's right edge; `None` means anchored to "now" (live).
- `live_anchor` — "now" captured at the moment scrolling away from live began.
- `local_hours` — screen-local zoom override for the global `graph_hours`;
  `None` means "follow the global value".
"""

from datetime import datetime, timedelta
from typing import Literal

# The reload a mutation asks the screen to perform afterwards:
#   "none"   — nothing changed, don't reload
#   "live"   — reload the live window (screen calls _reload_live(preserve_zoom=True))
#   "window" — reload the frozen window ending at `window_end`
ReloadSignal = Literal["none", "live", "window"]


class GraphWindow:
    def __init__(self) -> None:
        self.window_end: datetime | None = None
        self.live_anchor: datetime | None = None
        self.local_hours: float | None = None

    def window_hours(self, global_hours: float) -> float:
        """The effective window span: the zoom override when set, else global."""
        return self.local_hours if self.local_hours is not None else global_hours

    def status_badge(self) -> str:
        """LIVE / zoom / paged-back badge for the title bar."""
        parts = []
        if self.local_hours is not None:
            parts.append(f"⌕ {round(self.local_hours, 2):g}h")
        if self.window_end is None:
            parts.append("LIVE")
        elif self.live_anchor is not None:
            back_hours = (self.live_anchor - self.window_end).total_seconds() / 3600
            if back_hours > 0.01:
                parts.append(f"◀ {round(back_hours, 1):g}h back")
        return f"  [{' · '.join(parts)}]" if parts else ""

    def reset_live(self, preserve_zoom: bool = False) -> None:
        """Re-anchor to live: clear the frozen window edge and anchor, dropping
        the zoom override unless `preserve_zoom` keeps it (issue #138)."""
        self.window_end = None
        self.live_anchor = None
        if not preserve_zoom:
            self.local_hours = None

    def should_snap_live(self) -> bool:
        """Whether `home` has anything to snap back from (paged and/or zoomed)."""
        return self.window_end is not None or self.local_hours is not None

    def zoom(self, new_hours: float, global_hours: float) -> ReloadSignal:
        """Change the visible span. Live stays anchored to "now" (issue #138);
        a paged-back window re-centers the new span on the old midpoint and
        freezes, never running past the live anchor."""
        if new_hours == self.window_hours(global_hours):
            return "none"
        if self.window_end is None:
            self.local_hours = new_hours
            return "live"
        midpoint = self.window_end - timedelta(hours=self.window_hours(global_hours) / 2)
        new_end = midpoint + timedelta(hours=new_hours / 2)
        if self.live_anchor is not None and new_end > self.live_anchor:
            new_end = self.live_anchor
        self.window_end = new_end
        self.local_hours = new_hours
        return "window"

    def page_back(self, hours: float, now: datetime) -> None:
        """Scroll `hours` into the past. The first step away from live captures
        `now` as the anchor so paging forward can find its way home. Always a
        frozen-window reload."""
        if self.window_end is None:
            self.live_anchor = now
            anchor = self.live_anchor
        else:
            anchor = self.window_end
        self.window_end = anchor - timedelta(hours=hours)

    def page_forward(self, hours: float) -> ReloadSignal:
        """Scroll `hours` toward the present. Reaching/passing the live anchor
        re-enters live mode (keeping any zoom); a live window has nothing to
        page forward into."""
        if self.window_end is None:
            return "none"
        new_end = self.window_end + timedelta(hours=hours)
        if self.live_anchor is not None and new_end >= self.live_anchor:
            return "live"
        self.window_end = new_end
        return "window"
