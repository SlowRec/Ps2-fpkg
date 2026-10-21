"""Escritura y lectura de param.sfo (formato PSF de PS4)."""

import struct

FMT_UTF8_SPECIAL = 0x0004
FMT_UTF8 = 0x0204
FMT_INT32 = 0x0404


def build(entries):
    """entries: lista de (clave, valor, max_len). Un int se guarda como int32;
    un str como UTF-8 terminado en nulo con espacio reservado max_len."""
    items = []
    for key, value, max_len in entries:
        if isinstance(value, int):
            items.append((key, FMT_INT32, struct.pack("<I", value & 0xFFFFFFFF), 4))
        else:
            data = value.encode("utf-8") + b"\x00"
            if len(data) > max_len:
                raise ValueError(f"{key}: el valor excede {max_len} bytes.")
            items.append((key, FMT_UTF8, data, max_len))
    items.sort(key=lambda it: it[0])

    key_table_offset = 0x14 + 0x10 * len(items)
    key_table_size = sum(len(k) + 1 for k, *_ in items)
    data_table_offset = key_table_offset + key_table_size
    data_table_offset += -data_table_offset % 4

    header = struct.pack(">I", 0x00505346) + struct.pack("<IIII", 0x101, key_table_offset, data_table_offset, len(items))
    index, keys, data = bytearray(), bytearray(), bytearray()
    for key, fmt, raw, max_len in items:
        index += struct.pack("<HHIII", len(keys), fmt, len(raw), max_len, len(data))
        keys += key.encode("ascii") + b"\x00"
        data += raw + b"\x00" * (max_len - len(raw))
    keys += b"\x00" * (data_table_offset - key_table_offset - len(keys))
    return bytes(header + index + keys + data)


def parse(blob):
    """Devuelve un dict clave -> valor (int o str)."""
    if blob[:4] != b"\x00PSF":
        raise ValueError("No es un param.sfo válido.")
    key_off, data_off, count = struct.unpack_from("<III", blob, 8)
    out = {}
    for i in range(count):
        k, fmt, length, _max, d = struct.unpack_from("<HHIII", blob, 0x14 + 0x10 * i)
        name = blob[key_off + k:blob.index(b"\x00", key_off + k)].decode("ascii")
        raw = blob[data_off + d:data_off + d + length]
        if fmt == FMT_INT32:
            out[name] = struct.unpack("<I", raw)[0]
        else:
            out[name] = raw.rstrip(b"\x00").decode("utf-8")
    return out


def ps2_classic(title, title_id, content_id, version="01.00", attribute=0):
    """param.sfo mínimo para un juego (categoría gd) en fPKG. attribute 0x2: los diálogos del
    sistema (teclado) confirman con X."""
    return build([
        ("APP_TYPE", 1, 4),
        ("APP_VER", version, 8),
        ("ATTRIBUTE", attribute, 4),
        ("CATEGORY", "gd", 4),
        ("CONTENT_ID", content_id, 48),
        ("DOWNLOAD_DATA_SIZE", 0, 4),
        ("FORMAT", "obs", 4),
        ("PARENTAL_LEVEL", 1, 4),
        ("SYSTEM_VER", 0, 4),
        ("TITLE", title, 128),
        ("TITLE_ID", title_id, 12),
        ("VERSION", version, 8),
    ])
