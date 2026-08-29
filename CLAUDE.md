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

## Architecture & layout

```
User Keybindings → HACLI (main.py) → HAClient (client.py) ↔ Home Assistant WebSocket
                                          ↓
                         _update_entities_display() → EntitiesTable
```

Controllers (`src/hatty/controllers/`, instantiated in `HACLI.__init__`; see each docstring):
`lists.py` (`app.list_ctl`, list state), `dashboards.py` (`app.dash_ctl`, dashboard grid/slots),
`graphs.py` (`app.graph_ctl`, history/detail/saved graphs), `connection.py` (`app.conn_ctl`, HA
websocket pump), `notifications.py` (`app.notify_ctl`, change alerts), `logbook.py` (`app.log_ctl`,
shared activity-log state), `keybindings.py` (`app.keys_ctl`, overrides), `backup.py`
(`app.backup_ctl`, Backup & Sync prefs).
`app.keys_ctl` pushes overrides via `App.set_keymap`; every screen's `BINDINGS = bindings_for(scope)`
from `REGISTRY` (single source for ~220 bindings), whose registry half is cycle-safe — see its
docstring.

`HACLI` keeps its old attribute surface via `_controller_proxy` property pairs (`app.dashboards`,
`app.current_list_name`, `app._detail_entity_id`, …); new code calls controllers directly
(`self.app.dash_ctl.set_slot(...)`). **Injection seam**: `HACLI._client_factory` swaps in
`FakeHAClient`/`DemoHAClient`.

Lists/dashboards/graphs each expose `to_export_payload`/`import_from_payload`; `backup.py`'s
directory export reuses those payloads and `git_sync.py` optionally treats it as a git repo — see
their docstrings. `config.yaml` stays lean; user-data collections (`storage.COLLECTION_KEYS`) live
in SQLite, authoritative over the YAML — see `storage.py`. Entity dicts follow the
`Entity`/`EntityAttributes` TypedDicts in `types.py`; read `total=False` fields via `.get(...)`;
`const.py`/`types.py` import nothing from the app (cycle-safe).

- `src/hatty/main.py` — `spawn(coro)` for tracked fire-and-forget (never bare
  `asyncio.create_task`); `persist(*keys)` to mirror + save a collection.
- `src/hatty/client.py` — `HAClient`: websocket auth/requests, REST history/logbook fetchers.
- `src/hatty/config.py`/`storage.py` — YAML config + SQLite; `const.py`/`types.py`/
  `service_calls.py` — constants, TypedDicts, `call_service` builders.
- `src/hatty/backup.py`/`git_sync.py` — directory export/import + git layer (above).
- `src/hatty/ui/` — one module per surface; module docstrings are the source of truth (read before
  describing). `ui/popup_base.py` — subclass `PopupScreen`/`ListPopup`, don't hand-roll styling.

## Conventions

- Every source file (`.py` under `src/`/`tests/`, shell scripts under `sbin/`) starts with the
  license header `# hatty — MIT License. See LICENSE file for details.` as the first line (or right
  after a `#!` shebang).
- `uv run pyright` runs in CI (`.gitea/workflows/test.yml`) and must pass before pushing, alongside
  `uv run ruff check .`. It's `basic` mode with every category enabled — see `[tool.pyright]` in
  `pyproject.toml`; don't write code that fires any pyright diagnostic.
- Every popup/widget uses inline `DEFAULT_CSS`, no external stylesheets.
- Commit messages: concise, usually a single line; after each milestone of a plan, commit (and push
  if asked) once its tests pass, and run the full `pytest` suite after the final milestone.

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
