"""Validate a device profile and preserve its current save-layout symbols."""
import json
from .common import ROOT, padded, require
from .elf import rom_identities


def load_profile(name):
    profiles = json.loads((ROOT / 'config/device-profiles.json').read_text())
    require(name in profiles, 'Unknown or unvalidated device profile: ' + name)
    p = profiles[name]
    sector = p['erase_size']
    require(sector == 4096 and 0 < p['mutable_start'] < p['flash_size'], 'Invalid flash profile')
    require(p['mutable_start'] % sector == p['flash_size'] % sector == 0, 'Unaligned profile')
    require(p['mutable_start'] < p['battery_end'] <= p['config_start'] < p['flash_size'], 'Invalid save regions')
    return p


def symbols(path):
    from elftools.elf.elffile import ELFFile
    with path.open('rb') as f:
        table = ELFFile(f).get_section_by_name('.symtab')
        require(table is not None, 'ELF has no symbol table')
        return {s.name: (s['st_value'], s['st_size']) for s in table.iter_symbols()}


def verify_layout(old_elf, new_elf, external, profile):
    old, new = symbols(old_elf), symbols(new_elf)
    for name, (offset, size) in profile['save_symbols'].items():
        wanted = (profile['external_base'] + offset, size)
        require(old.get(name) == new.get(name) == wanted, 'Save address or size changed: ' + name)
    for name in ('__SAVEFLASH_START__', '__SAVEFLASH_END__', '__CONFIGFLASH_START__',
                 '__CONFIGFLASH_END__', '__BATTERYFLASH_START__', '__BATTERYFLASH_END__'):
        require(name in old and name in new and old[name][0] == new[name][0], 'Layout changed: ' + name)
    for name, offset in [('__BATTERYFLASH_START__', profile['mutable_start']),
                         ('__BATTERYFLASH_END__', profile['battery_end']),
                         ('__CONFIGFLASH_START__', profile['config_start']),
                         ('__CONFIGFLASH_END__', profile['flash_size'])]:
        require(new[name][0] == profile['external_base'] + offset, 'Profile mismatch: ' + name)
    require(len(padded(external, profile['erase_size'])) <= profile['mutable_start'], 'Image overlaps save storage')


def verify(old_elf, new_elf, external, profile):
    verify_layout(old_elf, new_elf, external, profile)
    require(rom_identities(old_elf, profile) == rom_identities(new_elf, profile),
            'ROM identity or save mapping changed; a separate save migration is required')
