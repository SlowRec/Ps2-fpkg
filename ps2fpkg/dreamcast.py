"""Dreamcast (GDI, CHD, CDI o CUE/BIN) -> fPKG de PS4 con Resonance (Flycast para PS4,
GPL-2.0), incluido en emus/resonance.zip (ver tools/build_launched_emus.py).

El paquete lleva Resonance, el juego en autoboot/ y un lanzador propio como eboot.bin: lee
autoboot/args.txt y arranca Resonance con las opciones de imagen y la ruta del juego, así que
el juego se inicia directo desde su icono. L3 + R3 abre el menú de Resonance (partidas
guardadas, ajustes, cerrar el juego). Las memorias (VMU) y los estados guardados se guardan en
/data/Resonance, como en la app de Resonance."""

import dataclasses
import os
import re
import shlex

from . import covers, cue, emu, pkgbuild, retro
from .pkgbuild import BuildError

BASE_ZIP = "resonance.zip"
EXTENSIONS = (".gdi", ".chd", ".cdi", ".cue")
GAME_DIR = "autoboot/game"
BIOS_FILES = ("dc_boot.bin", "dc_flash.bin")
# Resolución interna de Flycast (rend.Resolution: alto en píxeles, 480 = la de la Dreamcast) y
# filtrado anisotrópico de texturas. None = lo que se elija en los ajustes de Resonance.
RESOLUTIONS = {
    "alta": (960, 8),
    "maxima": (1440, 16),
    "nativa": (480, 4),
    "original": None,
}
RESOLUTION_LABELS = {
    "alta": "Alta: 2x (1280x960), recomendado",
    "maxima": "Máxima: 3x (1920x1440, supermuestreo); algunos juegos pueden ir lentos",
    "nativa": "Nativa: 640x480, la más rápida",
    "original": "Original: la que elijas en los ajustes de Resonance",
}


@dataclasses.dataclass
class Options:
    game: str                   # .gdi, .chd, .cdi o .cue
    output_dir: str
    title: str = ""
    title_id: str = ""
    content_id: str = ""
    icon: str = ""
    background: str = ""
    cover: str = ""
    find_cover: bool = False
    resolution: str = "alta"
    widescreen: bool = True     # 16:9 en los juegos que tienen parche de pantalla ancha
    show_fps: bool = False
    bios_dir: str = ""          # carpeta con dc_boot.bin / dc_flash.bin (opcional)
    emu_dir: str = ""           # base propia; por defecto la de emus/
    pkgtool: str = ""
    gp4_only: bool = False
    keep_work: bool = False
    validate: bool = True


def gdi_files(path):
    """Archivos de pista que nombra un .gdi (rutas absolutas)."""
    folder = os.path.dirname(os.path.abspath(path))
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if not lines or not lines[0].isdigit():
        raise BuildError(f"{os.path.basename(path)} no es un .gdi válido.")
    files = []
    for line in lines[1:int(lines[0]) + 1]:
        try:
            parts = shlex.split(line, posix=True)
        except ValueError:
            parts = line.split()
        if len(parts) < 6:
            raise BuildError(f"{os.path.basename(path)}: línea de pista no válida: {line}")
        files.append(os.path.join(folder, parts[4]))
    return files


