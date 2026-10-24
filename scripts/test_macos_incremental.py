"""Check a real incremental build in a checkout containing only the CI fixture."""
import argparse
import subprocess
import sys
from pathlib import Path

# Running a script sets sys.path to scripts/, rather than the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.gnw.common import require
from tools.gnw.elf import rom_identities
from tools.gnw.install import read_images
from tools.gnw.layout import symbols
from tools.gnw.package import create


def run(baseline):
    fixture = Path('roms/nes/ci-fixture.nes')
    require(list(Path('roms/nes').glob('*.nes')) == [fixture],
            'Incremental smoke test requires an isolated checkout with only the CI ROM')
    _, before = read_images(baseline)
    # Derive a test-only profile. This does not add a validated installer profile.
    sym = symbols(baseline / 'gw_retro_go.elf')
    profile = {'external_base': 0x90000000,
               'save_symbols': {name: [address - 0x90000000, size]
                                for name, (address, size) in sym.items() if name.startswith('SAVE_NES_')}}
    old = rom_identities(baseline / 'gw_retro_go.elf', profile)
    data = bytearray(fixture.read_bytes())
    require(data[:6] == b'NES\x1a\x01\x01' and len(data) == 24592,
            'Unexpected CI fixture')
    data[32] ^= 1
    fixture.write_bytes(data)
    subprocess.run(['./scripts/build_mario_custom.sh'], check=True)
    output = baseline.parent / (baseline.name + '-changed-rom')
    create(Path('build'), output)
    _, after = read_images(output)
    require(before != after, 'ROM edit did not change firmware')
    require(old != rom_identities(output / 'gw_retro_go.elf', profile),
            'ROM edit did not change compiled identity; compressed copy may be stale')
    archive_time = Path('build/roms.a').stat().st_mtime_ns
    subprocess.run(['./scripts/build_mario_custom.sh'], check=True)
    require(Path('build/roms.a').stat().st_mtime_ns == archive_time,
            'Unchanged ROM inputs triggered another ROM rebuild')
    print('PASS: ROM edit rebuilt compressed firmware; unchanged inputs skipped ROM regeneration')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    run(parser.parse_args().baseline)
