"""PSP (ISO) -> fPKG con el emulador oficial de PSP de PS4 ("PSPHD", el de PlayStation Plus).

El emulador necesita el ejecutable del UMD (PSP_GAME/SYSDIR/EBOOT.BIN) descifrado: se copia
la ISO, se descifra el EBOOT con tools/<plataforma>/eboot_decrypt y se escribe en su lugar,
actualizando el tamaño en el directorio de la ISO."""

import dataclasses
import os
import shutil
import struct
import subprocess
import tempfile

from . import builder, covers, emu, images, iso, pkgbuild, sfo
from .pkgbuild import BuildError

CONFIG_NAME = "config-title.txt"
IMAGE = "data/USER_L0.IMG"
EBOOT = "PSP_GAME/SYSDIR/EBOOT.BIN"
GAME_KEYS = {"--image", "--trophies", "--ps4-trophies", "--ps5-uds", "--notrophies"}
# --antialias: SSAA4x (supermuestreo, la mejor imagen), MSAA4x (solo bordes), off.
QUALITY_PROFILES = {
    "maxima": ["--antialias=SSAA4x"],
    "equilibrado": ["--antialias=MSAA4x"],
    "rendimiento": ["--antialias=off"],
    "original": [],
}


@dataclasses.dataclass
class Options:
    iso: str
    emu_dir: str
    output_dir: str
    title: str = ""
    serial: str = ""
    title_id: str = ""
    content_id: str = ""
    icon: str = ""              # por defecto, el de la carátula o el del propio UMD
    background: str = ""        # por defecto, el de la carátula o el del propio UMD
    cover: str = ""
    find_cover: bool = False
    quality: str = "maxima"
    emu_args: list = dataclasses.field(default_factory=list)
    eboot_decrypt: str = ""     # ruta a eboot_decrypt; por defecto el de tools/
    pkgtool: str = ""
    gp4_only: bool = False
    keep_work: bool = False
    validate: bool = True


def read_info(path):
    """(serial, título) del UMD: UMD_DATA.BIN y PSP_GAME/PARAM.SFO."""
    with iso.DiscImage(path) as disc:
        umd = disc.read_file("UMD_DATA.BIN") or b""
        param = disc.read_file("PSP_GAME/PARAM.SFO")
    serial = umd.split(b"|")[0].decode("ascii", "replace").strip().upper()
    title = ""
    if param:
        try:
            title = str(sfo.parse(param).get("TITLE", "")).strip()
        except ValueError:
            pass
    return serial, title


def detect_serial(path):
    return read_info(path)[0] or None


def decrypt_eboot(image, tool, log):
    """Descifra el EBOOT.BIN dentro de la copia `image` (ISO de 2048 bytes/sector)."""
    with iso.DiscImage(image) as disc:
        entry = disc.find_record(EBOOT)
        if entry is None:
            raise BuildError("La ISO no tiene PSP_GAME/SYSDIR/EBOOT.BIN; ¿es un juego de PSP?")
        lba, size, record = entry
        data = disc.read_extent(lba, size)
    if data[:4] == b"\x7fELF":
        log("EBOOT.BIN ya está descifrado.")
        return
    if data[:4] != b"~PSP":
        raise BuildError("EBOOT.BIN tiene un formato desconocido.")
    if tool is None:
        raise BuildError("Falta eboot_decrypt para descifrar el EBOOT.BIN. Usa el de tools/ o compílalo con "
                         "'python tools/build_pspdecrypt.py'.")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "EBOOT.BIN"), os.path.join(tmp, "EBOOT.dec")
        with open(src, "wb") as f:
            f.write(data)
        res = subprocess.run([tool, src, dst], capture_output=True, text=True)
        if res.returncode != 0 or not os.path.isfile(dst):
            raise BuildError(f"No se pudo descifrar el EBOOT.BIN: {(res.stderr or res.stdout).strip()}")
        with open(dst, "rb") as f:
            plain = f.read()
    if len(plain) > size:
        raise BuildError("El EBOOT descifrado no cabe en su lugar dentro de la ISO.")
    with open(image, "r+b") as f:
        f.seek(lba * iso.SECTOR)
        f.write(plain + bytes(size - len(plain)))  # el resto del archivo original queda en ceros
        f.seek(record + 10)
        f.write(struct.pack("<I", len(plain)) + struct.pack(">I", len(plain)))
    log(f"EBOOT.BIN descifrado ({size} -> {len(plain)} bytes).")


