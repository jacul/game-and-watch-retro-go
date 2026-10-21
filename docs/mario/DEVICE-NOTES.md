# Mario storage and debugger notes

## Flash storage

Erase checks must cover the complete sector-rounded range.
Battery storage needs its own permitted write region.
Use the settings region end, not the settings object end, when validating erases.
The tested object occupies 116 bytes; its erase sector occupies 4 KiB.

Invalidate mapped flash cache after erase and programming.
Otherwise, CPU readback can return old data despite successful physical writes.
Host tests exercise these checks using production storage functions.
