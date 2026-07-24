# hatty — MIT License. See LICENSE file for details.
"""Unit tests for the pure GraphWindow zoom/scroll/live-anchor math (issue #171).

GraphWindow holds only three datetime/float attrs and the arithmetic over them,
so these tests need no Textual app — just fixed timestamps.
"""

from datetime import datetime, timedelta

from hatty.ui.graph.window import GraphWindow

NOW = datetime.fromisoformat("2026-07-08T12:00:00+00:00")
GLOBAL = 4.0  # stand-in for app.graph_hours


def _hours(w: GraphWindow, dt: datetime) -> float:
    """Hours from `dt` back to the window's frozen end (positive = in the past)."""
    assert w.window_end is not None
    return (dt - w.window_end).total_seconds() / 3600


# ── window_hours ──────────────────────────────────────────────────────────────


def test_window_hours_follows_global_when_unzoomed():
    assert GraphWindow().window_hours(GLOBAL) == GLOBAL


def test_window_hours_uses_local_override():
    w = GraphWindow()
    w.local_hours = 2.0
    assert w.window_hours(GLOBAL) == 2.0


# ── reset_live / should_snap_live ─────────────────────────────────────────────


def test_reset_live_clears_everything():
    w = GraphWindow()
    w.window_end, w.live_anchor, w.local_hours = NOW, NOW, 2.0
    w.reset_live()
    assert (w.window_end, w.live_anchor, w.local_hours) == (None, None, None)


def test_reset_live_preserve_zoom_keeps_local_hours():
    w = GraphWindow()
    w.window_end, w.live_anchor, w.local_hours = NOW, NOW, 2.0
    w.reset_live(preserve_zoom=True)
    assert w.window_end is None and w.live_anchor is None
    assert w.local_hours == 2.0


def test_should_snap_live_false_when_live_and_unzoomed():
    assert GraphWindow().should_snap_live() is False


def test_should_snap_live_true_when_paged():
    w = GraphWindow()
    w.window_end = NOW
    assert w.should_snap_live() is True


def test_should_snap_live_true_when_zoomed():
    w = GraphWindow()
    w.local_hours = 2.0
    assert w.should_snap_live() is True


# ── page_back ─────────────────────────────────────────────────────────────────


def test_page_back_from_live_anchors_now_and_freezes():
    w = GraphWindow()
    w.page_back(2.0, NOW)
    assert w.live_anchor == NOW
    assert w.window_end == NOW - timedelta(hours=2.0)


def test_page_back_again_steps_from_current_edge_keeping_anchor():
    w = GraphWindow()
    w.page_back(2.0, NOW)
    w.page_back(2.0, NOW + timedelta(hours=1))  # a later "now" must not move the anchor
    assert w.live_anchor == NOW
    assert w.window_end == NOW - timedelta(hours=4.0)


# ── page_forward ──────────────────────────────────────────────────────────────


def test_page_forward_while_live_is_noop():
    w = GraphWindow()
    assert w.page_forward(2.0) == "none"
    assert w.window_end is None


def test_page_forward_steps_toward_present():
    w = GraphWindow()
    w.page_back(6.0, NOW)  # end = NOW - 6h, anchor = NOW
    assert w.page_forward(2.0) == "window"
    assert w.window_end == NOW - timedelta(hours=4.0)


def test_page_forward_past_anchor_reenters_live_without_touching_end():
    w = GraphWindow()
    w.page_back(2.0, NOW)  # end = NOW - 2h
    frozen_end = w.window_end
    assert w.page_forward(2.0) == "live"  # would reach the anchor
    # The end is left as-is; the screen's live reload resets it.
    assert w.window_end == frozen_end


# ── zoom ──────────────────────────────────────────────────────────────────────


def test_zoom_noop_when_span_unchanged():
    w = GraphWindow()
    assert w.zoom(GLOBAL, GLOBAL) == "none"
    assert w.local_hours is None


def test_zoom_while_live_freezes_span_and_stays_live():
    w = GraphWindow()
    assert w.zoom(2.0, GLOBAL) == "live"
    assert w.local_hours == 2.0
    assert w.window_end is None  # still live-anchored


def test_zoom_while_paged_recenters_on_midpoint_and_freezes():
    w = GraphWindow()
    w.page_back(4.0, NOW)  # 4h window ending NOW-4h → midpoint at NOW-6h
    assert w.zoom(2.0, GLOBAL) == "window"
    assert w.local_hours == 2.0
    # New 2h span centered on the old midpoint (NOW-6h): end = midpoint + 1h.
    assert w.window_end == NOW - timedelta(hours=5.0)


def test_zoom_while_paged_never_runs_past_the_live_anchor():
    w = GraphWindow()
    w.page_back(1.0, NOW)  # small 4h-context window near the anchor
    # Zoom out wide enough that the recentered end would pass NOW; it's clamped.
    w.zoom(48.0, GLOBAL)
    assert w.window_end == w.live_anchor == NOW


# ── status_badge ──────────────────────────────────────────────────────────────


def test_status_badge_live():
    assert GraphWindow().status_badge() == "  [LIVE]"


def test_status_badge_zoomed_live():
    w = GraphWindow()
    w.local_hours = 2.0
    assert w.status_badge() == "  [⌕ 2h · LIVE]"


def test_status_badge_paged_back():
    w = GraphWindow()
    w.page_back(6.0, NOW)
    assert w.status_badge() == "  [◀ 6h back]"


def test_status_badge_empty_when_paged_but_negligible():
    w = GraphWindow()
    w.window_end = NOW
    w.live_anchor = NOW  # zero offset → no badge
    assert w.status_badge() == ""
