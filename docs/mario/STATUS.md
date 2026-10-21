# Mario validation

Tested on an unlocked Mario Game & Watch with the original 1 MiB external flash.
Zelda and custom boards need separate validation.

## Save behavior

NES battery saves support one cartridge with up to 8 KiB of RAM.
Metal Max, mapper 74, is the hardware-tested battery cartridge.
Another battery-backed cartridge can overwrite its records.

Battery RAM is written on manual battery save, snapshot save, quit, or sleep/POWER.
There are no timed saves or gameplay scans.
An in-game save updates emulated RAM; sudden power loss can discard unflushed changes.

New game restores the separate battery save.
Resume game restores the snapshot, including its potentially older cartridge RAM.

Save snapshot on POWER defaults to On.
Off preserves the snapshot, saves battery RAM, and returns to the game list after wake.
Manual snapshots remain available in either mode.

## Tested memory layout

| Area | External offset | Bytes |
|---|---|---:|
| Code and ROM capacity | 0x00000–0xE7FFF | 950,272 |
| Battery journal | 0xE8000–0xEDFFF | 24,576 |
| Snapshot slots | 0xEE000–0xFEFFF | 69,632 |
| Settings erase sector | 0xFF000–0xFFFFF | 4,096 |

Snapshot addresses depend on the ROM selection.

## Validation scope

Hardware checks covered gameplay, manual battery saves, settings changes, and POWER behavior.
Installation checks verified firmware readback and preservation of all 98,304 mutable bytes.
Host tests cover interrupted writes, corruption, flash boundaries, cache visibility, and settings persistence.
Extended endurance testing remains incomplete.
