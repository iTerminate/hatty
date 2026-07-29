# hatty — MIT License. See LICENSE file for details.
"""Normalizes raw Home Assistant logbook entries — from both the REST
`/api/logbook` endpoint and the WS `logbook/get_events` command — into one
shape the activity/device log panel and the graph's event-mark overlay both
consume (issue #17).

The two transports disagree on shape: REST's entries have an ISO `when` and
always carry `name`; WS entries (`EventProcessor(timestamp=True,
include_entity_name=False)`) have an epoch-seconds `when` and omit `name` on
state-change entries, relying on the caller to resolve a display name. This
module is the one place that difference is resolved, so downstream code never
has to know which transport an entry came from.

Imports only stdlib plus const.py (itself stdlib-only) — no Textual, no app
state — so it's unit-testable without booting the app and stays near the
bottom of the dependency graph."""

from datetime import datetime, timezone
from typing import TypedDict

from hatty.const import binary_state_label

# HA's `logbook_entry`/`call_service`-style describers append this to an
# external event's message (e.g. ZHA's zha_event): the leading event type is
# the whole signal, the trailing dict is noise in a 52-column panel.
_EVENT_PARAMS_MARKER = " event was fired with parameters: "


class LogEntry(TypedDict):
    """The one shape ActivityLogPanel and the graph's event marks consume."""

    when: str  # always ISO 8601, tz-aware
    name: str  # resolved display name, never empty
    detail: str  # the state (kind="state") or the event message (kind="event")
    entity_id: str  # "" for device-scoped events
    kind: str  # "state" | "event"


def entry_when_iso(raw_when: object) -> str:
    """Normalize a raw entry's `when` to ISO 8601 — WS sends a float epoch,
    REST sends an ISO string (occasionally naive, which is stamped UTC).
    Anything unparseable becomes "" rather than raising."""
    if isinstance(raw_when, (int, float)):
        return datetime.fromtimestamp(raw_when, timezone.utc).isoformat()
    if isinstance(raw_when, str) and raw_when:
        try:
            dt = datetime.fromisoformat(raw_when)
        except ValueError:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return ""


def entry_kind(raw: dict) -> str:
    """"state" for a state-change entry, "event" for an external/describe
    event (zha_event and friends) — the two forms hatty renders differently."""
    if "state" in raw:
        return "state"
    if "message" in raw:
        return "event"
    return "state"


def compact_message(message: str) -> str:
    """Drop a trailing "<type> event was fired with parameters: {...}" tail,
    keeping the leading event type — the signal in a ZHA-style message, not
    the 100+ chars of raw parameters. A no-op when the phrase is absent, so
    this can only shorten a matching message, never mangle an unrelated one."""
    return message.split(_EVENT_PARAMS_MARKER, 1)[0]


def resolve_name(raw: dict, entity_names: dict[str, str], device_names: dict[str, str]) -> str:
    """Precedence: the entry's own `name` (REST always has it; WS external
    events do too) -> the entity's display name -> the device's display name
    (defensive; current HA logbook entries carry no `device_id` key) -> the
    entity_id -> the domain -> a last-resort literal."""
    name = raw.get("name")
    if name:
        return name
    entity_id = raw.get("entity_id")
    if entity_id and entity_id in entity_names:
        return entity_names[entity_id]
    device_id = raw.get("device_id")
    if device_id and device_id in device_names:
        return device_names[device_id]
    if entity_id:
        return entity_id
    domain = raw.get("domain")
    if domain:
        return domain
    return "unknown"


def state_detail(entity_id: str, state: str, device_class: str) -> str:
    """A state entry's display detail — device_class-aware (e.g. "Open") for
    binary_sensor, since its states are the raw on/off HA itself relabels;
    other domains (cover, switch, ...) already report human states as-is."""
    if entity_id.split(".", 1)[0] == "binary_sensor":
        return binary_state_label(state, device_class)
    return state


def normalize_entry(
    raw: dict,
    entity_names: dict[str, str],
    device_names: dict[str, str],
    device_classes: dict[str, str] | None = None,
) -> LogEntry:
    kind = entry_kind(raw)
    entity_id = raw.get("entity_id") or ""
    if kind == "event":
        detail = compact_message(raw.get("message", ""))
    else:
        device_class = (device_classes or {}).get(entity_id, "")
        detail = state_detail(entity_id, raw.get("state", ""), device_class)
    return LogEntry(
        when=entry_when_iso(raw.get("when")),
        name=resolve_name(raw, entity_names, device_names),
        detail=detail,
        entity_id=entity_id,
        kind=kind,
    )


def normalize_entries(
    raw_entries: list[dict],
    entity_names: dict[str, str],
    device_names: dict[str, str],
    device_classes: dict[str, str] | None = None,
) -> list[LogEntry]:
    """Maps normalize_entry over a raw logbook response, skipping any
    non-dict item, and preserving order — both transports return entries in
    ascending time order; reordering is left to the caller."""
    return [
        normalize_entry(e, entity_names, device_names, device_classes) for e in raw_entries if isinstance(e, dict)
    ]


def format_log_time(iso_str: str) -> str:
    """Local HH:MM:SS for display — moved from ActivityLogPanel so it's
    testable without Textual. Only ever sees the ISO output of entry_when_iso."""
    if not iso_str:
        return "??:??:??"
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return iso_str[:8] if len(iso_str) >= 8 else "??:??:??"


def format_log_line(entry: LogEntry, width: int) -> str:
    """One display line for the log panel, truncated to `width` with a
    trailing "…" — the panel is a 52-column docked, non-scrollable widget
    (ActivityLogPanel), so overflow must never happen. The `[HH:MM:SS] `
    prefix is never truncated."""
    when = format_log_time(entry["when"])
    if entry["kind"] == "event":
        body = f"⚡ {entry['name']}: {entry['detail']}"
    else:
        body = f"{entry['name']} → {entry['detail']}"
    line = f"[{when}] {body}"
    if len(line) <= width:
        return line
    prefix = f"[{when}] "
    keep = max(width - len(prefix) - 1, 0)
    return f"{prefix}{body[:keep]}…"
