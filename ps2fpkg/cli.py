"""Interfaz de línea de comandos."""

import argparse
import sys

from . import builder, emu, iso


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="ps2fpkg",
        description="Convierte ISOs de PS2 en fPKG de PS4 (PS2 Classics) usando LibOrbisPkg.",
    )
    p.add_argument("iso", nargs="+", help="ISO(s) del juego, en orden de disco (también acepta BIN de 2352 bytes/sector)")
    p.add_argument("-e", "--emu", required=True, help="carpeta extraída de un PS2 Classic de PS4 (la que tiene eboot.bin)")
    p.add_argument("-o", "--output", default=".", help="carpeta de salida (por defecto: la actual)")
    p.add_argument("-t", "--title", default="", help="nombre que se mostrará en el menú de PS4")
    p.add_argument("--serial", default="", help="serial del juego, p. ej. SLUS-20946 (por defecto se lee del disco)")
    p.add_argument("--title-id", default="", help="TITLE_ID del PKG (por defecto el serial sin guion)")
    p.add_argument("--content-id", default="", help="CONTENT_ID del PKG (36 caracteres)")
    p.add_argument("--icon", default="", help="imagen para icon0.png (se ajusta a 512x512)")
    p.add_argument("--background", default="", help="imagen de fondo pic0/pic1 (se ajusta a 1920x1080)")
    p.add_argument("--config-lua", default="", help="parche lua del juego (se copia a patches/<SERIAL>_config.lua)")
    p.add_argument("--cli-conf", default="", help="configuración del emulador (se copia a patches/<SERIAL>_cli.conf)")
    p.add_argument("--emu-arg", action="append", default=[], metavar="--CLAVE=VALOR",
                   help="argumento extra para config-emu-ps4.txt, p. ej. --emu-arg=--gs-uprender=2x2 (repetible)")
    p.add_argument("--pkgtool", default="", help="ruta a PkgTool.Core(.exe/.dll); por defecto se busca en tools/ y PATH")
    p.add_argument("--gp4-only", action="store_true", help="solo preparar el proyecto .gp4, sin crear el PKG")
    p.add_argument("--keep-work", action="store_true", help="no borrar la carpeta de trabajo al terminar")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    opts = builder.Options(
        isos=a.iso, emu_dir=a.emu, output_dir=a.output, title=a.title, serial=a.serial,
        title_id=a.title_id, content_id=a.content_id, icon=a.icon, background=a.background,
        config_lua=a.config_lua, cli_conf=a.cli_conf, emu_args=a.emu_arg, pkgtool=a.pkgtool,
        gp4_only=a.gp4_only, keep_work=a.keep_work,
    )

    def progress(done, total):
        print(f"\r  {done * 100 // max(1, total)}%", end="" if done < total else "\n", flush=True)

    try:
        builder.build(opts, progress=progress)
    except (builder.BuildError, emu.EmuError, iso.DiscError, OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
