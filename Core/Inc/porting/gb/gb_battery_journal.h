/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include "battery_journal.h"

#define GB_BATTERY_MAX 32768u
#define GB_BATTERY_HEADER 28u

typedef struct {
    uint32_t magic, version, rom_crc, size, sequence, data_crc, header_crc;
    uint8_t data[GB_BATTERY_MAX];
} gb_battery_record_t;

static uint32_t gb_battery_record_span(uint32_t size)
{
    return (GB_BATTERY_HEADER + size + 4095u) & ~4095u;
}

static bool gb_battery_valid(const gb_battery_record_t *r, uint32_t rom, uint32_t size)
{
    return size && size <= GB_BATTERY_MAX && r->magic == NES_BATTERY_MAGIC &&
        r->version == 1 && r->rom_crc == rom && r->size == size &&
        r->header_crc == nes_battery_crc(r, offsetof(gb_battery_record_t, header_crc)) &&
        r->data_crc == nes_battery_crc(r->data, size);
}

static int gb_battery_latest(const uint8_t *flash, uint32_t rom, uint32_t size)
{
    if (!size || size > GB_BATTERY_MAX) return -1;
    const gb_battery_record_t *a = (const void *)flash;
    const gb_battery_record_t *b = (const void *)(flash + gb_battery_record_span(size));
    bool va = gb_battery_valid(a, rom, size), vb = gb_battery_valid(b, rom, size);
    if (!va) return vb ? 1 : -1;
    if (!vb) return 0;
    uint32_t delta = b->sequence - a->sequence;
    return delta && delta < 0x80000000u ? 1 : 0;
}

static int gb_battery_prepare(const uint8_t *flash, gb_battery_record_t *r,
                              uint32_t rom, uint32_t size)
{
    if (!size || size > GB_BATTERY_MAX) return -1;
    int latest = gb_battery_latest(flash, rom, size);
    const gb_battery_record_t *old = latest < 0 ? NULL :
        (const void *)(flash + latest * gb_battery_record_span(size));
    if (old && memcmp(old->data, r->data, size) == 0) return -1;
    r->magic = NES_BATTERY_MAGIC; r->version = 1; r->rom_crc = rom; r->size = size;
    r->sequence = old ? old->sequence + 1u : 0;
    r->data_crc = nes_battery_crc(r->data, size);
    r->header_crc = nes_battery_crc(r, offsetof(gb_battery_record_t, header_crc));
    return latest == 0 ? 1 : 0;
}
