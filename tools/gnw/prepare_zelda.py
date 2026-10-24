"""Prepare the selected Zelda image from verified saves, without device access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib
from elftools.elf.elffile import ELFFile

SIZE = 4194304
BASE = 0x90000000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def span(size):
    return (28 + size + 4095) & ~4095


def record(ram, rom):
    if len(ram) not in (8192, 32768):
        raise ValueError('Unsupported cartridge RAM size')
    header = struct.pack('<6I', 0x3152424e, 1, zlib.crc32(rom), len(ram), 0, zlib.crc32(ram))
    return (header + struct.pack('<I', zlib.crc32(header)) + ram).ljust(span(len(ram)), b'\xff')


def firmware_layout(build, image):
    with (build / 'gw_retro_go.elf').open('rb') as file:
        elf = ELFFile(file)
        symbols = {s.name: (s['st_value'], s['st_size'])
                   for s in elf.get_section_by_name('.symtab').iter_symbols()}

        def read(address, size):
            for section in elf.iter_sections():
                offset = address - section['sh_addr']
                if section['sh_type'] != 'SHT_NOBITS' and 0 <= offset and offset + size <= section['sh_size']:
                    return section.data()[offset:offset + size]
            raise ValueError(f'Unmapped ELF address {address:x}')

        def string(address):
            result = bytearray()
            for offset in range(256):
                char = read(address + offset, 1)
                if char == b'\0':
                    return result.decode('utf-8')
                result.extend(char)
            raise ValueError('Unterminated ROM name')

        start = symbols['__BATTERYFLASH_START__'][0] - BASE
        end = symbols['__BATTERYFLASH_END__'][0] - BASE
        if not len(image) <= start < end < SIZE or symbols['__CONFIGFLASH_END__'][0] != BASE + SIZE:
            raise ValueError('Unexpected Zelda layout')
        gb_address, gb_size = symbols['gb_roms']
        gb_bytes = 0
        for index in range(gb_size // 52):
            rom, length = struct.unpack('<2I', read(gb_address + 52 * index + 12, 8))
            code = image[rom - BASE + 0x149] if length >= 0x150 else 255
            if code > 3:
                raise ValueError('Unsupported GB RAM header')
            gb_bytes += 2 * span(32768 if code == 3 else 8192)
        if end - start not in (gb_bytes, gb_bytes + 24576):
            raise ValueError('Unexpected NES/GB battery reservation')
        reserve_nes = end - start == gb_bytes + 24576
        cursor = start
        games = []
        for system in ('nes', 'gb'):
            address, size = symbols[system + '_roms']
            if size % 52 or (system == 'nes' and size != 52):
                raise ValueError('Unexpected ROM descriptor layout')
            for index in range(size // 52):
                _, name, ext, rom, length, save, capacity = struct.unpack('<7I', read(address + 52 * index, 28))
                stored = image[rom - BASE:rom - BASE + length]
                if rom < BASE or len(stored) != length:
                    raise ValueError('Invalid stored ROM range')
                if system == 'gb' and (length < 0x150 or stored[0x149] > 3):
                    raise ValueError('Unsupported GB RAM header')
                ram_size = 32768 if system == 'gb' and stored[0x149] == 3 else 8192
                reserved = system == 'gb' or reserve_nes
                slot = span(ram_size) if reserved else 0
                if cursor + slot * 2 > end or not end <= save - BASE < save - BASE + capacity <= SIZE - 4096:
                    raise ValueError('Save region exceeds reserved flash')
                code_ptr, desc_ptr, cheat_count = struct.unpack('<3I', read(address + 52 * index + 40, 12))
                if cheat_count > 16:
                    raise ValueError('Too many compiled cheats')
                cheats = []
                for cheat_index in range(cheat_count):
                    code = struct.unpack('<I', read(code_ptr + 4 * cheat_index, 4))[0]
                    desc = struct.unpack('<I', read(desc_ptr + 4 * cheat_index, 4))[0]
                    cheats.append(dict(code=string(code), label=string(desc) if desc else string(code)))
                games.append(dict(system=system, title=string(name), extension=string(ext), cheats=cheats,
                                  rom_offset=rom - BASE, stored_rom_size=length,
                                  stored_rom_sha256=sha(stored), rom_crc32=f'{zlib.crc32(stored):08x}',
                                  battery_offset=cursor if reserved else None, battery_size=ram_size if reserved else 0, slot_size=slot,
                                  snapshot_offset=save - BASE, snapshot_size=capacity,
                                  cartridge_battery=(stored[0x147] in (3, 6, 9, 13, 15, 16, 19, 27, 30, 255)) if system == 'gb' else bool(stored[6] & 2)))
                cursor += 2 * slot
        if cursor != end:
            raise ValueError('Reserved journal size differs from compiled games')
        return dict(flash_size=SIZE, journal_start=start, journal_end=end,
                    firmware_bytes=len(image), free_bytes=start - len(image), games=games)


def prepare(build, roms, transfer, output, dq_rom_sha256):
    image = (build / 'gw_retro_go_extflash.bin').read_bytes()
    layout = firmware_layout(build, image)
    full = bytearray(b'\xff' * SIZE)
    full[:len(image)] = image
    originals = json.loads((transfer / 'manifest.json').read_text())['games']
    details = []
    for system, title, filename in [('nes', 'Metal_Max(cn)', 'Metal_Max_cn.nes'), ('gb', 'DQ I.II', 'DQ_I_II.gbc')]:
        item = next(g for g in originals if g['system'] == system and g['name'] == title)
        ram = (transfer / item['battery_file']).read_bytes()
        raw = (roms / system / filename).read_bytes()
        if sha(ram) != item['battery_sha256']:
            raise ValueError('Battery hash mismatch')
        if system == 'nes' and sha(raw) != item['rom_sha256']:
            raise ValueError('NES ROM identity mismatch')
        if system == 'gb' and sha(raw) != dq_rom_sha256:
            raise ValueError('DQ full ROM identity mismatch')
        matches = [g for g in layout['games'] if g['system'] == system and
                   (image[g['rom_offset']:g['rom_offset'] + g['stored_rom_size']] == raw if system == 'nes'
                    else image[g['rom_offset']:g['rom_offset'] + 16384] == raw[:16384])]
        if len(matches) != 1:
            raise ValueError('Imported cartridge does not match exactly one compiled ROM')
        game = matches[0]
        stored = image[game['rom_offset']:game['rom_offset'] + game['stored_rom_size']]
        if len(ram) != game['battery_size']:
            raise ValueError('Imported RAM size differs')
        data = record(ram, stored)
        offset = game['battery_offset']
        full[offset:offset + len(data)] = data
        detail = dict(game, battery_sha256=sha(ram))
        if system == 'gb':
            if sha(stored[:16384]) != item['rom_bank0_sha256']:
                raise ValueError('DQ bank zero differs')
            snapshot = bytearray((transfer / item['snapshot_file']).read_bytes())
            if sha(snapshot) != item['snapshot_sha256']:
                raise ValueError('GB snapshot hash mismatch')
            keys = []
            for pos in range(0, 4096, 8):
                key = bytes(snapshot[pos:pos + 4])
                if key == bytes(4):
                    break
                keys.append(key)
                if key == b'rtct':
                    snapshot[pos:pos + 8] = b'rtce' + bytes(4)
            if keys.count(b'rtct') != 1 or b'rtce' in keys or len(snapshot) != game['snapshot_size']:
                raise ValueError('Unexpected GB snapshot layout')
            location = game['snapshot_offset']
            full[location:location + len(snapshot)] = snapshot
            detail.update(snapshot_sha256=sha(snapshot), snapshot_change='rtct replaced with rtce=0; cartridge has no RTC')
        else:
            detail['snapshot_import'] = 'Original SNSS archived; incompatible with FCEU. Latest battery RAM imported.'
        details.append(detail)
    output.mkdir(parents=True, exist_ok=False)
    for name in ('gw_retro_go.elf', 'gw_retro_go.map', 'gw_retro_go_intflash.bin', 'gw_retro_go_extflash.bin'):
        shutil.copyfile(build / name, output / name)
    (output / 'external-with-saves.bin').write_bytes(full)
    (output / 'layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    (output / 'save-migration.json').write_text(json.dumps(details, indent=2) + '\n')
    files = {p.name: dict(size=p.stat().st_size, sha256=sha(p.read_bytes())) for p in sorted(output.iterdir()) if p.is_file()}
    (output / 'manifest.json').write_text(json.dumps(files, indent=2) + '\n')
    print(json.dumps(layout, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'roms', 'transfer', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--dq-rom-sha256', required=True, help='Expected hash from your private ROM identity record')
    args = parser.parse_args()
    prepare(args.build, args.roms, args.transfer, args.output, args.dq_rom_sha256)
