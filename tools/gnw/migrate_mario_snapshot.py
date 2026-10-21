"""Extract mapper 74 WRAM from the existing FCEU snapshot and seed battery slot 0.

This reads the upstream FCS chunk format. It does not alter the snapshot.
"""
import struct
import zlib

SLOT_SIZE = 12288
BATTERY_START = 0xE8000
BATTERY_END = 0xEE000
SNAPSHOT_START = 0xEE000
SNAPSHOT_SIZE = 28672


def extract_wram(snapshot):
    if len(snapshot) < 16 or snapshot[:3] != b'FCS':
        raise ValueError('Metal Max snapshot is missing its FCS header')
    end = 16 + struct.unpack_from('<I', snapshot, 4)[0]
    if not 16 < end <= len(snapshot):
        raise ValueError('Invalid FCS payload length')
    pos = 16
    found = []
    while pos < end:
        if pos + 5 > end:
            raise ValueError('Truncated FCS chunk header')
        kind = snapshot[pos]
        size = struct.unpack_from('<I', snapshot, pos + 1)[0]
        pos += 5
        stop = pos + size
        if stop > end:
            raise ValueError('FCS chunk exceeds payload')
        if kind == 0x10:
            while pos < stop:
                if pos + 8 > stop:
                    raise ValueError('Truncated FCS field')
                tag = snapshot[pos:pos + 4]
                size = struct.unpack_from('<I', snapshot, pos + 4)[0]
                pos += 8
                if pos + size > stop:
                    raise ValueError('FCS field exceeds chunk')
                if tag == b'WRAM':
                    found.append(snapshot[pos:pos + size])
                pos += size
        pos = stop
    if len(found) != 1 or len(found[0]) != 8192:
        raise ValueError('Expected exactly one 8 KiB Metal Max WRAM field')
    return found[0]


def make_record(wram, rom):
    if len(wram) != 8192:
        raise ValueError('Expected 8 KiB WRAM')
    header = struct.pack('<6I', 0x3152424E, 1, zlib.crc32(rom), len(wram), 0, zlib.crc32(wram))
    record = header + struct.pack('<I', zlib.crc32(header)) + wram
    return record.ljust(SLOT_SIZE, b'\xff')


def seed_image(external_backup, rom):
    if len(external_backup) != 1048576:
        raise ValueError('Expected full 1 MiB device backup')
    wram = extract_wram(external_backup[SNAPSHOT_START:SNAPSHOT_START + SNAPSHOT_SIZE])
    return make_record(wram, rom) + bytes([255]) * SLOT_SIZE, wram


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--sram-out', type=Path, required=True)
    parser.add_argument('--journal-out', type=Path, required=True)
    args = parser.parse_args()
    rom = args.rom.read_bytes()
    if len(rom) < 16 or rom[:4] != b'NES\x1a' or not (rom[6] & 2) or ((rom[6] >> 4) | (rom[7] & 0xf0)) != 74:
        raise ValueError('Expected the battery-backed mapper 74 Metal Max ROM')
    wram = extract_wram(args.snapshot.read_bytes())
    journal = make_record(wram, rom) + b'\xff' * SLOT_SIZE
    # Exclusive creation protects an earlier exported save from replacement.
    with args.sram_out.open('xb') as out:
        out.write(wram)
    with args.journal_out.open('xb') as out:
        out.write(journal)
    print('Exported 8 KiB cartridge RAM and a two-slot journal image. No device access.')


if __name__ == '__main__':
    main()
