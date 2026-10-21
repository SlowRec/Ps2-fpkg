"""GameCube y Wii -> fPKG de PS4 con DolphinPS4 (Dolphin para PS4, GPL-2.0), incluido en
emus/dolphin.zip (ver tools/build_launched_emus.py).

El paquete lleva DolphinPS4, el juego en autoboot/game/ y el lanzador propio como eboot.bin:
escribe la ruta del juego en /data/DolphinPS4/launch.txt (donde Dolphin la busca al arrancar) y
abre Dolphin, que inicia el juego directo; al salir del juego se cierra la app. L3 + R3 abre el
menú de Dolphin (estados guardados, ajustes, trucos). Las tarjetas de memoria, los estados y los
ajustes se guardan en /data/DolphinPS4, como en la app DolphinPS4."""

import dataclasses
import os
import re

from . import covers, emu, pkgbuild, retro
from .pkgbuild import BuildError

BASE_ZIP = "dolphin.zip"
EXTENSIONS = (".rvz", ".iso", ".gcm", ".gcz", ".ciso", ".wia", ".wbfs", ".tgc", ".wad", ".dol", ".elf")
GAME_DIR = "autoboot/game"
GC_MAGIC = bytes.fromhex("C2339F3D")    # en 0x1C de la cabecera de un disco de GameCube
WII_MAGIC = bytes.fromhex("5D1C9EA3")   # en 0x18 de la de Wii
# Dónde empieza la copia de la cabecera del disco en cada formato.
HEADER_OFFSET = {".iso": 0, ".gcm": 0, ".rvz": 0x58, ".wia": 0x58, ".ciso": 0x8000, ".wbfs": 0x200}


@dataclasses.dataclass
class Options:
    discs: list                 # 1 o 2 discos (o un .wad/.dol), en orden
    output_dir: str
    title: str = ""
    serial: str = ""            # ID del juego (GALE01); por defecto se lee del disco
    title_id: str = ""
    content_id: str = ""
    icon: str = ""
    background: str = ""
    cover: str = ""
    find_cover: bool = False
    emu_dir: str = ""           # base propia; por defecto la de emus/
    pkgtool: str = ""
    gp4_only: bool = False
    keep_work: bool = False
    validate: bool = True


def read_header(path):
    """(ID del juego, título, "gc" | "wii") de la cabecera del disco, o ("", "", "")."""
    offset = HEADER_OFFSET.get(os.path.splitext(path)[1].lower())
    if offset is None:
        return "", "", ""
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            head = f.read(0x80)
    except OSError:
        return "", "", ""
    if len(head) < 0x80:
        return "", "", ""
    kind = "gc" if head[0x1C:0x20] == GC_MAGIC else "wii" if head[0x18:0x1C] == WII_MAGIC else ""
    game_id = head[:6].decode("ascii", "replace")
    if not kind or not re.fullmatch(r"[A-Z0-9]{6}", game_id):
        return "", "", ""
    title = head[0x20:0x80].split(b"\0")[0].decode("utf-8", "replace").strip()
    return game_id, title, kind


def detect_serial(path):
    return read_header(path)[0] or None


def default_title(path):
    """Del nombre del archivo, sin etiquetas ni "(Disc 1)"."""
    name = os.path.basename(path)
    for ext in (".nkit.iso", ".nkit.gcz") + EXTENSIONS:
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
            break
    return re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name).strip() or name


def build(opts, log=print, progress=None):
    if not opts.discs:
        raise BuildError("Indica el juego (.rvz, .iso, .gcz, .wbfs…).")
    if len(opts.discs) > 2:
        raise BuildError("Máximo 2 discos.")
    for path in opts.discs:
        if not path.lower().endswith(EXTENSIONS):
            raise BuildError(f"{os.path.basename(path)}: formato no válido para GameCube/Wii ({', '.join(EXTENSIONS)}).")
        if not os.path.isfile(path):
            raise BuildError(f"No existe {path}.")
    game_id, disc_title, kind = read_header(opts.discs[0])
    game_id = (opts.serial or game_id).upper()
    if game_id and not re.fullmatch(r"[A-Z0-9]{6}", game_id):
        raise BuildError(f"ID de juego no válido: {game_id} (6 letras o números, p. ej. GALE01).")
    with open(opts.discs[0], "rb") as f:
        fingerprint = game_id.encode() + str(os.path.getsize(opts.discs[0])).encode() + f.read(1 << 20)
    title_id, content_id = pkgbuild.ids_from_crc("GCFP", fingerprint, "GCFPKG00")
    title_id = (opts.title_id or title_id).upper()
    content_id = (opts.content_id or content_id).upper()
    pkgbuild.validate_ids(title_id, content_id)
    title = opts.title.strip() or default_title(opts.discs[0])
    system = {"wii": "Wii", "gc": "GameCube"}.get(kind, "GameCube/Wii")
    log(f"Juego: {title}  |  {system}" + (f"  |  {game_id}" if game_id else "") + f"  |  CONTENT_ID: {content_id}")

    base = emu.locate(opts.emu_dir, "DolphinPS4") if opts.emu_dir else retro.unpack(BASE_ZIP)
    if not os.path.isfile(os.path.join(base, "dolphin", "eboot.bin")):
        raise BuildError(f"{base} no es una base de DolphinPS4 preparada (falta dolphin/eboot.bin).")
    pkg = pkgbuild.Package(opts.output_dir, content_id)
    pkg.files.update(emu.collect_base(base, (), ("autoboot/",)))
    names = []
    for n, path in enumerate(opts.discs, 1):
        name = retro.safe_name(path)
        if len(opts.discs) > 1 and not re.search(r"\(Disc \d\)", name, re.I):
            stem, ext = os.path.splitext(name)
            name = f"{stem} (Disc {n}){ext}"   # así Dolphin encuentra el otro disco al cambiarlo
        pkg.add(f"{GAME_DIR}/{name}", path)
        names.append(name)
    pkg.write("autoboot/dolphin.txt", f"/app0/{GAME_DIR}/{names[0]}\n")
    log("Discos: " + ", ".join(names))

    cover_system = kind or "gc"
    cover = covers.resolve(opts, cover_system, game_id, [os.path.basename(opts.discs[0]), title, disc_title], log)
    return pkg.build(title=title, title_id=title_id, icon=opts.icon, background=opts.background, cover=cover,
                     subtitle=system, attribute=0x2, pkgtool=opts.pkgtool, gp4_only=opts.gp4_only,
                     keep_work=opts.keep_work, validate=opts.validate, log=log)
