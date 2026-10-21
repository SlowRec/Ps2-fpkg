"""Importa los emuladores de PS1, PS2 o PSP desde un archivo que tenga el usuario, a
emuladores/<consola>/ junto a la app (una sola vez):

- una carpeta con eboot.bin (o la carpeta de extracción, con uroot/),
- el .pkg de un clásico (se extrae con PkgTool),
- un .zip o .7z con la carpeta,
- o una herramienta que lleve la base dentro, en su .exe o en el .7z/.zip que la trae
  (PSP-FPKG, PSX-FPKG y PS2-FPKG guardan las bases comprimidas en .7z dentro del .exe): se
  buscan los archivos .7z y .zip incrustados.

Se detecta la consola por los archivos del emulador (si hay varias, se instalan todas), se
descartan los discos del juego original y, si algún ejecutable viene descifrado (ELF), se firma
como fSELF."""

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


def _seven_zip_tool():
    """7-Zip de línea de comandos (para .7z con el filtro BCJ2, que py7zr no lee), o None."""
    found = pkgbuild.find_tool(("7zr.exe", "7za.exe", "7z.exe", "7zz", "7zr", "7za", "7z"))
    if found:
        return found
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        path = os.path.join(os.environ.get(env, ""), "7-Zip", "7z.exe")
        if os.environ.get(env) and os.path.isfile(path):
            return path
    return None


def _extract_7z(data, dst):
    """Extrae un .7z (bytes) con py7zr y, si usa un método que py7zr no admite, con 7-Zip."""
    try:
        import py7zr
        with py7zr.SevenZipFile(io.BytesIO(data)) as z:
            z.extractall(dst)
        return
    except ImportError:
        error = "falta py7zr"
    except Exception as e:  # noqa: BLE001 — p. ej. el filtro BCJ2: se intenta con 7-Zip
        error = str(e).split("\n")[0][:120]
    tool = _seven_zip_tool()
    if tool is None:
        raise EmuImportError(f"No se pudo descomprimir el .7z ({error}). Descomprímelo primero (clic derecho → "
                             "Extraer todo, o con 7-Zip) y elige el archivo .exe que viene dentro.")
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "a.7z")
        with open(archive, "wb") as f:
            f.write(data)
        res = subprocess.run([tool, "x", "-y", f"-o{dst}", archive], capture_output=True, text=True,
                             errors="replace")
    if res.returncode != 0:
        raise EmuImportError(f"7-Zip no pudo descomprimir el archivo: {(res.stderr or res.stdout).strip()[-300:]}")


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


def _extract_embedded(data, work, log, name):
    """Extrae en `work` los .7z y .zip incrustados en un binario (p. ej. el .exe de PSP-FPKG)."""
    archives = _embedded_archives(data)
    if archives:
        log(f"Buscando el emulador dentro de {name}...")
    for n, (kind, blob) in enumerate(archives):
        dst = os.path.join(work, f"{kind}{n}")
        try:
            if kind == "7z":
                _extract_7z(blob, dst)
            else:
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    z.extractall(dst)
        except Exception:  # noqa: BLE001 — un falso positivo de la búsqueda; se prueba el siguiente
            continue


def _unpack(path, work, log):
    """Deja en `work` el contenido del archivo y devuelve las carpetas de emulador encontradas.
    Si un archivo comprimido trae un .exe con la base dentro, se busca también en ese .exe."""
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
    elif low.endswith(".7z") or data[:6] == SEVENZIP_MAGIC:
        log(f"Descomprimiendo {os.path.basename(path)}...")
        _extract_7z(data, work)
    else:
        _extract_embedded(data, work, log, os.path.basename(path))
        return find_bases(work)
    bases = find_bases(work)
    if not bases:
        for dirpath, _dirs, files in list(os.walk(work)):
            for name in files:
                if name.lower().endswith(".exe"):
                    with open(os.path.join(dirpath, name), "rb") as f:
                        inner = f.read()
                    _extract_embedded(inner, os.path.join(dirpath, name + ".contenido"), log, name)
        bases = find_bases(work)
    return bases


def _preferred(bases):
    """Una carpeta por consola; en PS2, la base de Jak and Daxter (la más compatible) primero."""
    chosen = {}
    for base in sorted(bases, key=lambda b: (0 if "jak" in os.path.basename(b).lower() else 1, b)):
        chosen.setdefault(detect_system(base), base)
    return chosen


def _install(base, dest):
    """Copia la base a `dest` (sin los discos del juego); firma los ejecutables descifrados."""
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
    return signed


def import_all(path, dest_root=None, log=print):
    """Instala todos los emuladores (uno por consola) que haya en `path`; devuelve {consola: carpeta}."""
    if not os.path.exists(path):
        raise EmuImportError(f"No existe {path}.")
    installed = {}
    with tempfile.TemporaryDirectory() as work:
        bases = _unpack(path, work, log)
        if not bases:
            raise EmuImportError(f"No se encontró un emulador de PS1, PS2 o PSP en {os.path.basename(path)}.")
        for system, base in _preferred(bases).items():
            dest = os.path.join(dest_root, system) if dest_root else emu.default_base_dirs(system)[0]
            signed = _install(base, dest) if os.path.abspath(base) != os.path.abspath(dest) else 0
            installed[system] = dest
            log(f"Listo: emulador de {emu.SYSTEM_NAMES[system]} ({os.path.basename(base)}) guardado en {dest}"
                + (f" ({signed} ejecutables firmados como fSELF)." if signed else "."))
    return installed


def import_base(path, system=None, dest_root=None, log=print):
    """Como import_all; devuelve (consola, carpeta) de la consola pedida (o de la primera encontrada)."""
    installed = import_all(path, dest_root, log)
    if system in installed:
        return system, installed[system]
    found = next(iter(installed))
    if system:
        log(f"Aviso: no es un emulador de {emu.SYSTEM_NAMES[system]}; se instaló el de "
            f"{emu.SYSTEM_NAMES[found]}.")
    return found, installed[found]
