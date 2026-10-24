"""Read build identities from the actual linked ELF, without source ROM access."""
import hashlib

from elftools.elf.elffile import ELFFile
from elftools.dwarf.dwarf_expr import DWARFExprParser

from .common import require

INTERNAL_SECTIONS = ('.isr_vector', '.text', '.rodata', '.ARM.extab',
                     '.preinit_array', '.init_array', '.fini_array', '.data')
EXTERNAL_SECTIONS = ('._itcram_hot', '._ram_exec', '._extflash') + tuple(
    '.overlay_' + name for name in ('nes', 'nes_fceu', 'gb', 'sms', 'col', 'pce',
                                   'msx', 'gw', 'wsv', 'md', 'a7800', 'amstrad',
                                   'zelda3', 'smw', 'tama'))


def read_address(elf, address, size):
    require(size > 0, 'Empty ELF data range')
    for section in elf.iter_sections():
        if section['sh_type'] == 'SHT_NOBITS' or not section['sh_flags'] & 2:
            continue
        offset = address - section['sh_addr']
        if 0 <= offset and offset + size <= section['sh_size']:
            return section.data()[offset:offset + size]
    raise ValueError('ELF data range is not mapped')


def binary_image(elf, names, base):
    """Match objcopy's selected sections, physical load addresses and zero gaps."""
    chunks = []
    for name in names:
        section = elf.get_section_by_name(name)
        if section is None or not section['sh_size'] or section['sh_type'] == 'SHT_NOBITS':
            continue
        for segment in elf.iter_segments():
            if segment['p_type'] == 'PT_LOAD' and segment.section_in_segment(section):
                address = segment['p_paddr'] + section['sh_addr'] - segment['p_vaddr']
                chunks.append((address, section.data()))
                break
        else:
            raise ValueError('ELF section has no load segment: ' + name)
    require(chunks and min(a for a, _ in chunks) == base, 'Unexpected ELF image base')
    end = max(a + len(data) for a, data in chunks)
    require(end - base <= 4 * 1024 * 1024, 'ELF image exceeds supported capacity')
    image = bytearray(end - base)
    for address, data in chunks:
        image[address - base:address - base + len(data)] = data
    return bytes(image)


def verify_images(path, internal, external):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        require(elf.elfclass == 32 and elf.little_endian and elf['e_machine'] == 'EM_ARM',
                'Expected a little-endian ARM ELF')
        require(binary_image(elf, INTERNAL_SECTIONS, 0x08000000) == internal,
                'Internal binary does not match ELF')
        require(binary_image(elf, EXTERNAL_SECTIONS, 0x90000000) == external,
                'External binary does not match ELF')
        bank2 = elf.get_section_by_name('.flash2')
        require(bank2 is None or bank2['sh_size'] == 0, 'Bank 2 images are not supported')


def descriptor_type(elf):
    require(elf.has_dwarf_info(), 'ELF needs debug information for ROM identity checks; build with DEBUG=1')
    for cu in elf.get_dwarf_info().iter_CUs():
        for die in cu.iter_DIEs():
            name = die.attributes.get('DW_AT_name')
            if die.tag != 'DW_TAG_typedef' or name is None or name.value != b'retro_emulator_file_t':
                continue
            struct = die.get_DIE_from_attribute('DW_AT_type')
            members = {}
            for member in struct.iter_children():
                if member.tag != 'DW_TAG_member':
                    continue
                kind = member.get_DIE_from_attribute('DW_AT_type')
                while 'DW_AT_byte_size' not in kind.attributes:
                    kind = kind.get_DIE_from_attribute('DW_AT_type')
                offset = member.attributes['DW_AT_data_member_location'].value
                if isinstance(offset, list):
                    operations = DWARFExprParser(cu.structs).parse_expr(offset)
                    require(len(operations) == 1 and operations[0].op_name == 'DW_OP_plus_uconst',
                            'Unsupported ELF member location expression')
                    offset = operations[0].args[0]
                require(isinstance(offset, int), 'Unsupported ELF member offset')
                members[member.attributes['DW_AT_name'].value.decode()] = (
                    offset, kind.attributes['DW_AT_byte_size'].value)
            return struct.attributes['DW_AT_byte_size'].value, members
    raise ValueError('ELF has no ROM descriptor debug type')


def rom_identities(path, profile):
    """Bind each validated save slot to compiled ROM bytes and emulator options."""
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        table = elf.get_section_by_name('.symtab')
        require(table is not None, 'ELF has no symbol table')
        entries = table.get_symbol_by_name('nes_roms')
        require(entries and len(entries) == 1, 'ELF has no unique NES ROM table')
        stride, members = descriptor_type(elf)
        entry = entries[0]
        require(stride > 0 and entry['st_size'] % stride == 0, 'Invalid NES ROM table size')
        data = read_address(elf, entry['st_value'], entry['st_size'])
        expected = {profile['external_base'] + offset: (name, size)
                    for name, (offset, size) in profile['save_symbols'].items()}
        identities = {}
        for start in range(0, len(data), stride):
            def value(name):
                offset, size = members[name]
                require(offset + size <= stride, 'Invalid ROM descriptor member')
                return int.from_bytes(data[start + offset:start + offset + size], 'little')
            if not value('save_size'):
                continue
            slot = expected.get(value('save_address'))
            require(slot and slot[1] == value('save_size'), 'Unvalidated ROM save slot')
            name = slot[0]
            require(name not in identities, 'Duplicate ROM save slot')
            rom = read_address(elf, value('address'), value('size'))
            identities[name] = {'sha256': hashlib.sha256(rom).hexdigest(),
                                'bytes': len(rom), 'mapper': value('mapper'),
                                'region': value('region'), 'game_config': value('game_config')}
        require(set(identities) == set(profile['save_symbols']), 'ROM save-slot inventory differs')
        return identities
