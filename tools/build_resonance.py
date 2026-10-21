"""Prepara la base de Dreamcast (emus/resonance.zip).

Resonance (https://github.com/iHaiDeeZ/Resonance, GPL-2.0) es Flycast para PS4. Se usa su
versión publicada tal cual: se descarga el .pkg, se comprueba su SHA-256 y se extraen sus
archivos con PkgTool. El eboot.bin de Resonance pasa a resonance/eboot.bin y en su lugar va el
lanzador de tools/dc-launcher (compilado aquí con el toolchain OpenOrbis de PacBrew), que arranca
Resonance con el juego del paquete (ver ps2fpkg/dreamcast.py).

Requisitos (Linux x86_64): el toolchain de PacBrew en /opt/pacbrew (python tools/build_pemu.py
lo instala) y tools/linux-x64/PkgTool.Core (python tools/build_pkgtool.py). Uso:
    python tools/build_resonance.py
"""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

VERSION = "01.41"
URL = f"https://github.com/iHaiDeeZ/Resonance/releases/download/v{VERSION}/Resonance-v{VERSION}.pkg"
SHA256 = "47c04310506fd819db9d31d5bdc721e19b36a73320e18923866c83b34b367720"
OPENORBIS = "/opt/pacbrew/ps4/openorbis"
# PAID y authinfo con los que se publica Resonance (toolchain/ps4-love-style.cmake), que puede
# usar sceSystemServiceLoadExec.
PAID = "0x3100000000000002"
AUTH_INFO = ("000000000000000000000000001C004000FF000000000080000000000000000000000000000000000000008000400040"
             "000000000000008000000000000000080040FFFF000000F0000000000000000000000000000000000000000000000000"
             "00000000000000000000000000000000000000000000000000000000000000000000000000000000")
# Versión que ven los paquetes: más nueva que cualquiera, para que Resonance no cambie al
# programa de una actualización descargada (/data/Resonance/app), que arrancaría sin el juego.
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
        pkg = os.path.join(tmp, "Resonance.pkg")
        print("descargando", URL, flush=True)
        with urllib.request.urlopen(URL) as r, open(pkg, "wb") as f:
            f.write(r.read())
        with open(pkg, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        if digest != SHA256:
            sys.exit(f"El SHA-256 de Resonance no coincide ({digest}).")
        run([pkgtool, "pkg_extract", "--passcode", "0" * 32, pkg, os.path.join(tmp, "ext")],
            stdout=subprocess.DEVNULL)
        root = os.path.join(tmp, "ext", "uroot")
        launcher = build_launcher(tmp)
        dst = os.path.join(REPO, "emus", "resonance.zip")
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for dirpath, _dirs, files in os.walk(root):
                for name in sorted(files):
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, root).replace(os.sep, "/")
                    if rel.startswith("sce_sys/") or rel == "version.txt":
                        continue
                    z.write(full, "resonance/eboot.bin" if rel == "eboot.bin" else rel)
            z.write(launcher, "eboot.bin")
            z.writestr("version.txt", PACKAGE_VERSION + "\n")
            z.writestr("resonance/VERSION", VERSION + "\n")
        print("listo:", dst)


if __name__ == "__main__":
    main()
