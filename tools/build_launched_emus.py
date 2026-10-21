"""Prepara las bases de Dreamcast y GameCube/Wii (emus/resonance.zip y emus/dolphin.zip).

Resonance (https://github.com/iHaiDeeZ/Resonance, Flycast para PS4) y DolphinPS4
(https://github.com/iHaiDeeZ/DolphinPS4), ambos GPL-2.0. Se usan sus versiones publicadas tal
cual: se descarga el .pkg, se comprueba su SHA-256 y se extraen sus archivos con PkgTool. Su
eboot.bin pasa a resonance/ o dolphin/ y en su lugar va el lanzador de tools/dc-launcher
(compilado aquí con el toolchain OpenOrbis de PacBrew), que arranca el emulador con el juego del
paquete (ver ps2fpkg/dreamcast.py y ps2fpkg/gamecube.py).

Requisitos (Linux x86_64): el toolchain de PacBrew en /opt/pacbrew (python tools/build_pemu.py
lo instala) y tools/linux-x64/PkgTool.Core (python tools/build_pkgtool.py). Uso:
    python tools/build_launched_emus.py
"""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

# (zip, carpeta del emulador, versión, URL del .pkg, SHA-256, archivo con la versión)
EMULATORS = [
    ("resonance.zip", "resonance", "01.41",
     "https://github.com/iHaiDeeZ/Resonance/releases/download/v01.41/Resonance-v01.41.pkg",
     "47c04310506fd819db9d31d5bdc721e19b36a73320e18923866c83b34b367720", "version.txt"),
    ("dolphin.zip", "dolphin", "04.16",
     "https://github.com/iHaiDeeZ/DolphinPS4/releases/download/v04.16/DolphinPS4-v04.16.pkg",
     "167624d93ecd1bc1146f55785505fe9405ad1d17f626bba6502abe024d3c6802", "xmb/version.txt"),
]
OPENORBIS = "/opt/pacbrew/ps4/openorbis"
# PAID y authinfo con los que se publican Resonance y DolphinPS4 (toolchain/ps4-love-style.cmake), que puede
# usar sceSystemServiceLoadExec.
PAID = "0x3100000000000002"
AUTH_INFO = ("000000000000000000000000001C004000FF000000000080000000000000000000000000000000000000008000400040"
             "000000000000008000000000000000080040FFFF000000F0000000000000000000000000000000000000000000000000"
             "00000000000000000000000000000000000000000000000000000000000000000000000000000000")
# Versión que ven los paquetes: más nueva que cualquiera, para que el emulador no cambie al
# programa de una actualización descargada (/data/<emulador>/app), que arrancaría sin el juego.
PACKAGE_VERSION = "99.99"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def build_launcher(tmp):
    cc = os.path.join(OPENORBIS, "bin")
    obj, elf, oelf = (os.path.join(tmp, n) for n in ("main.o", "launcher.elf", "launcher.oelf"))
    eboot = os.path.join(tmp, "eboot.bin")
    run([os.path.join(cc, "clang"), "--target=x86_64-pc-freebsd12-elf", "-O2", "-Wall", "-fPIC",
         "-funwind-tables", "-c", "-isysroot", OPENORBIS, "-isystem", os.path.join(OPENORBIS, "include"),
         "-o", obj, os.path.join(HERE, "dc-launcher", "main.c")])
    run([os.path.join(cc, "ld.lld"), "-m", "elf_x86_64", "-pie", "--script", os.path.join(OPENORBIS, "link.x"),
         "--eh-frame-hdr", "-L" + os.path.join(OPENORBIS, "lib"), os.path.join(OPENORBIS, "lib", "crt1.o"), obj,
         "-lc", "-lkernel", "-lSceSystemService", "-lSceLibcInternal", "-o", elf])
    run([os.path.join(cc, "linux", "create-fself"), f"-in={elf}", f"-out={oelf}", "--eboot", eboot,
         "--paid", PAID, "--authinfo", AUTH_INFO], env=dict(os.environ, OO_PS4_TOOLCHAIN=OPENORBIS), cwd=tmp)
    out = run([os.path.join(cc, "llvm-readelf"), "-l", "-W", oelf], capture_output=True, text=True).stdout
    if len(re.findall(r"^\s*LOAD\s.*\sRW\s", out, re.M)) != 1:
        sys.exit("create-fself duplicó el segmento de datos del lanzador; la PS4 no lo arrancaría.")
    return eboot


def main():
    if not sys.platform.startswith("linux"):
        sys.exit("Este script funciona en Linux (o WSL).")
    pkgtool = os.path.join(HERE, "linux-x64", "PkgTool.Core")
    if not os.path.isfile(pkgtool):
        sys.exit("Falta tools/linux-x64/PkgTool.Core: compílalo con 'python tools/build_pkgtool.py' primero.")
    if not os.path.isfile(os.path.join(OPENORBIS, "bin", "clang")):
        sys.exit("Falta el toolchain de PacBrew: ejecuta 'python tools/build_pemu.py' primero.")
    with tempfile.TemporaryDirectory() as tmp:
        launcher = build_launcher(tmp)
        for zip_name, folder, version, url, sha256, version_file in EMULATORS:
            pkg = os.path.join(tmp, folder + ".pkg")
            print("descargando", url, flush=True)
            with urllib.request.urlopen(url) as r, open(pkg, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            with open(pkg, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            if digest != sha256:
                sys.exit(f"El SHA-256 de {os.path.basename(url)} no coincide ({digest}).")
            out = os.path.join(tmp, "ext-" + folder)
            run([pkgtool, "pkg_extract", "--passcode", "0" * 32, pkg, out], stdout=subprocess.DEVNULL)
            os.remove(pkg)
            root = os.path.join(out, "uroot")
            dst = os.path.join(REPO, "emus", zip_name)
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                for dirpath, _dirs, files in os.walk(root):
                    for name in sorted(files):
                        full = os.path.join(dirpath, name)
                        rel = os.path.relpath(full, root).replace(os.sep, "/")
                        if rel.startswith("sce_sys/") or rel == version_file:
                            continue
                        z.write(full, f"{folder}/eboot.bin" if rel == "eboot.bin" else rel)
                z.write(launcher, "eboot.bin")
                z.writestr(version_file, PACKAGE_VERSION + "\n")
                z.writestr(f"{folder}/VERSION", version + "\n")
            print("listo:", dst, flush=True)

if __name__ == "__main__":
    main()