def game_files(path):
    """(archivo principal, [archivos de pista]) del juego."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in EXTENSIONS:
        raise BuildError(f"{os.path.basename(path)}: formato no válido para Dreamcast ({', '.join(EXTENSIONS)}).")
    if ext == ".gdi":
        tracks = gdi_files(path)
    elif ext == ".cue":
        try:
            tracks = cue.parse(path).files
        except cue.CueError as e:
            raise BuildError(str(e)) from e
    else:
        tracks = []
    missing = [t for t in tracks if not os.path.isfile(t)]
    if missing:
        raise BuildError("Faltan archivos del juego junto a " + os.path.basename(path) + ": "
                         + ", ".join(os.path.basename(m) for m in missing))
    return path, tracks


def read_ip(paths):
    """(número de producto, título) de la cabecera IP.BIN de la Dreamcast, o ("", "")."""
    for path in paths:
        try:
            with open(path, "rb") as f:
                head = f.read(2352 + 16)
        except OSError:
            continue
        pos = head.find(b"SEGA SEGAKATANA")
        if pos in (0, 16):
            product = head[pos + 0x40:pos + 0x4A].decode("ascii", "replace").strip(" \x00")
            title = head[pos + 0x80:pos + 0x100].decode("ascii", "replace").strip(" \x00")
            return product, re.sub(r"\s+", " ", title)
    return "", ""


def fingerprint(paths):
    """Bytes que identifican el juego (tamaños + inicio de cada archivo) para el TITLE_ID."""
    data = b""
    for p in paths:
        data += str(os.path.getsize(p)).encode()
        with open(p, "rb") as f:
            data += f.read(1 << 20)
    return data


def default_title(path, ip_title=""):
    """Del nombre del archivo; si es genérico (disc.gdi), de la carpeta o del IP.BIN."""
    title = retro.clean_title(path)
    if re.fullmatch(r"(disc|disco|game|juego|track)\s*\d*", title, re.I):
        folder = os.path.basename(os.path.dirname(os.path.abspath(path)))
        folder = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", folder).strip()
        title = folder or ip_title.title() or title
    return title


def args_text(opts, main_name):
    """Contenido de autoboot/args.txt: opciones "-config" de Flycast y la ruta del juego."""
    values = []
    res = RESOLUTIONS[opts.resolution]
    if res:
        values += [f"rend.Resolution={res[0]}", f"rend.AnisotropicFiltering={res[1]}"]
    values += [f"rend.WidescreenGameHacks={'yes' if opts.widescreen else 'no'}",
               "rend.WideScreen=no", "rend.SuperWideScreen=no",
               f"rend.ShowFPS={'yes' if opts.show_fps else 'no'}"]
    lines = []
    for v in values:
        lines += ["-config", f"config:{v}"]
    lines.append(f"/app0/{GAME_DIR}/{main_name}")
    return "".join(line + "\n" for line in lines)


def build(opts, log=print, progress=None):
    if not opts.game:
        raise BuildError("Indica el juego (.gdi, .chd, .cdi o .cue).")
    if opts.resolution not in RESOLUTIONS:
        raise BuildError(f"Resolución desconocida: {opts.resolution}.")
    main, tracks = game_files(opts.game)
    product, ip_title = read_ip(tracks or [main])
    files = [main] + tracks
    title_id, content_id = pkgbuild.ids_from_crc("DCFP", fingerprint(files), "DCFPKG00")
    title_id = (opts.title_id or title_id).upper()
    content_id = (opts.content_id or content_id).upper()
    pkgbuild.validate_ids(title_id, content_id)
    title = opts.title.strip() or default_title(main, ip_title)
    log(f"Juego: {title}  |  Dreamcast" + (f"  |  {product}" if product else "") + f"  |  CONTENT_ID: {content_id}")

    base = emu.locate(opts.emu_dir, "Resonance") if opts.emu_dir else retro.unpack(BASE_ZIP)
    if not os.path.isfile(os.path.join(base, "resonance", "eboot.bin")):
        raise BuildError(f"{base} no es una base de Resonance preparada (falta resonance/eboot.bin).")
    pkg = pkgbuild.Package(opts.output_dir, content_id)
    pkg.files.update(emu.collect_base(base, (), ("autoboot/", "data/")))

    # Las pistas conservan su nombre (el .gdi/.cue las nombra); el principal, nombre seguro.
    main_name = os.path.basename(main) if tracks else retro.safe_name(main)
    pkg.add(f"{GAME_DIR}/{main_name}", main)
    for t in tracks:
        pkg.add(f"{GAME_DIR}/{os.path.basename(t)}", t)
    pkg.write("autoboot/args.txt", args_text(opts, main_name))
    log(f"Imagen: {RESOLUTION_LABELS[opts.resolution]}"
        + ("; pantalla ancha en los juegos con parche" if opts.widescreen else "; 4:3"))

    if opts.bios_dir:
        found = [n for n in BIOS_FILES if os.path.isfile(os.path.join(opts.bios_dir, n))]
        if "dc_boot.bin" not in found:
            raise BuildError(f"No hay dc_boot.bin en {opts.bios_dir}.")
        for n in found:
            pkg.add(f"data/{n}", os.path.join(opts.bios_dir, n))
        log("BIOS de Dreamcast incluida: " + ", ".join(found))
    else:
        log("Sin BIOS: se usa la BIOS libre de Flycast (o la de /data/Resonance/data si la copiaste).")

    cover = covers.resolve(opts, "dc", names=[os.path.basename(main), title, ip_title], log=log)
    return pkg.build(title=title, title_id=title_id, icon=opts.icon, background=opts.background, cover=cover,
                     subtitle="Dreamcast", attribute=0x2, pkgtool=opts.pkgtool, gp4_only=opts.gp4_only,
                     keep_work=opts.keep_work, validate=opts.validate, log=log)
