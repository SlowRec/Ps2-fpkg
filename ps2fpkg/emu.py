"""Base del emulador: los archivos de un PS2 Classic oficial que el usuario extrajo de su propio PKG."""

import os

CONFIG_NAME = "config-emu-ps4.txt"

# Archivos de la base que no deben pasar al nuevo PKG: los regenera esta herramienta,
# los genera PkgTool, o pertenecen al juego original (trofeos, licencias, disco).
EXCLUDE_FILES = {
    CONFIG_NAME,
    "sce_sys/param.sfo",
    "sce_sys/keystone",
    "sce_sys/nptitle.dat",
    "sce_sys/npbind.dat",
    "sce_sys/icon0.png",
    "sce_sys/pic0.png",
    "sce_sys/pic1.png",
    "sce_sys/pubtoolinfo.dat",
    "sce_sys/license.dat",
    "sce_sys/license.info",
    "sce_sys/selfinfo.dat",
    "sce_sys/imageinfo.dat",
    "sce_sys/target-param.sfo",
    "sce_sys/origin-param.sfo",
    "sce_sys/psreserved.dat",
}
EXCLUDE_DIRS = ("image/", "sce_sys/trophy/", "sce_sys/changeinfo/")
EXCLUDE_PREFIXES = ("sce_sys/playgo-",)


class EmuError(Exception):
    pass


def locate(path):
    """Acepta la carpeta con eboot.bin o la carpeta de extracción que la contiene
    (PkgTool pkg_extract deja los archivos en uroot/; otras herramientas en Image0/)."""
    for candidate in (path, *(os.path.join(path, sub) for sub in ("uroot", "Image0", "image0"))):
        if os.path.isfile(os.path.join(candidate, "eboot.bin")):
            return candidate
    raise EmuError(
        f"{path}: no contiene eboot.bin. Indica la carpeta extraída de un PS2 Classic de PS4 "
        "(la que tiene eboot.bin, ps2-emu-compiler.self, sce_sys/, etc.)."
    )


def collect(base):
    """Devuelve dict ruta_en_pkg -> ruta absoluta para los archivos que se copian de la base."""
    files = {}
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            low = rel.lower()
            if low in EXCLUDE_FILES or low.startswith(EXCLUDE_DIRS) or low.startswith(EXCLUDE_PREFIXES):
                continue
            files[rel] = os.path.abspath(full)
    return files


def warnings(base):
    out = []
    if not os.path.isfile(os.path.join(base, "ps2-emu-compiler.self")):
        out.append("La base no tiene ps2-emu-compiler.self; puede que no sea un emulador de PS2 Classics.")
    if not os.path.isfile(os.path.join(base, CONFIG_NAME)):
        out.append(f"La base no tiene {CONFIG_NAME}; se creará uno mínimo.")
    return out


def _split(line):
    """'--clave=valor' -> ('--clave', 'valor'); '--clave' -> ('--clave', None)."""
    key, sep, value = line.partition("=")
    return key.strip(), (value.strip() if sep else None)


def make_config(base, serial, disc_count, overrides=()):
    """Copia config-emu-ps4.txt de la base, fijando el serial, el número de discos
    y los argumentos extra (`overrides`, líneas tipo '--gs-uprender=2x2')."""
    path = os.path.join(base, CONFIG_NAME)
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\r\n") for ln in f]

    wanted = [f"--ps2-title-id={serial}", f"--max-disc-num={disc_count}"] + list(overrides)
    for arg in wanted:
        key, _ = _split(arg)
        for i, ln in enumerate(lines):
            if ln.strip().startswith("--") and _split(ln)[0] == key:
                lines[i] = arg
                break
        else:
            lines.append(arg)
    return "\n".join(lines) + "\n"
