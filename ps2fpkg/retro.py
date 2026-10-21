"""NES, SNES y GBA -> fPKG de PS4 con pemu (pNES = Nestopia, pSNES = Snes9x, pGBA = mGBA),
emuladores libres (GPL-3.0) para PS4 que vienen incluidos en emus/. La versión incluida tiene un parche
(tools/pemu-autoboot.patch) para arrancar directo el juego del paquete: cada fPKG es un
juego con su icono en el menú de la PS4, y al salir del juego se vuelve al menú."""

import dataclasses
import hashlib
import os
import re
import zipfile

from . import covers, emu, pkgbuild
from .pkgbuild import BuildError

EMUS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "emus")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".ps2fpkg", "emus")


@dataclasses.dataclass(frozen=True)
class System:
    key: str
    name: str
    base_zip: str
    prefix: str          # 4 letras del TITLE_ID
    label: str           # 8 caracteres del final del CONTENT_ID
    extensions: tuple


SYSTEMS = {
    "nes": System("nes", "NES", "pnes.zip", "PNES", "NESFPKG0", (".nes", ".fds", ".unf", ".unif", ".zip")),
    "snes": System("snes", "Super Nintendo", "psnes.zip", "SNES", "SNESFPKG",
                   (".sfc", ".smc", ".fig", ".swc", ".bs", ".zip")),
    # mGBA también lee Game Boy y Game Boy Color.
    "gba": System("gba", "Game Boy Advance", "pgba.zip", "GBAF", "GBAFPKG0", (".gba", ".gb", ".gbc", ".zip")),
}
GB_LOGO = bytes.fromhex("CEED6666")  # inicio del logo de Nintendo en la cabecera (0x104) de Game Boy

# Ajustes de imagen (opciones del menú de pemu). SCALING=FIT llena la altura de la pantalla
# manteniendo la proporción original; EFFECT es el shader de la versión de PS4.
VIDEO_PROFILES = {
    "nitido": {"SCALING": "FIT", "SCALING_MODE": "ASPECT", "FILTER": "LINEAR",
               "EFFECT": "interpolation-sharp-bilinear"},
    "suavizado": {"SCALING": "FIT", "SCALING_MODE": "ASPECT", "FILTER": "LINEAR", "EFFECT": "sharp-sabr-v3.0"},
    "crt": {"SCALING": "FIT", "SCALING_MODE": "ASPECT", "FILTER": "LINEAR", "EFFECT": "crt-easymode"},
    "pixel": {"SCALING": "FIT", "SCALING_MODE": "INTEGER", "FILTER": "POINT", "EFFECT": "c2d-texture"},
}
VIDEO_LABELS = {
    "nitido": "Nítido: píxeles definidos sin parpadeo (recomendado)",
    "suavizado": "Suavizado: redondea los píxeles (SABR, tipo xBR)",
    "crt": "CRT: líneas y máscara de televisor antiguo",
    "pixel": "Píxel exacto: escala entera, sin filtro",
}


@dataclasses.dataclass
class Options:
    system: str                 # "nes" | "snes" | "gba"
    rom: str
    output_dir: str
    title: str = ""
    title_id: str = ""
    content_id: str = ""
    icon: str = ""
    background: str = ""
    cover: str = ""
    find_cover: bool = False
    video: str = "nitido"
    audio_sync: bool = True     # sonido sincronizado (sin chasquidos); solo SNES
    show_fps: bool = False
    emu_dir: str = ""           # base propia de pemu; por defecto la de emus/
    pkgtool: str = ""
    gp4_only: bool = False
    keep_work: bool = False
    validate: bool = True


def clean_title(path):
    """'Super Mario World (USA) [!].sfc' -> 'Super Mario World'."""
    name = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name).strip() or name


