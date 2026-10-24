#!/bin/sh
set -eu
./scripts/setup_macos.sh
unset PYTHON3
./scripts/test_mario_custom.sh
./scripts/test_zelda_custom.sh
.venv/bin/python scripts/create_ci_rom.py --output roms/nes/ci-fixture.nes
./scripts/build_mario_custom.sh
.venv/bin/python -m tools.gnw.package --output .local/ci-package
.venv/bin/python scripts/test_macos_incremental.py --baseline .local/ci-package
