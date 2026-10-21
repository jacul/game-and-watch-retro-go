/* SPDX-License-Identifier: GPL-2.0-or-later
 * Two-record journal for cartridge battery RAM. Payloads use FCEU SaveGame order.
 * The inactive record is erased/written; a CRC rejects an interrupted write.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>

#define NES_BATTERY_MAX 8192u
#define NES_BATTERY_SLOT_SIZE 12288u
#define NES_BATTERY_MAGIC 0x3152424eu /* NBR1, little endian */
typedef struct {
    uint32_t magic, version, rom_crc, size, sequence, data_crc, header_crc;
    uint8_t data[NES_BATTERY_MAX];
} nes_battery_record_t;
_Static_assert(sizeof(nes_battery_record_t) <= NES_BATTERY_SLOT_SIZE, "Battery slot overflow");

static uint32_t nes_battery_crc(const void *data, size_t size)
{
    const uint8_t *p = data;
    uint32_t crc = UINT32_MAX;
    while (size--) {
        crc ^= *p++;
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static bool nes_battery_valid(const nes_battery_record_t *r, uint32_t rom, uint32_t size)
{
    return size && size <= NES_BATTERY_MAX && r->magic == NES_BATTERY_MAGIC &&
        r->version == 1 && r->rom_crc == rom && r->size == size &&
        r->header_crc == nes_battery_crc(r, offsetof(nes_battery_record_t, header_crc)) &&
        r->data_crc == nes_battery_crc(r->data, size);
}

static int nes_battery_latest(const uint8_t *flash, uint32_t rom, uint32_t size)
{
    const nes_battery_record_t *a = (const void *)flash;
    const nes_battery_record_t *b = (const void *)(flash + NES_BATTERY_SLOT_SIZE);
    bool va = nes_battery_valid(a, rom, size), vb = nes_battery_valid(b, rom, size);
    if (!va) return vb ? 1 : -1;
    if (!vb) return 0;
    uint32_t delta = b->sequence - a->sequence;
    return delta && delta < 0x80000000u ? 1 : 0;
}

/* Returns -1 for unchanged data, otherwise the inactive record index. */
static int nes_battery_prepare(const uint8_t *flash, nes_battery_record_t *r,
                               uint32_t rom, uint32_t size)
{
    if (!size || size > NES_BATTERY_MAX) return -1;
    int latest = nes_battery_latest(flash, rom, size);
    const nes_battery_record_t *old = latest < 0 ? NULL :
        (const void *)(flash + latest * NES_BATTERY_SLOT_SIZE);
    if (old && memcmp(old->data, r->data, size) == 0) return -1;
    r->magic = NES_BATTERY_MAGIC;
    r->version = 1;
    r->rom_crc = rom;
    r->size = size;
    r->sequence = old ? old->sequence + 1u : 0;
    r->data_crc = nes_battery_crc(r->data, size);
    r->header_crc = nes_battery_crc(r, offsetof(nes_battery_record_t, header_crc));
    return latest == 0 ? 1 : 0;
}
