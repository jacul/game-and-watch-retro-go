"""Migrate unchanged cartridge journals and snapshots from a verified current backup."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import zlib
from .common import require
from .install_zelda import read_checked
from .prepare_zelda import firmware_layout, sha, SIZE


def valid_record(data, game):
    if len(data) < 28 + game['battery_size']:
        return False
    magic, version, rom, size, sequence, crc, header_crc = struct.unpack_from('<7I', data)
    return (magic == 0x3152424e and version == 1 and rom == int(game['rom_crc32'], 16)
            and size == game['battery_size'] and header_crc == zlib.crc32(data[:24])
            and crc == zlib.crc32(data[28:28 + size]))


def migrate(image, layout, previous_image, previous_layout):
    full = bytearray(b'\xff' * SIZE)
    full[:len(image)] = image
    migrations = []
    for game in layout['games']:
        matches = [old for old in previous_layout['games'] if old['system'] == game['system']
                   and old['stored_rom_sha256'] == game['stored_rom_sha256']]
        require(len(matches) <= 1, 'Ambiguous cartridge identity')
        if not matches:
            continue
        old = matches[0]
        require(old['rom_crc32'] == game['rom_crc32'], 'ROM identity differs')
        require(old['battery_size'] == game['battery_size'] and old['slot_size'] == game['slot_size'],
                'Battery journal size differs')
        require(old['snapshot_size'] == game['snapshot_size'], 'Snapshot size differs')
        detail = dict(game)
        if game['battery_size']:
            size = game['slot_size'] * 2
            journals = previous_image[old['battery_offset']:old['battery_offset'] + size]
            require(len(journals) == size, 'Incomplete source journal')
            valid = [i for i in (0, 1) if valid_record(journals[i*game['slot_size']:(i+1)*game['slot_size']], game)]
            require(valid or journals == b'\xff' * size, 'Both source battery records are invalid')
            pos = game['battery_offset']
            full[pos:pos + size] = journals
            detail.update(journal_sha256=sha(journals), valid_records=valid)
        snapshot = previous_image[old['snapshot_offset']:old['snapshot_offset'] + old['snapshot_size']]
        require(len(snapshot) == game['snapshot_size'], 'Incomplete source snapshot')
        pos = game['snapshot_offset']
        full[pos:pos + len(snapshot)] = snapshot
        detail.update(snapshot_sha256=sha(snapshot), snapshot_empty=snapshot == b'\xff'*len(snapshot))
        migrations.append(detail)
    require(migrations, 'No retained cartridges found')
    return full, migrations


def prepare(build, baseline, output):
    manifest = json.loads((baseline / 'manifest.json').read_text())
    previous_image = read_checked(baseline, 'external.bin', manifest)
    previous_layout = json.loads(read_checked(baseline, 'layout.json', manifest))
    require(len(previous_image) == SIZE, 'Expected full source flash image')
    image = (build / 'gw_retro_go_extflash.bin').read_bytes()
    layout = firmware_layout(build, image)
    full, migrations = migrate(image, layout, previous_image, previous_layout)
    output.mkdir(parents=True, exist_ok=False)
    for name in ('gw_retro_go.elf', 'gw_retro_go.map', 'gw_retro_go_intflash.bin', 'gw_retro_go_extflash.bin'):
        shutil.copyfile(build / name, output / name)
    (output / 'external-with-saves.bin').write_bytes(full)
    (output / 'layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    (output / 'save-migration.json').write_text(json.dumps(migrations, indent=2) + '\n')
    (output / 'baseline.json').write_text(json.dumps(dict(external_sha256=sha(previous_image),
        internal_sha256=manifest['bank1.bin']['sha256']), indent=2) + '\n')
    files = {p.name: dict(size=p.stat().st_size, sha256=sha(p.read_bytes())) for p in sorted(output.iterdir()) if p.is_file()}
    (output / 'manifest.json').write_text(json.dumps(files, indent=2) + '\n')
    print(json.dumps(dict(free_bytes=layout['free_bytes'], games=[g['title'] for g in layout['games']],
                         migrated=[g['title'] for g in migrations]), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'baseline', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    prepare(args.build, args.baseline, args.output)
