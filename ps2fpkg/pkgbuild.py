"""Empaquetado común a todas las consolas: param.sfo, imágenes del menú, proyecto GP4,
PkgTool y verificación del PKG terminado."""

import os
import platform
import re
import shutil
import subprocess
import zlib

from . import gp4, images, sfo

FAT32_LIMIT = 4 * 1024 ** 3 - 1
TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")


class BuildError(Exception):
    pass


def rid():
    """Plataforma de esta PC con el formato de tools/ (win-x64, linux-x64, osx-arm64…)."""
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    return {"Windows": "win", "Darwin": "osx"}.get(platform.system(), "linux") + "-" + arch


def find_tool(names, explicit="", env=""):
    """Ruta de una herramienta: la indicada, la variable de entorno, tools/<rid>/, tools/ o el PATH."""
    candidates = [explicit, os.environ.get(env, "") if env else ""]
    for name in names:
        candidates += [os.path.join(TOOLS_DIR, rid(), name), os.path.join(TOOLS_DIR, name),
                       shutil.which(name) or ""]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    if explicit:
        raise BuildError(f"No se encontró {explicit}.")
    return None


def find_pkgtool(explicit=""):
    """Devuelve el comando (lista) para ejecutar PkgTool, o None."""
    path = find_tool(("PkgTool.Core.exe", "PkgTool.Core", "PkgTool.exe", "PkgTool.Core.dll"),
                     explicit, "PS2FPKG_PKGTOOL")
    if path is None:
        return None
    if path.lower().endswith(".dll"):
        dotnet = shutil.which("dotnet")
        if not dotnet:
            raise BuildError(f"{path} requiere .NET (dotnet) instalado.")
        return [dotnet, path]
    return [path]


def run(cmd, log, name="PkgTool"):
    """Ejecuta un comando mostrando su salida; devuelve el texto completo."""
    lines = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, errors="replace") as proc:
        for line in proc.stdout:
            lines.append(line)
            log("  " + line.rstrip())
    text = "".join(lines)
    if proc.returncode != 0 and "not allocated enough space" not in text:
        raise BuildError(f"{name} falló (código {proc.returncode}):\n{text[-2000:]}")
    return text


def validate_ids(title_id, content_id):
    if not re.fullmatch(r"[A-Z]{4}\d{5}", title_id):
        raise BuildError(f"TITLE_ID '{title_id}' inválido: deben ser 4 letras y 5 números (p. ej. SLUS20946).")
    if not re.fullmatch(r"[A-Z]{2}\d{4}-[A-Z]{4}\d{5}_00-[A-Z0-9]{16}", content_id):
        raise BuildError(f"CONTENT_ID '{content_id}' inválido: formato XX0000-XXXX00000_00-ZZZZZZZZZZZZZZZZ.")
    if content_id[7:16] != title_id:
        raise BuildError(f"El CONTENT_ID {content_id} no contiene el TITLE_ID {title_id}.")


def ids_from_crc(prefix, data, label):
    """TITLE_ID y CONTENT_ID estables para juegos sin serial (ROMs): derivados del CRC32."""
    crc = zlib.crc32(data) & 0xFFFFFFFF
    title_id = f"{prefix}{crc % 100000:05d}"
    return title_id, f"IV0001-{title_id}_00-{crc:08X}{label}"[:36]


