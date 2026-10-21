#!/bin/sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
python_cmd=${PYTHON3:-"$repo_root/.local/venv/bin/python"}
if [ ! -x "$python_cmd" ]; then python_cmd=python3; fi
if [ -z "${GCC_PATH:-}" ]; then
  archive="$repo_root/.local/toolchains/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi.tar.xz"
  toolchain="$repo_root/.local/toolchains/arm-gnu-toolchain-14.2.rel1-darwin-arm64-arm-none-eabi"
  if [ ! -x "$toolchain/bin/arm-none-eabi-gcc" ]; then
    "$python_cmd" - "$archive" <<'PY'
import hashlib,json,sys
from pathlib import Path
expected=json.loads(Path('config/mario-toolchain.json').read_text())['archive_sha256']
if hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()!=expected: raise SystemExit('Toolchain archive hash mismatch')
PY
    tar -xJf "$archive" -C "$repo_root/.local/toolchains"
  fi
  GCC_PATH="$toolchain/bin"
fi
if [ ! -f Drivers/STM32H7xx_HAL_Driver/Inc/stm32h7xx_hal.h ]; then
  make GNW_TARGET=mario download_sdk
fi
exec make -j"${JOBS:-8}" GNW_TARGET=mario EXTFLASH_SIZE_MB=1 INTFLASH_BANK=1 \
 STATE_SAVING=1 DISABLE_SPLASH_SCREEN=1 CHEAT_CODES=0 NES_BATTERY_SAVE=1 \
 GCC_PATH="$GCC_PATH" PYTHON3="$python_cmd" "$@"
