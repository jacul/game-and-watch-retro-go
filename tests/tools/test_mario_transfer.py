import json
from pathlib import Path
import tempfile
import unittest
from tools.gnw.common import hashes
from tools.gnw.install import INTERNAL, EXTERNAL
from tools.gnw.layout import load_profile
from tools.gnw.migrate_mario_snapshot import make_record
from tools.gnw.update_mario_tank import make_image, install


class Backend:
    def open(self): self.opened = True
    def close(self): self.opened = False
    def set_frequency(self, value): assert value == 100000


class Device:
    external_flash_size = 1048576
    external_flash_block_size = 4096
    def __init__(self, ext, bank):
        self.ext = bytearray(ext); self.bank = bytearray(bank); self.writes = 0; self.restarted = False; self.corrupt = False
    def _get_status(self): return 'IDLE'
    def read_memory(self, address, size):
        if address >= 0x90000000: return bytes(self.ext[address-0x90000000:address-0x90000000+size])
        return bytes(self.bank[:size])
    def read_hashes(self, offset, size): return hashes(bytes(self.ext[offset:offset+size]))
    def flash(self, bank, offset, data, **kwargs):
        self.writes += 1
        if bank == 0:
            self.ext[offset:offset+len(data)] = data
            if self.corrupt: self.ext[-1] ^= 1
        else: self.bank[offset:offset+len(data)] = data
    def reset(self): self.restarted = True


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile('mario-stock-1mb')
        self.start = self.profile['mutable_start']
        self.old = {INTERNAL: b'old firmware', EXTERNAL: bytes([0x55])*self.start}
        self.images = {INTERNAL: b'new firmware', EXTERNAL: bytes([0x77])*self.start}
        self.before = bytearray(self.old[EXTERNAL] + bytes([0x33])*(1048576-self.start))
        self.before[0xff010:0xff014] = bytes(4)
        self.save = bytes([0x42])*8192; self.rom = b'matching ROM'
        self.device = Device(self.before, self.old[INTERNAL].ljust(262144, b'\xff'))
        self.backend = Backend()
        self.prepared = self.profile,self.old,self.images,self.save,self.rom

    def test_import_clears_old_snapshots_and_preserves_tetris_settings(self):
        after = make_image(self.before,self.images[EXTERNAL],self.save,self.rom,self.profile)
        self.assertEqual(after[0xe8000:0xeb000], make_record(self.save,self.rom))
        self.assertEqual(after[0xeb000:0xee000], b'\xff'*12288)
        self.assertEqual(after[0xee000:0xf5000], b'\xff'*28672)
        self.assertEqual(after[0xfb000:0xff000], b'\xff'*16384)
        self.assertEqual(after[0xf5000:0xfb000], self.before[0xf5000:0xfb000])
        self.assertEqual(after[0xff000:], self.before[0xff000:])

    def run_install(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'package';output.mkdir()
            (output/'build-info.json').write_text('{}')
            return install(self.backend,self.device,self.prepared,output,Path(directory)/'backup')

    def test_success_verifies_import(self):
        result=self.run_install()
        self.assertEqual(result['status'],'verified')
        self.assertEqual(self.device.ext[0xe801c:0xea01c],self.save)
        self.assertTrue(self.device.restarted)
        self.assertFalse(self.backend.opened)

    def test_wrong_device_stops_before_write(self):
        self.device.external_flash_size=4194304
        with self.assertRaisesRegex(ValueError,'Mario original'):self.run_install()
        self.assertEqual(self.device.writes,0)

    def test_changed_rom_prefix_stops_before_write(self):
        self.device.ext[100]^=1
        with self.assertRaisesRegex(ValueError,'backup differs'):self.run_install()
        self.assertEqual(self.device.writes,0)

    def test_active_game_stops_before_write(self):
        self.device.ext[0xff010:0xff014]=b'\x12\x34\x56\x78'
        with self.assertRaisesRegex(ValueError,'game menu'):self.run_install()
        self.assertEqual(self.device.writes,0)

    def test_failed_verification_does_not_reset(self):
        self.device.corrupt=True
        with self.assertRaisesRegex(ValueError,'verification failed'):self.run_install()
        self.assertFalse(self.device.restarted)

if __name__=='__main__':unittest.main()
