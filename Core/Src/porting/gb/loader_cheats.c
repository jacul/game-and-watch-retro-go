/* SPDX-License-Identifier: GPL-2.0-or-later
 * Adapt the upstream loader without changing the dependency checkout.
 * ROM patches must survive bank eviction and snapshot cache restoration.
 */
#define rom_loadbank gb_original_loadbank
#define gb_loader_restore_cache gb_original_restore_cache
#include "../../../../retro-go-stm32/gnuboy-go/components/gnuboy/loader.c"
#undef rom_loadbank
#undef gb_loader_restore_cache

#ifdef ENABLE_EMULATOR_GB
#if CHEAT_CODES == 1
extern uint8_t *gb_cheat_rom_bank(unsigned bank, uint8_t *data, bool writable);
#endif

int IRAM_ATTR rom_loadbank(short bank)
{
    int result = gb_original_loadbank(bank);
#if CHEAT_CODES == 1
    rom.bank[bank] = gb_cheat_rom_bank(bank, rom.bank[bank], rom_bank_cache_enabled && bank != 0);
#endif
    return result;
}

void gb_loader_restore_cache(void)
{
    gb_original_restore_cache();
#if CHEAT_CODES == 1
    if (rom_bank_cache_enabled) {
        for (int bank = 1; bank < rom_banks_number; ++bank) {
            if (rom.bank[bank]) rom.bank[bank] = gb_cheat_rom_bank(bank, rom.bank[bank], true);
        }
    }
#endif
}
#endif
