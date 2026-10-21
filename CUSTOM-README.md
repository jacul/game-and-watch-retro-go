# Custom Retro-Go for Game & Watch

A fork of [Sylverb's Retro-Go](https://github.com/sylverb/game-and-watch-retro-go)
focused on reliable NES saves. Tested on a Mario Game & Watch with the original
1 MiB flash. Zelda is not supported yet.

## What's different

- **In-game saves are kept on their own.** Games with a battery save (such as
  Metal Max) store it apart from resume snapshots. It is written when you save,
  quit or sleep.
- **POWER button option.** Choose whether POWER also saves a resume snapshot,
  or only the in-game save.
- **Quick-load asks first**, with No selected.
- **Flash writing and caching fixes**, covered by regression tests.

Battery saves currently support one NES game with up to 8 KiB of cartridge RAM.
Saving another battery-backed game can overwrite the previous game’s save.

## Build

Place compatible ROMs in `roms/nes/`. The build must fit the device’s flash.
See the [upstream build guide](README.md#how-to-build) for setup.
See [Mario validation](docs/mario/STATUS.md) for save behavior and tested limits.

## Credits

Battery-save storage adapts code from Sylverb's SD-card fork (GPL-2.0).
