"""Orquesta la conversión: ISO(s) de PS2 + base del emulador -> proyecto GP4 -> fPKG."""

import dataclasses
import os
import re
import shutil
import subprocess

from . import emu, gp4, images, iso, sfo

REGIONS = {"U": "UP", "E": "EP", "P": "JP", "K": "HP", "A": "HP", "C": "HP"}
SERIAL_FMT = re.compile(r"^[A-Z]{4}-\d{5}$")


class BuildError(Exception):
    pass


@dataclasses.dataclass
class Options:
    isos: list
    emu_dir: str
    output_dir: str
    title: str = ""
    serial: str = ""            # vacío = se lee de SYSTEM.CNF
    title_id: str = ""          # vacío = derivado del serial (SLUS-20946 -> SLUS20946)
    content_id: str = ""        # vacío = derivado del title_id
    icon: str = ""
    background: str = ""
    config_lua: str = ""        # patches/<SERIAL>_config.lua
    cli_conf: str = ""          # patches/<SERIAL>_cli.conf
    emu_args: list = dataclasses.field(default_factory=list)
    pkgtool: str = ""           # vacío = buscar automáticamente
    gp4_only: bool = False      # solo preparar el proyecto, sin compilar
    keep_work: bool = False


def title_id_from_serial(serial):
    return serial.replace("-", "")


def content_id_for(title_id):
    region = REGIONS.get(title_id[2:3], "UP")
    return f"{region}9000-{title_id}_00-{title_id}PS2FPKG"


def validate_ids(title_id, content_id):
    if not re.fullmatch(r"[A-Z]{4}\d{5}", title_id):
        raise BuildError(f"TITLE_ID '{title_id}' inválido: deben ser 4 letras y 5 números (p. ej. SLUS20946).")
    if not re.fullmatch(r"[A-Z]{2}\d{4}-[A-Z]{4}\d{5}_00-[A-Z0-9]{16}", content_id):
        raise BuildError(f"CONTENT_ID '{content_id}' inválido: formato XX0000-XXXX00000_00-ZZZZZZZZZZZZZZZZ.")
    if content_id[7:16] != title_id:
        raise BuildError(f"El CONTENT_ID {content_id} no contiene el TITLE_ID {title_id}.")


def detect_serial(path):
    with iso.DiscImage(path) as disc:
        return iso.read_serial(disc)


def find_pkgtool(explicit=""):
    """Devuelve el comando (lista) para ejecutar PkgTool, o None."""
    candidates = [explicit, os.environ.get("PS2FPKG_PKGTOOL", "")]
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("PkgTool.Core.exe", "PkgTool.exe", "PkgTool.Core", "PkgTool.Core.dll"):
        candidates.append(os.path.join(here, "tools", name))
        candidates.append(shutil.which(name) or "")
    for c in candidates:
        if c and os.path.isfile(c):
            if c.lower().endswith(".dll"):
                dotnet = shutil.which("dotnet")
                if not dotnet:
                    raise BuildError(f"{c} requiere .NET (dotnet) instalado.")
                return [dotnet, c]
            return [c]
    if explicit:
        raise BuildError(f"No se encontró PkgTool en {explicit}.")
    return None


def build(opts, log=print, progress=None):
    """Ejecuta la conversión completa. Devuelve la ruta del .pkg (o del .gp4 si gp4_only)."""
    if not opts.isos:
        raise BuildError("Indica al menos una ISO.")
    if len(opts.isos) > 9:
        raise BuildError("Máximo 9 discos.")

    base = emu.locate(opts.emu_dir)
    for w in emu.warnings(base):
        log(f"Aviso: {w}")

    # Discos: comprobar formato y detectar serial.
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

        os.makedirs(opts.output_dir, exist_ok=True)
        work = os.path.abspath(os.path.join(opts.output_dir, f"{content_id}_work"))
        if os.path.exists(work):
            shutil.rmtree(work)
        os.makedirs(os.path.join(work, "sce_sys"))

        files = emu.collect(base)

        for n, disc in enumerate(discs, 1):
            target = f"image/disc{n:02d}.iso"
            if disc.is_raw:
                dst = os.path.join(work, f"disc{n:02d}.iso")
                log(f"Disco {n}: imagen BIN de {disc.sector_size} bytes/sector, convirtiendo a ISO...")
                disc.convert_to_iso(dst, progress)
                files[target] = dst
            else:
                files[target] = os.path.abspath(disc.path)
            log(f"Disco {n}: {os.path.basename(disc.path)} -> {target}")
    finally:
        for disc in discs:
            disc.close()

    def write(rel, data):
        dst = os.path.join(work, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        files[rel] = dst

    write("sce_sys/param.sfo", sfo.ps2_classic(title, title_id, content_id))
    write(emu.CONFIG_NAME, emu.make_config(base, serial, len(discs), opts.emu_args).encode("utf-8"))
    for src, suffix in ((opts.config_lua, "_config.lua"), (opts.cli_conf, "_cli.conf")):
        if src:
            with open(src, "rb") as f:
                write(f"patches/{serial}{suffix}", f.read())

    log("Generando imágenes del menú...")
    for rel, size, src in (("sce_sys/icon0.png", images.ICON_SIZE, opts.icon),
                           ("sce_sys/pic0.png", images.BG_SIZE, opts.background),
                           ("sce_sys/pic1.png", images.BG_SIZE, opts.background)):
        dst = os.path.join(work, *rel.split("/"))
        images.make(dst, size, src or None, title=title)
        files[rel] = dst

    gp4_path = os.path.join(work, "project.gp4")
    with open(gp4_path, "wb") as f:
        f.write(gp4.build(content_id, files))
    log(f"Proyecto GP4: {gp4_path} ({len(files)} archivos)")

    if opts.gp4_only:
        return gp4_path

    cmd = find_pkgtool(opts.pkgtool)
    if cmd is None:
        raise BuildError(
            "No se encontró PkgTool (LibOrbisPkg). Descárgalo de https://github.com/maxton/LibOrbisPkg/releases "
            "y pon PkgTool.Core.exe en ps2-fpkg/tools/, o indica la ruta. "
            f"El proyecto quedó listo en {gp4_path}."
        )
    out_dir = os.path.abspath(opts.output_dir)
    log("Creando el fPKG con PkgTool (puede tardar varios minutos)...")
    with subprocess.Popen(cmd + ["pkg_build", gp4_path, out_dir], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, errors="replace") as proc:
        for line in proc.stdout:
            log("  " + line.rstrip())
    if proc.returncode != 0:
        raise BuildError(f"PkgTool terminó con error (código {proc.returncode}). Archivos de trabajo en {work}.")

    pkg_path = os.path.join(out_dir, f"{content_id}.pkg")
    if not os.path.isfile(pkg_path):
        raise BuildError(f"PkgTool no generó {pkg_path}.")
    if not opts.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    log(f"Listo: {pkg_path}")
    return pkg_path
