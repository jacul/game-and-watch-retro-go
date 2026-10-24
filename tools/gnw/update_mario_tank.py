"""Replace Mario's SMB ROM with Tank and import verified Zelda Metal Max SRAM."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from .common import hashes, make_connection, padded, require
from .install import read_images, INTERNAL, EXTERNAL
from .layout import load_profile, verify_layout
from .elf import rom_identities, verify_images
from .migrate_mario_snapshot import make_record


def sha(data):
    return hashlib.sha256(data).hexdigest()


def make_image(old, firmware, save, rom, profile):
    require(len(old) == profile['flash_size'], 'Expected full Mario backup')
    start = profile['mutable_start']
    require(len(firmware) <= start, 'Firmware overlaps saves')
    result = bytearray(b'\xff' * len(old))
    result[:len(firmware)] = firmware
    result[start:] = old[start:]
    journal = make_record(save, rom) + b'\xff' * 12288
    require(len(journal) == profile['battery_end'] - start, 'Journal reservation differs')
    result[start:profile['battery_end']] = journal
    # Both games change state: Metal Max imports different SRAM; Tank replaces SMB.
    for symbol in ('SAVE_NES_2', 'SAVE_NES_0'):
        offset, size = profile['save_symbols'][symbol]
        result[offset:offset + size] = b'\xff' * size
    offset, size = profile['save_symbols']['SAVE_NES_1']
    require(result[offset:offset + size] == old[offset:offset + size], 'Tetris snapshot changed')
    require(result[profile['config_start']:] == old[profile['config_start']:], 'Settings changed')
    return bytes(result)


def prepare(previous, build, roms, save_path, save_info, output):
    profile = load_profile('mario-stock-1mb')
    _, old = read_images(previous)
    images = {name: (build / name).read_bytes() for name in (INTERNAL, EXTERNAL)}
    verify_images(build / 'gw_retro_go.elf', images[INTERNAL], images[EXTERNAL])
    verify_layout(previous / 'gw_retro_go.elf', build / 'gw_retro_go.elf', images[EXTERNAL], profile)
    old_ids = rom_identities(previous / 'gw_retro_go.elf', profile)
    new_ids = rom_identities(build / 'gw_retro_go.elf', profile)
    for name in ('SAVE_NES_1', 'SAVE_NES_2'):
        require(old_ids[name] == new_ids[name], 'Retained cartridge identity changed: ' + name)
    require(len(padded(old[EXTERNAL], 4096)) == profile['mutable_start'], 'Previous image size differs')
    info = json.loads(save_info.read_text())
    save = save_path.read_bytes()
    rom = (roms / 'Metal_Max_cn.nes').read_bytes()
    require(len(save) == info['bytes'] == 8192 and sha(save) == info['sha256'], 'Save export hash differs')
    require(sha(rom) == info['rom_sha256'], 'Metal Max ROM identity differs')
    require(old[EXTERNAL].count(rom) == images[EXTERNAL].count(rom) == 1, 'Metal Max ROM differs from installed/target firmware')
    for name in ('Tetris.nes.lzma',):
        data = (roms / name).read_bytes()
        require(old[EXTERNAL].count(data) == images[EXTERNAL].count(data) == 1, 'Tetris ROM differs')
    tank = (roms / 'Tank_90.nes.lzma').read_bytes()
    require(images[EXTERNAL].count(tank) == 1, 'Tank ROM missing from target image')
    if output.exists():
        _, existing = read_images(output)
        require(existing == images, 'Existing package contains different firmware')
        require(json.loads((output / 'save-source.json').read_text()) == info, 'Existing package contains a different save source')
        print('Existing package reverified against build, ROMs, layout, and source save.', flush=True)
        return profile, old, images, save, rom
    output.mkdir(parents=True, exist_ok=False)
    for name in (INTERNAL, EXTERNAL, 'gw_retro_go.elf', 'gw_retro_go.map'):
        shutil.copyfile(build / name, output / name)
    (output / 'save-source.json').write_text(json.dumps(info, indent=2) + '\n')
    (output / 'layout.json').write_text(json.dumps(profile, indent=2) + '\n')
    meta = dict(titles=['Metal Max', '90 Tank', 'Tetris'], free_bytes=profile['mutable_start']-len(images[EXTERNAL]),
                sha256={**{name: sha(data) for name, data in images.items()},
                        'gw_retro_go.elf': sha((build / 'gw_retro_go.elf').read_bytes())}, flashed=False)
    (output / 'build-info.json').write_text(json.dumps(meta, indent=2) + '\n')
    print('Package prepared; layout, ROM identities, and imported battery save verified.', flush=True)
    return profile, old, images, save, rom


def install(backend, device, prepared, output, backup):
    profile, old, images, save, rom = prepared
    opened = False
    try:
        backend.open(); opened = True; backend.set_frequency(100000)
        require(device._get_status() == 'IDLE', 'Start a fresh verified RAM helper first')
        device._gnwmanager_started = True
        require(device.external_flash_size == profile['flash_size'], 'Expected Mario original 1 MiB flash; check connected device')
        require(device.external_flash_block_size == 4096, 'Expected 4 KiB erase sectors')
        bank = device.read_memory(profile['internal_base'], profile['internal_bank_size'])
        require(bank[:len(old[INTERNAL])] == old[INTERNAL], 'Mario installed firmware differs from verified baseline')
        start = profile['mutable_start']
        tail = device.read_memory(profile['external_base'] + start, profile['flash_size'] - start)
        before = padded(old[EXTERNAL], 4096) + tail
        require(len(before) == profile['flash_size'] and device.read_hashes(0, len(before)) == hashes(before),
                'Full Mario backup differs from device hashes')
        pointer = profile['config_start'] + profile['startup_pointer_offset']
        require(int.from_bytes(before[pointer:pointer+4], 'little') in (0, 0xffffffff), 'Leave Mario at the game menu before updating')
        backup.mkdir(parents=True, exist_ok=False)
        data_files = {'bank1.bin': bank, 'external.bin': before}
        for name, data in data_files.items():
            (backup / name).write_bytes(data)
        manifest = {name: dict(size=len(data), sha256=sha(data)) for name, data in data_files.items()}
        (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        after = make_image(before, images[EXTERNAL], save, rom, profile)
        (output / 'external-with-saves.bin').write_bytes(after)
        meta = dict(status='writing', backup_verified=True, source_battery_sha256=sha(save),
                    external_before_sha256=sha(before))
        (output / 'installation.json').write_text(json.dumps(meta, indent=2) + '\n')
        print('Mario backup verified. Installing Tank and Zelda Metal Max battery save; preserving Tetris and settings.', flush=True)
        device.flash(0, 0, after, progress=True, desc='Mario firmware and save transfer')
        device.flash(1, 0, images[INTERNAL])
        require(device.read_hashes(0, len(after)) == hashes(after), 'External flash verification failed')
        require(device.read_memory(profile['internal_base'], len(images[INTERNAL])) == images[INTERNAL], 'Internal flash verification failed')
        require(device.read_memory(profile['external_base'] + start, len(tail)) == after[start:], 'Save/settings readback differs')
        meta.update(status='verified', installed_at_utc=datetime.now(timezone.utc).isoformat(),
                    external_after_sha256=sha(after), internal_after_sha256=sha(images[INTERNAL]), gameplay_test='pending')
        (output / 'installation.json').write_text(json.dumps(meta, indent=2) + '\n')
        info = json.loads((output / 'build-info.json').read_text()); info['flashed'] = True
        (output / 'build-info.json').write_text(json.dumps(info, indent=2) + '\n')
        device.reset()
        print('Firmware, imported SRAM, cleared snapshots, Tetris snapshot, and settings verified. Mario restarted.', flush=True)
        return meta
    finally:
        if opened:
            backend.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('previous', 'build', 'roms', 'save', 'save-info', 'output', 'backup'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    prepared = prepare(args.previous, args.build, args.roms, args.save, args.save_info, args.output)
    if args.install:
        backend, device = make_connection()
        install(backend, device, prepared, args.output, args.backup)
