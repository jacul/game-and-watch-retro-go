#!/bin/sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
for rom in Metal_Max_cn.nes Tank_90.nes Tetris.nes; do test -f "roms/nes/$rom"; done
config=${GNW_MARIO_ROM_CONFIG:-"$repo_root/.local/config/mario-tank-roms.json"}
test -f "$config" || { echo "Set GNW_MARIO_ROM_CONFIG to your private ROM configuration." >&2; exit 1; }
if ! cmp -s "$config" roms/nes.json; then cp "$config" roms/nes.json; fi
exec ./scripts/build_mario_custom.sh "$@"
