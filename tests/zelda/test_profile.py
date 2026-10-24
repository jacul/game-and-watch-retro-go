"""Run production GB journal/write code against simulated flash and CPU cache."""
from pathlib import Path
import subprocess
import sys
import tempfile
repo = Path(sys.argv[1]).resolve()
# Synthetic 4 MiB layout. Host tests need no device ELF or ROM library.
symbols = {
    '__BATTERYFLASH_START__': 0x9033b000, '__BATTERYFLASH_END__': 0x90383000,
    '__OFFSAVEFLASH_START__': 0x90383000, '__OFFSAVEFLASH_END__': 0x90383000,
    '__SAVEFLASH_START__': 0x90383000, '__SAVEFLASH_END__': 0x903ff000,
    '__CONFIGFLASH_START__': 0x903ff000, '__CONFIGFLASH_END__': 0x90400000,
    '__FBFLASH_START__': 0x90400000, '__FBFLASH_END__': 0x90400000,
}

def function(text, name):
    start = text.index(name+'(')
    start = text.rfind('\n',0,start)+1
    end = text.index('{',start)+1
    depth=1
    while depth:
        if text[end]=='{':depth+=1
        if text[end]=='}':depth-=1
        end+=1
    return text[start:end]+'\n'

main=(repo/'Core/Src/main.c').read_text()
gb=(repo/'Core/Src/porting/gb/main_gb.c').read_text()
block=gb.split('#if GB_BATTERY_SAVE == 1\n',1)[1].split('#else\n#define gb_battery_init()',1)[0]
block=block.replace('extern uint8_t __BATTERYFLASH_START__[], __BATTERYFLASH_END__[];','')
assert 'gb_battery_flush();\n    printf("Saving state' in gb
assert 'emu_init();\n    gb_battery_init();' in gb
assert 'gb_battery_poll' not in gb
macros='#define __EXTFLASH_BASE__ mapped[0]\n'
for name in ['__OFFSAVEFLASH_START__','__OFFSAVEFLASH_END__','__SAVEFLASH_START__','__SAVEFLASH_END__']:
    macros+=f'#define {name} mapped[{symbols[name]-0x90000000}]\n'
for name in ['__BATTERYFLASH_START__','__BATTERYFLASH_END__','__CONFIGFLASH_START__','__CONFIGFLASH_END__','__FBFLASH_START__','__FBFLASH_END__']:
    macros+=f'#define {name} (mapped+{symbols[name]-0x90000000})\n'
