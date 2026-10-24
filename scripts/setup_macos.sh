#!/bin/sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
  echo 'Automatic setup currently supports Apple Silicon macOS.' >&2
  exit 1
fi
xcode-select -p >/dev/null 2>&1 || {
  echo 'Install Command Line Tools with: xcode-select --install' >&2; exit 1;
}
python_cmd=${PYTHON3:-python3.11}
command -v "$python_cmd" >/dev/null 2>&1 || {
  echo 'Install Python 3.11, for example: brew install python@3.11' >&2; exit 1;
}
"$python_cmd" -c 'import sys; assert (3, 11, 8) <= sys.version_info < (3, 12), "Python 3.11.8 or later within 3.11 is required"'
if [ ! -x .venv/bin/python ]; then "$python_cmd" -m venv .venv; fi
.venv/bin/python -c 'import sys; assert (3, 11, 8) <= sys.version_info < (3, 12), "Existing .venv must use Python 3.11.8 or later within 3.11"'
.venv/bin/python -m pip install -r config/mario-requirements.lock.txt
.venv/bin/python -m tools.gnw.toolchain
git submodule update --init --recursive
echo 'Setup complete. See docs/MACOS.md for build and package commands.'
