"""Offline release checks use generated ARM data, never personal ROMs or USB."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.gnw import elf, install, layout, package
from tools.gnw.common import ROOT


class InputTests(unittest.TestCase):
    def test_content_metadata_deletion_and_generated_compression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'roms/nes').mkdir(parents=True)
            rom = root / 'roms/nes/test file.nes'
            rom.write_bytes(b'first')
            command = [sys.executable, str(ROOT / 'scripts/update_rom_files.py'), 'build/inputs', 'roms']
            def update():
                subprocess.run(command, cwd=root, check=True, stdout=subprocess.DEVNULL)
                return (root / 'build/inputs').read_bytes(), (root / 'build/inputs').stat().st_mtime_ns
            original = update()
            self.assertEqual(update(), original)
            rom.write_bytes(b'other')
            changed = update()
            self.assertNotEqual(changed[0], original[0])
            rom.with_suffix('.nes.lzma').write_bytes(b'generated')
            self.assertEqual(update(), changed)
            (root / 'roms/nes.json').write_text('{"title": "changed"}')
            metadata = update()
            self.assertNotEqual(metadata[0], changed[0])
            rom.unlink()
            self.assertNotEqual(update()[0], metadata[0])


class ElfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads((ROOT / 'config/mario-toolchain.json').read_text())
        compiler_dir = Path(os.environ.get('GCC_PATH', ROOT / '.local/toolchains' / config['compiler_subdirectory']))
        cls.compiler = compiler_dir / 'arm-none-eabi-gcc'
        if not cls.compiler.is_file():
            raise unittest.SkipTest('ARM fixture tests need the pinned compiler; run scripts/setup_macos.sh')

    def build(self, root, changed=False, reordered=False):
        p = layout.load_profile('mario-stock-1mb')
        root.mkdir()
        source = '''
typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;
typedef struct {
 const uint8_t *address; uint32_t size;
 const uint8_t *save_address; uint32_t save_size;
 uint16_t mapper, region, game_config;
} retro_emulator_file_t;
const uint32_t vectors[2] __attribute__((section(".isr_vector"))) = {0x20010000, 0x08000001};
'''
        for i in range(3):
            name = 'SAVE_NES_' + str(i)
            source += f'uint8_t {name}[{p["save_symbols"][name][1]}] __attribute__((section(".save_{i}")));\n'
        for i in range(3):
            first = 10 + i + (20 if changed and i == 0 else 0)
            source += f'const uint8_t rom_{i}[8] __attribute__((section("._extflash"))) = {{{first}, 2, 3}};\n'
        source += 'const retro_emulator_file_t nes_roms[] __attribute__((section("._extflash"))) = {\n'
        order = [1, 0, 2] if reordered else [0, 1, 2]
        source += ',\n'.join(f'{{rom_{order[i]}, 8, SAVE_NES_{i}, sizeof(SAVE_NES_{i}), 74, 0, 0}}' for i in range(3)) + '};\n'
        (root / 'fixture.c').write_text(source)
        script = 'SECTIONS { .isr_vector 0x08000000 : { *(.isr_vector) }\n'
        script += '._extflash 0x90000000 : { *(._extflash) . = 0xE8000 - 1; BYTE(0); }\n'
        for i in range(3):
            offset, _ = p['save_symbols']['SAVE_NES_' + str(i)]
            script += f'.save_{i} {p["external_base"] + offset:#x} (NOLOAD) : {{ *(.save_{i}) }}\n'
        for name, offset in [('__SAVEFLASH_START__', p['battery_end']), ('__SAVEFLASH_END__', p['config_start']),
                             ('__CONFIGFLASH_START__', p['config_start']), ('__CONFIGFLASH_END__', p['flash_size']),
                             ('__BATTERYFLASH_START__', p['mutable_start']), ('__BATTERYFLASH_END__', p['battery_end'])]:
            script += f'{name} = {p["external_base"] + offset:#x};\n'
        (root / 'fixture.ld').write_text(script + '}\n')
        target = root / 'gw_retro_go.elf'
        subprocess.run([str(self.compiler), '-g', '-gdwarf-2' if changed else '-gdwarf-4', '-fno-eliminate-unused-debug-types',
                        '-nostdlib', '-Wl,--build-id=none', '-T', str(root / 'fixture.ld'),
                        str(root / 'fixture.c'), '-o', str(target)], check=True, capture_output=True)
        from elftools.elf.elffile import ELFFile
        with target.open('rb') as stream:
            linked = ELFFile(stream)
            (root / install.INTERNAL).write_bytes(elf.binary_image(linked, elf.INTERNAL_SECTIONS, p['internal_base']))
            (root / install.EXTERNAL).write_bytes(elf.binary_image(linked, elf.EXTERNAL_SECTIONS, p['external_base']))
        return root

    def test_package_and_legacy_elf_binding_and_changed_rom_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = self.build(root / 'old-build')
            new = self.build(root / 'new-build', changed=True)
            baseline, updated = root / 'baseline', root / 'updated'
            package.create(old, baseline)
            package.create(new, updated)
            p = layout.load_profile('mario-stock-1mb')
            install.prepare(baseline, baseline, p)
            with self.assertRaisesRegex(ValueError, 'ROM identity'):
                install.prepare(baseline, updated, p)
            swapped = self.build(root / 'swapped-build', reordered=True)
            swapped_package = root / 'swapped'
            package.create(swapped, swapped_package)
            with self.assertRaisesRegex(ValueError, 'ROM identity'):
                install.prepare(baseline, swapped_package, p)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                package.create(old, baseline)
            # Historical metadata has binary hashes only. The ELF still binds to those binaries.
            metadata = json.loads((baseline / 'build-info.json').read_text())
            del metadata['sha256']['gw_retro_go.elf']
            (baseline / 'build-info.json').write_text(json.dumps(metadata))
            install.read_images(baseline)
            (baseline / 'gw_retro_go.elf').write_bytes((updated / 'gw_retro_go.elf').read_bytes())
            with self.assertRaisesRegex(ValueError, 'does not match ELF'):
                install.read_images(baseline)

    def test_reject_stale_build_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = self.build(root / 'build')
            (build / 'source-info.json').write_text(json.dumps({'sha256': {}}))
            with self.assertRaisesRegex(ValueError, 'provenance'):
                package.create(build, root / 'package')
            self.assertFalse((root / 'package').exists())


if __name__ == '__main__':
    unittest.main()
