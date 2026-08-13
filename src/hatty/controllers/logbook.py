# hatty — MIT License. See LICENSE file for details.
"""Shared activity-log state machine for three log hosts: HACLI's docked
panel, GraphPreviewScreen's fullscreen-graph panel, and DashboardScreen's
docked panel — extracted (issue #38) so a new host is a matter of wiring,
not another copy of this file. (A fourth, device-tree-scoped host is issue
#28, still open.)

One LogbookController (app.log_ctl) holds a LogSession per open host, keyed
by id(host) — not a single global session, since the main screen's log and a
pushed GraphPreviewScreen's log can both be `-visible` at once (opening a
fullscreen graph via `G` does not close the main log; only the docked-panel
toggle does that mutual-exclusion dance). HAClient has exactly one
logbook_subscription_id, though, so a *live* WS subscription is a singleton
resource — `live_session()` picks among the sessions allowed to hold it.

HACLI and DashboardScreen are both live-capable (LOG_SUPPORTS_LIVE = True);
either's panel can be `-visible` while the other is hidden behind it (the
main screen's panel stays `-visible` when `d` pushes the dashboard on top).
When more than one live-capable session is visible and now-anchored,
`live_session()` prefers whichever host is the screen currently on top —
the singleton subscription always follows what the user is looking at, and
`close()`/screen-transition hooks resync it to whatever remains live.
GraphPreviewScreen stays fetch-only on purpose: its log window follows the
graph's own paged/zoomed span, and a live WS append is always anchored to
"now" — it would inject entries outside whatever span is currently plotted.

LogScopeOption.resolve is pure (never notifies) so every option can be
resolved just to preview it (the `v` scope popup, issue #38) without side
effects; apply_option is the only place that surfaces cap/no-device notices,
exactly once, for the option actually applied (unless called quiet=True).

A cursor_option-backed session tracks the table cursor live: HACLI debounces
DataTable.CellHighlighted into follow_cursor, which quietly re-applies the
active option when the resolved scope actually changed. A maximized panel
opts out — the table isn't what's focused there.

A base_option's entity set is fixed only for as long as the session's
current `options` list says so — when what it closed over changes (the
table switching lists, issue #48), the host rebuilds fresh options and
hands them to rebuild_options, which swaps them in and re-applies the
still-active option id.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from textual.css.query import NoMatches

from hatty.logbook import LogEntry, entry_when_iso, is_continuous_sensor, normalize_entries, normalize_entry
from hatty.types import Entity
from hatty.ui.activity_log_panel import ActivityLogPanel
from hatty.ui.device_tree_screen import device_display_name
from hatty.ui.entity_table import get_display_name

# A device log covering a whole list can expand to many sibling entities; cap
# the set so a single logbook GET's entity= param can't blow up.
_DEVICE_LOG_MAX_ENTITIES = 200
# Every device_id widens the WS logbook query's event-type set (HA's
# async_determine_event_types), making device count the expensive axis — cap
# it independently of the entity cap above.
_DEVICE_LOG_MAX_DEVICES = 50


@dataclass(frozen=True)
class LogScope:
    """What one resolved LogScopeOption logs: the wire ids, the panel title,
    and (when capped, or when a cursor_device option's entity has no device)
    the facts a caller needs to notify/annotate — resolve() itself never
    does, so it's safe to call for every option just to preview it."""

    entity_ids: list[str]
    device_ids: list[str]
    title: str
    entity_total: int = 0  # pre-cap entity count; 0 when not capped
    device_total: int = 0  # pre-cap device count; 0 when not capped
    no_device: bool = False  # a cursor_device option whose entity has no device


@dataclass(frozen=True)
class LogScopeOption:
    """One row of the `v` scope popup (`LogScopePopup`, `ui/log_scope_popup.py`).
    `resolve` is pure — see the module docstring. `follows_cursor` marks a
    cursor_option so LogbookController.follow_cursor knows to re-resolve it
    as the table selection moves."""

    id: str
    label: str
    resolve: Callable[[], LogScope | None]
    follows_cursor: bool = False


@dataclass
class LogSession:
    host: "LogHost"
    panel_id: str
    supports_live: bool
    options: list[LogScopeOption]
    option_id: str
    query_ids: list[str]
    device_ids: list[str]
    entity_ids: set[str]
    title_base: str
    end: "datetime | None" = None
    generation: int = 0

    def panel(self) -> ActivityLogPanel:
        return self.host.query_one(f"#{self.panel_id}", ActivityLogPanel)

    def is_visible(self) -> bool:
        return self.panel().has_class("-visible")


class LogHost(Protocol):
    """The per-host hooks LogbookController needs — implemented by HACLI and
    GraphPreviewScreen. Documentation-grade typing only, like the other
    controllers' untyped `app` reference."""

    LOG_PANEL_ID: str
    LOG_SUPPORTS_LIVE: bool

    def query_one(self, selector: str, expect_type: type) -> ActivityLogPanel: ...
    def log_window(self, session: LogSession) -> "tuple[float, datetime | None]": ...
    def log_title_suffix(self, session: LogSession) -> str: ...


class LogbookController:
    """Owns every open log session's scope/paging/fetch/subscription state.
    Widget lookups go through each session's host; the live WS subscription
    and registries are reached through app.client / app.entity_registry etc.
    — app is always the HACLI instance (this controller lives at app.log_ctl),
    regardless of which host (HACLI itself, or a pushed GraphPreviewScreen)
    a given session belongs to."""

    def __init__(self, app) -> None:
        self._app = app
        self._sessions: dict[int, LogSession] = {}

    # ── session lifecycle ────────────────────────────────────────────────────

    def open(self, host: LogHost, *, options: list[LogScopeOption], option_id: str, hint: str) -> LogSession:
        session = LogSession(
            host=host,
            panel_id=host.LOG_PANEL_ID,
            supports_live=host.LOG_SUPPORTS_LIVE,
            options=options,
            option_id=option_id,
            query_ids=[],
            device_ids=[],
            entity_ids=set(),
            title_base="",
        )
        self._sessions[id(host)] = session
        panel = session.panel()
        panel.set_hint(hint)
        panel.remove_class("-maximized")
        panel.add_class("-visible")
        self._app.refresh_bindings()
        self.apply_option(host, option_id)
        return session

    def close(self, host: LogHost) -> None:
        session = self._sessions.pop(id(host), None)
        if session is None:
            return
        try:
            panel = session.panel()
        except NoMatches:
            # The host is mid-teardown (e.g. a screen's on_unmount closing its
            # own session so it can't linger — see LogHost's docstring) and its
            # children, including the panel, are already gone. Nothing left to
            # un-visible/un-maximize; still resync the subscription below.
            panel = None
        if panel is not None:
            panel.remove_class("-visible")
            panel.remove_class("-maximized")
        if session.supports_live:
            # Don't just drop the subscription — another live session (e.g. the
            # main screen's, left `-visible` behind a dismissed dashboard) may
            # still want it.
            self._app.spawn(self.resync_subscription())
        self._app.refresh_bindings()

    def session_for(self, host: LogHost) -> "LogSession | None":
        return self._sessions.get(id(host))

    def is_open(self, host: LogHost) -> bool:
        return id(host) in self._sessions

    def paged_back(self, host: LogHost) -> bool:
        session = self.session_for(host)
        return session is not None and session.end is not None

    # ── scope option factories ───────────────────────────────────────────────

    def base_option(
        self, option_id: str, label: str, entity_ids: list[str], *, with_devices: bool
    ) -> LogScopeOption:
        """A fixed base entity set — the table's active list/all-entities
        snapshot, or an i/graph-opened entity set. Captured by closure at
        build time since the base doesn't change while these options stay
        current (only cursor_option below re-derives on every call); a host
        whose base can change from under it (the table switching lists)
        rebuilds fresh options and swaps them in via rebuild_options."""

        def _resolve() -> "LogScope | None":
            if not entity_ids:
                return None
            if with_devices:
                device_ids = self._device_ids_for_entities(entity_ids)
                capped_entities, capped_devices, entity_total, device_total = self._cap(entity_ids, device_ids)
                title = self._device_log_title("Device Log", label, capped_devices)
                return LogScope(capped_entities, capped_devices, title, entity_total, device_total)
            return LogScope(list(entity_ids), [], f"Activity Log — {label}")

        return LogScopeOption(option_id, label, _resolve)

    def cursor_option(
        self, option_id: str, selected_entity_id: Callable[[], "str | None"], *, with_device: bool
    ) -> LogScopeOption:
        """The table's currently-selected row — re-resolved on every call
        (not captured at build time), since the cursor can move while the
        panel stays open."""

        def _resolve() -> "LogScope | None":
            entity_id = selected_entity_id()
            if not entity_id:
                return None
            if with_device:
                entity_ids, cursor_label, device_id = self._get_device_entity_ids(entity_id)
                capped_entities, capped_devices, entity_total, device_total = self._cap(
                    entity_ids, [device_id] if device_id else []
                )
                return LogScope(
                    capped_entities,
                    capped_devices,
                    f"Device Log — {cursor_label}",
                    entity_total,
                    device_total,
                    no_device=device_id is None,
                )
            entity = self._app.find_entity(entity_id)
            cursor_label = get_display_name(entity) if entity else entity_id
            return LogScope([entity_id], [], f"Activity Log — {cursor_label}")

        label = "Selected entity's device" if with_device else "Selected entity"
        return LogScopeOption(option_id, label, _resolve, follows_cursor=True)

    # ── applying a scope ─────────────────────────────────────────────────────

    def resolved_options(self, host: LogHost) -> list[tuple[LogScopeOption, "LogScope | None"]]:
        session = self.session_for(host)
        if session is None:
            return []
        return [(option, option.resolve()) for option in session.options]

    def apply_option(self, host: LogHost, option_id: str, *, quiet: bool = False) -> None:
        """Resolve `option_id` and point the session at it — clears +
        retitles + refetches + resyncs the subscription, leaving the paged
        window and maximized state alone (a scope change in place, not a
        reopen). The only place a resolved LogScope's cap/no-device facts
        get surfaced as a notification, unless quiet=True (follow_cursor's
        silent re-apply as the table selection moves)."""
        session = self.session_for(host)
        if session is None:
            return
        option = next((o for o in session.options if o.id == option_id), None)
        if option is None:
            return
        scope = option.resolve()
        if scope is None:
            return
        if not quiet:
            if scope.no_device:
                self._app.notify(
                    "No device found for the selected entity. Showing single entity log.", title="Device Log"
                )
            self._notify_caps(scope.entity_total, scope.device_total)
        session.option_id = option_id
        session.entity_ids = set(scope.entity_ids)
        session.query_ids = list(scope.entity_ids)
        session.device_ids = list(scope.device_ids)
        session.title_base = scope.title
        session.panel().clear()
        self.reload(host)

    def rebuild_options(self, host: LogHost, options: list[LogScopeOption]) -> None:
        """Swap an open session's scope options for freshly-built ones and
        re-apply the active one — for when what a base_option closed over
        changed underneath it (the table switching lists, issue #48). Keeps
        the paged window and maximized state: a scope change in place, not a
        reopen. A follows_cursor option needs no re-apply — follow_cursor
        already re-resolves it as the table's new selection lands."""
        session = self.session_for(host)
        if session is None:
            return
        session.options = options
        option = next((o for o in options if o.id == session.option_id), None)
        if option is None or option.follows_cursor:
            return
        self.apply_option(host, session.option_id)

    def handle_scope_popup_result(self, host: LogHost, result: "str | None") -> None:
        if result is not None:
            self.apply_option(host, result)

    def follow_cursor(self, host: LogHost) -> None:
        """Re-point a cursor-scoped session at the table's new selection.
        No-op for base scopes, for a maximized panel (the log list owns
        focus there, not the table), and when the cursor resolves to the
        same scope already applied (moving between siblings of one device
        under cursor_device)."""
        session = self.session_for(host)
        if session is None:
            return
        option = next((o for o in session.options if o.id == session.option_id), None)
        if option is None or not option.follows_cursor:
            return
        if session.panel().has_class("-maximized"):
            return
        scope = option.resolve()
        if scope is None:
            return
        if (
            scope.entity_ids == session.query_ids
            and scope.device_ids == session.device_ids
            and scope.title == session.title_base
        ):
            return
        self.apply_option(host, session.option_id, quiet=True)

    # ── window / paging ──────────────────────────────────────────────────────

    def reload(self, host: LogHost) -> None:
        session = self.session_for(host)
        if session is None:
            return
        session.generation += 1
        session.panel().set_title(session.title_base + host.log_title_suffix(session))
        self._app.spawn(self.load(session))
        self._app.spawn(self.resync_subscription())

    async def load(self, session: LogSession) -> None:
        generation = session.generation
        host = session.host
        hours, end = host.log_window(session)
        entries = await self.fetch_entries(session.query_ids, hours=hours, end=end, device_ids=session.device_ids)
        panel = session.panel()
        if not panel.has_class("-visible") or session.generation != generation:
            return
        if entries is None:
            self._app.notify(
                "Failed to load activity log from Home Assistant.", title="Activity Log", severity="error"
            )
            normalized: list[LogEntry] = []
        else:
            normalized = self.normalize(entries)
        panel.load_history(normalized)

    def page(self, host: LogHost, direction: int) -> None:
        """direction<0 pages older, >0 pages newer (snapping back to live at
        or past "now"). Only ever called for HACLI — GraphPreviewScreen pages
        its own GraphWindow instead."""
        session = self.session_for(host)
        if session is None:
            return
        now = datetime.now(timezone.utc)
        span = timedelta(hours=self._app.log_hours)
        if direction < 0:
            session.end = (session.end or now) - span
        else:
            if session.end is None:
                return
            new_end = session.end + span
            session.end = None if new_end >= now else new_end
        self.reload(host)

    def range_suffix(self, session: LogSession) -> str:
        """`(last Xh)` while live, or the paged-back window's full start–end
        range — mirrors the fullscreen graph's window-status suffix."""
        from hatty.ui.graph.plot_time import ts_to_full

        if session.end is None:
            return f"  (last {self._format_log_hours(self._app.log_hours)})"
        end = session.end
        start = end - timedelta(hours=self._app.log_hours)
        return f"  ({ts_to_full(start.isoformat())} – {ts_to_full(end.isoformat())})"

    # ── fetch / normalize ────────────────────────────────────────────────────

    def display_names(self) -> tuple[dict[str, str], dict[str, str]]:
        """entity_id -> display name, device_id -> display name — the name
        maps LogScopePopup's preview (issue #38) and normalize() both need,
        built once so there's one precedence chain for both."""
        entity_names = {e["entity_id"]: get_display_name(e) for e in self._app.all_entities if e.get("entity_id")}
        for reg in self._app.entity_registry:
            entity_id = reg.get("entity_id")
            if entity_id and entity_id not in entity_names:
                entity_names[entity_id] = reg.get("name") or reg.get("original_name") or entity_id
        device_names = {d["id"]: device_display_name(d) for d in self._app.device_registry if d.get("id")}
        return entity_names, device_names

    def normalize(self, raw: list[dict]) -> list[LogEntry]:
        """Raw REST/WS logbook entries -> the single shape the log panel and
        the graph's event marks consume. WS entries have an epoch `when` and
        no `name` on state entries (issue #17) — this resolves both."""
        entity_names, device_names = self.display_names()
        device_classes = {
            e["entity_id"]: e.get("attributes", {}).get("device_class") or ""
            for e in self._app.all_entities
            if e.get("entity_id")
        }
        units = {
            e["entity_id"]: e.get("attributes", {}).get("unit_of_measurement") or ""
            for e in self._app.all_entities
            if e.get("entity_id")
        }
        for reg in self._app.entity_registry:
            entity_id = reg.get("entity_id")
            if entity_id and not device_classes.get(entity_id):
                device_classes[entity_id] = reg.get("device_class") or reg.get("original_device_class") or ""
        return normalize_entries(raw, entity_names, device_names, device_classes, units)

    def _continuous_log_ids(self, entity_ids: list[str]) -> list[str]:
        """The subset of entity_ids that are continuous sensors (issue #29)
        — HA's logbook silently excludes these, so fetch_entries fills the
        gap with history-derived entries. Order-preserving."""
        result = []
        for entity_id in entity_ids:
            entity = self._app.find_entity(entity_id)
            if entity and is_continuous_sensor(entity_id, entity.get("attributes", {})):
                result.append(entity_id)
        return result

    async def fetch_entries(
        self,
        entity_ids: list[str],
        hours: float,
        end: "datetime | None" = None,
        device_ids: "list[str] | None" = None,
    ) -> "list[dict] | None":
        """The one seam both log hosts call instead of client.fetch_logbook
        directly — merges in history-derived entries for continuous sensors
        (issue #29), which HA's own logbook never returns. Failure semantics
        of the base fetch are preserved: a None here still means "ask HA
        failed", not "nothing to show"."""
        entries = await self._app.client.fetch_logbook(entity_ids, hours=hours, end=end, device_ids=device_ids)
        continuous_ids = self._continuous_log_ids(entity_ids)
        if not continuous_ids:
            return entries

        semaphore = asyncio.Semaphore(8)

        async def _fetch(entity_id: str) -> list[dict]:
            async with semaphore:
                result = await self._app.client.fetch_state_log(entity_id, hours=hours, end=end)
                return result or []

        synthesized: list[dict] = []
        for rows in await asyncio.gather(*(_fetch(eid) for eid in continuous_ids)):
            synthesized.extend(rows)
        if not synthesized:
            return entries

        merged = list(entries or []) + synthesized
        merged.sort(key=lambda e: entry_when_iso(e.get("when")))
        return merged

    # ── device-scope helpers ─────────────────────────────────────────────────

    def _get_device_entity_ids(self, entity_id: str) -> "tuple[list[str], str, str | None]":
        """Sibling entity_ids sharing entity_id's device, its display label,
        and the device_id itself (None when the entity has no device — the
        WS logbook query then falls back to entity-only scope)."""
        entity = self._app.find_entity(entity_id)
        label = get_display_name(entity) if entity else entity_id

        reg_entry = next((e for e in self._app.entity_registry if e.get("entity_id") == entity_id), None)
        device_id = reg_entry.get("device_id") if reg_entry else None

        if not device_id:
            return ([entity_id], label, None)

        siblings = [
            e["entity_id"] for e in self._app.entity_registry if e.get("device_id") == device_id and e.get("entity_id")
        ]
        if not siblings:
            siblings = [entity_id]

        return (siblings, label, device_id)

    def _device_ids_for_entities(self, entity_ids: list[str]) -> list[str]:
        """Distinct device_ids backing any of entity_ids, order-preserving —
        used by both hosts' device-scoped views."""
        reg_device = {e.get("entity_id"): e.get("device_id") for e in self._app.entity_registry}
        device_ids: list[str] = []
        seen: set[str] = set()
        for entity_id in entity_ids:
            device_id = reg_device.get(entity_id)
            if device_id and device_id not in seen:
                seen.add(device_id)
                device_ids.append(device_id)
        return device_ids

    @staticmethod
    def _device_log_title(prefix: str, label: str, device_ids: list[str]) -> str:
        suffix = f" ({len(device_ids)} devices)" if len(device_ids) > 1 else ""
        return f"{prefix} — {label}{suffix}"

    @staticmethod
    def _cap(entity_ids: list[str], device_ids: list[str]) -> tuple[list[str], list[str], int, int]:
        entity_total = len(entity_ids) if len(entity_ids) > _DEVICE_LOG_MAX_ENTITIES else 0
        device_total = len(device_ids) if len(device_ids) > _DEVICE_LOG_MAX_DEVICES else 0
        return entity_ids[:_DEVICE_LOG_MAX_ENTITIES], device_ids[:_DEVICE_LOG_MAX_DEVICES], entity_total, device_total

    def _notify_caps(self, entity_total: int, device_total: int) -> None:
        if entity_total:
            self._app.notify(
                f"Showing device log for the first {_DEVICE_LOG_MAX_ENTITIES} entities.", title="Device Log"
            )
        if device_total:
            self._app.notify(
                f"Showing device log for the first {_DEVICE_LOG_MAX_DEVICES} devices.", title="Device Log"
            )

    @staticmethod
    def _format_log_hours(hours: float) -> str:
        return f"{int(hours)}h" if hours == int(hours) else f"{hours:.1f}h"

    # ── live subscription + streamed frames ──────────────────────────────────

    def live_session(self) -> "LogSession | None":
        """The one session that may own the WS subscription: live-capable
        host, window anchored to now, panel actually visible. Two can
        qualify at once (the main screen's panel stays `-visible` behind a
        pushed DashboardScreen) — in that case prefer whichever host is the
        screen currently on top, since that's the panel the user can
        actually see."""
        candidates = [s for s in self._sessions.values() if s.supports_live and s.end is None and s.is_visible()]
        if len(candidates) <= 1:
            return candidates[0] if candidates else None
        screen = self._app.screen
        base = self._app.screen_stack[0]
        for session in candidates:
            if session.host is screen or (session.host is self._app and screen is base):
                return session
        return candidates[0]

    async def resync_subscription(self) -> None:
        """Realign the live logbook/event_stream subscription with whichever
        session is currently live (issue #19) — called on every open, page,
        scope change, and timeframe change, so a stale subscription never
        survives. Always unsubscribes first: the real client allocates a
        fresh WS id per subscribe, so an old one would otherwise leak
        server-side."""
        await self._app.client.unsubscribe_logbook()
        session = self.live_session()
        if session is not None:
            await self._app.client.subscribe_logbook(session.query_ids, session.device_ids)

    def resubscribe_after_reconnect(self) -> None:
        """The logbook/event_stream subscription (if any) died with the old
        socket — re-arm it so a live-open log doesn't go silent post-
        reconnect. No unsubscribe first: client.connect() already reset
        logbook_subscription_id to None for the new socket."""
        session = self.live_session()
        if session is not None:
            self._app.spawn(self._app.client.subscribe_logbook(session.query_ids, session.device_ids))

    def handle_stream_frame(self, raw_entries: list[dict]) -> None:
        """Live logbook/event_stream frames (issue #19) — device-scoped
        events (a zha_event button press, a ping) never fire state_changed,
        so this is the only way they can appear without reloading the log.
        The panel's own dedupe (ActivityLogPanel.add_log_entry) absorbs the
        boundary overlap between the fetched window and the first live
        push."""
        if not raw_entries:
            return
        session = self.live_session()
        if session is None:
            return
        panel = session.panel()
        for entry in self.normalize(raw_entries):
            self._app.call_later(panel.add_log_entry, entry)

    def handle_state_change(self, entity_id: str, new_state: Entity) -> None:
        """The state_changed fallback (issue #19) — while a logbook/
        event_stream subscription is active, it already carries this same
        state change (plus device events state_changed can never see), so
        appending here too would double the line; only fires when no
        subscription is live for the session that would want this entity."""
        session = self.live_session()
        if session is None or entity_id not in session.entity_ids:
            return
        if self._app.client.logbook_subscription_id is not None:
            return
        panel = session.panel()
        device_class = new_state.get("attributes", {}).get("device_class") or ""
        raw = {
            "when": datetime.now(timezone.utc).isoformat(),
            "state": new_state.get("state", ""),
            "entity_id": entity_id,
            "name": get_display_name(new_state),
        }
        # name is always set above, so entity_names/device_names can stay
        # empty — resolve_name short-circuits on it (issue #25's transport
        # consistency: this shares format_log_line/state_detail with the
        # fetched path instead of writing a raw, unlabeled string).
        entry = normalize_entry(raw, {}, {}, {entity_id: device_class})
        self._app.call_later(panel.add_log_entry, entry)
