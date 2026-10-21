"""Update a verified baseline while retaining battery RAM, snapshots and settings.

Start the helper separately before invoking this command. Backups and image
folders are explicit arguments; no historical local paths are embedded.
"""
import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from .common import hashes, make_connection, padded, require
from .layout import load_profile, verify

INTERNAL = 'gw_retro_go_intflash.bin'
EXTERNAL = 'gw_retro_go_extflash.bin'


def read_images(directory):
    info = json.loads((directory / 'build-info.json').read_text())
    images = {}
    for name in (INTERNAL, EXTERNAL):
        data = (directory / name).read_bytes()
        require(hashlib.sha256(data).hexdigest() == info['sha256'][name], 'Image hash mismatch: ' + name)
        images[name] = data
    return info, images


def prepare(previous_dir, image_dir, profile):
    _, previous = read_images(previous_dir)
    info, images = read_images(image_dir)
    verify(previous_dir / 'gw_retro_go.elf', image_dir / 'gw_retro_go.elf', images[EXTERNAL], profile)
    require(len(padded(previous[EXTERNAL], profile['erase_size'])) == profile['mutable_start'],
            'Baseline does not cover the expected immutable prefix')
    require(len(padded(images[INTERNAL], 8192)) <= profile['internal_bank_size'], 'Internal image is too large')
    return info, previous, images


def install(backend, device, image_dir, backup_root, profile, prepared):
    info, previous, images = prepared
    opened = False
    try:
        backend.open()
        opened = True
        backend.set_frequency(100000)
        require(device._get_status() == 'IDLE', 'Start the verified RAM helper separately first')
        device._gnwmanager_started = True
        require(device.external_flash_size == profile['flash_size'], 'Device flash capacity differs')
        require(device.external_flash_block_size == profile['erase_size'], 'Erase size differs')
        backup = backup_root / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        backup.mkdir(parents=True, exist_ok=False)
        bank = device.read_memory(profile['internal_base'], profile['internal_bank_size'])
        (backup / 'bank1-before.bin').write_bytes(bank)
        require(bank[:len(previous[INTERNAL])] == previous[INTERNAL], 'Installed internal baseline differs')
        start = profile['mutable_start']
        tail = device.read_memory(profile['external_base'] + start, profile['flash_size'] - start)
        before = padded(previous[EXTERNAL], profile['erase_size']) + tail
        (backup / 'external-before.bin').write_bytes(before)
        require(len(before) == profile['flash_size'], 'External backup length differs')
        require(hashes(before) == device.read_hashes(0, len(before)), 'External backup hashes differ')
        pointer = profile['config_start'] + profile['startup_pointer_offset']
        require(int.from_bytes(before[pointer:pointer + 4], 'little') in (0, 0xFFFFFFFF),
                'Return to the game selection menu before updating')
        manifest = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                    for name, data in [('bank1-before.bin', bank), ('external-before.bin', before)]}
        (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        # Record only the session name, not a path that exposes the host machine.
        (image_dir / 'installation-pending.json').write_text(json.dumps({'backup_session': backup.name, 'status': 'writing'}, indent=2) + '\n')
        print('Current saves backed up and verified. Updating firmware.')
        device.flash(0, 0, images[EXTERNAL], progress=True, desc='Game & Watch firmware')
        device.flash(1, 0, images[INTERNAL])
        readback = device.read_memory(profile['internal_base'], len(images[INTERNAL]))
        require(readback == images[INTERNAL], 'Internal firmware readback differs')
        ext = padded(images[EXTERNAL], profile['erase_size'])
        require(device.read_hashes(0, len(ext)) == hashes(ext), 'External image hashes differ')
        after = device.read_memory(profile['external_base'] + start, len(tail))
        require(after == tail, 'Battery/snapshot/settings preservation check failed')
        result = {'installed_at_utc': datetime.now(timezone.utc).isoformat(), 'verification': 'passed',
                  'backup_session': backup.name, 'preserved_bytes': len(tail),
                  'internal_sha256': hashlib.sha256(readback).hexdigest(), 'gameplay_test': 'pending'}
        (image_dir / 'installation.json').write_text(json.dumps(result, indent=2) + '\n')
        (image_dir / 'installation-pending.json').unlink()
        info['flashed'] = True
        (image_dir / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n')
        device.reset()
        print('Firmware verified. Battery RAM, snapshots and settings are unchanged.')
        return result
    finally:
        if opened:
            backend.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--previous-dir', type=Path, required=True)
    parser.add_argument('--image-dir', type=Path, required=True)
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--helper-running', action='store_true', required=True,
                        help='Require an already running helper; this command does not load or reset it')
    args = parser.parse_args()
    profile = load_profile(args.profile)
    prepared = prepare(args.previous_dir, args.image_dir, profile)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    backend, device = make_connection()
    install(backend, device, args.image_dir, args.backup_dir, profile, prepared)


if __name__ == '__main__':
    main()
