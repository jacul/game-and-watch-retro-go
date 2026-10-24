#!/bin/sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"
for argument in "$@"; do
  case "$argument" in
    all|*=*) ;;
    *) echo 'This wrapper builds firmware only. Pass make variable assignments or all.' >&2; exit 1 ;;
  esac
done
if [ -n "${PYTHON3:-}" ]; then
  python_cmd=$PYTHON3
elif [ -x "$repo_root/.venv/bin/python" ]; then
  python_cmd="$repo_root/.venv/bin/python"
elif [ -x "$repo_root/.local/venv/bin/python" ]; then
  python_cmd="$repo_root/.local/venv/bin/python"
else
  echo 'Run ./scripts/setup_macos.sh first, or set PYTHON3 to a Python 3.11 environment.' >&2
  exit 1
fi
"$python_cmd" -c 'import sys; assert (3, 11, 8) <= sys.version_info < (3, 12), "Python 3.11.8 or later within 3.11 is required"'
"$python_cmd" - <<'CHECK'
from importlib.metadata import version
from pathlib import Path
for line in Path('config/mario-requirements.lock.txt').read_text().splitlines():
    if line and not line.startswith('#'):
        name, expected = line.split('==')
        if version(name) != expected:
            raise SystemExit('Dependency version differs: ' + name + '. Run scripts/setup_macos.sh.')
CHECK
if [ -z "${GCC_PATH:-}" ]; then
  GCC_PATH=$("$python_cmd" -m tools.gnw.toolchain)
fi
export GCC_PATH
"$python_cmd" - "$GCC_PATH" "$@" <<'CHECK'
import hashlib, json, subprocess, sys
from pathlib import Path
config = json.loads(Path('config/mario-toolchain.json').read_text())
compiler = Path(sys.argv[1]) / 'arm-none-eabi-gcc'
actual = subprocess.check_output([str(compiler), '-dumpfullversion'], text=True).strip()
if actual != config['compiler_version']:
    raise SystemExit('Use Arm GNU Toolchain ' + config['name'] + '; found GCC ' + actual)
contents = json.dumps({'gcc': actual, 'compiler': str(compiler.resolve()), 'arguments': sys.argv[2:],
                      'script': hashlib.sha256(Path('scripts/build_mario_custom.sh').read_bytes()).hexdigest()}, sort_keys=True) + '\n'
p = Path('.local/mario-build-options.json')
p.parent.mkdir(exist_ok=True)
if not p.exists() or p.read_text() != contents:
    # Apple make 3.81 compares whole seconds. Remove stale objects before make starts.
    for obj in Path('build').rglob('*.o'):
        obj.unlink()
    Path('build/roms.a').unlink(missing_ok=True)
    p.write_text(contents)
from scripts.update_rom_files import update
if update(Path('build/rom_files.txt'), [Path('roms')]):
    Path('build/roms.a').unlink(missing_ok=True)
CHECK
make_cmd=${MAKE:-make}
"$make_cmd" GNW_TARGET=mario download_sdk
"$make_cmd" -j"${JOBS:-8}" GNW_TARGET=mario EXTFLASH_SIZE_MB=1 INTFLASH_BANK=1 \
 STATE_SAVING=1 DISABLE_SPLASH_SCREEN=1 CHEAT_CODES=0 NES_BATTERY_SAVE=1 DEBUG=1 \
 CUSTOM_BUILD_CONFIG=.local/mario-build-options.json \
 GCC_PATH="$GCC_PATH" PYTHON3="$python_cmd" "$@"
"$python_cmd" - <<'METADATA'
import hashlib, json, subprocess
from pathlib import Path
names = ('gw_retro_go.elf', 'gw_retro_go_intflash.bin', 'gw_retro_go_extflash.bin')
info = {'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'])),
        'compiler_version': json.loads(Path('.local/mario-build-options.json').read_text())['gcc'],
        'sha256': {name: hashlib.sha256((Path('build') / name).read_bytes()).hexdigest() for name in names}}
Path('build/source-info.json').write_text(json.dumps(info, indent=2) + '\n')
METADATA