def build(opts, log=print, progress=None):
    if not opts.iso:
        raise BuildError("Indica la ISO del juego.")
    if opts.iso.lower().endswith((".cso", ".zso", ".pbp", ".chd")):
        raise BuildError(f"{os.path.basename(opts.iso)}: convierte el juego a .iso antes (p. ej. con UMDGen o maxcso).")
    if opts.quality not in QUALITY_PROFILES:
        raise BuildError(f"Perfil de calidad desconocido: {opts.quality}.")
    tool = pkgbuild.find_tool(("eboot_decrypt.exe", "eboot_decrypt"), opts.eboot_decrypt)

    base = emu.locate(opts.emu_dir, "PSP Classic (PlayStation Plus)")
    files = emu.collect_base(base, {CONFIG_NAME})
    files = {k: v for k, v in files.items()
             if not (k.lower().startswith("data/") and k.lower().endswith((".img", ".iso", ".cso")))}

    umd_serial, umd_title = read_info(opts.iso)
    serial = (opts.serial or umd_serial).upper()
    if not builder.SERIAL_FMT.match(serial):
        raise BuildError("No se pudo leer el serial del UMD (UMD_DATA.BIN). Indícalo, p. ej. ULUS-10041.")
    title_id = (opts.title_id or builder.title_id_from_serial(serial)).upper()
    content_id = (opts.content_id or builder.content_id_for(title_id, "PSPFPKG")).upper()
    pkgbuild.validate_ids(title_id, content_id)
    title = opts.title.strip() or umd_title or serial
    log(f"Juego: {title}  |  Serial: {serial}  |  CONTENT_ID: {content_id}")

    pkg = pkgbuild.Package(opts.output_dir, content_id)
    pkg.files.update(files)
    image = pkg.path(IMAGE)
    log("Copiando la ISO...")
    shutil.copyfile(opts.iso, image)
    pkg.add(IMAGE, image)
    decrypt_eboot(image, tool, log)

    # Carátula; si no hay, el arte del propio UMD (hace falta Pillow para ampliarlo).
    cover = covers.resolve(opts, "psp", serial, [os.path.basename(opts.iso), title], log)
    icon = opts.icon or ("" if cover else None)              # None = tomarlo del UMD
    background = opts.background or ("" if cover else None)
    with iso.DiscImage(image) as disc:
        for want, name, attr in ((icon is None, "PSP_GAME/ICON0.PNG", "icon"),
                                 (background is None, "PSP_GAME/PIC1.PNG", "background")):
            data = disc.read_file(name) if want and images.Image is not None else None
            if data and data[:8] == b"\x89PNG\r\n\x1a\n":
                path = os.path.join(pkg.work, os.path.basename(name))
                with open(path, "wb") as f:
                    f.write(data)
                if attr == "icon":
                    icon = path
                else:
                    background = path

    overrides = ["--ps4-trophies=0", "--ps5-uds=0", "--trophies=0", f'--image="{IMAGE}"',
                 *QUALITY_PROFILES[opts.quality], "--multisaves=true", "--notrophies=true", *opts.emu_args]
    config = emu.merge_args(emu.read_lines(os.path.join(base, CONFIG_NAME)), overrides, GAME_KEYS)
    pkg.write(CONFIG_NAME, config)
    log("config-title.txt: " + "  ".join(a for a in emu.parse_args(config) if emu.arg_key(a) in ("--image", "--antialias")))

    return pkg.build(title=title, title_id=title_id, icon=icon or "", background=background or "", cover=cover,
                     subtitle="PSP",
                     pkgtool=opts.pkgtool, gp4_only=opts.gp4_only, keep_work=opts.keep_work,
                     validate=opts.validate, log=log, icon_fit="cover" if opts.icon or cover else "contain")
