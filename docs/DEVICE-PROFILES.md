# Device profiles

Shared emulator and interface changes live in the common source tree.
Device configurations and hardware validation remain separate.

| Device | Status |
|---|---|
| Mario, original 1 MiB flash | Tested; see [save behavior and memory layout](mario/STATUS.md). |
| Zelda | Not validated. |
| Custom PCB | Requires its own board configuration and validation. |

The Mario save-preserving installer checks its configured capacity, previous firmware, and snapshot layout.
Changing ROMs can change snapshot addresses, even when the image fits flash.
Validate a new layout before using the installer with another ROM selection or device.
