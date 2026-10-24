"""Check Zelda migration rejection paths and exact full-image preservation offline."""
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.gnw.common import hashes
from tools.gnw.install_zelda import install

class Backend:
    def open(self):self.opened=True
    def close(self):self.opened=False
    def set_frequency(self,hz):assert hz==100000

class Device:
    external_flash_size=4194304
    external_flash_block_size=4096
    def __init__(self,old_ext,old_int):
        self.ext=bytearray(old_ext);self.internal=bytearray(old_int);self.writes=0;self.restarted=False;self.corrupt=False
    def _get_status(self):return 'IDLE'
    def read_memory(self,address,size):
        if address==0x08000000:return bytes(self.internal[:size])
        offset=address-0x90000000
        assert offset>=0
        return bytes(self.ext[offset:offset+size])
    def read_hashes(self,offset,size):return hashes(bytes(self.ext[offset:offset+size]))
    def flash(self,bank,offset,data,**kwargs):
        self.writes+=1
        if bank==0:
            self.ext[offset:offset+len(data)]=data
            if self.corrupt:self.ext[-100]^=1
        else:self.internal[offset:offset+len(data)]=data
    def reset(self):self.restarted=True

class Tests(unittest.TestCase):
    def setUp(self):
        self.old_ext=bytes([0x55])*4194304;self.old_int=bytes([0x66])*262144
        self.target_ext=bytes([0xa5])*4194304;self.target_int=bytes([0x77])*190000
        self.images=(self.target_ext,self.target_int,self.old_ext,self.old_int,0x33b000)
        self.backend=Backend();self.device=Device(self.old_ext,self.old_int)
    def run_install(self):
        with tempfile.TemporaryDirectory() as directory:
            result=install(self.backend,self.device,self.images,Path(directory)/'backup')
            self.assertEqual((Path(directory)/'backup/external-before.bin').read_bytes(),self.old_ext)
            return result
    def test_success(self):
        self.assertEqual(self.run_install()['status'],'verified')
        self.assertEqual(bytes(self.device.ext),self.target_ext)
        self.assertTrue(self.device.restarted)
        self.assertFalse(self.backend.opened)
    def test_wrong_capacity_stops_before_write(self):
        self.device.external_flash_size=1048576
        with self.assertRaisesRegex(ValueError,'4 MiB'):self.run_install()
        self.assertEqual(self.device.writes,0)
    def test_wrong_firmware_stops_before_write(self):
        self.device.internal[10]^=1
        with self.assertRaisesRegex(ValueError,'firmware differs'):self.run_install()
        self.assertEqual(self.device.writes,0)
    def test_newer_save_stops_before_write(self):
        self.device.ext[0x3ea123]^=1
        with self.assertRaisesRegex(ValueError,'data changed'):self.run_install()
        self.assertEqual(self.device.writes,0)
    def test_failed_readback_does_not_restart(self):
        self.device.corrupt=True
        with self.assertRaisesRegex(ValueError,'External flash verification'):self.run_install()
        self.assertFalse(self.device.restarted)

if __name__=='__main__':unittest.main()
