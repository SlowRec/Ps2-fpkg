"""Compila PkgTool (LibOrbisPkg) con la corrección para PKG grandes.

LibOrbisPkg calcula el tamaño de la tabla PLAYGO_CHUNK_SHA con una estimación que, según
el tamaño exacto del juego y de las imágenes, se queda corta por un bloque de alineación
(512 KB) y aborta con "Playgo Chunk hash file was not allocated enough space". La tabla
cuenta en el propio tamaño del PKG, así que aquí se calcula exactamente iterando hasta
que el tamaño se estabiliza (mismo cálculo que hace después el comprobador).

Requisitos: git y .NET SDK 8. Uso:
    python tools/build_pkgtool.py                # para este sistema
    python tools/build_pkgtool.py --rid win-x64  # para Windows (desde cualquier sistema)

LibOrbisPkg es LGPL-3.0; su código fuente y esta modificación están disponibles aquí.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile

REPO = "https://github.com/maxton/LibOrbisPkg"
COMMIT = "643477263b2644e0803e0f58b8726ea4e3f3b7d4"
HERE = os.path.dirname(os.path.abspath(__file__))

PLAYGO_OLD = "e.DataSize = (uint)(pkgSize / 0x10000L) * 4;"
PLAYGO_MARK = "// ps2-fpkg: tamaño exacto de PLAYGO_CHUNK_SHA"
PLAYGO_NEW = PLAYGO_MARK + """
          long shaSize = 0;
          var following = pkg.Entries.SkipWhile(x => x != entry).Skip(1).ToList();
          while (true)
          {
            long end = Align((long)dataOffset + shaSize, 16L);
            foreach (var other in following)
              end = Align(end + (other == pkg.Metas ? pkg.Entries.Count * 32L : other.Length), 16L);
            long needed = ((Align(end, 0x80000L) + pfsSize) / 0x10000L) * 4;
            if (needed <= shaSize) break;
            shaSize = needed;
          }
          e.DataSize = (uint)shaSize;"""


def default_rid():
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    system = {"Windows": "win", "Darwin": "osx"}.get(platform.system(), "linux")
    return f"{system}-{arch}"


def run(cmd, cwd=None):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def patch_source(src):
    builder = os.path.join(src, "LibOrbisPkg", "PKG", "PkgBuilder.cs")
    with open(builder, encoding="utf-8-sig") as f:
        text = f.read()
    if PLAYGO_MARK not in text:
        if PLAYGO_OLD not in text:
            sys.exit("No se encontró el código a corregir en PkgBuilder.cs (¿cambió LibOrbisPkg?).")
        text = text.replace(PLAYGO_OLD, PLAYGO_NEW)
        with open(builder, "w", encoding="utf-8") as f:
            f.write(text)
    for proj in ("LibOrbisPkg.Core/LibOrbisPkg.Core.csproj", "PkgTool.Core/PkgTool.Core.csproj"):
        path = os.path.join(src, *proj.split("/"))
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace("<TargetFramework>netcoreapp3.0</TargetFramework>",
                                 "<TargetFramework>net8.0</TargetFramework>"))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--rid", default=default_rid(), help="plataforma destino: win-x64, linux-x64, osx-arm64…")
    p.add_argument("--out", default="", help="carpeta de salida (por defecto tools/<rid>)")
    a = p.parse_args()
    dotnet = shutil.which("dotnet")
    if not dotnet:
        sys.exit("Falta .NET SDK 8: https://dotnet.microsoft.com/download")
    out = os.path.abspath(a.out or os.path.join(HERE, a.rid))

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "LibOrbisPkg")
        run(["git", "init", "-q", src])
        run(["git", "fetch", "-q", "--depth", "1", REPO, COMMIT], cwd=src)
        run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=src)
        patch_source(src)
        run([dotnet, "publish", os.path.join(src, "PkgTool.Core", "PkgTool.Core.csproj"),
             "-c", "Release", "-r", a.rid, "--self-contained", "true", "-nologo",
             "-p:PublishSingleFile=true", "-p:IncludeNativeLibrariesForSelfExtract=true",
             "-p:EnableCompressionInSingleFile=true", "-p:DebugType=none", "-o", out])
        shutil.copy(os.path.join(src, "LICENSE.txt"), os.path.join(out, "LibOrbisPkg-LICENSE.txt"))
    print(f"\nPkgTool parcheado listo en {out}")


if __name__ == "__main__":
    main()
