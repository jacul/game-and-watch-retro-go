/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define GB_CHEAT_LIMIT 64u
#define GB_CHEAT_TEXT_LIMIT 256u

typedef struct {
    uint16_t address;
    uint8_t value, compare;
    bool rom, conditional;
} gb_cheat_t;

typedef struct {
    gb_cheat_t codes[GB_CHEAT_LIMIT];
    unsigned count;
} gb_cheat_list_t;

static int gb_cheat_hex(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static bool gb_cheat_decode(const char *text, size_t length, gb_cheat_t *out)
{
    unsigned digits[9], count = 0;
    bool genie = length == 7 || length == 11;
    if (!genie && length != 8) return false;
    if (genie && (text[3] != '-' || (length == 11 && text[7] != '-'))) return false;
    for (size_t i = 0; i < length; ++i) {
        if (genie && (i == 3 || i == 7)) continue;
        int value = gb_cheat_hex(text[i]);
        if (value < 0 || count >= 9) return false;
        digits[count++] = value;
    }
    memset(out, 0, sizeof(*out));
    if (genie) {
        out->rom = true;
        out->value = digits[0] * 16 + digits[1];
        out->address = ((digits[5] ^ 15) << 12) | (digits[2] << 8) | (digits[3] << 4) | digits[4];
        if (out->address >= 0x8000) return false;
        out->conditional = count == 9;
        if (out->conditional) {
            unsigned encoded = digits[6] * 16 + digits[8];
            out->compare = ((encoded >> 2) | (encoded << 6)) ^ 0xba;
        }
    } else {
        /* Only 01 writes to work RAM. Bank-select and IO writes are unsupported. */
        if (digits[0] != 0 || digits[1] != 1) return false;
        out->value = digits[2] * 16 + digits[3];
        out->address = (digits[6] << 12) | (digits[7] << 8) | (digits[4] << 4) | digits[5];
        if (out->address < 0xc000 || out->address >= 0xe000) return false;
    }
    return true;
}

static bool gb_cheat_add_group(gb_cheat_list_t *list, const char *text)
{
    size_t length = 0;
    while (length < GB_CHEAT_TEXT_LIMIT && text[length]) ++length;
    if (!length || length == GB_CHEAT_TEXT_LIMIT) return false;
    unsigned original = list->count;
    size_t start = 0;
    for (size_t pos = 0; pos <= length; ++pos) {
        if (pos != length && text[pos] != '+') continue;
        if (list->count >= GB_CHEAT_LIMIT ||
            !gb_cheat_decode(text + start, pos - start, &list->codes[list->count])) {
            list->count = original;
            return false;
        }
        ++list->count;
        start = pos + 1;
    }
    return true;
}

static bool gb_cheat_matches(const gb_cheat_t *code, unsigned bank, const uint8_t *data)
{
    return code->rom && ((code->address < 0x4000) == (bank == 0)) &&
        (!code->conditional || data[code->address & 0x3fff] == code->compare);
}

static uint8_t *gb_cheat_patch(const gb_cheat_list_t *list, unsigned bank,
                               uint8_t *data, bool writable, uint8_t *shadow)
{
    for (unsigned i = 0; i < list->count; ++i) {
        if (!gb_cheat_matches(&list->codes[i], bank, data)) continue;
        if (!writable) {
            memcpy(shadow, data, 16384);
            data = shadow;
            writable = true;
        }
        data[list->codes[i].address & 0x3fff] = list->codes[i].value;
    }
    return data;
}