class Package:
    """Carpeta de trabajo + lista de archivos (ruta en el PKG -> ruta en disco)."""

    def __init__(self, output_dir, content_id):
        os.makedirs(output_dir, exist_ok=True)
        self.output_dir = os.path.abspath(output_dir)
        self.content_id = content_id
        self.work = os.path.join(self.output_dir, f"{content_id}_work")
        if os.path.exists(self.work):
            shutil.rmtree(self.work)
        os.makedirs(os.path.join(self.work, "sce_sys"))
        self.files = {}

    def path(self, rel):
        """Ruta en la carpeta de trabajo para un archivo generado."""
        dst = os.path.join(self.work, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        return dst

    def write(self, rel, data):
        dst = self.path(rel)
        with open(dst, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        self.files[rel] = dst

    def add(self, rel, source):
        self.files[rel] = os.path.abspath(source)

    def build(self, *, title, title_id, icon="", background="", cover="", subtitle="", pkgtool="",
              gp4_only=False, keep_work=False, validate=True, log=print, icon_fit="cover", attribute=0):
        """Añade param.sfo e imágenes, crea el PKG y lo verifica. Devuelve la ruta del .pkg
        (o del .gp4 si gp4_only). Imágenes: icono/fondo propios > carátula > genéricas con el título."""
        validate_ids(title_id, self.content_id)
        self.write("sce_sys/param.sfo", sfo.ps2_classic(title, title_id, self.content_id, attribute=attribute))
        log("Generando imágenes del menú...")
        if cover and images.Image is None:
            log("Aviso: instala Pillow (pip install pillow) para usar la carátula; se usan imágenes genéricas.")
            cover = ""
        extra = {"subtitle": subtitle} if subtitle else {}
        icon_path = self.path("sce_sys/icon0.png")
        if icon or not cover:
            images.make(icon_path, images.ICON_SIZE, icon or None, title=title, fit=icon_fit, **extra)
        else:
            images.icon_from_cover(cover, icon_path)
        self.files["sce_sys/icon0.png"] = icon_path
        for rel in ("sce_sys/pic0.png", "sce_sys/pic1.png"):
            path = self.path(rel)
            if background or not cover:
                images.make(path, images.BG_SIZE, background or None, title=title, **extra)
            else:
                images.background_from_cover(cover, path)
            self.files[rel] = path

        gp4_path = os.path.join(self.work, "project.gp4")
        with open(gp4_path, "wb") as f:
            f.write(gp4.build(self.content_id, self.files))
        log(f"Proyecto GP4: {gp4_path} ({len(self.files)} archivos)")
        if gp4_only:
            return gp4_path

        cmd = find_pkgtool(pkgtool)
        if cmd is None:
            raise BuildError(
                "No se encontró PkgTool. Usa el incluido en tools/ o compílalo con "
                f"'python tools/build_pkgtool.py'. El proyecto quedó listo en {gp4_path}."
            )
        pkg_path = os.path.join(self.output_dir, f"{self.content_id}.pkg")
        if os.path.exists(pkg_path):
            os.remove(pkg_path)
        log("Creando el fPKG con PkgTool (puede tardar varios minutos)...")
        output = run(cmd + ["pkg_build", gp4_path, self.output_dir], log)
        if "not allocated enough space" in output:
            raise BuildError("Este PkgTool tiene el fallo de PlayGo con juegos grandes. Usa el PkgTool "
                             "parcheado de tools/ (o compílalo con 'python tools/build_pkgtool.py').")
        if not os.path.isfile(pkg_path):
            raise BuildError(f"PkgTool no generó {pkg_path}. Archivos de trabajo en {self.work}.")

        if validate:
            log("Verificando hashes y firmas del PKG...")
            report = run(cmd + ["pkg_validate", pkg_path], lambda _line: None)
            errors = [ln for ln in report.splitlines() if ln.startswith("[ERROR]")]
            if errors or "[OK]" not in report:
                raise BuildError("El PKG no pasó la verificación:\n" + ("\n".join(errors) or report[-2000:]))
            log(f"Verificación correcta ({report.count('[OK]')} comprobaciones).")

        if not keep_work:
            shutil.rmtree(self.work, ignore_errors=True)
        size = os.path.getsize(pkg_path)
        log(f"Listo: {pkg_path} ({size / 1024 ** 3:.2f} GB)")
        if size > FAT32_LIMIT:
            log("Nota: pesa más de 4 GB. Para instalar por USB formatea la memoria en exFAT "
                "(FAT32 no admite archivos tan grandes) o instálalo por red.")
        return pkg_path
