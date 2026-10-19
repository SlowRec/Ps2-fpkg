"""Imágenes BIN/CUE de PS1: lectura del .cue, unión de pistas en un solo .bin y el TOC
binario que usa el emulador de PS1 de PS4 (necesario para la música en CD-Audio)."""

import os
import re
from dataclasses import dataclass, field

RAW_SECTOR = 2352
LEAD_IN = 150  # 2 segundos de pregap del disco: las posiciones absolutas empiezan en 00:02:00


class CueError(Exception):
    pass


@dataclass
class Track:
    number: int
    mode: str                 # "AUDIO", "MODE2/2352", ...
    file_index: int
    indexes: dict = field(default_factory=dict)  # número de índice -> sector relativo al archivo

    @property
    def is_audio(self):
        return self.mode.upper() == "AUDIO"


@dataclass
class Cue:
    path: str
    files: list               # rutas absolutas de los .bin
    tracks: list

    def file_starts(self):
        """Sector absoluto (sin lead-in) donde empieza cada archivo una vez unidos."""
        starts, pos = [], 0
        for path in self.files:
            starts.append(pos)
            pos += os.path.getsize(path) // RAW_SECTOR
        return starts

    def total_sectors(self):
        return sum(os.path.getsize(p) for p in self.files) // RAW_SECTOR

    def absolute(self, track, index):
        """Sector absoluto de un índice de pista (o None si no existe)."""
        if index not in track.indexes:
            return None
        return self.file_starts()[track.file_index] + track.indexes[index]


def msf_to_sectors(text):
    m, s, f = (int(x) for x in text.split(":"))
    return (m * 60 + s) * 75 + f


def sectors_to_msf(sectors):
    return sectors // 4500, sectors // 75 % 60, sectors % 75


def parse(path):
    """Lee un .cue (una o varias pistas/archivos). Los .bin deben estar junto al .cue."""
    folder = os.path.dirname(os.path.abspath(path))
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    files, tracks = [], []
    for raw in lines:
        line = raw.strip()
        word = line.split(" ", 1)[0].upper()
        if word == "FILE":
            m = re.match(r'FILE\s+"(.+)"\s+(\S+)$', line, re.I) or re.match(r"FILE\s+(\S+)\s+(\S+)$", line, re.I)
            if not m:
                raise CueError(f"{path}: línea FILE no válida: {line}")
            bin_path = os.path.join(folder, m.group(1))
            if not os.path.isfile(bin_path):
                raise CueError(f"No se encuentra {m.group(1)} (indicado en {os.path.basename(path)}).")
            if os.path.getsize(bin_path) % RAW_SECTOR:
                raise CueError(f"{m.group(1)}: el tamaño no es múltiplo de 2352; no es una imagen BIN en bruto.")
            files.append(bin_path)
        elif word == "TRACK":
            parts = line.split()
            if not files:
                raise CueError(f"{path}: TRACK antes de FILE.")
            tracks.append(Track(int(parts[1]), parts[2].upper(), len(files) - 1))
        elif word == "INDEX":
            parts = line.split()
            if not tracks:
                raise CueError(f"{path}: INDEX antes de TRACK.")
            tracks[-1].indexes[int(parts[1])] = msf_to_sectors(parts[2])
        elif word in ("PREGAP", "POSTGAP"):
            raise CueError(f"{path}: usa {word}, que exige insertar datos en la imagen. "
                           "Usa una imagen en formato Redump (cada pista con su INDEX 00).")
    if not tracks:
        raise CueError(f"{path}: no tiene pistas.")
    if tracks[0].is_audio or "2352" not in tracks[0].mode:
        raise CueError(f"{path}: la pista 1 debe ser de datos en bruto (MODE2/2352).")
    for t in tracks:
        if 1 not in t.indexes:
            raise CueError(f"{path}: la pista {t.number} no tiene INDEX 01.")
    return Cue(path, files, tracks)


def merge_bins(cue, dst, progress=None):
    """Une los .bin de un .cue con varias pistas en un solo archivo."""
    total = sum(os.path.getsize(p) for p in cue.files)
    done = 0
    with open(dst, "wb") as out:
        for path in cue.files:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)


def single_bin_cue(cue, bin_name):
    """Texto de un .cue equivalente que apunta a un único .bin (posiciones absolutas)."""
    out = [f'FILE "{bin_name}" BINARY']
    for t in cue.tracks:
        out.append(f"  TRACK {t.number:02d} {t.mode}")
        for idx in sorted(t.indexes):
            m, s, f = sectors_to_msf(cue.absolute(t, idx))
            out.append(f"    INDEX {idx:02d} {m:02d}:{s:02d}:{f:02d}")
    return "\r\n".join(out) + "\r\n"


def _bcd(value):
    return (value // 10) * 16 + value % 10


def _msf_bcd(sectors):
    return bytes(_bcd(v) for v in sectors_to_msf(sectors))


def toc(cue):
    """TOC binario para el emulador de PS1 de PS4: entradas de 10 bytes con
    control, punto (pista o A0/A1/A2) y posiciones MSF en BCD (con los 2 s de lead-in)."""
    last = cue.tracks[-1].number
    out = bytearray()
    out += bytes([0x41, 0x00, 0xA0, 0, 0, 0, 0, 0x01, 0x20, 0x00])               # primera pista, disco XA
    out += bytes([0x01, 0x00, 0xA1, 0, 0, 0, 0, _bcd(last), 0x00, 0x00])          # última pista
    out += bytes([0x01, 0x00, 0xA2, 0, 0, 0, 0]) + _msf_bcd(cue.total_sectors() + LEAD_IN)  # lead-out
    for t in cue.tracks:
        entry = bytearray(10)
        entry[0] = 0x01 if t.is_audio else 0x41
        entry[2] = _bcd(t.number)
        pregap = cue.absolute(t, 0)
        if pregap is not None and t.number > 1:
            entry[3:6] = _msf_bcd(pregap + LEAD_IN)
        entry[7:10] = _msf_bcd(cue.absolute(t, 1) + LEAD_IN)
        out += entry
    return bytes(out)


def stage(cue_path, bin_dst, progress=None):
    """Prepara un disco: devuelve (ruta del .bin a usar, Cue). Une las pistas si hace falta."""
    cue = parse(cue_path)
    if len(cue.files) == 1:
        return cue.files[0], cue
    merge_bins(cue, bin_dst, progress)
    return bin_dst, cue

