"""Shared configuration; importing this module never accesses a device."""
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER_ADDRESS = 0x240E6800
CHUNK_SIZE = 262144


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hashes(data):
    return [hashlib.sha256(data[i:i + CHUNK_SIZE]).digest()
            for i in range(0, len(data), CHUNK_SIZE)]


def padded(data, block_size):
    return data + b'\xff' * (-len(data) % block_size)


def make_connection():
    # Resolve the checked-in wrapper, rather than a machine-specific executable.
    os.environ.setdefault('OPENOCD', str(ROOT / 'scripts/openocd_mario_100khz.sh'))
    from gnwmanager.gnw import GnW
    from gnwmanager.ocdbackend import OCDBackend
    backend = OCDBackend['openocd']()
    return backend, GnW(backend)


def helper_firmware():
    from importlib.resources import files
    return (files('gnwmanager') / 'firmware.bin').read_bytes()
