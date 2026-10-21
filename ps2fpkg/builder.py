"""Orquesta la conversión: ISO(s) de PS2 + base del emulador -> proyecto GP4 -> fPKG."""

import dataclasses
import os
import re

from . import covers, db, emu, iso, pkgbuild, pnach
from .pkgbuild import FAT32_LIMIT, BuildError, find_pkgtool, validate_ids

__all__ = ["Options", "build", "detect_serial", "title_id_from_serial", "content_id_for",
           "BuildError", "FAT32_LIMIT", "find_pkgtool", "validate_ids"]

REGIONS = {"U": "UP", "E": "EP", "P": "JP", "K": "HP", "A": "HP", "C": "HP"}
SERIAL_FMT = re.compile(r"^[A-Z]{4}-\d{5}$")


@dataclasses.dataclass
class Options:
    isos: list
    emu_dir: str
    output_dir: str
    title: str = ""
    serial: str = ""            # vacío = se lee de SYSTEM.CNF
    title_id: str = ""          # vacío = derivado del serial (SLUS-20946 -> SLUS20946)
    content_id: str = ""        # vacío = derivado del title_id
    icon: str = ""              # icono propio (si no, se hace con la carátula)
    background: str = ""        # fondo propio (si no, se hace con la carátula)
    cover: str = ""             # carátula: genera icono y fondo
    find_cover: bool = False    # buscar la carátula en internet si no se indica
    config_lua: str = ""        # patches/<SERIAL>_config.lua
    cli_conf: str = ""          # patches/<SERIAL>_cli.conf (si se da, reemplaza a la oficial)
    emu_args: list = dataclasses.field(default_factory=list)
    # Calidad de imagen y sonido
    quality: str = "maxima"     # maxima | rendimiento | original (ver emu.QUALITY_PROFILES)
    widescreen: bool = True     # parche 16:9 de PCSX2 para esta versión del juego
    no_interlace: bool = True   # quita el entrelazado (imagen más nítida y estable)
    progressive: bool = False   # activa el modo 480p del juego, si tiene parche
    no_blur: bool = False       # quita filtros de desenfoque/bloom
    fps60: bool = False         # 60 FPS (puede acelerar el juego o exigir más)
    official_config: bool = True  # opciones del emulador que Sony usó para este juego
    patches_dir: str = ""       # carpeta local con .pnach (sin internet)
    online: bool = True         # descargar parches/configuraciones si no están en caché
    # Empaquetado
    pkgtool: str = ""           # vacío = buscar automáticamente
    gp4_only: bool = False      # solo preparar el proyecto, sin compilar
    keep_work: bool = False
    validate: bool = True       # comprobar hashes y firmas del PKG terminado


def title_id_from_serial(serial):
    return serial.replace("-", "")


def content_id_for(title_id, label="PS2FPKG"):
    region = REGIONS.get(title_id[2:3], "UP")
    return f"{region}9000-{title_id}_00-{title_id}{label}"


def detect_serial(path):
    with iso.DiscImage(path) as disc:
        return iso.read_serial(disc)


def _quality_patches(opts, disc, serial, title, log):
    """Script Lua con los parches de PCSX2 elegidos, o None. Devuelve (lua, aplicó_16:9)."""
    wanted = [(opts.widescreen, pnach.WIDESCREEN), (opts.no_interlace, pnach.NO_INTERLACE),
              (opts.progressive, pnach.PROGRESSIVE), (opts.no_blur, pnach.NO_BLUR), (opts.fps60, pnach.FPS60)]
    wanted = [name for enabled, name in wanted if enabled]
    if not wanted:
        return None, False
    elf = iso.read_boot_elf(disc)
    if elf is None:
        log("Parches: no se pudo leer el ejecutable del juego; se omiten.")
        return None, False
    crc = iso.elf_crc(elf)
    try:
        text = db.pcsx2_patch(serial, crc, opts.patches_dir) if (opts.online or opts.patches_dir) else None
    except OSError as e:
        log(f"Parches: no se pudo descargar la base de PCSX2 ({e}); se omiten.")
        return None, False
    if text is None:
        log(f"Parches: no hay parches de PCSX2 para {serial} (CRC {crc:08X}).")
        return None, False
    _meta, sections = pnach.parse(text)
    chosen, has_ws = [], False
    for name in wanted:
        section = pnach.find_section(sections, name)
        if section is None:
            log(f"Parches: {name} no disponible para este juego.")
        elif section.unsupported:
            # Aplicar solo una parte de un parche puede romper el juego: se descarta entero.
            log(f"Parches: {name} usa códigos que el emulador de PS4 no admite; se omite.")
        elif section.writes:
            chosen.append(section)
            has_ws = has_ws or name == pnach.WIDESCREEN
            log(f"Parches: {section.name} ✓")
    if not chosen:
        return None, False
    lua = pnach.to_lua(chosen, title=f"{title} [{serial}] CRC {crc:08X}",
                       source=f"{serial}_{crc:08X}.pnach", widescreen=has_ws)
    return lua, has_ws


