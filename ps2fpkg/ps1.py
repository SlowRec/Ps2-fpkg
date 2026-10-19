"""PS1 (BIN/CUE) -> fPKG con el emulador oficial de PS1 de PS4 ("PS1HD", el de los clásicos
de PlayStation Plus). Como en PS2, el emulador sale de un PS1 Classic que tenga el usuario."""

import dataclasses
import os
import tempfile

from . import builder, covers, cue, emu, iso, pkgbuild
from .pkgbuild import BuildError

CONFIG_NAME = "config-title.txt"
DISC_EXT = (".bin", ".cue", ".toc", ".img", ".iso", ".ccd", ".sub", ".sbi", ".pbp", ".ecm")
# Opciones del juego original que no deben pasar al nuevo paquete.
GAME_KEYS = {"--image", "--ps1-title-id", "--libcrypt", "--trophies", "--ps4-trophies", "--ps5-uds",
             "--boot-disc-id", "--request-ntsc-region"}
# --scale: resolución interna (1 = nativa ... 6 = 6x, el máximo del emulador).
QUALITY_PROFILES = {
    "maxima": ["--scale=6"],
    "alta": ["--scale=4"],
    "rendimiento": ["--scale=2"],
    "original": [],
}


@dataclasses.dataclass
class Options:
    discs: list                 # .cue (o .bin de una sola pista), en orden
    emu_dir: str
    output_dir: str
    title: str = ""
    serial: str = ""
    title_id: str = ""
    content_id: str = ""
    icon: str = ""
    background: str = ""
    cover: str = ""
    find_cover: bool = False
    quality: str = "maxima"
    graphics_menu: bool = True  # menú "Gráficos" del emulador: filtro Lanczos/AA CMAA desde el juego
    force_60hz: bool = False    # juegos PAL a 60 Hz
    analog: bool = False        # simular sticks analógicos en juegos que no los usan
    skip_bios_logo: bool = False
    config_lua: str = ""        # scripts/<TITLE_ID>.lua
    emu_args: list = dataclasses.field(default_factory=list)
    pkgtool: str = ""
    gp4_only: bool = False
    keep_work: bool = False
    validate: bool = True


def detect_serial(path):
    """Serial de un .cue/.bin de PS1, o None."""
    bin_path = cue.parse(path).files[0] if path.lower().endswith(".cue") else path
    with iso.DiscImage(bin_path) as disc:
        return iso.read_ps1_serial(disc)


def _single_track_cue(bin_path, folder):
    """.cue mínimo para un .bin suelto (una pista de datos)."""
    path = os.path.join(folder, os.path.splitext(os.path.basename(bin_path))[0] + ".cue")
    with open(path, "w") as f:
        f.write(f'FILE "{os.path.abspath(bin_path)}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    return path


def build(opts, log=print, progress=None):
    if not opts.discs:
        raise BuildError("Indica al menos un disco (.cue o .bin).")
    if len(opts.discs) > 5:
        raise BuildError("Máximo 5 discos.")
    if opts.quality not in QUALITY_PROFILES:
        raise BuildError(f"Perfil de calidad desconocido: {opts.quality}.")
    for path in opts.discs:
        if path.lower().endswith((".iso", ".chd", ".pbp", ".ecm")):
            raise BuildError(f"{os.path.basename(path)}: el emulador de PS1 necesita la imagen en bruto BIN/CUE.")

    base = emu.locate(opts.emu_dir, "PS1 Classic (PlayStation Plus)")
    files = emu.collect_base(base, {CONFIG_NAME}, ("scripts/",))
    # El disco del juego original vive en data/: se descarta (lo demás de data/ se conserva).
    files = {k: v for k, v in files.items() if not (k.lower().startswith("data/") and k.lower().endswith(DISC_EXT))}

    with tempfile.TemporaryDirectory() as tmp:
        cues = [p if p.lower().endswith(".cue") else _single_track_cue(p, tmp) for p in opts.discs]
        parsed = [cue.parse(p) for p in cues]

        serial = opts.serial.upper()
        if not serial:
            with iso.DiscImage(parsed[0].files[0]) as disc:
                serial = iso.read_ps1_serial(disc) or ""
        if not builder.SERIAL_FMT.match(serial):
            raise BuildError("No se pudo leer el serial del disco (SYSTEM.CNF). Indícalo, p. ej. SLUS-00067.")
        title_id = (opts.title_id or builder.title_id_from_serial(serial)).upper()
        content_id = (opts.content_id or builder.content_id_for(title_id, "PS1FPKG")).upper()
        pkgbuild.validate_ids(title_id, content_id)
        title = opts.title.strip() or serial
        log(f"Juego: {title}  |  Serial: {serial}  |  CONTENT_ID: {content_id}")

        pkg = pkgbuild.Package(opts.output_dir, content_id)
        pkg.files.update(files)
        images = []
        for n, (path, disc) in enumerate(zip(cues, parsed), 1):
            name = f"disc{n}.bin"
            if len(disc.files) > 1:
                log(f"Disco {n}: uniendo {len(disc.files)} pistas en un solo .bin...")
                bin_path, _ = cue.stage(path, pkg.path(f"data/{name}"), progress)
            else:
                bin_path = disc.files[0]
            pkg.add(f"data/{name}", bin_path)
            pkg.write(f"data/disc{n}.cue", cue.single_bin_cue(disc, name))
            pkg.write(f"data/disc{n}.toc", cue.toc(disc))
            audio = sum(t.is_audio for t in disc.tracks)
            log(f"Disco {n}: {os.path.basename(path)} -> data/{name} ({len(disc.tracks)} pistas"
                + (f", {audio} de audio CD" if audio else "") + ")")
            images.append(f'--image="data/{name}"')

    overrides = ["--ps4-trophies=0", "--ps5-uds=0", "--trophies=0", *QUALITY_PROFILES[opts.quality]]
    if opts.graphics_menu:
        overrides.append("--userui-settings-graphics=1")
    if opts.force_60hz:
        overrides.append("--gpu-scanout-fps-override=60")
    if opts.analog:
        overrides.append("--sim-analog-pad=0x2020")
    if opts.skip_bios_logo:
        overrides.append("--bios-hide-sce-osd=1")
    if len(opts.discs) > 1:
        overrides.append("--enable-change-disc-ui=1")
    if opts.config_lua:
        with open(opts.config_lua, "rb") as f:
            pkg.write(f"scripts/{title_id}.lua", f.read())
        overrides.append(f"--ps1-title-id={title_id}")
    overrides += opts.emu_args
    config = emu.merge_args(emu.read_lines(os.path.join(base, CONFIG_NAME)), overrides, GAME_KEYS, extra=images)
    pkg.write(CONFIG_NAME, config)
    log("config-title.txt: " + "  ".join(a for a in emu.parse_args(config)
                                         if emu.arg_key(a) in ("--scale", "--userui-settings-graphics", "--image")))

    cover = covers.resolve(opts, "ps1", serial, [os.path.basename(opts.discs[0]), opts.title], log)
    return pkg.build(title=title, title_id=title_id, icon=opts.icon, background=opts.background, cover=cover,
                     subtitle="PlayStation", pkgtool=opts.pkgtool, gp4_only=opts.gp4_only,
                     keep_work=opts.keep_work, validate=opts.validate, log=log)
