#!/bin/sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
python_cmd=${PYTHON3:-"$repo_root/.venv/bin/python"}
if [ ! -x "$python_cmd" ]; then python_cmd=${PYTHON3:-"$repo_root/.local/venv/bin/python"}; fi
if [ ! -x "$python_cmd" ]; then python_cmd=python3; fi
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/gnw-tests.XXXXXX")
trap 'rm -rf "$test_dir"' EXIT HUP INT TERM
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
 -ICore/Inc/porting/nes_fceu tests/mario/test_battery.c -o "$test_dir/test-battery"
"$test_dir/test-battery"
"$python_cmd" tests/mario/test_storage_and_battery.py "$repo_root"
"$python_cmd" tests/mario/test_power_setting.py "$repo_root"

"$python_cmd" -m unittest discover -s tests/tools -v
