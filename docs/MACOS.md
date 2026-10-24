# Native macOS build

Build Mario firmware directly on an Apple Silicon Mac.
You do not need a Raspberry Pi or Docker for this flow.
The automatic setup supports Apple Silicon only.
Intel Macs need separate compiler setup and validation.
Zelda installation remains outside this flow's validated scope.

## Setup

Install Apple's Command Line Tools:

```sh
xcode-select --install
```

Install Python 3.11. For example, use an existing Homebrew installation:

```sh
brew install python@3.11
```

Clone this fork with its submodules, then enter its directory.
Use a checkout path without spaces; upstream Make rules require this.
Run:

```sh
./scripts/setup_macos.sh
```

Setup creates `.venv` and installs the pinned Python dependencies.
It downloads Arm GNU Toolchain 14.2.Rel1 from Arm and verifies its SHA-256 checksum.
The compiler stays in the ignored `.local/toolchains` directory.
Setup also initializes the Git submodules.
Use `PYTHON3=/path/to/python3.11` if Python 3.11 is not on `PATH`.

## Build and package

Place your compatible ROM files in `roms/nes/`.
Use only ROM data that you can lawfully use.
Keep ROMs and firmware packages local.

```sh
./scripts/test_mario_custom.sh
./scripts/build_mario_custom.sh
.venv/bin/python -m tools.gnw.package --output .local/packages/mario-update-01
```

The build downloads missing SDK files with macOS's `curl`.
It builds Mario firmware for the original 1 MiB external flash.
It enables NES battery saves and disables cheats.
ROM content and metadata changes trigger ROM regeneration, including compressed copies.
Build option changes also trigger recompilation.

The package command creates a new directory and refuses to replace an existing package.
It checks that both firmware binaries match the ELF.
It records binary hashes, the ELF hash, and build provenance from the build wrapper.
Build provenance includes the source commit, source modification flag, and compiler version.
Packages from older build directories report unknown provenance when the build record is absent.
Keep each installed package as the baseline for its next update.
Package creation does not connect to a device.

Use `GCC_PATH=/path/to/bin` to select another installation of the pinned compiler.
Use `PYTHON3=/path/to/environment/bin/python` to select an equivalent pinned Python environment.
The build checks compiler and Python dependency versions.
These overrides do not establish validation for another host or device.

## Save-preserving updates

Read [the device tool instructions](../tools/gnw/README.md) before installation.
The installer accepts only the validated `mario-stock-1mb` save layout.
A successful build does not establish compatibility with that layout.
Different ROM selections can require different save layouts.

The installer compares compiled ROM bytes, save mappings, and emulator options between both ELFs.
It rejects replaced ROMs, changed save slots, and binaries that do not match their ELF.
Changed ROMs require a separate save migration.
Older packages remain usable when their ELF matches the binaries and retains debug information.
The package command cannot recover a missing historical ELF.

Build and package commands do not flash, unlock, or reset hardware.
Use the explicit installation commands only when you intend to update a connected device.

## Continuous integration

The macOS job uses the Apple Silicon `macos-15` runner.
It runs setup, host regression tests, a complete firmware build, and package validation.
It generates an original NES fixture instead of downloading commercial ROMs.
It also checks that changed ROM bytes rebuild compressed firmware.
An unchanged rebuild must skip ROM regeneration.
The fixture checks build mechanics; it does not establish gameplay or hardware behavior.
CI does not publish firmware packages or access hardware.

References: [Arm toolchain](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads),
[GitHub runner architectures](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
