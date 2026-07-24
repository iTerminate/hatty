#!/bin/bash
# hatty — MIT License. See LICENSE file for details.
# Record a scripted screencast of `uv run hatty --demo` -> docs/demo.cast + docs/demo.gif
set -euo pipefail
cd "$(dirname "$0")/.."

# ── Config ───────────────────────────────────────────────────────────────────
SESSION="hatty-demo"
COLS=110
ROWS=32
CAST="docs/demo.cast"
GIF="docs/demo.gif"
AGG_VERSION="v1.9.0"
# Pinned SHA-256 of the agg-<arch>-unknown-linux-gnu release asset for AGG_VERSION,
# verified before the downloaded binary is made executable (issue #159). Update
# these alongside AGG_VERSION. Values computed from the published release binaries.
declare -A AGG_SHA256=(
    [aarch64]="2b4be407b97e00e1c313a41d154ced8fa3d02c560c8f47a0db4950a2576444c9"
    [x86_64]="f111e315cd71056b116302342553dd765b7297579ed511f111d0cedb442aeda6"
)

mkdir -p docs dist

# ── Ensure agg (asciinema cast -> gif) ───────────────────────────────────────
# No cargo/npm here, so fall back to the prebuilt aarch64 release binary cached
# under the already-gitignored dist/.
if command -v agg >/dev/null 2>&1; then
    AGG="agg"
else
    AGG="dist/agg"
    if [ ! -x "$AGG" ]; then
        ARCH="$(uname -m)"
        EXPECTED_SHA="${AGG_SHA256[$ARCH]:-}"
        if [ -z "$EXPECTED_SHA" ]; then
            echo "ERROR: no pinned agg SHA-256 for arch '$ARCH'; refusing to run an unverified binary." >&2
            exit 1
        fi
        echo "Downloading agg $AGG_VERSION ..."
        curl -fL --retry 3 -o "$AGG" \
            "https://github.com/asciinema/agg/releases/download/${AGG_VERSION}/agg-${ARCH}-unknown-linux-gnu"
        # Verify integrity BEFORE making the binary executable — a compromised
        # release asset or MITM must not run arbitrary code (issue #159).
        if ! echo "${EXPECTED_SHA}  ${AGG}" | sha256sum -c - >/dev/null 2>&1; then
            echo "ERROR: agg checksum mismatch — expected ${EXPECTED_SHA}, got $(sha256sum "$AGG" | cut -d' ' -f1)." >&2
            rm -f "$AGG"
            exit 1
        fi
        chmod +x "$AGG"
    fi
fi

# ── Choreography helpers ─────────────────────────────────────────────────────
# key <sleep_secs> <send-keys args...>   send keystrokes to the recorded pane, then pause.
key() {
    local delay="$1"; shift
    tmux send-keys -t "$SESSION" "$@"
    sleep "$delay"
}
# type <sleep_secs> <literal string>     send literal text (spaces, /, +) verbatim.
type() { key "$1" -l "$2"; }

# ── Record ───────────────────────────────────────────────────────────────────
tmux kill-session -t "$SESSION" 2>/dev/null || true
rm -f "$CAST"

echo "Recording ${CAST} (${COLS}x${ROWS}) ..."
tmux new-session -d -s "$SESSION" -x "$COLS" -y "$ROWS"
# new-session -x/-y is advisory when no client is attached; pin the exact size so the
# recorded pty (and thus the GIF) is a stable COLSxROWS grid.
tmux set-option -t "$SESSION" window-size manual \; resize-window -t "$SESSION" -x "$COLS" -y "$ROWS"
# asciinema records the pane's pty; tmux send-keys below drives hatty through it.
# COLORTERM=truecolor makes Textual emit 24-bit color, so the Catppuccin Mocha theme
# (selected below) renders as its exact palette in the GIF rather than a 256-color remap.
tmux send-keys -t "$SESSION" \
    "COLORTERM=truecolor uvx asciinema rec --overwrite --idle-time-limit 2 -c 'COLORTERM=truecolor uv run hatty --demo' '$CAST'" Enter

sleep 9   # uvx resolve + app boot + held splash (DEMO_SPLASH_SECONDS) -> populated entity table ("hatty — DEMO")

# 0. Switch to the Catppuccin Mocha theme via the command palette (Ctrl+P). The rest
# of the demo then renders in that theme.
key 1.5 C-p                          # open the command palette
type 1.5 "theme"                     # filter to "Change the current theme"
key 2.0 Enter                        # run it -> theme picker
type 2.0 "mocha"                     # filter to catppuccin-mocha
key 2.5 Enter                        # apply the theme
sleep 0.8

# Escape discipline: `/` always clears+opens the search box, so the ONLY safe way to clear a
# filter is `/` then Escape (box visible -> hide+clear). A bare Escape at the main table with
# no active filter falls through to the "Leave list?" confirm (a default list is always
# active in demo) and swallows every later key — so never press a second Escape at the table.

