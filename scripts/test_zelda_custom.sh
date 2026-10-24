#!/bin/sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
python_cmd=${PYTHON3:-"$repo_root/.venv/bin/python"}
if [ ! -x "$python_cmd" ]; then python_cmd=${PYTHON3:-"$repo_root/.local/venv/bin/python"}; fi
"$python_cmd" tests/zelda/test_profile.py "$repo_root"
"$python_cmd" tests/zelda/test_cheats.py "$repo_root"
"$python_cmd" tests/zelda/test_gb_cheats.py "$repo_root"
"$python_cmd" tests/zelda/test_install.py
"$python_cmd" tests/zelda/test_migration.py
if [ -n "${GNW_DQ_ROM:-}" ]; then
 : "${GNW_DQ_SHA256:?Set GNW_DQ_SHA256 to the expected private ROM hash}"
 : "${GNW_DQ_CODES:?Set GNW_DQ_CODES to the private cheat preset file}"
 "$python_cmd" tests/zelda/test_dq_gold_rom.py --repo "$repo_root" --rom "$GNW_DQ_ROM" --sha256 "$GNW_DQ_SHA256" --codes "$GNW_DQ_CODES"
else
 echo 'SKIP: optional DQ ROM-routine test needs explicit private ROM, hash, and preset inputs.'
fi
