"""Base del emulador: la carpeta de la app de PS4 que hace de emulador (un PS Classic oficial
que el usuario extrajo de su propio PKG, o pemu para NES/SNES), y sus archivos de opciones."""

import os
import sys

CONFIG_NAME = "config-emu-ps4.txt"

# Archivos de la base que no deben pasar al nuevo PKG: los regenera esta herramienta,
# los genera PkgTool, o pertenecen al juego original (trofeos, licencias, disco).
COMMON_EXCLUDE_FILES = {
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
COMMON_EXCLUDE_DIRS = ("sce_sys/trophy/", "sce_sys/changeinfo/")
EXCLUDE_PREFIXES = ("sce_sys/playgo-",)


class EmuError(Exception):
    pass


SYSTEM_NAMES = {"ps2": "PS2", "ps1": "PS1", "psp": "PSP"}


def app_dir():
    """Carpeta de la app: la del .exe, o la raíz del proyecto si se ejecuta desde el código."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_base_dirs(system):
    """Dónde se busca solo el emulador de cada consola (para no tener que indicarlo nunca)."""
    return [os.path.join(app_dir(), "emuladores", system),
            os.path.join(os.path.expanduser("~"), ".ps2fpkg", "emuladores", system)]


def find_base(system):
    """Carpeta del emulador encontrada en las ubicaciones fijas, o None."""
    for folder in default_base_dirs(system):
        try:
            return locate(folder)
        except EmuError:
            continue
    return None


def prepare_default_dirs():
    """Crea emuladores/ps2, ps1 y psp junto a la app (si se puede), con instrucciones."""
    root = os.path.join(app_dir(), "emuladores")
    try:
        for system in SYSTEM_NAMES:
            os.makedirs(os.path.join(root, system), exist_ok=True)
        readme = os.path.join(root, "LEEME.txt")
        if not os.path.exists(readme):
            with open(readme, "w", encoding="utf-8") as f:
                f.write("Copia aquí, una sola vez, la carpeta de cada emulador (la que tiene eboot.bin):\n"
                        "  ps2\\  -> de un PS2 Classic de PS4\n"
                        "  ps1\\  -> de un PS1 Classic de PS4 (PlayStation Plus)\n"
                        "  psp\\  -> de un PSP Classic de PS4 (PlayStation Plus)\n"
                        "La app los usa sola y no vuelve a pedirlos. NES y SNES no necesitan nada.\n")
    except OSError:
        pass
    return root


def locate(path, kind="PS2 Classic", system=None):
    """Acepta la carpeta con eboot.bin o la carpeta de extracción que la contiene
    (PkgTool pkg_extract deja los archivos en uroot/; otras herramientas en Image0/).
    Sin `path`, usa el emulador guardado en emuladores/<system> junto a la app."""
    if not path:
        found = find_base(system) if system else None
        if found:
            return found
        where = default_base_dirs(system)[0] if system else "la carpeta emuladores junto a la app"
        raise EmuError(f"Falta el emulador de {SYSTEM_NAMES.get(system, kind)}. Copia una sola vez la carpeta "
                       f"de un {kind} de PS4 (la que tiene eboot.bin) en:\n{where}\n"
                       "Desde entonces la app la usará sola, sin volver a pedirla.")
    for candidate in (path, *(os.path.join(path, sub) for sub in ("uroot", "Image0", "image0"))):
        if os.path.isfile(os.path.join(candidate, "eboot.bin")):
            return candidate
    raise EmuError(
        f"{path}: no contiene eboot.bin. Indica la carpeta extraída de un {kind} de PS4 "
        "(la que tiene eboot.bin, sce_module/, sce_sys/, etc.)."
    )


def collect_base(base, exclude_files=(), exclude_dirs=()):
    """Devuelve dict ruta_en_pkg -> ruta absoluta para los archivos que se copian de la base,
    sin los comunes a excluir ni los indicados (rutas en minúsculas; carpetas terminadas en /)."""
    skip_files = COMMON_EXCLUDE_FILES | {f.lower() for f in exclude_files}
    skip_dirs = COMMON_EXCLUDE_DIRS + tuple(d.lower() for d in exclude_dirs)
    files = {}
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            low = rel.lower()
            if low in skip_files or low.startswith(skip_dirs) or low.startswith(EXCLUDE_PREFIXES):
                continue
            files[rel] = os.path.abspath(full)
    return files


def collect(base):
    """Archivos de una base de PS2 Classic (sin su disco ni su configuración)."""
    return collect_base(base, {CONFIG_NAME}, ("image/",))


EXECUTABLE_EXT = (".bin", ".self", ".sprx", ".prx")

# Perfiles de calidad: opciones de config-emu-ps4.txt.
#   --gs-uprender: resolución interna (none = nativa de PS2, 2x2 = doble en cada eje, lo máximo del emulador).
#   --gs-upscale:  filtro al escalar a la salida (edgesmooth suaviza bordes; point/bilinear/gpu/none).
#   --host-audio:  salida de audio del emulador activada.
QUALITY_PROFILES = {
    "maxima": ["--gs-uprender=2x2", "--gs-upscale=edgesmooth", "--host-audio=1"],
    "rendimiento": ["--gs-uprender=none", "--gs-upscale=edgesmooth", "--host-audio=1"],
    "original": [],
}


def warnings(base):
    out = []
    if not os.path.isfile(os.path.join(base, "ps2-emu-compiler.self")):
        out.append("La base no tiene ps2-emu-compiler.self; puede que no sea un emulador de PS2 Classics.")
    if not os.path.isfile(os.path.join(base, CONFIG_NAME)):
        out.append(f"La base no tiene {CONFIG_NAME}; se creará uno mínimo.")
    unsigned = unsigned_executables(base)
    if unsigned:
        out.append("Estos ejecutables son ELF sin firmar (no fSELF) y la PS4 podría no abrirlos: "
                   + ", ".join(unsigned) + ". Fírmalos con make_fself o usa una base extraída de un fPKG.")
    return out


def unsigned_executables(base):
    """Ejecutables que son ELF planos (descifrados pero sin la firma falsa fSELF)."""
    found = []
    for rel in collect(base):
        if rel.lower().endswith(EXECUTABLE_EXT):
            with open(os.path.join(base, *rel.split("/")), "rb") as f:
                if f.read(4) == b"\x7fELF":
                    found.append(rel)
    return sorted(found)


def arg_key(line):
    """'--clave=valor' o '#--clave=valor' -> '--clave'; None si no es una opción."""
    text = line.strip().lstrip("#").strip()
    return text.partition("=")[0].strip() if text.startswith("--") else None


def parse_args(text):
    """Opciones de un archivo de configuración (ignora comentarios)."""
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("--")]


def read_lines(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\r\n") for ln in f]


def merge_args(lines, overrides=(), drop=(), uncomment=(), extra=()):
    """Aplica opciones '--clave=valor' sobre las líneas de un archivo de configuración.
    `overrides`: reemplazan la línea con la misma clave (aunque esté comentada) o se añaden;
    la última gana. `drop`: claves que se quitan (salvo que estén en overrides).
    `uncomment`: claves comentadas que se activan. `extra`: líneas que se añaden tal cual
    (para opciones que se repiten, como --image)."""
    wanted = {}
    for arg in overrides:
        wanted[arg_key(arg)] = arg.strip()
    out = []
    for ln in lines:
        key = arg_key(ln)
        commented = ln.strip().startswith("#")
        if key in wanted:
            if wanted[key] is not None:
                out.append(wanted[key])  # reemplaza en su lugar, aunque estuviera comentada
                wanted[key] = None
            continue
        if key and not commented and key in drop:
            continue
        if commented and key in uncomment:
            ln = ln.strip().lstrip("#")
        out.append(ln)
    out += [arg for arg in wanted.values() if arg is not None]
    out += list(extra)
    return "\n".join(out) + "\n"


def make_config(base, serial, disc_count, overrides=(), drop=()):
    """Copia config-emu-ps4.txt de la base fijando el serial y el número de discos, y aplica
    `overrides` (líneas '--clave=valor', la última gana). Las claves de `drop` se quitan
    (salvo que estén en overrides): sirve para que la configuración oficial del juego mande.
    Con varios discos activa el script de cambio de disco de la base."""
    return merge_args(read_lines(os.path.join(base, CONFIG_NAME)),
                      [f"--ps2-title-id={serial}", f"--max-disc-num={disc_count}", *overrides], drop,
                      uncomment={"--path-toolingscript"} if disc_count > 1 else ())
