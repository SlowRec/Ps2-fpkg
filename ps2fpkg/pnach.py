"""Parches de PCSX2 (.pnach) -> script Lua del emulador PS2 Classics de PS4.

La base de datos de PCSX2 (github.com/PCSX2/pcsx2_patches) tiene, por versión exacta de
cada juego (SERIAL_CRC.pnach), secciones como [Widescreen 16:9] o [No-Interlacing]. Cada
línea `patch=LUGAR,EE,DIRECCIÓN,TIPO,VALOR` es una escritura en la memoria del EE, que
aquí se traduce a eeObj.WriteMem8/WriteMem32 del API Lua del emulador.
"""

import re

# Secciones que se pueden aplicar, en el orden en que se ofrecen.
WIDESCREEN = "Widescreen 16:9"
NO_INTERLACE = "No-Interlacing"
PROGRESSIVE = "480p Mode"
NO_BLUR = "Remove Blur"
FPS60 = "60 FPS"
SECTION_ALIASES = {
    WIDESCREEN: ("widescreen 16:9",),
    NO_INTERLACE: ("no-interlacing", "no interlacing", "remove interlacing"),
    PROGRESSIVE: ("480p mode", "progressive scan", "480p"),
    NO_BLUR: ("remove blur", "no blur", "remove blur/bloom", "no motion blur"),
    FPS60: ("60 fps", "50/60 fps"),
}

PATCH_RE = re.compile(r"^patch\s*=\s*(\d)\s*,\s*EE\s*,\s*([0-9A-Fa-f]+)\s*,\s*(\w+)\s*,\s*([0-9A-Fa-f]+)", re.IGNORECASE)
EE_RAM_MASK = 0x01FFFFFF


class Section:
    def __init__(self, name):
        self.name = name
        self.writes = []          # (lugar, bytes, dirección, valor)
        self.unsupported = []     # líneas que no se pueden traducir


def parse(text):
    """Devuelve (metadatos, {nombre: Section}). Las líneas fuera de una sección se ignoran."""
    meta, sections, current = {}, {}, None
    for raw in text.splitlines():
        line = raw.split("//")[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            current = sections.setdefault(name, Section(name))
            continue
        key = line.split("=", 1)[0].strip().lower()
        if key == "patch":
            if current is None:
                continue
            m = PATCH_RE.match(line)
            if not m:
                current.unsupported.append(line)
                continue
            write = _translate(int(m.group(1)), m.group(3).lower(), int(m.group(2), 16), int(m.group(4), 16))
            if write is None:
                current.unsupported.append(line)
            else:
                current.writes.extend(write)
        elif "=" in line and current is None:
            meta[key] = line.split("=", 1)[1].strip()
    return meta, sections


def _translate(place, kind, addr, value):
    """Lista de (lugar, ancho, dirección, valor) o None si el tipo no es soportado."""
    if kind == "extended":
        op = addr >> 28
        widths = {0: 1, 1: 2, 2: 4}
        if op not in widths:
            return None  # condicionales, punteros, copias, etc.
        kind, addr = {1: "byte", 2: "short", 4: "word"}[widths[op]], addr & 0x0FFFFFFF
    addr &= EE_RAM_MASK
    if kind == "byte":
        return [(place, 1, addr, value & 0xFF)]
    if kind == "short":
        return [(place, 2, addr, value & 0xFFFF)] if addr % 2 == 0 else None
    if kind == "word":
        return [(place, 4, addr, value & 0xFFFFFFFF)] if addr % 4 == 0 else None
    if kind == "double":
        if addr % 8:
            return None
        return [(place, 4, addr, value & 0xFFFFFFFF), (place, 4, addr + 4, (value >> 32) & 0xFFFFFFFF)]
    return None


def find_section(sections, wanted):
    """Busca una sección por su nombre canónico (WIDESCREEN, NO_INTERLACE, ...)."""
    aliases = SECTION_ALIASES.get(wanted, (wanted.lower(),))
    for name, section in sections.items():
        if name.lower() in aliases:
            return section
    return None


def _lua_write(width, addr, value):
    if width == 1:
        return f"\tps2fpkgEE.WriteMem8(0x{addr:08X}, 0x{value:02X})"
    if width == 4:
        return f"\tps2fpkgEE.WriteMem32(0x{addr:08X}, 0x{value:08X})"
    # 16 bits: lectura-modificación-escritura de la palabra alineada (WriteMem32 está en todas las versiones del API).
    base, shift = addr & ~3, (addr & 2) * 8
    mask = (0xFFFF << shift) ^ 0xFFFFFFFF
    return (f"\tps2fpkgEE.WriteMem32(0x{base:08X}, (ps2fpkgEE.ReadMem32(0x{base:08X}) & 0x{mask:08X})"
            f" | 0x{value << shift:08X})")


def to_lua(sections, title="", source="", widescreen=False):
    """Genera el script Lua con las secciones dadas. Los parches de lugar 0 (una vez) se
    aplican al iniciar el juego; los de lugar 1/2 además en cada cuadro (vsync), como PCSX2."""
    once, every = [], []
    for section in sections:
        for place, width, addr, value in section.writes:
            line = _lua_write(width, addr, value)
            once.append(line)
            if place != 0:
                every.append(line)
    out = [
        "-- Generado por ps2-fpkg a partir de los parches de PCSX2 (github.com/PCSX2/pcsx2_patches).",
        f"-- Juego: {title}" if title else None,
        f"-- Origen: {source}" if source else None,
        "-- Secciones: " + ", ".join(s.name for s in sections),
        "",
        "apiRequest(1.2)",
        "",
        "local ps2fpkgEE  = getEEObject()",
        "local ps2fpkgEmu = getEmuObject()",
        "",
        "local ps2fpkgOnce = function()",
        *once,
        "end",
        "ps2fpkgEmu.AddEntryPointHook(ps2fpkgOnce)",
    ]
    if every:
        out += ["", "local ps2fpkgEveryFrame = function()", *every, "end",
                "ps2fpkgEmu.AddVsyncHook(ps2fpkgEveryFrame)"]
    if widescreen:
        out += ["", "ps2fpkgEmu.SetDisplayAspectWide()"]
    return "\n".join(line for line in out if line is not None) + "\n"
