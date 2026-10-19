"""Interfaz de línea de comandos.

    python -m ps2fpkg JUEGO.iso -e EMULADOR [opciones]     convertir
    python -m ps2fpkg instalar JUEGO.pkg --ps4 IP          instalar por red con GoldHEN
"""

import argparse
import sys
import time

from . import builder, emu, install, iso


def parse_convert(argv):
    p = argparse.ArgumentParser(
        prog="ps2fpkg",
        description="Convierte ISOs de PS2 en fPKG de PS4 (PS2 Classics). "
                    "Para instalar por red: 'ps2fpkg instalar --help'.",
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

    q = p.add_argument_group("calidad de imagen y sonido")
    q.add_argument("-q", "--calidad", choices=sorted(emu.QUALITY_PROFILES), default="maxima",
                   help="maxima: resolución interna 2x + suavizado de bordes (por defecto); "
                        "rendimiento: resolución nativa + suavizado; original: no toca la base")
    q.add_argument("--sin-16-9", dest="widescreen", action="store_false",
                   help="no aplicar el parche de pantalla panorámica 16:9")
    q.add_argument("--con-entrelazado", dest="no_interlace", action="store_false",
                   help="no aplicar el parche que quita el entrelazado")
    q.add_argument("--480p", dest="progressive", action="store_true", help="activar el modo 480p del juego (si existe)")
    q.add_argument("--sin-desenfoque", dest="no_blur", action="store_true", help="quitar filtros de desenfoque/bloom")
    q.add_argument("--60fps", dest="fps60", action="store_true", help="parche de 60 FPS (puede cambiar la velocidad del juego)")
    q.add_argument("--sin-config-oficial", dest="official_config", action="store_false",
                   help="no usar las opciones del emulador que Sony definió para este juego")
    q.add_argument("--parches", default="", metavar="CARPETA",
                   help="carpeta local con parches .pnach de PCSX2 (para trabajar sin internet)")
    q.add_argument("--sin-internet", dest="online", action="store_false",
                   help="no descargar parches ni configuraciones (usa solo la caché y --parches)")
    q.add_argument("--config-lua", default="", help="parche lua del juego (se copia a patches/<SERIAL>_config.lua)")
    q.add_argument("--cli-conf", default="", help="opciones del emulador para el juego (patches/<SERIAL>_cli.conf)")
    q.add_argument("--emu-arg", action="append", default=[], metavar="--CLAVE=VALOR",
                   help="línea extra para config-emu-ps4.txt, p. ej. --emu-arg=--gs-upscale=point (repetible)")

    k = p.add_argument_group("empaquetado e instalación")
    k.add_argument("--pkgtool", default="", help="ruta a PkgTool; por defecto el de tools/")
    k.add_argument("--gp4-only", action="store_true", help="solo preparar el proyecto .gp4, sin crear el PKG")
    k.add_argument("--keep-work", action="store_true", help="no borrar la carpeta de trabajo al terminar")
    k.add_argument("--instalar-en", default="", metavar="IP_PS4",
                   help="al terminar, enviarlo a la PS4 (Remote Package Installer abierto)")
    return p.parse_args(argv)


def parse_install(argv):
    p = argparse.ArgumentParser(
        prog="ps2fpkg instalar",
        description="Sirve PKG por la red local para instalarlos en la PS4 con GoldHEN. Con --ps4 se los "
                    "envía a Remote Package Installer; sin él, muestra las URL para usarlas en otro "
                    "instalador por URL. Deja esta ventana abierta hasta que la descarga termine.",
    )
    p.add_argument("pkg", nargs="+", help="archivo(s) .pkg")
    p.add_argument("--ps4", default="", help="IP de la PS4 con Remote Package Installer abierto")
    p.add_argument("--puerto", type=int, default=8000, help="puerto HTTP de esta PC (por defecto 8000)")
    p.add_argument("--ip-pc", default="", help="IP de esta PC si la detección automática falla")
    return p.parse_args(argv)


def run_install(pkgs, ps4="", port=8000, host_ip=""):
    server, urls = install.serve(pkgs, port=port, host_ip=host_ip, ps4_ip=ps4)
    for url in urls.values():
        print(f"Sirviendo: {url}")
    try:
        if ps4:
            answer = install.send_to_ps4(ps4, list(urls.values()))
            print(f"La PS4 aceptó la instalación ({answer.get('title', '')}, tarea {answer.get('task_id', '?')}).")
        print("Deja esta ventana abierta hasta que la PS4 termine de descargar. Ctrl+C para salir.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv and argv[0] == "instalar":
            a = parse_install(argv[1:])
            run_install(a.pkg, a.ps4, a.puerto, a.ip_pc)
            return 0
        a = parse_convert(argv)
        opts = builder.Options(
            isos=a.iso, emu_dir=a.emu, output_dir=a.output, title=a.title, serial=a.serial,
            title_id=a.title_id, content_id=a.content_id, icon=a.icon, background=a.background,
            config_lua=a.config_lua, cli_conf=a.cli_conf, emu_args=a.emu_arg, quality=a.calidad,
            widescreen=a.widescreen, no_interlace=a.no_interlace, progressive=a.progressive,
            no_blur=a.no_blur, fps60=a.fps60, official_config=a.official_config,
            patches_dir=a.parches, online=a.online, pkgtool=a.pkgtool, gp4_only=a.gp4_only,
            keep_work=a.keep_work,
        )

        def progress(done, total):
            print(f"\r  {done * 100 // max(1, total)}%", end="" if done < total else "\n", flush=True)

        pkg = builder.build(opts, progress=progress)
        if a.instalar_en and not a.gp4_only:
            run_install([pkg], a.instalar_en)
    except (builder.BuildError, emu.EmuError, iso.DiscError, OSError, ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
