#!/bin/bash
# hatty — MIT License. See LICENSE file for details.
# Build the standalone PyInstaller binary -> dist/hatty
set -euo pipefail
cd "$(dirname "$0")/.."
uv run pyinstaller --noconfirm hatty.spec
echo "Built: $(ls -lh dist/hatty | awk '{print $9, "("$5")"}')"
