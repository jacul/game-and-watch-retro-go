# Device tools

Run Python commands from the repository root. Use Python 3.11 with the pinned
config/mario-requirements.lock.txt environment, including gnwmanager 0.24.0.
Importing these modules and using --help does not connect to USB.

For native Apple Silicon setup, see [the macOS guide](../../docs/MACOS.md).

## Create an installation package

After a successful build:

    python -m tools.gnw.package --output .local/packages/mario-update-01

The command creates a new directory containing both binaries, their ELF, and build-info.json.
It verifies that the binaries match the ELF and records hashes for all three files.
Keep installed packages as baselines. Keep packages local because they contain ROM data.

## Voltage and OpenOCD

Compile the read-only probe utility with the libusb flags from pkg-config:

    cc tools/stlink_voltage.c $(pkg-config --cflags --libs libusb-1.0) -o stlink-voltage
    ./stlink-voltage

ST-LINK reports sometimes changed after reset/helper execution. See device notes;
the reported ADC value does not independently establish the target supply voltage.

The wrapper scripts/openocd_mario_100khz.sh finds openocd on PATH. Set
OPENOCD_BINARY to select another executable. The wrapper sets 100 kHz.

## Separate RAM-helper startup

    python -m tools.gnw.helper load
    python -m tools.gnw.helper start

Use separate processes. Load resets/halts the target, reads core registers,
loads the packaged helper and verifies every byte without starting it. Start
verifies that RAM again, sets registers/status, resumes and waits for IDLE.
Neither stage writes flash. The default OpenOCD wrapper path is resolved from
this repository. Set OPENOCD explicitly to use another configuration.

## Preserve saves during a firmware update

    python -m tools.gnw.install --profile mario-stock-1mb \
      --previous-dir PREVIOUS_IMAGE_DIRECTORY --image-dir NEW_IMAGE_DIRECTORY \
      --backup-dir BACKUP_DIRECTORY --helper-running

Each image directory must contain build-info.json with SHA256 values, both
firmware .bin files, and gw_retro_go.elf. The expected baseline is explicit.
Offline binary, ELF, ROM identity, and layout checks precede device access. The running helper,
device capacity, erase size, internal baseline and full backup hashes are checked
before any flash write. Every battery/snapshot/settings byte is compared after
writing. No whole-chip erase is used. Metadata records a backup session name,
not a machine-specific absolute path. A failed post-write check leaves the
installation-pending.json marker and verified backups for recovery.

Both ELFs must retain their debug information. ROM identity checks use the compiled ROM descriptors.
They compare ROM bytes, save-slot mappings, mapper, region, and game configuration.
Changed ROMs require a separate save migration, even when save addresses stay unchanged.
Historical packages without an ELF hash still require binaries that exactly match their ELF.

config/device-profiles.json contains the current validated Mario memory layout.
Add a separately validated Zelda profile later; the installer rejects unknown
profiles. Shared tools do not assume that all devices have the Mario capacity.

## Offline save migration and photo OCR

Metal Max snapshot migration is an offline operation:

    python -m tools.gnw.migrate_mario_snapshot --snapshot SNAPSHOT_FILE \
      --rom ROM_FILE --sram-out SAVE_FILE --journal-out JOURNAL_FILE

It exports 8 KiB WRAM from an FCS snapshot and creates two journal slots. It
requires the matching mapper 74 ROM and creates new output files exclusively.
It never writes a device. This is separate from the ordinary update installer.

On macOS, tools/gnw/crash_ocr.swift reads a supplied photo file with local Vision
OCR. Small crash text still needs visual verification.
It does not capture screens or control apps.

## Specialist migration tools

The source tree also includes Zelda capture, preparation, migration, and installation tools.
See [Zelda source support](../../docs/zelda/STATUS.md) for their scope and configuration requirements.
These tools use device-specific layouts and a different package format from the Mario update installer.

tools.gnw.update_mario_tank handles an explicit Mario ROM replacement and battery-save transfer.
It clears affected snapshots and checks retained cartridge identities separately.
Its build wrapper reads GNW_MARIO_ROM_CONFIG or an ignored local ROM configuration.
Keep ROM selections and device records local. Do not reuse a migration plan for another ROM layout.
