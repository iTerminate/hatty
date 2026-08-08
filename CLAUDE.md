# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Commands

```bash
uv run hatty                          # Run with default config
uv run hatty -c /path/to/config.yaml  # Run with custom config
uv run hatty --debug                  # Textual debug logging to debug.log
uv run hatty --demo                   # Offline against curated fake data, no HA needed
pytest                                # Full suite
pytest tests/unit                     # Fast unit-only, no Textual app boot
uv sync                               # Create/update .venv with the dev group
uv build                              # sdist + wheel
sbin/build-binary.sh                  # PyInstaller standalone (hatty.spec)
sbin/record-demo.sh                   # Re-record docs/demo.cast + demo.gif from --demo
```

Dependencies are managed by **uv** (`pyproject.toml` + committed `uv.lock`, no requirements.txt).
Console script `hatty` → `hatty.cli:main`, a thin entry applying `--debug` before importing the
Textual app. `--demo` serves data from `src/hatty/demo/` through `DemoHAClient`, which echoes each
`call_service` back as a `state_changed` event (interactive, but a static snapshot — writes nothing
to disk). Nothing is published to PyPI yet.

hatty is an independent reimplementation of `../ha-cli`'s BUILD_PLAN.md spec — same conventions,
separate codebase, not a port of ha-cli's source.

## Architecture

```
User Keybindings → HACLI (main.py) → HAClient (client.py) ↔ Home Assistant WebSocket
                                          ↓
                         _update_entities_display() → EntitiesTable
```

Domain state lives on controllers instantiated in `HACLI.__init__`, each holding one slice and
taking an injected app reference: `controllers/lists.py` (`app.list_ctl`), `dashboards.py`
(`app.dash_ctl`), `graphs.py` (`app.graph_ctl`), `connection.py` (`app.conn_ctl` — the HA websocket
message pump, `handle_ha_message`/`_HA_MESSAGE_HANDLERS`), `notifications.py` (`app.notify_ctl`),
`logbook.py` (`app.log_ctl` — the activity log's scope/paging/fetch/subscription state machine,
shared by `HACLI`'s docked panel and `GraphPreviewScreen`'s). **`HACLI` keeps its old attribute surface
via property pairs** (`app.dashboards`, `app.current_list_name`, `app._detail_entity_id`, …) so
screens and tests read/assign through the app unchanged; new UI code should call controllers
directly instead (`self.app.dash_ctl.set_slot(...)`).

**Two-tier config persistence.** `config.yaml` is lean — connection settings and display
preferences only. The user-data collections (`lists`, `entity_names`, `dashboards`, `saved_graphs`,
`manual_lists`, `default_list`, `default_dashboard` — the exact set is `storage.COLLECTION_KEYS`)
live in SQLite (`src/hatty/storage.py`, `Storage`) at `<config dir>/hatty.db`. SQLite is
authoritative: on boot the DB's collections are loaded back over the YAML config, and every save
strips collection keys from the YAML while writing them to the DB in one transaction. See
`storage.py`'s module docstring for the collection shapes.

**Test/demo injection seam**: `HACLI._client_factory` is where the test suite's `FakeHAClient` and
`--demo`'s `DemoHAClient` both replace the real `HAClient` — `DemoHAClient` is signature-parity-tested
against it.

Entity dicts follow the `Entity`/`EntityAttributes` TypedDicts in `src/hatty/types.py`; pass entity
params typed as `Entity` (not bare `dict`) and read `total=False` fields via `.get(...)`.
`const.py`/`types.py` import nothing from the app, so they stay cycle-safe.

## Layout

- `src/hatty/main.py` — the `HACLI` Textual app: keybindings, message routing, entity-table state,
  cross-cutting plumbing (`spawn(coro)` for tracked fire-and-forget tasks — never bare
  `asyncio.create_task`; `persist(*keys)` to mirror + save a collection).
- `src/hatty/controllers/` — the four controllers above.
- `src/hatty/client.py` — `HAClient`: websocket auth/requests, REST history/logbook fetchers (swallow
  errors, return `None`).
- `src/hatty/config.py` / `storage.py` — YAML config and SQLite collection persistence.
- `src/hatty/const.py` / `types.py` / `service_calls.py` — shared constants, entity TypedDicts, and
  the pure per-domain functions that build `call_service` data for entity controls.
- `src/hatty/ui/` — screens and popups, one module per surface (entity table, dashboard grid +
  widgets, device/area tree, graph panel/fullscreen/preview, per-domain control screens, config,
  onboarding). Each module's own docstring is the source of truth for its behavior — read the file
  before describing it.
- `src/hatty/ui/popup_base.py` — shared modal scaffolding (`PopupScreen`, `ListPopup`); new popups
  should subclass these rather than hand-rolling styling.

## Conventions

- Every source file (`.py` under `src/`/`tests/`, shell scripts under `sbin/`) starts with the
  license header `# hatty — MIT License. See LICENSE file for details.` as the first line (or right
  after a `#!` shebang).
- `uv run pyright` runs in CI (`.gitea/workflows/test.yml`) and must pass before pushing, alongside
  `uv run ruff check .`. It's `basic` mode over `src/hatty` with every basic-mode category enabled,
  including `reportOptionalMemberAccess`/`reportAttributeAccessIssue`/`reportArgumentType` — don't
  write code that fires any of them.
- Every popup/widget uses inline `DEFAULT_CSS`, no external stylesheets.
- Commit messages: concise, usually a single line.
- When implementing a plan with multiple milestones: commit (and push, if asked) after each
  milestone once its tests pass, and run the full `pytest` suite after the final milestone before
  reporting the plan complete.

## Testing

- `tests/unit/` — pure logic, no live Textual app required.
- `tests/` (top-level) — acceptance tests booting the real `HACLI` app via Textual's `Pilot` and a
  `FakeHAClient` (see `tests/conftest.py`). No test touches a real Home Assistant instance.
- Verifying against a real HA instance (auth handshake, real `call_service` effects, real history) is
  a manual step: fill in `~/.config/hatty/config.yaml` from `config.example.yaml`, then `uv run hatty`.
- **Always ask before interacting with a real Home Assistant instance.** Running `uv run hatty`
  against a real config connects to live HA and can call real services — e.g. flipping a real switch
  — not just read state. Get explicit confirmation first, even for "just verifying the fix."

## Wiki

User-facing documentation (quick start guide, screen-by-screen walkthrough) lives in a **separate,
supplemental git repository** — a self-hosted Gitea/Forgejo wiki. It is not part of this repo's
history; `CLAUDE.md` and `README.md` remain the canonical engineering docs here. The wiki remote is
configured locally but not recorded here — ask before assuming its location.

To edit the wiki (clone URL kept out of this file — check your local remotes or ask):

```bash
git clone <wiki-remote> wiki   # first time only; wiki/ is gitignored
cd wiki
# edit/add .md pages
git add -A && git commit -m "..."
git push origin main
```

Conventions: `Home.md` is the landing page; other pages use `Dash-Case.md` filenames and link to
each other with bare filenames (no `.md` extension), e.g. `[Quick Start](Quick-Start)`. Current
pages: `Home.md`, `Quick-Start.md`, `Screens-and-Pages.md`.
