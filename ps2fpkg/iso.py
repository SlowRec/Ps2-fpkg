"""Lectura de imágenes de disco de PS2: formato de sector, SYSTEM.CNF y serial."""

import os
import re
import struct

SECTOR = 2048
RAW_SECTOR = 2352
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


class DiscError(Exception):
    pass


class DiscImage:
    """Imagen ISO (2048 bytes/sector) o BIN en bruto (2352 bytes/sector, modo 1 o 2)."""

    def __init__(self, path):
        self.path = path
        self.size = os.path.getsize(path)
        self._f = open(path, "rb")
        try:
            self._detect()
        except Exception:
            self._f.close()
            raise

    def _detect(self):
        path = self.path
        head = self._f.read(16)
        if head[:12] == SYNC:
            self.sector_size = RAW_SECTOR
            mode = head[15]
            if mode == 1:
                self.data_offset = 16
            elif mode == 2:
                self.data_offset = 24
            else:
                raise DiscError(f"{path}: modo de sector desconocido ({mode}).")
        else:
            self.sector_size = SECTOR
            self.data_offset = 0
        if self.read_sector(16)[:6] != b"\x01CD001":
            raise DiscError(f"{path}: no es una imagen ISO9660 válida (no se encontró el descriptor de volumen).")

    @property
    def is_raw(self):
        return self.sector_size != SECTOR

    @property
    def sector_count(self):
        return self.size // self.sector_size

    def read_sector(self, lba):
        self._f.seek(lba * self.sector_size + self.data_offset)
        data = self._f.read(SECTOR)
        if len(data) != SECTOR:
            raise DiscError(f"{self.path}: lectura fuera de rango (sector {lba}).")
        return data

    def read_extent(self, lba, size):
        out = bytearray()
        for i in range((size + SECTOR - 1) // SECTOR):
            out += self.read_sector(lba + i)
        return bytes(out[:size])

    def _find_in_dir(self, lba, size, name):
        """Busca `name` en un directorio; devuelve (lba, tamaño, es_directorio, posición del
        registro en el directorio) o None."""
        data = self.read_extent(lba, size)
        pos = 0
        while pos < len(data):
            rec_len = data[pos]
            if rec_len == 0:
                # Los registros no cruzan sectores: saltar al siguiente.
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            name_len = data[pos + 32]
            raw_name = data[pos + 33:pos + 33 + name_len].decode("ascii", "replace")
            if raw_name.split(";")[0].rstrip(".").upper() == name.upper():
                return (struct.unpack_from("<I", data, pos + 2)[0],
                        struct.unpack_from("<I", data, pos + 10)[0],
                        bool(data[pos + 25] & 2), lba * SECTOR + pos)
            pos += rec_len
        return None

    def find_record(self, path):
        """Devuelve (lba, tamaño, posición del registro de directorio en la imagen ISO) de un
        archivo ('SYSTEM.CNF' o 'DATA\\SLUS_209.46'), o None. La posición solo es válida en
        imágenes ISO de 2048 bytes/sector."""
        root = self.read_sector(16)[156:190]
        lba, size = struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0]
        parts = [p for p in re.split(r"[\\/]", path) if p]
        record = None
        for i, part in enumerate(parts):
            entry = self._find_in_dir(lba, size, part.split(";")[0])
            if entry is None or entry[2] != (i < len(parts) - 1):
                return None
            lba, size, record = entry[0], entry[1], entry[3]
        return lba, size, record

    def find_file(self, path):
        """Devuelve (lba, tamaño) de un archivo, o None."""
        entry = self.find_record(path)
        return entry[:2] if entry else None

    def read_file(self, path):
        entry = self.find_file(path)
        if entry is None:
            return None
        return self.read_extent(*entry)

    def copy_with_limg(self, dst, progress=None):
        """Copia la imagen BIN en bruto (2352 bytes/sector) y le añade el sector LIMG al final, como
        PS2 Classics GUI y PS2-FPKG: el emulador de PS2 lee entonces el CD tal cual, sin convertirlo
        a 2048 bytes/sector (lo que rompe los juegos que usan tablas de sectores)."""
        total = self.size
        done = 0
        self._f.seek(0)
        with open(dst, "wb") as out:
            while True:
                chunk = self._f.read(1 << 22)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
            out.write(limg_sector(self.size // RAW_SECTOR, RAW_SECTOR))

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


SERIAL_RE = re.compile(r"BOOT2\s*=\s*cdrom0:\\?(?:[^\r\n;]*\\)?([A-Z]{4})[_-](\d{3})\.?(\d{2})", re.IGNORECASE)
BOOT_PATH_RE = re.compile(r"BOOT2\s*=\s*cdrom0:\\?([^\r\n;]+)", re.IGNORECASE)


LIMG_SIZE = 0x4000


def limg_sector(sectors, sector_size=RAW_SECTOR):
    """Sector LIMG (0x4000 bytes al final de la imagen): tipo 2 = CD (0x930 bytes/sector), 1 = DVD."""
    kind = 2 if sector_size == RAW_SECTOR else 1
    head = b"LIMG" + struct.pack(">III", kind, sectors, sector_size)
    return head + bytes(LIMG_SIZE - len(head))


def parse_serial(system_cnf):
    """'BOOT2 = cdrom0:\\SLUS_209.46;1' -> 'SLUS-20946'."""
    m = SERIAL_RE.search(system_cnf)
    if not m:
        if re.search(r"^\s*BOOT\s*=", system_cnf, re.MULTILINE):
            raise DiscError("El disco parece ser de PS1 (SYSTEM.CNF usa BOOT, no BOOT2).")
        raise DiscError("No se encontró la línea BOOT2 en SYSTEM.CNF.")
    return f"{m.group(1).upper()}-{m.group(2)}{m.group(3)}"


def read_serial(disc):
    cnf = disc.read_file("SYSTEM.CNF")
    if cnf is None:
        raise DiscError(f"{disc.path}: no contiene SYSTEM.CNF; ¿es un disco de PS2?")
    return parse_serial(cnf.decode("ascii", "replace"))


PS1_SERIAL_RE = re.compile(r"BOOT\s*=\s*cdrom:\\?(?:[^\r\n;]*\\)?([A-Z]{4})[_-](\d{3})\.?(\d{2})", re.IGNORECASE)


def read_ps1_serial(disc):
    """Serial de un disco de PS1 (línea BOOT de SYSTEM.CNF), o None si no se puede leer."""
    cnf = disc.read_file("SYSTEM.CNF")
    m = PS1_SERIAL_RE.search(cnf.decode("ascii", "replace")) if cnf else None
    return f"{m.group(1).upper()}-{m.group(2)}{m.group(3)}" if m else None


def read_boot_elf(disc):
    """Contenido del ejecutable principal indicado en BOOT2, o None."""
    cnf = disc.read_file("SYSTEM.CNF")
    m = BOOT_PATH_RE.search(cnf.decode("ascii", "replace")) if cnf else None
    return disc.read_file(m.group(1).strip()) if m else None


def elf_crc(data):
    """CRC de PCSX2: XOR de todas las palabras de 32 bits del ELF. Identifica la versión
    exacta del juego (los parches de PCSX2 se nombran SERIAL_CRC.pnach)."""
    crc = 0
    for (word,) in struct.iter_unpack("<I", data[:len(data) // 4 * 4]):
        crc ^= word
    return crc
