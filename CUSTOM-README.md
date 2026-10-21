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
Use Arm GNU Toolchain 14.2.Rel1 and Python 3.11 with
[the pinned dependencies](config/mario-requirements.lock.txt). See the
[upstream build guide](README.md#how-to-build) for general setup.

```sh
git submodule update --init --recursive
./scripts/test_mario_custom.sh
GCC_PATH=/path/to/toolchain/bin ./scripts/build_mario_custom.sh
```

## Install

To flash without losing existing saves, use the installer in
[device tools](tools/gnw/README.md). [Mario status](docs/mario/STATUS.md) covers
behaviour and limits, and [device notes](docs/mario/DEVICE-NOTES.md) covers
troubleshooting.

## Credits

Battery-save storage adapts code from Sylverb's SD-card fork (GPL-2.0).
