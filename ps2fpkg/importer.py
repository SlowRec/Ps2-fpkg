"""Importa el emulador de PS1, PS2 o PSP desde un archivo que tenga el usuario, a
emuladores/<consola>/ junto a la app (una sola vez):

- una carpeta con eboot.bin (o la carpeta de extracción, con uroot/),
- el .pkg de un clásico (se extrae con PkgTool),
- un .zip o .7z con la carpeta,
- o el .exe de otra herramienta que lleve la base dentro (por ejemplo PSP-FPKG, que trae la
  de PSP comprimida en .7z): se buscan los archivos .7z y .zip incrustados.

Se detecta la consola por los archivos del emulador, se descartan los discos del juego original
y, si algún ejecutable viene descifrado (ELF), se firma como fSELF."""

import io
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile

from . import emu, fself, pkgbuild, ps4ftp

SEVENZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"
ZIP_EOCD = b"PK\x05\x06"


class EmuImportError(Exception):
    pass


def detect_system(base):
    """"ps2", "ps1", "psp" o None según los archivos de la carpeta del emulador."""
    names = {n.lower() for n in os.listdir(base)}
    if "config-emu-ps4.txt" in names:
        return "ps2"
    if "config-title.txt" in names:
        with open(os.path.join(base, "config-title.txt"), encoding="utf-8", errors="replace") as f:
            config = f.read().lower()
        data = {n.lower() for n in os.listdir(os.path.join(base, "data"))} if "data" in names else set()
        if "user_l0" in config or "--antialias" in config or "user_l0.img" in data:
            return "psp"
        return "ps1"
    return None


def find_bases(root):
    """Carpetas con eboot.bin de un emulador reconocible, dentro de `root`."""
    found = []
    for dirpath, _dirs, files in os.walk(root):
        if "eboot.bin" in files and detect_system(dirpath):
            found.append(dirpath)
    return found


def _extract_7z(data, dst):
    try:
        import py7zr
    except ImportError as e:  # pragma: no cover - el .exe lo incluye
        raise EmuImportError("Para archivos .7z hace falta py7zr (pip install py7zr).") from e
    with py7zr.SevenZipFile(io.BytesIO(data)) as z:
        z.extractall(dst)


def _embedded_archives(data):
    """Archivos .7z y .zip incrustados en un binario: [(tipo, bytes)]."""
    out = []
    for m in re.finditer(re.escape(SEVENZIP_MAGIC), data):
        start = m.start()
        if len(data) < start + 32:
            continue
        next_off, next_size = struct.unpack_from("<QQ", data, start + 12)
        end = start + 32 + next_off + next_size
        if 0 < next_size < 1 << 24 and end <= len(data):
            out.append(("7z", data[start:end]))
    for m in re.finditer(re.escape(ZIP_EOCD), data):
        eocd = m.start()
        if len(data) < eocd + 22:
            continue
        cd_size, cd_off = struct.unpack_from("<II", data, eocd + 12)
        start = eocd - cd_size - cd_off
        comment_len, = struct.unpack_from("<H", data, eocd + 20)
        if start >= 0 and data[start:start + 4] == b"PK\x03\x04":
            out.append(("zip", data[start:eocd + 22 + comment_len]))
    return out


def _unpack(path, work, log):
    """Deja en `work` el contenido del archivo y devuelve las carpetas de emulador encontradas."""
    if os.path.isdir(path):
        return find_bases(path)
    low = path.lower()
    if low.endswith(".pkg"):
        cmd = pkgbuild.find_pkgtool()
        if cmd is None:
            raise EmuImportError("Falta PkgTool para extraer el .pkg.")
        log("Extrayendo el .pkg...")
        res = subprocess.run(cmd + ["pkg_extract", "--passcode", "0" * 32, path, work],
                             capture_output=True, text=True, errors="replace")
        if res.returncode != 0:
            raise EmuImportError(f"No se pudo extraer el .pkg: {(res.stderr or res.stdout).strip()[-500:]}")
        return find_bases(work)
    with open(path, "rb") as f:
        data = f.read()
    if low.endswith(".zip") or data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(work)
        return find_bases(work)
    if low.endswith(".7z") or data[:6] == SEVENZIP_MAGIC:
        _extract_7z(data, work)
        return find_bases(work)
    archives = _embedded_archives(data)
    if not archives:
        raise EmuImportError(f"{os.path.basename(path)} no contiene ningún emulador reconocible.")
    log(f"Buscando el emulador dentro de {os.path.basename(path)}...")
    for n, (kind, blob) in enumerate(archives):
        dst = os.path.join(work, f"{kind}{n}")
        try:
            if kind == "7z":
                _extract_7z(blob, dst)
            else:
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    z.extractall(dst)
        except EmuImportError:
            raise
        except Exception:  # noqa: BLE001 — un falso positivo de la búsqueda; se prueba el siguiente
            continue
    return find_bases(work)


def import_base(path, system=None, dest_root=None, log=print):
    """Instala el emulador de `path` en emuladores/<consola>; devuelve (consola, carpeta)."""
    if not os.path.exists(path):
        raise EmuImportError(f"No existe {path}.")
    with tempfile.TemporaryDirectory() as work:
        bases = _unpack(path, work, log)
        if not bases:
            raise EmuImportError(f"No se encontró un emulador de PS1, PS2 o PSP en {os.path.basename(path)}.")
        detected = [(b, detect_system(b)) for b in bases]
        base, found = next(((b, s) for b, s in detected if s == system), detected[0])
        if system and found != system:
            log(f"Aviso: es un emulador de {emu.SYSTEM_NAMES[found]}, no de {emu.SYSTEM_NAMES[system]}: "
                f"se guarda como emulador de {emu.SYSTEM_NAMES[found]}.")
        dest = os.path.join(dest_root, found) if dest_root else emu.default_base_dirs(found)[0]
        if os.path.abspath(base) == os.path.abspath(dest):
            return found, dest
        tmp = dest + ".importando"
        shutil.rmtree(tmp, ignore_errors=True)
        signed = 0
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                src = os.path.join(dirpath, name)
                rel = os.path.relpath(src, base).replace(os.sep, "/")
                if ps4ftp.skipped(rel):
                    continue
                out = os.path.join(tmp, *rel.split("/"))
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(src, "rb") as f:
                    head = f.read(4)
                if head == fself.ELF_MAGIC and rel.lower().endswith(emu.EXECUTABLE_EXT):
                    with open(src, "rb") as f:
                        data = fself.make(f.read())
                    with open(out, "wb") as f:
                        f.write(data)
                    signed += 1
                else:
                    shutil.copyfile(src, out)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.replace(tmp, dest)
    log(f"Listo: emulador de {emu.SYSTEM_NAMES[found]} guardado en {dest}"
        + (f" ({signed} ejecutables firmados como fSELF)." if signed else "."))
    return found, dest
