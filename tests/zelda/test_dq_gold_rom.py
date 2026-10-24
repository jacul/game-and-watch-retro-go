"""Execute this ROM's actual 24-bit add, spend, and comparison instructions.

This small instruction runner tests fixed ROM routines, not full gameplay or video.
The production GB cheat parser supplies the candidate memory writes.
"""
from pathlib import Path
import argparse
import hashlib
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
parser.add_argument('--rom', type=Path, required=True)
parser.add_argument('--sha256', required=True)
parser.add_argument('--codes', type=Path, required=True)
args = parser.parse_args()
root = args.repo.resolve()
rom = args.rom.read_bytes()
assert hashlib.sha256(rom).hexdigest() == args.sha256



class Routine:
    def __init__(self):
        self.mem = bytearray(65536)
        self.mem[:16384] = rom[:16384]
        self.reg = dict.fromkeys('ABCDEHL', 0)
        self.carry = self.zero = False

    def hl(self):
        return self.reg['H'] * 256 + self.reg['L']

    def set_hl(self, value):
        self.reg['H'], self.reg['L'] = (value >> 8) & 255, value & 255

    def get8(self, index):
        return self.mem[self.hl()] if index == 6 else self.reg['BCDEHL A'[index]]

    def set8(self, index, value):
        if index == 6:
            self.mem[self.hl()] = value
        else:
            self.reg['BCDEHL A'[index]] = value

    def run(self, address, amount):
        self.reg['E'], self.reg['H'], self.reg['L'] = amount >> 16, (amount >> 8) & 255, amount & 255
        pc, stack = address, [0xffff]
        for _ in range(256):
            op = self.mem[pc]; pc += 1
            if 0x40 <= op <= 0x7f and op != 0x76:
                self.set8((op >> 3) & 7, self.get8(op & 7))
            elif op in (0x21, 0x11):
                value = int.from_bytes(self.mem[pc:pc+2], 'little'); pc += 2
                if op == 0x21: self.set_hl(value)
                else: self.reg['D'], self.reg['E'] = value >> 8, value & 255
            elif op == 0x0e:
                self.reg['C'] = self.mem[pc]; pc += 1
            elif op == 0xfa:
                value = int.from_bytes(self.mem[pc:pc+2], 'little'); pc += 2
                self.reg['A'] = self.mem[value]
            elif op == 0x2a:
                self.reg['A'] = self.mem[self.hl()]; self.set_hl((self.hl()+1) & 65535)
            elif op == 0x22:
                self.mem[self.hl()] = self.reg['A']; self.set_hl((self.hl()+1) & 65535)
            elif op == 0xe5: stack.append(self.hl())
            elif op == 0xe1: self.set_hl(stack.pop())
            elif op == 0xcd:
                target = int.from_bytes(self.mem[pc:pc+2], 'little'); stack.append(pc+2); pc = target
            elif op in (0xc9, 0xc0):
                if op == 0xc9 or not self.zero: pc = stack.pop()
                if pc == 0xffff: return self.zero, self.carry
            elif op in (0x18, 0x30, 0x38):
                delta = self.mem[pc]; pc += 1
                if delta >= 128: delta -= 256
                if op == 0x18 or (op == 0x30 and not self.carry) or (op == 0x38 and self.carry): pc += delta
            elif op in (0x83, 0x89, 0x8a, 0x93, 0x99, 0x9a, 0xbb, 0xbc, 0xbd, 0xd6, 0xde):
                if op in (0xd6, 0xde): value = self.mem[pc]; pc += 1
                else: value = self.get8(op & 7)
                incoming = int(self.carry) if op in (0x89, 0x8a, 0x99, 0x9a, 0xde) else 0
                result = self.reg['A'] + value + incoming if op in (0x83, 0x89, 0x8a) else self.reg['A'] - value - incoming
                self.carry, self.zero = result < 0 or result > 255, (result & 255) == 0
                if op not in (0xbb, 0xbc, 0xbd): self.reg['A'] = result & 255
            else:
                raise AssertionError(f'Unsupported instruction {op:02x} at {pc-1:04x}')
        raise AssertionError('Routine did not return')


candidate = args.codes.read_text().split(',',1)[0]
assert candidate == '01FF84CA+01FF85CA+010086CA'
source = r'''
#include <stdio.h>
#include "gb_cheats.h"
int main(void) {
    gb_cheat_list_t list = {0};
    if (!gb_cheat_add_group(&list, "CANDIDATE")) return 1;
    for (unsigned i=0; i<list.count; ++i) printf("%u %u\n", list.codes[i].address, list.codes[i].value);
    uint8_t bank[16384]={0},shadow[16384];
    (void)gb_cheat_patch(&list,0,bank,true,shadow);
}
'''.replace('CANDIDATE', candidate)
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)/'test.c'; path.write_text(source)
    binary = Path(directory)/'test'
    subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-I'+str(root/'Core/Inc/porting/gb'),str(path),'-o',str(binary)],check=True)
    writes = [tuple(map(int,line.split())) for line in subprocess.check_output([str(binary)],text=True).splitlines()]
assert writes == [(0xca84,255),(0xca85,255),(0xca86,0)]
cpu = Routine()
cpu.mem[0xca84:0xca87] = (81).to_bytes(3,'little')
cpu.mem[0xca87:0xca89] = (123).to_bytes(2,'little')
# The old preset changes the adjacent bank balance, not the carried amount.
cpu.mem[0xca87:0xca89] = b'\xff\xff'
assert cpu.run(0x21c5,81)[0]
for address,value in writes: cpu.mem[address] = value
assert cpu.run(0x21c5,65535)[0]
bank = cpu.mem[0xca87:0xca89]
cpu.run(0x21bb,123)
assert cpu.run(0x21c5,65412)[0]
assert cpu.mem[0xca87:0xca89] == bank
cpu.run(0x21b1,123)
assert cpu.run(0x21c5,65535)[0]
# Both entry points and comparison use CA84..CA86 in the fixed bank.
assert rom[0x21b4:0x21b7] == bytes.fromhex('2184ca')
assert rom[0x21be:0x21c1] == bytes.fromhex('2184ca')
print('PASS: production candidate decodes; actual ROM comparison sees 65535; spend/add routines update the same three bytes; adjacent bank balance is unchanged')
print('Candidate only:', candidate, '(not a full gameplay test)')
