# hatty

**hatty — a TTY for your HA.**

Your whole smart home, live, in a terminal. hatty connects to Home Assistant over WebSocket (first-run setup wizard, auto-reconnect) and gives you:

- A live-updating table of every entity — search, favorite lists, or browse by device/area in a tree
- Dedicated live-apply controls for lights, media players, and other entity attributes
- Sensor/thermostat history as sparklines or a fullscreen graph, with multi-entity comparison and saved configs
- Customizable **dashboards** of widgets — graphs, gauges, thermostats, panels — freely resized and split across tiles

## Demo

![hatty demo](docs/demo.gif)

A scripted tour of the offline `--demo` mode — search, live light control, sparkline and
comparison graphs, a widget dashboard, and the device activity log. Recorded with
`sbin/record-demo.sh` (drives the TUI under `asciinema` and renders the GIF with `agg`); re-run
it to regenerate `docs/demo.cast` + `docs/demo.gif` after UI changes.

## Installation

From source (requires [uv](https://docs.astral.sh/uv/)):

```bash
git clone <this-repo>
cd hatty
uv sync
cp config.example.yaml config.yaml   # then fill in your HA url + long-lived access token
uv run hatty                         # add --debug to log Textual internals to debug.log
```

### Try it without Home Assistant

```bash
uv run hatty --demo
```

Boots offline against a curated fake dataset — entities across every domain, pre-built
lists/dashboards/saved graphs, and generated history. Fully interactive (toggles, thermostat, light
control all respond), a static snapshot, and writes nothing to disk. Great for a first look or
screenshots.

### Coming soon (not yet published)

Once the first release is out, these will be the supported install paths — **they do not work yet**:

```bash
uv tool install hatty   # or run without installing: uvx hatty
pipx install hatty
```

Or grab the standalone binary (no Python required) from this repository's Releases page:

```bash
curl -LO <releases-page>/download/vX.Y.Z/hatty-linux-aarch64
chmod +x hatty-linux-aarch64
./hatty-linux-aarch64
```

Each tagged release ships an sdist, a wheel, and a standalone binary built by the release workflow.

## Configuration

`config.yaml` is searched for at: an explicit `-c` path, then `~/.config/hatty/config.yaml`, then `./config.yaml`. You can also skip it entirely and let the first-run setup wizard create it.

```yaml
home_assistant:
  url: "http://homeassistant.local:8123"
  token: "YOUR_LONG_LIVED_ACCESS_TOKEN"
columns: ["name", "value", "last_changed", "in_list"]
theme: null
graph_type: line
graph_hours: 4
```

The YAML is lean — connection settings and display preferences only. Your favorite lists, entity-name overrides, dashboards, and saved graphs live in a small SQLite database (`hatty.db`) created next to the config file, not in the YAML.

## Keybindings

| Key      | Action                                  |
|----------|------------------------------------------|
| `/`      | Search entities                          |
| `enter`  | Toggle selected switch/light             |
| `space`  | Add/remove selected entity from the current list |
| `r`      | Rename selected entity (locally or in Home Assistant) |
| `l`      | Open list selection/management popup     |
| `d`      | Dashboard view                           |
| `D`      | Device / area tree                       |
| `g` / `G`| Sparkline graph panel / fullscreen graph |
| `e`      | Open controls (light, media player, attributes) |
| `escape` | Clear search, exit list filter, or close popups |
| `ctrl+q` | Quit                                     |

Press `?` in-app for a live cheat-sheet of every key on the current screen. Full reference: Keybindings, on the project wiki.

## Development

### Prerequisites

Install [uv](https://docs.astral.sh/uv/) — it manages the Python interpreter and virtualenv for
you, no separate install needed. `pyproject.toml` requires Python `>=3.11`; CI runs on 3.13.

### Set up the environment

```bash
git clone <this-repo>
cd hatty
uv sync                   # creates .venv with runtime deps + dev tools (pytest, ruff, pyright, pyinstaller)
uv run hatty --demo       # sanity-check the setup with the offline demo (no HA needed)
```

`uv run` uses the editable install directly — no venv activation or `PYTHONPATH` juggling
required for any command below.

### Before you push

These are the same checks CI runs (`.gitea/workflows/test.yml`), in order:

```bash
uv run ruff check .        # lint (add --fix to auto-fix)
uv run pyright             # type check (basic mode over src/hatty)
uv run pytest              # full suite
uv run pytest tests/unit   # fast unit tests only, no Textual app boot
```

```bash
uv build                   # sdist + wheel in dist/
```

See `CLAUDE.md` for architecture details.

## License

hatty is released under the [MIT License](LICENSE).

---

**hatty — your smart home, wearing a terminal.** 🎩
