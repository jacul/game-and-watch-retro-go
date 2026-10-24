"""Capture current Zelda data using a verified installed package and RAM helper."""
import argparse
import json
from pathlib import Path
from .common import hashes, make_connection, require
from .install_zelda import read_checked
from .prepare_zelda import BASE, SIZE, sha


def capture(backend, device, previous, output):
    manifest = json.loads((previous / 'manifest.json').read_text())
    expected_int = read_checked(previous, 'gw_retro_go_intflash.bin', manifest)
    expected_ext = read_checked(previous, 'external-with-saves.bin', manifest)
    layout = json.loads(read_checked(previous, 'layout.json', manifest))
    start = layout['journal_start']
    opened = False
    try:
        backend.open(); opened = True; backend.set_frequency(100000)
        require(device._get_status() == 'IDLE', 'Start the verified RAM helper first')
        device._gnwmanager_started = True
        require(device.external_flash_size == SIZE and device.external_flash_block_size == 4096, 'Unexpected Zelda flash')
        internal = device.read_memory(0x08000000, 262144)
        require(internal[:len(expected_int)] == expected_int, 'Current internal firmware differs from installed package')
        print('Installed firmware matches. Reading current journals, snapshots, and settings.', flush=True)
        tail = device.read_memory(BASE + start, SIZE - start)
        require(len(tail) == SIZE - start, 'Incomplete mutable flash read')
        external = expected_ext[:start] + tail
        require(device.read_hashes(0, SIZE) == hashes(external), 'Reconstructed full backup differs from device hashes')
        require(int.from_bytes(external[-4096 + 16:-4096 + 20], 'little') in (0, 0xffffffff),
                'Return to the game selection menu before updating')
        output.mkdir(parents=True, exist_ok=False)
        files = {'bank1.bin': internal, 'external.bin': external}
        for name, data in files.items():
            (output / name).write_bytes(data)
        (output / 'layout.json').write_text(json.dumps(layout, indent=2) + '\n')
        records = {name: dict(size=len(data), sha256=sha(data)) for name, data in files.items()}
        records['layout.json'] = dict(size=(output / 'layout.json').stat().st_size, sha256=sha((output / 'layout.json').read_bytes()))
        (output / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
        print('Current Zelda backup verified against every device flash hash. No flash writes occurred.', flush=True)
        print('Reload and start the RAM helper before installing from a new process; do not reuse its command sequence.', flush=True)
    finally:
        if opened:
            backend.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    backend, device = make_connection()
    capture(backend, device, args.previous, args.output)
