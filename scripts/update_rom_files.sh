#!/bin/sh
set -eu
exec "${PYTHON3:-python3}" "$(dirname "$0")/update_rom_files.py" "$@"
