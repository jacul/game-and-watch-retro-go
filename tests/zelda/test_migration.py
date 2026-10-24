"""Test relocation, cartridge identity, and corruption rejection for current saves."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.gnw.migrate_zelda_current import migrate
from tools.gnw.prepare_zelda import SIZE, record, sha


class Tests(unittest.TestCase):
    def setUp(self):
        self.rom = b'cartridge bytes'
        import zlib
        self.game = dict(system='gb', title='DQ', stored_rom_sha256=sha(self.rom),
                         rom_crc32=f'{zlib.crc32(self.rom):08x}', battery_size=8192,
                         slot_size=12288, battery_offset=0x380000,
                         snapshot_offset=0x390000, snapshot_size=61440)
        self.previous = dict(games=[self.game])
        self.new_game = dict(self.game, battery_offset=0x350000, snapshot_offset=0x360000)
        self.target = dict(games=[self.new_game])
        self.data = bytearray(b'\xff' * SIZE)
        self.ram = bytes([0x42]) * 8192
        self.data[0x380000:0x383000] = record(self.ram, self.rom)
        self.snapshot = bytes([0x33]) * 61440
        self.data[0x390000:0x39f000] = self.snapshot

    def test_relocation_preserves_both_records_and_snapshot(self):
        full, info = migrate(b'firmware', self.target, self.data, self.previous)
        self.assertEqual(full[0x350000:0x356000], self.data[0x380000:0x386000])
        self.assertEqual(full[0x360000:0x36f000], self.snapshot)
        self.assertEqual(info[0]['valid_records'], [0])
        self.assertEqual(full[-4096:], b'\xff'*4096)

    def test_invalid_battery_stops(self):
        self.data[0x380000] ^= 1
        with self.assertRaisesRegex(ValueError, 'invalid'):
            migrate(b'firmware', self.target, self.data, self.previous)

    def test_empty_journal_is_retained(self):
        self.data[0x380000:0x386000] = b'\xff'*24576
        _, info = migrate(b'firmware', self.target, self.data, self.previous)
        self.assertEqual(info[0]['valid_records'], [])

    def test_new_cartridge_does_not_receive_removed_game_data(self):
        new_nes = dict(self.new_game, system='nes', title='76-in-1', stored_rom_sha256='other',
                       battery_size=0, slot_size=0, battery_offset=None,
                       snapshot_offset=0x370000, snapshot_size=16384)
        full, info = migrate(b'firmware', dict(games=[new_nes, self.new_game]), self.data, self.previous)
        self.assertEqual(full[0x370000:0x374000], b'\xff'*16384)
        self.assertEqual([item['title'] for item in info], ['DQ'])

    def test_changed_snapshot_capacity_stops(self):
        self.target['games'][0]['snapshot_size'] -= 4096
        with self.assertRaisesRegex(ValueError, 'Snapshot size'):
            migrate(b'firmware', self.target, self.data, self.previous)

    def test_changed_ram_size_stops(self):
        self.target['games'][0]['battery_size'] = 32768
        with self.assertRaisesRegex(ValueError, 'journal size'):
            migrate(b'firmware', self.target, self.data, self.previous)


if __name__ == '__main__':
    unittest.main()
