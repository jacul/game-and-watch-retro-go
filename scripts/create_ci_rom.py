"""Generate an original NES build fixture. It contains no commercial game data."""
import argparse
from pathlib import Path


def create(path):
    # NROM, 16 KiB PRG, 8 KiB CHR. The program loops at $8000.
    header = b'NES\x1a' + bytes([1, 1]) + bytes(10)
    program = bytearray([0xEA] * 16384)
    program[:3] = bytes([0x4C, 0x00, 0x80])
    program[-6:] = bytes([0x00, 0x80]) * 3
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(header + program + bytes(8192))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    create(parser.parse_args().output)
