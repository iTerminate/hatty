# hatty v0.1.0

The first release of **hatty — a TTY for your HA.** Your whole smart home, live, in a terminal:
search and control every entity, sparkline or fullscreen graph its history, and lay out widget
dashboards, all over Home Assistant's WebSocket API.

Never used it? `uv run hatty --demo` boots fully offline against a curated fake home — no HA
required. See `docs/demo.gif` for a scripted tour.

## The entity table

A live-updating table over every entity in your home, with nine columns you can mix and match
(`c`): icon, name, state, value, unit, device class, entity ID, last-changed, list membership.
`/` searches incrementally with `n`/`N` to step matches; `enter` toggles a switch/light/fan or
play-pauses a media player; `r` renames an entity, locally or by writing straight through to
Home Assistant's own entity registry.

Favorite entities into named **lists** (`space` to add, `l` to manage) — alphabetical or hand-
ordered per list, lockable against accidental edits, with full undo/redo on membership changes.

## Graphs

`g` opens an inline sparkline, `G` a fullscreen graph — sparkline, line, or scatter, comparing
several entities at once with per-line colors you can cycle or pick freely. `enter` drops into
inspect mode and reads every plotted series at one timestamp; paging keeps a live anchor so
scrolling back and forward again lands you exactly where "now" still is. Save a comparison as a
named graph and reload it later.

Dense series get downsampled min/max-per-bucket rather than by stride or averaging, so a spike in
your power sensor survives the render instead of getting smoothed away. Inspect-mode's keys are
literal twin bindings of the paging keys — the footer always shows what a key does *right now*,
never what it does in the other mode.

## Dashboards

Build named grid dashboards out of 13 widget types — graph, gauge, switch, light, fan,
thermostat, cover, lock, media player, sensor, binary sensor, weather, panel — plus nested split
panes for finer layouts. Use mode drives the entities directly; Edit mode (`E`) resizes slots with
`ctrl+arrows`, grab-moves or swaps them, and splits/unsplits panes. Some widgets repurpose the
arrow keys entirely: a thermostat slot adjusts setpoint, a fan slot adjusts speed, a media player
slot adjusts volume and skips tracks.

The slot picker works either direction — pick a widget type first and then a matching entity, or
pick an entity first and see only the widget types it actually supports. A grab-move can cross a
split pane's boundary without letting go of what you're carrying.

## Device / area tree

`D` opens a full registry tree, grouped by device, area, or integration (`v` cycles), with a
filter scoped to just one of those levels. It's not read-only: reassign a device to a different
area, create or rename areas, or spin up a new dashboard from everything in an area with one key.

## Activity log

A dockable logbook panel, on both the entity table (`a`/`i`) and the fullscreen graph (`a`), with
scope cycling, time-window paging, and live streaming as events happen. Device events (a Zigbee
button press, say) get marked `⚡` in the log list.

Home Assistant's own logbook quietly omits continuous sensors (temperature, humidity, power) — so
hatty synthesizes their log entries from history instead. The REST and WebSocket logbook APIs
disagree about entry shape; one normalizer resolves that so nothing downstream has to care which
one answered.

## Controls

`e` opens dedicated live-apply screens for lights (brightness, kelvin, color swatches/picker,
effects) and media players (volume, transport, source), plus a lighter field popup for fans,
climate, covers, locks, and number inputs. Every control is capability-gated against what the
entity actually reports, so the light's tabs don't flicker as it turns on and off, and the media
player's footer never shows a button the device doesn't have.

Weather entities get a fullscreen multi-day forecast with tabs for whatever ranges the entity
supports (daily/twice-daily/hourly) — fetched live via `weather.get_forecasts`, since modern Home
Assistant no longer keeps a forecast attribute populated on the entity itself.

## Alerts

Watch any entity for changes via the reserved `🔔 Notifications` list (or promote any list you
already have into a notification source). Channels: in-app toast, terminal beep, desktop
notification, ntfy push, and a highlighted row in the table — configurable independently.

## Setup & storage

First run walks you through a connection wizard with a live test; after that, an in-app config
screen covers connection, theme, graph defaults, columns, terminal/tmux title, and ntfy. Storage
is two-tier: a lean, hand-editable `config.yaml` for connection and display settings, and a SQLite
database next to it for the things that actually grow — lists, dashboards, saved graphs, entity
name overrides. Lost connection to HA reconnects automatically. `ctrl+p` opens a command palette,
`?` a live cheat-sheet of every key on the current screen.

## Install

From source, with [uv](https://docs.astral.sh/uv/):

```bash
git clone <this-repo> && cd hatty
uv sync
uv run hatty --demo   # or: cp config.example.yaml config.yaml, then uv run hatty
```

This release also attaches an sdist, a wheel, and standalone Linux binaries
(`hatty-linux-x86_64`, `hatty-linux-aarch64`) — no Python required for the binaries. **Not yet
on PyPI**: `uv tool install hatty` and `pipx install hatty` don't work yet.

## Rough edges

- Pre-release (`v0.x`) — expect breaking changes to config/storage shape between minor versions.
- No PyPI package yet; source or the attached binaries only.
- Release binaries are Linux-only (x86_64, aarch64).
- Split dashboard panes nest one level deep.
- Alerts fire on state changes only — no threshold or duration conditions yet.