def check_rom(system, path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in system.extensions:
        raise BuildError(f"{os.path.basename(path)}: extensión no válida para {system.name} "
                         f"({', '.join(system.extensions)}).")
    with open(path, "rb") as f:
        head = f.read(4)
    if ext == ".zip":
        if head != b"PK\x03\x04":
            raise BuildError(f"{os.path.basename(path)} no es un .zip válido.")
    elif system.key == "nes" and ext == ".nes" and head != b"NES\x1a":
        raise BuildError(f"{os.path.basename(path)} no tiene la cabecera iNES; no parece una ROM de NES.")
    elif system.key == "snes" and os.path.getsize(path) % 1024 not in (0, 512):
        raise BuildError(f"{os.path.basename(path)}: tamaño no válido para una ROM de SNES.")
    elif system.key == "gba" and ext == ".gba":
        with open(path, "rb") as f:
            header = f.read(0xC0)
        if len(header) < 0xC0 or header[0xB2] != 0x96:
            raise BuildError(f"{os.path.basename(path)} no tiene la cabecera de GBA; no parece una ROM de GBA.")
    elif system.key == "gba" and ext in (".gb", ".gbc"):
        with open(path, "rb") as f:
            f.seek(0x104)
            if f.read(4) != GB_LOGO:
                raise BuildError(f"{os.path.basename(path)} no tiene la cabecera de Game Boy.")


def base_dir(system, explicit=""):
    """Carpeta de la app pemu: la indicada o la incluida en emus/ (se descomprime una vez)."""
    if explicit:
        return emu.locate(explicit, f"pemu ({system.name})")
    return unpack(system.base_zip)


def unpack(base_zip):
    """Descomprime (una vez, en la caché) un emulador incluido en emus/ y devuelve su carpeta."""
    zip_path = os.path.join(EMUS_DIR, base_zip)
    if not os.path.isfile(zip_path):
        raise BuildError(f"Falta {zip_path} (emulador incluido).")
    with open(zip_path, "rb") as f:
        digest = hashlib.sha1(f.read()).hexdigest()[:10]
    dst = os.path.join(CACHE_DIR, f"{os.path.splitext(base_zip)[0]}-{digest}")
    if not os.path.isfile(os.path.join(dst, "eboot.bin")):
        tmp = dst + ".tmp"
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        os.replace(tmp, dst)
    return dst


def safe_name(path):
    """Nombre de archivo de la ROM dentro del paquete (sin caracteres problemáticos)."""
    name = os.path.basename(path)
    return re.sub(r"[^A-Za-z0-9 ._()\[\]!+,&'-]", "_", name)


def options_text(opts):
    values = dict(VIDEO_PROFILES[opts.video])
    if opts.system == "snes":
        values["AUDIO_SYNC"] = "ON" if opts.audio_sync else "OFF"
    values["SHOW_FPS"] = "ON" if opts.show_fps else "OFF"
    return "".join(f"{k}={v}\n" for k, v in values.items())


def build(opts, log=print, progress=None):
    system = SYSTEMS.get(opts.system)
    if system is None:
        raise BuildError(f"Consola desconocida: {opts.system}.")
    if not opts.rom:
        raise BuildError("Indica la ROM del juego.")
    if opts.video not in VIDEO_PROFILES:
        raise BuildError(f"Ajuste de imagen desconocido: {opts.video}.")
    check_rom(system, opts.rom)
    with open(opts.rom, "rb") as f:
        data = f.read()
    title_id, content_id = pkgbuild.ids_from_crc(system.prefix, data, system.label)
    title_id = (opts.title_id or title_id).upper()
    content_id = (opts.content_id or content_id).upper()
    pkgbuild.validate_ids(title_id, content_id)
    title = opts.title.strip() or clean_title(opts.rom)
    log(f"Juego: {title}  |  {system.name}  |  CONTENT_ID: {content_id}")

    base = base_dir(system, opts.emu_dir)
    pkg = pkgbuild.Package(opts.output_dir, content_id)
    pkg.files.update(emu.collect_base(base, (), ("autoboot/",)))
    rom_name = safe_name(opts.rom)
    pkg.add(f"autoboot/{rom_name}", opts.rom)
    pkg.write("autoboot/rom.txt", rom_name + "\n")
    pkg.write("autoboot/options.txt", options_text(opts))
    log(f"Imagen: {VIDEO_LABELS[opts.video]}")

    ext = os.path.splitext(opts.rom)[1].lower()
    cover_system = {".gb": "gb", ".gbc": "gbc"}.get(ext, system.key) if system.key == "gba" else system.key
    subtitle = {".gb": "Game Boy", ".gbc": "Game Boy Color"}.get(ext, system.name) if system.key == "gba" else system.name
    cover = covers.resolve(opts, cover_system, names=[os.path.basename(opts.rom), opts.title], log=log)
    return pkg.build(title=title, title_id=title_id, icon=opts.icon, background=opts.background, cover=cover,
                     subtitle=subtitle, pkgtool=opts.pkgtool, gp4_only=opts.gp4_only,
                     keep_work=opts.keep_work, validate=opts.validate, log=log)