def build(opts, log=print, progress=None):
    """Ejecuta la conversión completa. Devuelve la ruta del .pkg (o del .gp4 si gp4_only)."""
    if not opts.isos:
        raise BuildError("Indica al menos una ISO.")
    if len(opts.isos) > 9:
        raise BuildError("Máximo 9 discos.")
    if opts.quality not in emu.QUALITY_PROFILES:
        raise BuildError(f"Perfil de calidad desconocido: {opts.quality}.")

    base = emu.locate(opts.emu_dir, system="ps2")
    for w in emu.warnings(base):
        log(f"Aviso: {w}")

    # Discos: comprobar formato, detectar serial y preparar parches de imagen.
    discs = []
    try:
        for path in opts.isos:
            discs.append(iso.DiscImage(path))
        serial = (opts.serial or iso.read_serial(discs[0])).upper()
        if not SERIAL_FMT.match(serial):
            raise BuildError(f"Serial '{serial}' inválido; formato esperado SLUS-20946.")
        title_id = (opts.title_id or title_id_from_serial(serial)).upper()
        content_id = (opts.content_id or content_id_for(title_id)).upper()
        validate_ids(title_id, content_id)
        title = opts.title.strip() or serial
        log(f"Juego: {title}  |  Serial: {serial}  |  CONTENT_ID: {content_id}")

        patch_lua, widescreen = _quality_patches(opts, discs[0], serial, title, log)

        pkg = pkgbuild.Package(opts.output_dir, content_id)
        pkg.files.update(emu.collect(base))

        for n, disc in enumerate(discs, 1):
            target = f"image/disc{n:02d}.iso"
            if disc.is_raw:
                dst = pkg.path(target)
                log(f"Disco {n}: imagen BIN de {disc.sector_size} bytes/sector, convirtiendo a ISO...")
                disc.convert_to_iso(dst, progress)
                pkg.add(target, dst)
            else:
                pkg.add(target, disc.path)
            log(f"Disco {n}: {os.path.basename(disc.path)} -> {target}")
    finally:
        for disc in discs:
            disc.close()

    # Configuración del emulador: perfil de calidad < configuración oficial del juego < argumentos del usuario.
    overrides = list(emu.QUALITY_PROFILES[opts.quality])
    if widescreen:
        overrides.append("--host-display-mode=16:9")
    elif opts.quality != "original":
        overrides.append("--host-display-mode=normal")  # respeta la proporción 4:3 original

    cli_conf = None
    if opts.cli_conf:
        with open(opts.cli_conf, encoding="utf-8", errors="replace") as f:
            cli_conf = f.read()
    elif opts.official_config and opts.online:
        try:
            cli_conf = db.official_cli_conf(serial)
        except OSError as e:
            log(f"Configuración oficial: no se pudo descargar ({e}).")
        if cli_conf:
            log("Configuración oficial de Sony para este juego ✓")
    drop = set()
    if cli_conf:
        pkg.write(f"patches/{serial}_cli.conf", cli_conf)
        # Lo que el juego ajusta en su configuración propia no se pisa desde el perfil general.
        drop = {emu.arg_key(a) for a in emu.parse_args(cli_conf)}
        overrides = [a for a in overrides if emu.arg_key(a) not in drop]
    if opts.config_lua:
        with open(opts.config_lua, "rb") as f:
            pkg.write(f"patches/{serial}_config.lua", f.read())
    if cli_conf or opts.config_lua:
        overrides.append('--path-patches="/app0/patches"')
    if patch_lua:
        pkg.write(f"feature_data/{serial}_features.lua", patch_lua)
        overrides.append('--path-featuredata="/app0/feature_data"')
    overrides += opts.emu_args

    config = emu.make_config(base, serial, len(discs), overrides, drop)
    pkg.write(emu.CONFIG_NAME, config)
    log("config-emu-ps4.txt: " + "  ".join(a for a in emu.parse_args(config)
                                            if emu.arg_key(a).startswith(("--gs-", "--host-"))))

    cover = covers.resolve(opts, "ps2", serial, [os.path.basename(opts.isos[0]), opts.title], log)
    return pkg.build(title=title, title_id=title_id, icon=opts.icon, background=opts.background, cover=cover,
                     pkgtool=opts.pkgtool, gp4_only=opts.gp4_only, keep_work=opts.keep_work,
                     validate=opts.validate, log=log)
