"""Exercise real erase/program integration against flash+CPU-cache simulation.
All address limits come from the installed ELF, including its 116-byte config.
"""
from pathlib import Path
import subprocess
import sys
repo=Path(sys.argv[1]);root=Path(__file__).resolve().parent
import json
syms=json.loads((root/'fixtures/installed-linker-symbols.json').read_text())['symbols']

def extract(text,name):
    at=text.index(name+'(');start=text.rfind('\n',0,at)+1
    end=text.index('{',at)+1;depth=1
    while depth:
        if text[end]=='{':depth+=1
        elif text[end]=='}':depth-=1
        end+=1
    return text[start:end]+'\n'
main=(repo/'Core/Src/main.c').read_text()
legacy=(root/'fixtures/legacy-write-guard.c').read_text()
nes=(repo/'Core/Src/porting/nes_fceu/main_nes_fceu.c').read_text()
assert 'battery_poll' not in nes and 'battery_saved_tick' not in nes
battery=nes.split('#if NES_BATTERY_SAVE == 1\n',1)[1].split('#else\n#define battery_init()',1)[0]
battery=battery.replace('extern uint8_t __BATTERYFLASH_START__[], __BATTERYFLASH_END__[];','')
regions=['__OFFSAVEFLASH_START__','__OFFSAVEFLASH_END__','__SAVEFLASH_START__','__SAVEFLASH_END__','__configflash_start__','__configflash_end__','__fbflash_start__','__fbflash_end__']
arrays=['__BATTERYFLASH_START__','__BATTERYFLASH_END__','__CONFIGFLASH_START__','__CONFIGFLASH_END__','__FBFLASH_START__','__FBFLASH_END__']
macros='#define __EXTFLASH_BASE__ mapped[0]\n'
for name in regions: macros+=f'#define {name} mapped[{syms[name]-0x90000000}]\n'
for name in arrays: macros+=f'#define {name} (mapped+{syms[name]-0x90000000})\n'
assert syms['__configflash_end__']-syms['__configflash_start__']==116
preamble=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
static jmp_buf jump;
static bool rejecting;
#define assert(c) do {if(!(c)) {if(rejecting) longjmp(jump,1);fprintf(stderr,"Unexpected assertion: %s\n",#c);abort();}}while(0)
static uint8_t mapped[1048576] __attribute__((aligned(4096)));
static uint8_t physical[1048576];
static int programs, erases, invalidates;
static bool memory_mapped=true;
static size_t write_limit=SIZE_MAX;
static void OSPI_DisableMemoryMappedMode(void) {assert(memory_mapped);memory_mapped=false;}
static void OSPI_EnableMemoryMappedMode(void) {assert(!memory_mapped);memory_mapped=true;}
static void OSPI_EraseSync(uint32_t a,uint32_t n) {assert(!memory_mapped && a+n<=sizeof(physical));++erases;memset(physical+a,255,n);}
static void OSPI_Program(uint32_t a,const uint8_t *data,size_t n) {
    assert(!memory_mapped && a+n<=sizeof(physical));++programs;
    memcpy(physical+a,data,n<write_limit?n:write_limit);
}
static void SCB_InvalidateDCache_by_Addr(uint32_t *addr,int32_t n) {
    uintptr_t a=(uintptr_t)addr-(uintptr_t)mapped;
    assert(memory_mapped && !(a&31) && !(n&31) && n>=0 && a+n<=sizeof(mapped));
    ++invalidates;memcpy(mapped+a,physical+a,n);
}
'''+macros
stubs=r'''
#define GIT_CART 1
#define GIT_VSUNI 2
#define ODROID_DIALOG_ENTER 1
struct {int type;} info={GIT_CART};
static typeof(info) *GameInfo=&info;
static struct {bool battery;uint8_t *SaveGame[4];uint32_t SaveGameLen[4];} iNESCart;
static const uint8_t rom[]={1,2,3,4};
static const uint8_t *ROM_DATA=rom;
static uint32_t ROM_DATA_LENGTH=sizeof(rom);
static void (*save_hook)(void);
static void wdog_refresh(void) {}
static void odroid_system_set_battery_save_hook(void (*f)(void)) {save_hook=f;}
typedef struct {int dummy;} odroid_dialog_choice_t;
typedef int odroid_dialog_event_t;
'''
tests=r'''
static void rejected(uint32_t addr,uint32_t size) {
    int before=erases;rejecting=true;
    if(!setjmp(jump)) {store_erase(mapped+addr,size);abort();}
    rejecting=false;assert(erases==before);
}
int main(void) {
    memset(mapped,255,sizeof(mapped));memset(physical,255,sizeof(physical));
#if LEGACY
    // The old guard used the 116-byte object end after rounding to 4096 bytes.
    rejected(0xFF000,116);
    uint8_t payload[256]={1};store_save(mapped+0xEE000,payload,sizeof(payload));
    assert(memcmp(physical+0xEE000,payload,sizeof(payload))==0);
    assert(memcmp(mapped+0xEE000,payload,sizeof(payload))!=0);
    puts("PASS: reproduced settings assertion and stale CPU readback with installed code");
#else
    uint8_t config[116];memset(config,0x42,sizeof(config));
    store_save(mapped+0xFF000,config,sizeof(config));
    assert(!memcmp(mapped+0xFF000,config,116) && !memcmp(physical+0xFF000,config,116));
    assert(invalidates==2);
    uint8_t ram[8192]={0};iNESCart.battery=true;iNESCart.SaveGame[0]=ram;iNESCart.SaveGameLen[0]=8192;
    battery_init();assert(save_hook);
    ram[100]=0x53;battery_save_cb(NULL,ODROID_DIALOG_ENTER,0);
    int latest=nes_battery_latest(__BATTERYFLASH_START__,battery_rom_crc,8192);
    assert(latest==0);
    assert(!memcmp(mapped+0xE8000,physical+0xE8000,24576));
    int count=programs;save_hook();assert(programs==count); // Unchanged SRAM: no write.
    ram[100]=0x54;save_hook();assert(nes_battery_latest(__BATTERYFLASH_START__,battery_rom_crc,8192)==1);
    ram[100]=0x55;save_hook();assert(nes_battery_latest(__BATTERYFLASH_START__,battery_rom_crc,8192)==0);
    memset(ram,0,sizeof(ram));battery_init();assert(ram[100]==0x55);
    // A torn new record preserves the last complete copy.
    ram[100]=0x56;write_limit=100;save_hook();write_limit=SIZE_MAX;
    memset(ram,0,sizeof(ram));battery_init();assert(ram[100]==0x55);
    // Exit from Options must still commit 116-byte settings without asserting.
    config[1]++;store_save(mapped+0xFF000,config,sizeof(config));
    assert(!memcmp(mapped+0xFF000,config,116));
    rejected(0xE7000,4096);rejected(0xED000,4097);rejected(0xFE000,4097);
    rejected(0xFF000,4097);rejected(0xEE001,4096);rejected(0xEE000,UINT32_MAX);
    puts("PASS: real ELF bounds, settings commit, real battery writes, cache visibility, repeated saves, fresh launch, torn write, protected ranges; no timed-save code");
#endif
}
'''
for old in (True,False):
    writer=(extract(legacy,'store_erase')+extract(legacy,'store_save')) if old else (extract(main,'store_invalidate_cache')+extract(main,'store_erase')+extract(main,'store_save'))
    # Cache stub intentionally unused by old implementation.
    text=preamble+writer+('' if old else stubs+battery)+tests
    import tempfile
    with tempfile.TemporaryDirectory(prefix='gnw-storage-test-') as directory:
        p=Path(directory)/'test-cache.c';p.write_text(text)
        exe=str(Path(directory)/'test-cache')
        subprocess.run(['clang','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-function','-fsanitize=address,undefined','-DNES_BATTERY_SAVE=1','-DLEGACY='+str(int(old)),str(p),'-I'+str(repo/'Core/Inc/porting/nes_fceu'),'-o',exe],check=True)
        subprocess.run([exe],check=True)