# 1. Live search filter, then clear it
type 0.4 "/"; sleep 0.6
type 0.25 "t"; type 0.25 "e"; type 0.25 "m"; type 0.25 "p"; sleep 2.0
key 1.4 Escape                       # box visible -> hide + clear (safe)

# 2. Toggle a switch (Coffee Maker off -> on; demo client echoes state_changed)
type 0.4 "/"; type 0.2 "c"; type 0.2 "o"; type 0.2 "f"; key 0.8 Enter
sleep 1.0
key 1.8 Enter                        # toggle the switch on

# 3. Add the selected entity to the current list (In List ✓ column)
key 1.6 Space                        # add to list
key 1.6 Space                        # remove again

# 4. Light control screen (live-apply presets + on/off)
type 0.4 "/"; type 0.2 "l"; type 0.2 "a"; type 0.2 "m"; type 0.2 "p"; key 0.8 Enter
sleep 0.8
key 1.6 "e"                          # -> LightControlScreen
type 1.6 "2"                         # Neutral white preset
type 1.6 "3"                         # Cool white preset
key 1.4 Space                        # power off
key 1.8 Space                        # power on
key 1.2 Escape                       # dismiss LightControlScreen (its own escape)

# 5. Graph pop-up while browsing the Living Room list (renders as a line via graph_type).
# Beat 4 left the cursor on the Lamp (row 2); clearing the filter keeps it, so two
# Downs land on Living Room Temperature (row 4) without a search filter.
type 0.4 "/"; key 1.2 Escape         # clear the "lamp" filter -> full Living Room list
key 1.0 Down                         # Lamp -> Motion
key 1.6 Down                         # Motion -> Living Room Temperature
key 3.0 "g"                          # inline line graph pop-up over the list rows
key 2.4 "G"                          # fullscreen line graph
key 1.4 Escape                       # dismiss fullscreen graph (its own escape)
key 1.2 "g"                          # close inline panel

# 6. Saved comparison graph ("Temperatures": two series over 12h)
key 1.6 "s"                          # SavedGraphsPopup
key 2.0 Enter                        # open the highlighted saved graph
sleep 1.6
key 1.4 Escape                       # dismiss fullscreen graph (its own escape)

# 7. Clear the lingering filter before switching lists
type 0.4 "/"; key 1.2 Escape         # box visible -> hide + clear (safe)

# 8. Switch the active list (table repopulates with the "Climate" list).
# The ListView starts with nothing highlighted, so the first Down just highlights
# item 0 (View All); three Downs land on Climate (View All -> Living Room -> Climate).
key 1.6 "l"                          # ListSelectionPopup
sleep 0.8                            # let the ListView mount + take focus
key 0.8 Down                         # highlight "View All"
key 0.8 Down                         # -> "Living Room"
key 1.0 Down                         # -> "Climate"
key 2.0 Enter                        # select "Climate" (dismisses popup)

# 9. Dashboard view ("Home" 3x4 widget grid), including the weather forecast expand
key 1.8 "d"                          # DashboardScreen
key 1.0 Right                        # roam the grid cursor: thermostat -> Power Consumption
key 0.8 Right                        # -> Solar Production
key 1.0 Right                        # -> Home Weather (col 3)
key 1.6 "e"                          # -> WeatherForecastScreen (multi-day forecast strip)
sleep 1.6
key 1.4 Escape                       # dismiss forecast screen (its own escape) -> back to dashboard
key 1.0 Down                         # weather's row_span skips its footprint -> the empty (2,3) cell
key 1.6 Left                         # -> Front Door
key 1.0 Escape                       # -> "Leave dashboard?" confirm
key 1.4 "y"                          # confirm, back to table

# 10. Device / area tree (D): browse entities grouped by device, then by area
key 1.8 "D"                          # DeviceTreeScreen (grouped by device)
key 1.2 Down                         # roam the device tree
key 1.2 Down
key 1.6 "g"                          # switch to area grouping (Area -> Device -> Entity)
key 1.2 Down                         # roam the nested tree
key 1.4 Down
key 1.4 Escape                       # back to the main table

# 11. Device log grouping (living-room device siblings)
type 0.4 "/"; type 1.0 "living room temp"; key 0.8 Enter
sleep 0.6
key 2.2 "A"                          # Device Log panel
key 1.4 "A"                          # toggle it back off

# 12. Quit -> hatty exits -> asciinema stops and writes the cast
sleep 1.0
key 2.0 "q"

# Wait for asciinema to flush the cast, then tear down the session.
for _ in $(seq 1 20); do
    [ -s "$CAST" ] && break
    sleep 0.5
done
tmux kill-session -t "$SESSION" 2>/dev/null || true

if [ ! -s "$CAST" ]; then
    echo "ERROR: $CAST was not written (asciinema/hatty may have failed to start)." >&2
    exit 1
fi

# ── Convert to GIF ───────────────────────────────────────────────────────────
echo "Rendering ${GIF} ..."
"$AGG" "$CAST" "$GIF"

echo "Recorded: $CAST  ->  $GIF ($(du -h "$GIF" | cut -f1))"