preamble=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
static uint8_t mapped[4194304] __attribute__((aligned(4096)));
static uint8_t physical[4194304];
static uint8_t cartridge[32768];
static uint8_t rom_headers[7][512];
typedef struct rom_system_t rom_system_t;
typedef struct {const uint8_t *address;uint32_t size;const rom_system_t *system;} retro_emulator_file_t;
struct rom_system_t {const retro_emulator_file_t *roms;uint32_t roms_count;};
static retro_emulator_file_t files[7];
static rom_system_t system={files,7};
static retro_emulator_file_t *ACTIVE_FILE;
static struct {int batt,rtc,ramsize;} mbc={1,0,1};
static struct {void *sbank;} ram={cartridge};
static const uint8_t *ROM_DATA;
static uint32_t ROM_DATA_LENGTH=512;
static void (*save_hook)(void);
static int writes;
static size_t write_limit=SIZE_MAX;
static void wdog_refresh(void) {}
static void odroid_system_set_battery_save_hook(void (*f)(void)) {save_hook=f;}
typedef int odroid_dialog_event_t;
typedef struct {int unused;} odroid_dialog_choice_t;
#define ODROID_DIALOG_ENTER 1
static bool memory_mapped=true;
static void OSPI_DisableMemoryMappedMode(void) {assert(memory_mapped);memory_mapped=false;}
static void OSPI_EnableMemoryMappedMode(void) {assert(!memory_mapped);memory_mapped=true;}
static void OSPI_EraseSync(uint32_t a,uint32_t n) {assert(!memory_mapped && a+n<=sizeof(physical));memset(physical+a,255,n);}
static void OSPI_Program(uint32_t a,const uint8_t *p,size_t n) {assert(!memory_mapped && a+n<=sizeof(physical));++writes;memcpy(physical+a,p,n<write_limit?n:write_limit);}
static void SCB_InvalidateDCache_by_Addr(uint32_t *p,int32_t n) {uintptr_t a=(uintptr_t)p-(uintptr_t)mapped;assert(memory_mapped && n>=0 && !(a&31) && !(n&31) && a+n<=sizeof(mapped));memcpy(mapped+a,physical+a,n);}
'''+macros
writer=''.join(function(main,name) for name in ['store_invalidate_cache','store_erase','store_save'])
tests=r'''
static void select_game(int i) {
    ACTIVE_FILE=&files[i];ROM_DATA=files[i].address;
    mbc.batt=1;mbc.rtc=0;mbc.ramsize=ROM_DATA[0x149]==3?4:1;
}
int main(void) {
    memset(mapped,255,sizeof(mapped));memset(physical,255,sizeof(physical));
    uint8_t codes[7]={2,2,3,2,2,0,3};
    for(int i=0;i<7;i++) {
        rom_headers[i][0x149]=codes[i];rom_headers[i][0x100]=(uint8_t)i;
        files[i]=(retro_emulator_file_t){rom_headers[i],512,&system};
    }
#if NES_BATTERY_SAVE
    uint8_t nes[24576];memset(nes,0x5a,sizeof(nes));store_save(__BATTERYFLASH_START__,nes,sizeof(nes));
#endif
    for(int i=0;i<7;i++) {
        select_game(i);memset(cartridge,0x30+i,sizeof(cartridge));gb_battery_init();assert(save_hook);
        assert(gb_battery_size==(codes[i]==3?32768u:8192u));
        gb_battery_save_cb(NULL,ODROID_DIALOG_ENTER,0);
        assert(gb_battery_latest(gb_battery_base(),gb_battery_rom_crc,gb_battery_size)==0);
        int count=writes;save_hook();assert(writes==count);
        cartridge[123]=(uint8_t)(0x70+i);cartridge[gb_battery_size-1]=(uint8_t)(0x80+i);save_hook();
        assert(gb_battery_latest(gb_battery_base(),gb_battery_rom_crc,gb_battery_size)==1);
    }
    /* Revisit every cartridge: no other game's commit may replace its RAM. */
    for(int i=0;i<7;i++) {
        select_game(i);memset(cartridge,0,sizeof(cartridge));gb_battery_init();
        assert(cartridge[123]==0x70+i && cartridge[gb_battery_size-1]==0x80+i);
        assert(cartridge[0]==0x30+i);
    }
#if NES_BATTERY_SAVE
    assert(!memcmp(__BATTERYFLASH_START__,nes,sizeof(nes)));
#endif
    /* Interrupt writes to a 32 KiB game at each 4 KiB boundary. */
    select_game(2);gb_battery_init();
    for(size_t limit=0;limit<32768+28;limit+=4096) {
        cartridge[123]=0x99;write_limit=limit;save_hook();write_limit=SIZE_MAX;
        memset(cartridge,0,sizeof(cartridge));gb_battery_init();assert(cartridge[123]==0x72);
    }
    /* A different ROM must not restore the old game's record. */
    rom_headers[2][0x100]^=0x80;memset(cartridge,0xa6,sizeof(cartridge));gb_battery_init();assert(cartridge[123]==0xa6);
    rom_headers[2][0x100]^=0x80;
    mbc.rtc=1;gb_battery_init();assert(!gb_battery_size);
    mbc.rtc=0;mbc.ramsize=16;gb_battery_init();assert(!gb_battery_size);
    mbc.ramsize=1;mbc.batt=0;gb_battery_init();assert(!gb_battery_size);
    select_game(0);files[0].size=1;gb_battery_init();assert(!gb_battery_size);files[0].size=512;
    rom_headers[0][0x149]=4;gb_battery_init();assert(!gb_battery_size);rom_headers[0][0x149]=2;
    assert(!memcmp(mapped,physical,sizeof(mapped)));
#if NES_BATTERY_SAVE
    assert(!memcmp(__BATTERYFLASH_START__,nes,sizeof(nes)));
#endif
    uint8_t settings[128]={0};store_save(__CONFIGFLASH_START__,settings,sizeof(settings));
    assert(!memcmp(__CONFIGFLASH_START__,settings,sizeof(settings)));
    puts("PASS: seven independent journals, 8/32 KiB fresh launch, unchanged-data skip, interrupted 32 KiB writes, ROM identity, invalid header/RTC/size rejection, NES isolation, settings/cache guards");
}

'''
with tempfile.TemporaryDirectory(prefix='gnw-zelda-') as directory:
    file=Path(directory)/'test.c';file.write_text(preamble+writer+block+tests)
    exe=Path(directory)/'test'
    for nes_enabled in (0,1):
        subprocess.run(['clang','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-fsanitize=address,undefined',f'-DNES_BATTERY_SAVE={nes_enabled}','-DGB_BATTERY_SAVE=1','-I'+str(repo/'Core/Inc/porting/nes_fceu'),'-I'+str(repo/'Core/Inc/porting/gb'),str(file),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
