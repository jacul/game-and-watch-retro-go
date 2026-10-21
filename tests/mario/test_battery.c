#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "battery_journal.h"

static uint8_t flash[2 * NES_BATTERY_SLOT_SIZE] __attribute__((aligned(4)));
static nes_battery_record_t work;
static void commit(int slot) { assert(slot >= 0); memcpy(flash + slot * NES_BATTERY_SLOT_SIZE, &work, sizeof(work)); }
int main(void)
{
    assert(nes_battery_crc("123456789", 9) == 0xcbf43926);
    memset(flash, 255, sizeof(flash));
    assert(nes_battery_latest(flash, 42, 8192) == -1);
    memset(work.data, 0x5a, sizeof(work.data));
    assert(nes_battery_prepare(flash, &work, 42, 8192) == 0);
    commit(0);
    assert(nes_battery_latest(flash, 42, 8192) == 0);
    assert(nes_battery_prepare(flash, &work, 42, 8192) == -1);
    assert(nes_battery_latest(flash, 43, 8192) == -1);
    assert(nes_battery_latest(flash, 42, 8191) == -1);
    assert(nes_battery_latest(flash, 42, 0) == -1);
    assert(nes_battery_prepare(flash, &work, 42, 8193) == -1);
    memset(work.data, 0x37, sizeof(work.data));
    assert(nes_battery_prepare(flash, &work, 42, 8192) == 1);
    /* Simulate power loss at every program page boundary and in the header. */
    for (size_t n = 0; n < sizeof(work); n += n < 32 ? 1 : 256) {
        memset(flash + NES_BATTERY_SLOT_SIZE, 255, NES_BATTERY_SLOT_SIZE);
        memcpy(flash + NES_BATTERY_SLOT_SIZE, &work, n);
        assert(nes_battery_latest(flash, 42, 8192) == 0);
    }
    commit(1);
    assert(nes_battery_latest(flash, 42, 8192) == 1);
    /* Header and data corruption reject the newest copy. */
    flash[NES_BATTERY_SLOT_SIZE + 16] ^= 1;
    assert(nes_battery_latest(flash, 42, 8192) == 0);
    commit(1);
    flash[NES_BATTERY_SLOT_SIZE + 100] ^= 1;
    assert(nes_battery_latest(flash, 42, 8192) == 0);
    commit(1);
    /* Sequence wrap still selects the latest record. */
    nes_battery_record_t *a=(void *)flash, *b=(void *)(flash+NES_BATTERY_SLOT_SIZE);
    a->sequence=UINT32_MAX;
    a->header_crc=nes_battery_crc(a, offsetof(nes_battery_record_t,header_crc));
    b->sequence=0;
    b->header_crc=nes_battery_crc(b, offsetof(nes_battery_record_t,header_crc));
    assert(nes_battery_latest(flash,42,8192)==1);
    puts("PASS: CRC, restore, unchanged data, wrong ROM, bounds, interrupted writes, corruption, sequence wrap");
}
