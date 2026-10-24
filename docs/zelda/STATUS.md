# Zelda source support

Shared source includes Game Boy battery journals and bounded cheat decoders.
Game Boy journals support 8 KiB and 32 KiB cartridge RAM without RTC support.
Writes occur on manual battery save, snapshot save, quit, or POWER.
The code performs no periodic battery writes during gameplay.

Host tests cover journal isolation, interrupted writes, cache visibility, and cheat parsing.
They also cover loader integration and migration rejection paths.
Run them with `./scripts/test_zelda_custom.sh` after installing the pinned Python environment.
The optional ROM-routine test requires explicit private inputs.

The Zelda build wrapper requires `GCC_PATH` and private ROM configuration files.
Set `GNW_ZELDA_CONFIG_DIR` to a directory containing `nes.json` and `gb.json`.
Optional cheat files belong in its `nes/` and `gb/` subdirectories.
Set `GB_BATTERY_BYTES` through make arguments when your journal allocation differs from the wrapper's default.
Validate each game order, ROM identity, journal allocation, and snapshot layout separately.

Zelda tools provide capture, package preparation, save migration, and verified installation.
These commands use a separate package format from the Mario update installer.
Use each module's `--help` before preparing a device-specific workflow.
The current macOS guide and CI firmware build validate the Mario flow.
Shared Zelda source does not establish validation for arbitrary Zelda configurations.

Keep ROM selections, cheat presets, device observations, captures, saves, and installation packages local.
