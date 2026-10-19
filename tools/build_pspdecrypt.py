"""Compila eboot_decrypt: descifra el EBOOT.BIN de un juego de PSP (formato ~PSP).

El emulador de PSP de los PS Classics de PS4 necesita el ejecutable del UMD descifrado.
Se usa PrxDecrypter + libkirk de pspdecrypt (https://github.com/John-K/pspdecrypt, GPL-3.0),
que no dependen de otras bibliotecas, con un main mínimo propio.

Requisitos: git y un compilador de C++ (g++/clang++) o Zig para compilar para otro sistema.
    python tools/build_pspdecrypt.py                      # para este sistema
    python tools/build_pspdecrypt.py --rid win-x64 --zig RUTA/zig   # para Windows
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile

REPO = "https://github.com/John-K/pspdecrypt"
COMMIT = "c156627db7634d395c380c0a9589130f603307fc"
HERE = os.path.dirname(os.path.abspath(__file__))
ZIG_TARGETS = {"win-x64": "x86_64-windows-gnu", "linux-x64": "x86_64-linux-musl",
               "linux-arm64": "aarch64-linux-musl", "osx-x64": "x86_64-macos", "osx-arm64": "aarch64-macos"}

MAIN = r"""// ps2-fpkg: descifra un EBOOT.BIN de PSP (~PSP) con PrxDecrypter de pspdecrypt.
// Uso: eboot_decrypt ENTRADA SALIDA   (imprime el tamaño descifrado)
#include <cstdio>
#include <vector>
#include "PrxDecrypter.h"

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "uso: %s ENTRADA SALIDA\n", argv[0]);
        return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 2; }
    std::vector<u8> in;
    u8 buf[65536];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0) in.insert(in.end(), buf, buf + n);
    fclose(f);
    if (in.size() < 0x150 || in[0] != '~' || in[1] != 'P' || in[2] != 'S' || in[3] != 'P') {
        fprintf(stderr, "no es un ejecutable cifrado (~PSP)\n");
        return 3;
    }
    std::vector<u8> out(in.size());
    int size = pspDecryptPRX(in.data(), out.data(), (u32)in.size(), nullptr, false);
    if (size <= 0) {
        fprintf(stderr, "no se pudo descifrar (codigo %d)\n", size);
        return 1;
    }
    f = fopen(argv[2], "wb");
    if (!f || fwrite(out.data(), 1, (size_t)size, f) != (size_t)size) { perror(argv[2]); return 2; }
    fclose(f);
    printf("%d\n", size);
    return 0;
}
"""


def default_rid():
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    return {"Windows": "win", "Darwin": "osx"}.get(platform.system(), "linux") + "-" + arch


def run(cmd, cwd=None):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--rid", default=default_rid(), help="plataforma destino: win-x64, linux-x64…")
    p.add_argument("--zig", default="", help="ruta a zig para compilar para otra plataforma")
    p.add_argument("--out", default="", help="carpeta de salida (por defecto tools/<rid>)")
    a = p.parse_args()
    out = os.path.abspath(a.out or os.path.join(HERE, a.rid))
    os.makedirs(out, exist_ok=True)
    exe = os.path.join(out, "eboot_decrypt" + (".exe" if a.rid.startswith("win") else ""))

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "pspdecrypt")
        run(["git", "init", "-q", src])
        run(["git", "fetch", "-q", "--depth", "1", REPO, COMMIT], cwd=src)
        run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=src)
        with open(os.path.join(src, "eboot_decrypt.cpp"), "w") as f:
            f.write(MAIN)
        c_files = [os.path.join("libkirk", n) for n in sorted(os.listdir(os.path.join(src, "libkirk")))
                   if n.endswith(".c")]
        if a.zig:
            if a.rid not in ZIG_TARGETS:
                sys.exit(f"Plataforma no soportada con zig: {a.rid}")
            cc = [a.zig, "cc", "-target", ZIG_TARGETS[a.rid]]
            cxx = [a.zig, "c++", "-target", ZIG_TARGETS[a.rid]]
        else:
            cc = [shutil.which("cc") or shutil.which("clang") or "gcc"]
            cxx = [shutil.which("c++") or shutil.which("clang++") or "g++"]
        objs = []
        for c in c_files:
            obj = c.replace(os.sep, "_") + ".o"
            run(cc + ["-O2", "-c", c, "-o", obj], cwd=src)
            objs.append(obj)
        static = ["-static"] if a.rid.startswith(("win", "linux")) else []
        run(cxx + ["-O2", "-std=c++17", "eboot_decrypt.cpp", "PrxDecrypter.cpp", *objs, *static, "-s", "-o", exe], cwd=src)
        for extra in (".lib", ".pdb"):  # restos del enlazador de Windows
            leftover = os.path.splitext(exe)[0] + extra
            if os.path.exists(leftover):
                os.remove(leftover)
        shutil.copy(os.path.join(src, "LICENSE.TXT"), os.path.join(out, "pspdecrypt-LICENSE.txt"))
    print(f"\neboot_decrypt listo en {exe}")


if __name__ == "__main__":
    main()
