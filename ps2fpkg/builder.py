"""Orquesta la conversión: ISO(s) de PS2 + base del emulador -> proyecto GP4 -> fPKG."""

import dataclasses
import os
import platform
import re
import shutil
import subprocess

from . import db, emu, gp4, images, iso, pnach, sfo

REGIONS = {"U": "UP", "E": "EP", "P": "JP", "K": "HP", "A": "HP", "C": "HP"}
SERIAL_FMT = re.compile(r"^[A-Z]{4}-\d{5}$")
FAT32_LIMIT = 4 * 1024 ** 3 - 1


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


def _rid():
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    return {"Windows": "win", "Darwin": "osx"}.get(platform.system(), "linux") + "-" + arch


def find_pkgtool(explicit=""):
    """Devuelve el comando (lista) para ejecutar PkgTool, o None."""
    candidates = [explicit, os.environ.get("PS2FPKG_PKGTOOL", "")]
    tools = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
    for name in ("PkgTool.Core.exe", "PkgTool.Core", "PkgTool.exe", "PkgTool.Core.dll"):
        candidates += [os.path.join(tools, _rid(), name), os.path.join(tools, name), shutil.which(name) or ""]
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

    base = emu.locate(opts.emu_dir)
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
        write(f"patches/{serial}_cli.conf", cli_conf.encode("utf-8"))
        # Lo que el juego ajusta en su configuración propia no se pisa desde el perfil general.
        drop = {emu.arg_key(a) for a in emu.parse_args(cli_conf)}
        overrides = [a for a in overrides if emu.arg_key(a) not in drop]
    if opts.config_lua:
        with open(opts.config_lua, "rb") as f:
            write(f"patches/{serial}_config.lua", f.read())
    if cli_conf or opts.config_lua:
        overrides.append('--path-patches="/app0/patches"')
    if patch_lua:
        write(f"feature_data/{serial}_features.lua", patch_lua.encode("utf-8"))
        overrides.append('--path-featuredata="/app0/feature_data"')
    overrides += opts.emu_args

    config = emu.make_config(base, serial, len(discs), overrides, drop)
    write(emu.CONFIG_NAME, config.encode("utf-8"))
    log("config-emu-ps4.txt: " + "  ".join(a for a in emu.parse_args(config)
                                            if emu.arg_key(a).startswith(("--gs-", "--host-"))))

    write("sce_sys/param.sfo", sfo.ps2_classic(title, title_id, content_id))

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
            "No se encontró PkgTool. Usa el incluido en tools/ o compílalo con "
            f"'python tools/build_pkgtool.py'. El proyecto quedó listo en {gp4_path}."
        )
    out_dir = os.path.abspath(opts.output_dir)
    pkg_path = os.path.join(out_dir, f"{content_id}.pkg")
    if os.path.exists(pkg_path):
        os.remove(pkg_path)
    log("Creando el fPKG con PkgTool (puede tardar varios minutos)...")
    output = _run(cmd + ["pkg_build", gp4_path, out_dir], log)
    if "not allocated enough space" in output:
        raise BuildError("Este PkgTool tiene el fallo de PlayGo con juegos grandes. Usa el PkgTool "
                         "parcheado de tools/ (o compílalo con 'python tools/build_pkgtool.py').")
    if not os.path.isfile(pkg_path):
        raise BuildError(f"PkgTool no generó {pkg_path}. Archivos de trabajo en {work}.")

    if opts.validate:
        log("Verificando hashes y firmas del PKG...")
        report = _run(cmd + ["pkg_validate", pkg_path], lambda _line: None)
        errors = [ln for ln in report.splitlines() if ln.startswith("[ERROR]")]
        if errors or "[OK]" not in report:
            raise BuildError("El PKG no pasó la verificación:\n" + ("\n".join(errors) or report[-2000:]))
        log(f"Verificación correcta ({report.count('[OK]')} comprobaciones).")

    if not opts.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    size = os.path.getsize(pkg_path)
    log(f"Listo: {pkg_path} ({size / 1024 ** 3:.2f} GB)")
    if size > FAT32_LIMIT:
        log("Nota: pesa más de 4 GB. Para instalar por USB formatea la memoria en exFAT "
            "(FAT32 no admite archivos tan grandes) o instálalo por red.")
    return pkg_path


def _run(cmd, log):
    """Ejecuta un comando mostrando su salida; devuelve el texto completo."""
    lines = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, errors="replace") as proc:
        for line in proc.stdout:
            lines.append(line)
            log("  " + line.rstrip())
    text = "".join(lines)
    if proc.returncode != 0 and "not allocated enough space" not in text:
        raise BuildError(f"PkgTool falló (código {proc.returncode}):\n{text[-2000:]}")
    return text
