from pathlib import Path
import subprocess
import sys
repo=Path(sys.argv[1])
settings=(repo/'Core/Src/porting/odroid_settings.c').read_text()
system=(repo/'Core/Src/porting/odroid_system.c').read_text()
overlay=(repo/'Core/Src/porting/odroid_overlay.c').read_text()
common=(repo/'Core/Src/porting/common.c').read_text()

def function(text, name):
    start=text.index(name+'(')
    # Include the return type, which can be on its own line.
    start=text.rfind('\n',0,start)+1
    if text[start:].startswith(name): start=text.rfind('\n',0,start-1)+1
    pos=text.index('{',start);depth=1;end=pos+1
    while depth:
        if text[end]=='{':depth+=1
        if text[end]=='}':depth-=1
        end+=1
    return text[start:end]+'\n'

parts=[function(settings,n) for n in ('odroid_settings_StartAction_get','odroid_settings_StartAction_set','odroid_settings_SaveOnPower_get','odroid_settings_SaveOnPower_set')]
parts += [function(system,'odroid_system_save_on_power'),function(system,'odroid_system_sleep'),function(overlay,'save_on_power_update_cb')]
assert common.count('odroid_system_save_on_power();')==1
assert overlay.count('odroid_system_save_on_power();')==2
assert 'Do NOT save-state and then poweroff' in common
assert 'odroid_system_emu_save_state(0);' in common # Manual PAUSE+A remains direct.
assert 'odroid_system_emu_save_state(0);' in overlay # Manual Save & Quit remains direct.
source=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef int ODROID_START_ACTION;
static struct { uint8_t start_action; } persistent_config_ram;
static int snapshots, last_slot, battery_saves, sleeps, logos, stops;
static void (*battery_save_hook)(void);
static void (*sleep_hook)(void);
static int game;
static void *ACTIVE_FILE=&game, *startup_file;
static bool odroid_system_emu_save_state(int slot) { ++snapshots;last_slot=slot;return true; }
static void odroid_settings_StartupFile_set(void *f) {startup_file=f;}
static void gui_save_current_tab(void) {}
static void app_sleep_logo(void) {++logos;}
static void GW_EnterDeepSleep(void) {++sleeps;}
static void battery_flush(void) {++battery_saves;}
static void audio_stop_playing(void) {++stops;}
typedef struct { char *value; } odroid_dialog_choice_t;
typedef int odroid_dialog_event_t;
#define ODROID_DIALOG_PREV 1
#define ODROID_DIALOG_NEXT 2
#define ODROID_DIALOG_ENTER 3
'''+''.join(parts)+r'''
int main(void) {
    for(int action=0; action<4; ++action) {
        persistent_config_ram.start_action=action;
        assert(odroid_settings_SaveOnPower_get());
        odroid_settings_SaveOnPower_set(false);
        assert(!odroid_settings_SaveOnPower_get());
        assert(odroid_settings_StartAction_get()==action);
        odroid_settings_StartAction_set((action+1)%4);
        assert(!odroid_settings_SaveOnPower_get());
        assert(odroid_settings_StartAction_get()==(action+1)%4);
        uint8_t persisted=persistent_config_ram.start_action;
        persistent_config_ram.start_action=0;
        persistent_config_ram.start_action=persisted;
        assert(!odroid_settings_SaveOnPower_get());
        odroid_settings_SaveOnPower_set(true);
        assert(odroid_settings_StartAction_get()==(action+1)%4);
    }
    battery_save_hook=battery_flush;
    odroid_settings_SaveOnPower_set(false);
    odroid_system_save_on_power();odroid_system_sleep();
    assert(snapshots==0 && battery_saves==1 && sleeps==1 && startup_file==NULL);
    odroid_settings_SaveOnPower_set(true);
    odroid_system_save_on_power();odroid_system_sleep();
    assert(snapshots==1 && last_slot==OFF_SAVESTATE && battery_saves==2 && sleeps==2 && startup_file==ACTIVE_FILE);
    odroid_settings_SaveOnPower_set(false);
    odroid_system_emu_save_state(0); // Explicit snapshot save ignores POWER preference.
    assert(snapshots==2 && last_slot==0);
    char value[4]={0};odroid_dialog_choice_t option={value};
    save_on_power_update_cb(&option,0,0);assert(!strcmp(value,"Off"));
    save_on_power_update_cb(&option,ODROID_DIALOG_NEXT,0);assert(!strcmp(value,"On"));
    save_on_power_update_cb(&option,ODROID_DIALOG_PREV,0);assert(!strcmp(value,"Off"));
    assert(save_on_power_update_cb(&option,ODROID_DIALOG_ENTER,0));
    // PAUSE+POWER still bypasses automatic snapshot saving.
    audio_stop_playing();odroid_system_sleep();
    assert(stops==1 && snapshots==2 && sleeps==3 && battery_saves==3 && logos==3);
    puts("PASS: POWER On/Off, battery flush, manual snapshots, settings persistence, startup-action isolation, menu toggle");
}
'''
import tempfile
with tempfile.TemporaryDirectory(prefix='gnw-power-test-') as directory:
    folder=Path(directory)
    p=folder/'test-power-setting.c';p.write_text(source)
    for slot in (0,1):
        out=str(folder/('test-power-setting-'+str(slot)))
        subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-DOFF_SAVESTATE='+str(slot),str(p),'-o',out],check=True)
        subprocess.run([out],check=True)
