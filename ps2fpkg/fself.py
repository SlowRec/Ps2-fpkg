"""Firma falsa (fSELF) de ejecutables de PS4 descifrados (ELF), como make_fself.py de flatz y
create-fself de OpenOrbis (pkg/fself/FSELF.go, del que es un port): GoldHEN carga los fSELF sin
la firma de Sony. Se usa para el emulador traído de la PS4 por FTP (ps4ftp.py), que llega
descifrado."""

import hashlib
import struct

SELF_MAGIC = b"\x4f\x15\x3d\x1d"
ELF_MAGIC = b"\x7fELF"
BLOCK_SIZE = 0x4000
PT_LOAD = 1
PT_SCE_RELRO = 0x61000010
PT_SCE_DYNLIBDATA = 0x61000000
ENTRY_SIZE = 0x50               # tamaño que cuenta MetaSize por entrada
META_FOOTER_SIZE = 0x50
SIGNATURE_SIZE = 0x100
EXTENDED_INFO_SIZE = 0x40
NPDRM_BLOCK_SIZE = 0x30
PTYPE_FAKE = 1
PTYPE_NPDRM_EXEC = 4
PTYPE_NPDRM_DYNLIB = 5
DEFAULT_PAID = 0x3800000000000011


class FselfError(Exception):
    pass


def _align(value, alignment):
    return (value + alignment - 1) & ~(alignment - 1)


def _segments(elf):
    if elf[:4] != ELF_MAGIC or len(elf) < 0x40:
        raise FselfError("no es un ELF")
    phoff, = struct.unpack_from("<Q", elf, 0x20)
    phentsize, phnum = struct.unpack_from("<HH", elf, 0x36)
    progs = []
    for i in range(phnum):
        p_type, p_flags, p_off, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from(
            "<IIQQQQQQ", elf, phoff + i * phentsize)
        progs.append((p_type, p_flags, p_off, p_vaddr, p_paddr, p_filesz, p_memsz, p_align))
    return progs


def read_info(self_data):
    """(paid, ptype, app_version, fw_version) de un SELF (cifrado o no): esa parte va en claro."""
    if self_data[:4] != SELF_MAGIC:
        raise FselfError("no es un SELF")
    num_entries, = struct.unpack_from("<H", self_data, 0x18)
    elf_off = 0x20 + num_entries * 0x20
    phnum, = struct.unpack_from("<H", self_data, elf_off + 0x38)
    ext_off = _align(elf_off + 0x40 + phnum * 0x38, 0x10)
    return struct.unpack_from("<QQQQ", self_data, ext_off)


def _signature(auth_info, paid):
    if not auth_info:
        return bytes(SIGNATURE_SIZE)
    raw = bytes.fromhex(auth_info)
    sig = struct.pack("<QQ", len(raw), paid) + raw[8:]
    return sig + bytes(-len(sig) % SIGNATURE_SIZE)


def make(elf, paid=None, ptype=None, app_version=0, fw_version=0, auth_info=""):
    """fSELF (bytes) a partir de un ELF de PS4 (bytes). Sin ptype: fake (1), como make_fself."""
    progs = _segments(elf)
    paid = DEFAULT_PAID if paid is None else paid
    ptype = PTYPE_FAKE if ptype is None else ptype
    kept = [(i, p) for i, p in enumerate(progs) if p[0] in (PT_LOAD, PT_SCE_RELRO, PT_SCE_DYNLIBDATA)]

    # Dos entradas por segmento: metadatos (firmados, con resúmenes) y datos (firmados, por bloques).
    entries = []
    for n, (i, _p) in enumerate(kept):
        meta_props = (1 << 2) | (1 << 16) | (((2 * n + 1) & 0xFFFF) << 20)
        data_props = (1 << 2) | (1 << 11) | (((BLOCK_SIZE.bit_length() - 1 - 12) & 0xF) << 12) | ((i & 0xFFFF) << 20)
        entries += [[meta_props, 0, 0, 0, b""], [data_props, 0, 0, 0, b""]]

    header_size = 0x20 + len(entries) * 0x20 + 0x40 + len(progs) * 0x38
    header_size = _align(header_size, 0x10) + EXTENDED_INFO_SIZE + NPDRM_BLOCK_SIZE
    meta_size = len(entries) * ENTRY_SIZE + META_FOOTER_SIZE + SIGNATURE_SIZE
    offset = header_size + meta_size
    for n, (_i, p) in enumerate(kept):
        filesz = p[5]
        meta = bytes(0x20 * (_align(filesz, BLOCK_SIZE) // BLOCK_SIZE))
        entries[2 * n][1:] = [offset, len(meta), len(meta), meta]
        offset = _align(offset + len(meta), 0x10)
        data = elf[p[2]:p[2] + filesz]
        if len(data) != filesz:
            raise FselfError("segmento fuera del archivo")
        entries[2 * n + 1][1:] = [offset, filesz, filesz, data]
        offset = _align(offset + filesz, 0x10)
    file_size = offset

    flags = 0x2 | ((0x2 & 0x7) << 4)
    out = bytearray()
    out += SELF_MAGIC + struct.pack("<BBBBIHHQHH", 0, 1, 1, 0x12, 0x101, header_size, meta_size, file_size,
                                    len(entries), flags)
    out += bytes(-len(out) % 0x10)
    for props, off, fsz, msz, _data in entries:
        out += struct.pack("<QQQQ", props, off, fsz, msz)
    out += elf[:0x40]
    for p in progs:
        out += struct.pack("<IIQQQQQQ", *p)
    out += bytes(-len(out) % 0x10)
    out += struct.pack("<QQQQ", paid, ptype, app_version, fw_version) + hashlib.sha256(elf).digest()
    out += struct.pack("<H", 3) + bytes(NPDRM_BLOCK_SIZE - 2)
    out += bytes(ENTRY_SIZE * len(entries))
    out += bytes(0x30) + struct.pack("<I", 0x10000) + bytes(0x1C)
    out += _signature(auth_info, paid)
    if len(out) > file_size:
        raise FselfError("cabecera mayor que el archivo")
    out += bytes(file_size - len(out))
    for _props, off, _fsz, _msz, data in entries:
        out[off:off + len(data)] = data
    return bytes(out)


def unwrap(fself_data):
    """Segmentos (índice de programa -> bytes) de un fSELF; para comprobar el resultado."""
    num_entries, = struct.unpack_from("<H", fself_data, 0x18)
    segments = {}
    for n in range(num_entries):
        props, off, fsz, _msz = struct.unpack_from("<QQQQ", fself_data, 0x20 + n * 0x20)
        if props & (1 << 11):
            segments[(props >> 20) & 0xFFFF] = fself_data[off:off + fsz]
    return segments
