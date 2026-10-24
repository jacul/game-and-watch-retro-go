"""Exercise production GB decoder, selected-code callbacks, and loader adapter."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
port = (root / 'Core/Src/porting/gb/main_gb.c').read_text()
start = port.index('#if CHEAT_CODES == 1\n#include "gb_cheats.h"')
end = port.index('#define NVS_KEY_SAVE_SRAM', start)
callbacks = port[start:end]
loader = (root / 'Core/Src/porting/gb/loader_cheats.c').read_text()
upstream = '''
static bool rom_bank_cache_enabled = true;
static int rom_banks_number = 3;
static uint8_t flash_banks[3][16384], cache_bank[16384];
static struct { uint8_t *bank[3]; } rom;
int rom_loadbank(short bank) {
    if (bank && rom_bank_cache_enabled) {
        memcpy(cache_bank, flash_banks[bank], sizeof(cache_bank));
        rom.bank[bank] = cache_bank;
        for (unsigned i = 1; i < 3; ++i) if (i != (unsigned)bank) rom.bank[i] = NULL;
    } else rom.bank[bank] = flash_banks[bank];
    return 0;
}
void gb_loader_restore_cache(void) {
    for (unsigned i = 1; i < 3; ++i) if (rom.bank[i]) memcpy(rom.bank[i], flash_banks[i], 16384);
}
'''
loader = loader.replace('#include "../../../../retro-go-stm32/gnuboy-go/components/gnuboy/loader.c"', upstream)
harness = r'''
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#define CHEAT_CODES 1
#define ENABLE_EMULATOR_GB 1
#define IRAM_ATTR
#define MAX_CHEAT_CODES 16
static struct { unsigned id, cheat_count; const char **cheat_codes; } active;
#define ACTIVE_FILE (&active)
static bool enabled[16];
static bool odroid_settings_ActiveGameGenieCodes_is_enabled(unsigned id, unsigned i) { assert(id == 42); return enabled[i]; }
static uint8_t work_ram[8192];
static void writeb(uint16_t a, uint8_t value) { assert(a >= 0xc000 && a < 0xe000); work_ram[a - 0xc000] = value; }
'''
tests = r'''
int main(void) {
    gb_cheat_t code;
    assert(gb_cheat_decode("C9D-CBE-7FD", 11, &code));
    assert(code.rom && code.conditional && code.address == 0x1dcb && code.value == 0xc9 && code.compare == 0xe5);
    assert(gb_cheat_decode("00D-CDE-A24", 11, &code));
    assert(code.address == 0x1dcd && code.value == 0 && code.compare == 0x93);
    assert(gb_cheat_decode("C9D-CBE", 7, &code) && !code.conditional);
    assert(gb_cheat_decode("01FF87CA", 8, &code));
    assert(!code.rom && code.address == 0xca87 && code.value == 255);
    const char *bad[] = {"", "C9D_CBE_7FD", "C9D-CBE-7FZ", "C9DCBE7FD", "91FF87CA", "01FF00FF", "01FF00A0", "C9D-CB0"};
    for (unsigned i = 0; i < sizeof(bad)/sizeof(*bad); ++i) assert(!gb_cheat_decode(bad[i], strlen(bad[i]), &code));
    gb_cheat_list_t list = {0};
    assert(gb_cheat_add_group(&list, "01FF87CA+01FF88CA") && list.count == 2);
    assert(!gb_cheat_add_group(&list, "01FF87CA+BAD") && list.count == 2);
    assert(!gb_cheat_add_group(&list, "01FF87CA+") && list.count == 2);
    char long_code[257]; memset(long_code, '0', 256); long_code[256] = 0;
    assert(!gb_cheat_add_group(&list, long_code));
    while (list.count < GB_CHEAT_LIMIT) assert(gb_cheat_add_group(&list, "01FF87CA"));
    assert(!gb_cheat_add_group(&list, "01FF87CA") && list.count == GB_CHEAT_LIMIT);

    const char *groups[] = {"01FF84CA+01FF85CA+010086CA", "C9D-CBE-7FD", "AA0-00B-7FD"};
    active.id = 42; active.cheat_count = 3; active.cheat_codes = groups;
    gb_cheats_init(); assert(gb_cheats.count == 0); gb_cheats_frame();
    assert(work_ram[0xa84] == 0 && work_ram[0xa85] == 0);
    work_ram[0xa86] = 9;
    enabled[0] = true; gb_cheats_init(); assert(gb_cheats.count == 3);
    gb_cheats_frame(); assert(work_ram[0xa84] == 255 && work_ram[0xa85] == 255 && work_ram[0xa86] == 0);
    for (unsigned i = 0; i < sizeof(work_ram); ++i) if (i != 0xa84 && i != 0xa85) assert(work_ram[i] == 0);
    enabled[0] = false; gb_cheats_init(); work_ram[0xa84] = 7; gb_cheats_frame(); assert(work_ram[0xa84] == 7);

    enabled[1] = enabled[2] = true; gb_cheats_init();
    flash_banks[0][0x1dcb] = 0xe5; flash_banks[1][0] = flash_banks[2][0] = 0xe5;
    rom_loadbank(0); assert(rom.bank[0][0x1dcb] == 0xc9 && flash_banks[0][0x1dcb] == 0xe5);
    rom_loadbank(1); assert(rom.bank[1][0] == 0xaa && flash_banks[1][0] == 0xe5);
    assert(rom.bank[1][0x1dcb] == 0); /* Fixed-bank patch must not affect switchable bank. */
    rom_loadbank(2); assert(rom.bank[2][0] == 0xaa && rom.bank[1] == NULL);
    rom_loadbank(1); assert(rom.bank[1][0] == 0xaa); /* Eviction reload reapplies patch. */
    gb_loader_restore_cache(); assert(rom.bank[1][0] == 0xaa); /* Snapshot restores also reapply. */
    flash_banks[2][0] = 0x11; rom_loadbank(2); assert(rom.bank[2][0] == 0x11); /* Compare guard. */
    rom_bank_cache_enabled = false; rom_loadbank(1);
    assert(rom.bank[1][0] == 0xaa && flash_banks[1][0] == 0xe5); /* Raw ROM also uses shadow. */
    assert(rom.bank[0][0x1dcb] == 0xc9); /* Separate fixed-bank shadow survives. */
    enabled[1] = enabled[2] = false; gb_cheats_init(); rom_loadbank(0); rom_loadbank(1);
    assert(rom.bank[0][0x1dcb] == 0xe5 && rom.bank[1][0] == 0xe5); /* Relaunch disables patches. */
    puts("PASS: GB Game Genie decoding and bank guards, three-byte gold RAM preset, disabled defaults, cache eviction/restoration, raw-ROM shadows, malformed groups and limits");
}
'''
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory) / 'test.c'; binary = Path(directory) / 'test'
    source.write_text(harness + callbacks + loader + tests)
    subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-I'+str(root/'Core/Inc/porting/gb'), str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
