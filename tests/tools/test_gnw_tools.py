import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.gnw import helper, install, layout
from tools.gnw.common import HELPER_ADDRESS, ROOT, hashes, padded
from tools.gnw.migrate_mario_snapshot import extract_wram, make_record


class Backend:
    def __init__(self):
        self.opened = self.closed = self.resumed = False
        self.memory = b''
        self.registers = {}
    def open(self): self.opened = True
    def close(self): self.closed = True
    def set_frequency(self, value):
        if value != 100000: raise ValueError('Wrong frequency')
    def __call__(self, command, **kwargs): return command.encode()
    def read_uint32(self, address): return 0x411FC271
    def write_memory(self, address, data):
        if address != HELPER_ADDRESS: raise ValueError('Wrong helper address')
        self.memory = data
    def read_memory(self, address, size): return self.memory[:size]
    def write_register(self, name, value): self.registers[name] = value
    def read_register(self, name): return self.registers[name]
    def resume(self): self.resumed = True


class HelperDevice:
    def __init__(self): self.status = {}; self.idle = False
    def write_uint32(self, key, value): self.status[key] = value
    def wait_for_idle(self): self.idle = True


class Device:
    def __init__(self, p, previous, corrupt=False):
        self.external_flash_size = p['flash_size']
        self.external_flash_block_size = p['erase_size']
        self.profile = p
        self.bank = bytearray(previous[install.INTERNAL].ljust(p['internal_bank_size'], b'\xff'))
        self.flash_data = bytearray(previous[install.EXTERNAL])
        self.flash_data += bytes(range(256)) * ((p['flash_size'] - p['mutable_start']) // 256)
        pointer = p['config_start'] + p['startup_pointer_offset']
        self.flash_data[pointer:pointer + 4] = bytes(4)
        self.calls = []; self.reset_called = False; self.corrupt = corrupt
    def _get_status(self): return 'IDLE'
    def read_memory(self, address, size):
        if address >= self.profile['external_base']:
            start = address - self.profile['external_base']
            return bytes(self.flash_data[start:start + size])
        start = address - self.profile['internal_base']
        return bytes(self.bank[start:start + size])
    def read_hashes(self, offset, size): return hashes(self.flash_data[offset:offset + size])
    def flash(self, bank, offset, data, **kwargs):
        self.calls.append((bank, offset, len(data)))
        if bank == 0:
            data = padded(data, self.profile['erase_size'])
            if offset + len(data) > self.profile['mutable_start']: raise ValueError('Save overlap')
            self.flash_data[offset:offset + len(data)] = data
            if self.corrupt: self.flash_data[-1] ^= 1
        else: self.bank[offset:offset + len(data)] = data
    def reset(self): self.reset_called = True


class ToolsTest(unittest.TestCase):
    def test_separate_helper_stages_and_rejected_ram(self):
        firmware = struct.pack('<II', 0x20020000, 0x240F0001) + b'test helper'
        b, d = Backend(), HelperDevice()
        with contextlib.redirect_stdout(io.StringIO()): helper.run('load', b, d, firmware)
        self.assertTrue(b.closed); self.assertFalse(b.resumed)
        b.closed = False
        with contextlib.redirect_stdout(io.StringIO()): helper.run('start', b, d, firmware)
        self.assertTrue(b.closed and b.resumed and d.idle)
        b.memory = b'bad'; b.resumed = False
        with self.assertRaisesRegex(ValueError, 'readback mismatch'): helper.run('start', b, d, firmware)
        self.assertTrue(b.closed); self.assertFalse(b.resumed)

    def test_profile_and_layout_checks(self):
        p = layout.load_profile('mario-stock-1mb')
        with self.assertRaises(ValueError): layout.load_profile('zelda-unvalidated')
        symbols = {name: (p['external_base'] + offset, size) for name, (offset, size) in p['save_symbols'].items()}
        for name, offset in [('__SAVEFLASH_START__', p['battery_end']), ('__SAVEFLASH_END__', p['config_start']),
                             ('__CONFIGFLASH_START__', p['config_start']), ('__CONFIGFLASH_END__', p['flash_size']),
                             ('__BATTERYFLASH_START__', p['mutable_start']), ('__BATTERYFLASH_END__', p['battery_end'])]:
            symbols[name] = (p['external_base'] + offset, 0)
        with patch.object(layout, 'symbols', side_effect=[symbols, dict(symbols)]), \
                patch.object(layout, 'rom_identities', return_value={'SAVE_NES_0': 'same ROM'}):
            layout.verify(Path('old.elf'), Path('new.elf'), b'image', p)
        changed = dict(symbols); changed['SAVE_NES_2'] = (0, 1)
        with patch.object(layout, 'symbols', side_effect=[symbols, changed]):
            with self.assertRaises(ValueError): layout.verify(Path('old.elf'), Path('new.elf'), b'image', p)

    def test_install_preserves_saves_and_stops_before_unknown_baseline(self):
        p = layout.load_profile('mario-stock-1mb')
        previous = {install.INTERNAL: b'old' * 40, install.EXTERNAL: b'\xff' * p['mutable_start']}
        images = {install.INTERNAL: b'new' * 40, install.EXTERNAL: b'new ROM'}
        for fault in ('none', 'baseline', 'external-baseline', 'post-write'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory); image_dir = folder / 'images'; image_dir.mkdir()
                b, d = Backend(), Device(p, previous, corrupt=fault == 'post-write')
                before = bytes(d.flash_data[p['mutable_start']:])
                if fault == 'baseline': d.bank[0] ^= 1
                if fault == 'external-baseline': d.flash_data[0] ^= 1
                with contextlib.redirect_stdout(io.StringIO()):
                    if fault != 'none':
                        with self.assertRaises(ValueError):
                            install.install(b, d, image_dir, folder / 'backups', p, ({}, previous, images))
                    else:
                        result = install.install(b, d, image_dir, folder / 'backups', p, ({}, previous, images))
                self.assertTrue(b.closed)
                if fault in ('baseline', 'external-baseline'):
                    self.assertEqual(d.calls, [])
                elif fault == 'post-write':
                    self.assertEqual(json.loads((image_dir / 'installation-pending.json').read_text())['status'], 'writing')
                    self.assertFalse(d.reset_called)
                else:
                    self.assertTrue(d.reset_called)
                    self.assertEqual(json.loads((image_dir / 'installation.json').read_text()), result)
                    self.assertTrue(json.loads((image_dir / 'build-info.json').read_text())['flashed'])
                    sessions = list((folder / 'backups').iterdir())
                    self.assertEqual(len(json.loads((sessions[0] / 'manifest.json').read_text())), 2)
                    self.assertEqual(bytes(d.flash_data[p['mutable_start']:]), before)
                    self.assertEqual(result['preserved_bytes'], 98304)
                    self.assertEqual(Path(result['backup_session']).name, result['backup_session'])
                    self.assertEqual([c[0] for c in d.calls], [0, 1])
                    self.assertFalse((image_dir / 'installation-pending.json').exists())

    def test_image_hash_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'build-info.json').write_text(json.dumps({'sha256': {install.INTERNAL: 'bad'}}))
            (folder / install.INTERNAL).write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'): install.read_images(folder)

    def test_offline_migration(self):
        ram = bytes(range(256)) * 32
        fields = b'WRAM' + struct.pack('<I', len(ram)) + ram
        chunk = b'\x10' + struct.pack('<I', len(fields)) + fields
        state = b'FCS\xff' + struct.pack('<I', len(chunk)) + bytes(8) + chunk
        self.assertEqual(extract_wram(state), ram)
        self.assertEqual(len(make_record(ram, b'ROM')), 12288)
        with self.assertRaises(ValueError): extract_wram(state[:-1])

    def test_help_and_openocd_wrapper_without_hardware(self):
        for module in ('helper', 'install', 'migrate_mario_snapshot', 'package'):
            subprocess.run([sys.executable, '-m', 'tools.gnw.' + module, '--help'], cwd=ROOT,
                           check=True, stdout=subprocess.DEVNULL)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); executable = folder / 'fake-openocd'; capture = folder / 'arguments'
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE"\n')
            executable.chmod(0o755)
            env = dict(os.environ, OPENOCD_BINARY=str(executable), CAPTURE=str(capture))
            subprocess.run([str(ROOT / 'scripts/openocd_mario_100khz.sh'), '-c', 'init'], env=env, check=True)
            self.assertEqual(capture.read_text().splitlines(), ['-c', 'init', '-c', 'adapter speed 100'])


if __name__ == '__main__':
    unittest.main()
