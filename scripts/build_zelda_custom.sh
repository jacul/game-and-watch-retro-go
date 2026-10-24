#!/bin/sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
: "${GCC_PATH:?Set GCC_PATH to Arm GNU Toolchain 14.2.Rel1 bin}"
python_cmd=${PYTHON3:-"$repo_root/.venv/bin/python"}
if [ ! -x "$python_cmd" ]; then python_cmd=${PYTHON3:-"$repo_root/.local/venv/bin/python"}; fi
config_dir=${GNW_ZELDA_CONFIG_DIR:-"$repo_root/.local/config/zelda"}
copy_changed() {
 if ! cmp -s "$1" "$2"; then cp "$1" "$2"; fi
}
for system in nes gb; do
 test -f "$config_dir/$system.json" || { echo "Set GNW_ZELDA_CONFIG_DIR to your private ROM configurations." >&2; exit 1; }
 copy_changed "$config_dir/$system.json" "roms/$system.json"
 for codes in "$config_dir/$system/"*.ggcodes; do
  [ -f "$codes" ] || continue
  copy_changed "$codes" "roms/$system/$(basename "$codes")"
 done
done
export GCC_PATH
"${MAKE:-make}" GNW_TARGET=zelda download_sdk
exec make -j"${JOBS:-8}" GNW_TARGET=zelda EXTFLASH_SIZE_MB=4 INTFLASH_BANK=1 \
 STATE_SAVING=1 DISABLE_SPLASH_SCREEN=1 CHEAT_CODES=1 NES_BATTERY_SAVE=0 \
 GB_BATTERY_SAVE=1 GB_BATTERY_BYTES=172032 COMPRESS=lzma COVERFLOW=0 CHECK_DIRTY_SUBMODULE=0 \
 GCC_PATH="$GCC_PATH" PYTHON3="$python_cmd" "$@"
