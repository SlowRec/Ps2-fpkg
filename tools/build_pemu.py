"""Recompila las bases de NES, SNES y GBA (emus/pnes.zip, emus/psnes.zip, emus/pgba.zip) desde el código fuente.

pemu (https://github.com/Cpasjuste/pemu, GPL-3.0) con tools/pemu-autoboot.patch: si el paquete
trae /app0/autoboot/rom.txt, la app arranca ese juego directamente y aplica
/app0/autoboot/options.txt como ajustes iniciales del juego.

Requisitos (Linux x86_64): git, cmake, make, curl, nasm, Python 3, y el toolchain de PS4 de
PacBrew instalado en /opt/pacbrew (este script lo descarga si se ejecuta con permisos para
crear /opt/pacbrew). Uso:
    python tools/build_pemu.py
"""

import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

PEMU = "https://github.com/Cpasjuste/pemu"
PEMU_COMMIT = "eeb5199ee0657b87f65197cbb043e5014befffbd"
SUBMODULES = ("external/libcross2d", "external/sscrap", "external/cores/nestopia", "external/cores/snes9x",
              "external/cores/mgba")
PACBREW = "https://pacman.mydedibox.fr/pacbrew/packages/"
OPENORBIS = "/opt/pacbrew/ps4/openorbis"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CORES = {"pnes": "PNES", "psnes": "PSNE", "pgba": "PGBA"}


def run(cmd, cwd=None, env=None):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def install_toolchain():
    """Descarga y descomprime los paquetes ps4-openorbis-* de PacBrew en /opt/pacbrew."""
    if os.path.isfile(os.path.join(OPENORBIS, "bin", "clang")):
        return
    with urllib.request.urlopen(PACBREW + "pacbrew.db") as r:
        db = tarfile.open(fileobj=io.BytesIO(r.read()))
    names = []
    for member in db.getmembers():
        if member.name.endswith("/desc") and member.name.startswith("ps4-openorbis-"):
            desc = db.extractfile(member).read().decode()
            names.append(re.search(r"%FILENAME%\n(.+)\n", desc).group(1))
    for name in names:
        print("descargando", name, flush=True)
        with urllib.request.urlopen(PACBREW + name) as r, tempfile.TemporaryFile() as tmp:
            tmp.write(r.read())
            tmp.seek(0)
            with tarfile.open(fileobj=tmp) as pkg:
                pkg.extractall("/", members=[m for m in pkg.getmembers() if m.name.startswith("opt/")])


def check_oelf(build, core):
    """El create-fself de PacBrew a veces duplica el segmento de datos y la PS4 rechaza el eboot
    (CE-41839-5): debe haber exactamente un PT_LOAD de lectura/escritura."""
    for dirpath, _dirs, files in os.walk(build):
        if f"{core}.oelf" in files:
            out = subprocess.run([os.path.join(OPENORBIS, "bin", "llvm-readelf"), "-l", "-W",
                                  os.path.join(dirpath, f"{core}.oelf")], capture_output=True, text=True).stdout
            if len(re.findall(r"^\s*LOAD\s.*\sRW\s", out, re.M)) != 1:
                sys.exit(f"{core}.oelf tiene segmentos de datos duplicados (fallo de create-fself):\n{out}")
            return
    print(f"aviso: no se encontró {core}.oelf para revisarlo", flush=True)


def main():
    if not sys.platform.startswith("linux"):
        sys.exit("Este script funciona en Linux (o WSL).")
    install_toolchain()
    pkgtool = os.path.join(HERE, "linux-x64", "PkgTool.Core")
    if not os.path.isfile(pkgtool):
        sys.exit("Falta tools/linux-x64/PkgTool.Core: compílalo con 'python tools/build_pkgtool.py' primero.")
    env = dict(os.environ, OPENORBIS=OPENORBIS)
    env.pop("CFLAGS", None)
    env.pop("CXXFLAGS", None)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "pemu")
        run(["git", "init", "-q", src])
        run(["git", "fetch", "-q", "--depth", "1", PEMU, PEMU_COMMIT], cwd=src)
        run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=src)
        run(["git", "submodule", "update", "--init", "--depth", "1", *SUBMODULES], cwd=src)
        run(["git", "apply", os.path.join(HERE, "pemu-autoboot.patch")], cwd=src)
        # Solo NES, SNES y GBA: los demás núcleos necesitan submódulos que no hacen falta aquí.
        cmake = os.path.join(src, "CMakeLists.txt")
        with open(cmake) as f:
            text = f.read()
        for core in ("pfbneo", "pgen"):
            text = text.replace(f"add_subdirectory(src/cores/{core})", f"#add_subdirectory(src/cores/{core})")
        with open(cmake, "w") as f:
            f.write(text)
        build = os.path.join(src, "build")
        os.makedirs(build)
        run(["cmake", "-G", "Unix Makefiles", "-DPLATFORM_PS4=ON", "-DCMAKE_BUILD_TYPE=Release", ".."], build, env)
        run(["make", f"-j{os.cpu_count() or 2}", *(f"{c}_pkg" for c in CORES)], build, env)
        for core, prefix in CORES.items():
            check_oelf(build, core)
            pkg = next(f for f in os.listdir(build) if f.endswith(".pkg") and f"-{prefix}" in f)
            out = os.path.join(build, f"ext_{core}")
            run([pkgtool, "pkg_extract", "--passcode", "0" * 32, os.path.join(build, pkg), out])
            root = os.path.join(out, "uroot")
            dst = os.path.join(REPO, "emus", f"{core}.zip")
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                for dirpath, _dirs, files in os.walk(root):
                    for name in sorted(files):
                        full = os.path.join(dirpath, name)
                        rel = os.path.relpath(full, root).replace(os.sep, "/")
                        if rel not in ("sce_sys/keystone", "sce_sys/param.sfo"):
                            z.write(full, rel)
            print("listo:", dst)


if __name__ == "__main__":
    main()
