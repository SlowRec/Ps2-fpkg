"""Interfaz de línea de comandos.

    python -m ps2fpkg [ps2] JUEGO.iso -e EMULADOR [opciones]   PS2
    python -m ps2fpkg ps1 JUEGO.cue -e EMULADOR [opciones]     PS1
    python -m ps2fpkg psp JUEGO.iso -e EMULADOR [opciones]     PSP
    python -m ps2fpkg nes JUEGO.nes [opciones]                 NES
    python -m ps2fpkg snes JUEGO.sfc [opciones]                SNES
    python -m ps2fpkg gba JUEGO.gba [opciones]                 GBA (también Game Boy / Color)
    python -m ps2fpkg genesis JUEGO.md [opciones]              Genesis (también Master System / Game Gear)
    python -m ps2fpkg dc JUEGO.gdi [opciones]                  Dreamcast (GDI, CHD, CDI o CUE)
    python -m ps2fpkg gc JUEGO.rvz [opciones]                  GameCube / Wii
    python -m ps2fpkg instalar JUEGO.pkg --ps4 IP              instalar por red con GoldHEN
    python -m ps2fpkg traer-emulador ps2 --ps4 IP              copiar el emulador de un clásico abierto en la PS4
"""

import argparse
import sys
import time

from . import builder, cue, dreamcast, emu, gamecube, install, iso, ps1, ps4ftp, psp, retro

SYSTEM_COMMANDS = ("ps2", "ps1", "psp", "nes", "snes", "gba", "genesis", "dc", "gc")


def _cover_args(p):
    g = p.add_argument_group("nombre e imágenes del juego en la PS4")
    g.add_argument("--caratula", default="", help="imagen de la carátula: con ella se hacen el icono y el fondo")
    g.add_argument("--buscar-caratula", action="store_true",
                   help="buscar la carátula en internet (por serial o por nombre) si no se indica una")
    g.add_argument("--icon", default="", help="icono propio (reemplaza al de la carátula; se ajusta a 512x512)")
    g.add_argument("--background", default="", help="fondo propio (reemplaza al de la carátula; 1920x1080)")


def _common(p, emu_required=True, emu_help="carpeta del emulador (la app de PS4 extraída, con eboot.bin)"):
    """Opciones compartidas por todas las consolas."""
    p.add_argument("-e", "--emu", required=emu_required, default="", help=emu_help)
    p.add_argument("-o", "--output", default=".", help="carpeta de salida (por defecto: la actual)")
    p.add_argument("-t", "--title", default="", help="nombre que se mostrará en el menú de PS4")
    p.add_argument("--title-id", default="", help="TITLE_ID del PKG (4 letras y 5 números)")
    p.add_argument("--content-id", default="", help="CONTENT_ID del PKG (36 caracteres)")
    _cover_args(p)
    k = p.add_argument_group("empaquetado e instalación")
    k.add_argument("--pkgtool", default="", help="ruta a PkgTool; por defecto el de tools/")
    k.add_argument("--gp4-only", action="store_true", help="solo preparar el proyecto .gp4, sin crear el PKG")
    k.add_argument("--keep-work", action="store_true", help="no borrar la carpeta de trabajo al terminar")
    k.add_argument("--instalar-en", default="", metavar="IP_PS4",
                   help="al terminar, enviarlo a la PS4 (Remote Package Installer abierto)")


def parse_system(cmd, argv):
    if cmd == "ps1":
        p = argparse.ArgumentParser(prog="ps2fpkg ps1", description="Convierte un juego de PS1 (BIN/CUE) "
                                    "en fPKG de PS4 con el emulador oficial de PS1 (PlayStation Plus).")
        p.add_argument("discos", nargs="+", help=".cue (o .bin de una pista) de cada disco, en orden")
        p.add_argument("--serial", default="", help="serial, p. ej. SLUS-00067 (por defecto se lee del disco)")
        p.add_argument("-q", "--calidad", choices=list(ps1.QUALITY_PROFILES), default="maxima",
                       help="maxima: resolución 6x (por defecto); alta: 4x; rendimiento: 2x; original: no toca la base")
        p.add_argument("--sin-menu-graficos", dest="graphics_menu", action="store_false",
                       help="no activar el menú Gráficos del emulador (filtro Lanczos y antialiasing en el juego)")
        p.add_argument("--60hz", dest="force_60hz", action="store_true", help="forzar 60 Hz (juegos PAL)")
        p.add_argument("--analogico", dest="analog", action="store_true", help="simular sticks analógicos")
        p.add_argument("--sin-logo", dest="skip_bios_logo", action="store_true", help="saltar el logo de PlayStation")
        p.add_argument("--config-lua", default="", help="script lua del juego")
        p.add_argument("--emu-arg", action="append", default=[], metavar="--CLAVE=VALOR",
                       help="línea extra para config-title.txt (repetible)")
    elif cmd == "psp":
        p = argparse.ArgumentParser(prog="ps2fpkg psp", description="Convierte un juego de PSP (ISO) "
                                    "en fPKG de PS4 con el emulador oficial de PSP (PlayStation Plus).")
        p.add_argument("iso", help="ISO del juego")
        p.add_argument("--serial", default="", help="serial, p. ej. ULUS-10041 (por defecto se lee del UMD)")
        p.add_argument("-q", "--calidad", choices=list(psp.QUALITY_PROFILES), default="maxima",
                       help="maxima: antialiasing SSAA4x (por defecto); equilibrado: MSAA4x; "
                            "rendimiento: sin antialiasing; original: no toca la base")
        p.add_argument("--eboot-decrypt", default="", help="ruta a eboot_decrypt; por defecto el de tools/")
        p.add_argument("--emu-arg", action="append", default=[], metavar="--CLAVE=VALOR",
                       help="línea extra para config-title.txt (repetible)")
    elif cmd == "dc":
        p = argparse.ArgumentParser(prog="ps2fpkg dc", description="Convierte un juego de Dreamcast en fPKG de "
                                    "PS4 con Resonance (Flycast, incluido): el juego arranca directo desde el menú.")
        p.add_argument("juego", help="juego (" + ", ".join(dreamcast.EXTENSIONS) + "); con sus pistas al lado")
        p.add_argument("-q", "--resolucion", choices=list(dreamcast.RESOLUTIONS), default="alta",
                       help="; ".join(f"{k}: {v}" for k, v in dreamcast.RESOLUTION_LABELS.items()))
        p.add_argument("--sin-16-9", dest="widescreen", action="store_false",
                       help="no usar los parches de pantalla ancha de los juegos (siempre 4:3)")
        p.add_argument("--mostrar-fps", dest="show_fps", action="store_true", help="mostrar los FPS")
        p.add_argument("--bios", default="", metavar="CARPETA",
                       help="carpeta con dc_boot.bin y dc_flash.bin de tu Dreamcast (opcional)")
    elif cmd == "gc":
        p = argparse.ArgumentParser(prog="ps2fpkg gc", description="Convierte un juego de GameCube o Wii en fPKG "
                                    "de PS4 con DolphinPS4 (incluido): el juego arranca directo desde el menú.")
        p.add_argument("discos", nargs="+", help="disco(s) en orden (" + ", ".join(gamecube.EXTENSIONS) + ")")
        p.add_argument("--serial", default="", help="ID del juego, p. ej. GALE01 (por defecto se lee del disco)")
    else:
        system = retro.SYSTEMS[cmd]
        p = argparse.ArgumentParser(prog=f"ps2fpkg {cmd}", description=f"Convierte una ROM de {system.name} "
                                    "en fPKG de PS4 con pemu (incluido): cada juego arranca directo desde el menú.")
        p.add_argument("rom", help="ROM del juego (" + ", ".join(system.extensions) + ")")
        p.add_argument("-v", "--imagen", choices=list(retro.VIDEO_PROFILES), default="nitido",
                       help="; ".join(f"{k}: {v}" for k, v in retro.VIDEO_LABELS.items()))
        if cmd == "snes":
            p.add_argument("--sin-sincronia-audio", dest="audio_sync", action="store_false",
                           help="no sincronizar con el audio (puede dar chasquidos)")
        p.add_argument("--mostrar-fps", dest="show_fps", action="store_true", help="mostrar los FPS")
    _common(p, emu_required=False,
            emu_help=("carpeta de un " + {"ps1": "PS1 Classic", "psp": "PSP Classic"}[cmd] + " de PS4 extraído; "
                      f"por defecto la de emuladores/{cmd}") if cmd in ("ps1", "psp")
            else {"dc": "base de Resonance propia (opcional)", "gc": "base de DolphinPS4 propia (opcional)"}.get(
                cmd, "pemu propio (opcional)"))
    return p.parse_args(argv)


def system_options(cmd, a):
    common = dict(output_dir=a.output, title=a.title, title_id=a.title_id, content_id=a.content_id,
                  icon=a.icon, background=a.background, cover=a.caratula, find_cover=a.buscar_caratula, pkgtool=a.pkgtool, gp4_only=a.gp4_only,
                  keep_work=a.keep_work, emu_dir=a.emu)
    if cmd == "ps1":
        return ps1, ps1.Options(discs=a.discos, serial=a.serial, quality=a.calidad, graphics_menu=a.graphics_menu,
                                force_60hz=a.force_60hz, analog=a.analog, skip_bios_logo=a.skip_bios_logo,
                                config_lua=a.config_lua, emu_args=a.emu_arg, **common)
    if cmd == "psp":
        return psp, psp.Options(iso=a.iso, serial=a.serial, quality=a.calidad, eboot_decrypt=a.eboot_decrypt,
                                emu_args=a.emu_arg, **common)
    if cmd == "dc":
        return dreamcast, dreamcast.Options(game=a.juego, resolution=a.resolucion, widescreen=a.widescreen,
                                            show_fps=a.show_fps, bios_dir=a.bios, **common)
    if cmd == "gc":
        return gamecube, gamecube.Options(discs=a.discos, serial=a.serial, **common)
    return retro, retro.Options(system=cmd, rom=a.rom, video=a.imagen, audio_sync=getattr(a, "audio_sync", True),
                                show_fps=a.show_fps, **common)


def parse_convert(argv):
    p = argparse.ArgumentParser(
        prog="ps2fpkg",
        description="Convierte ISOs de PS2 en fPKG de PS4 (PS2 Classics). Otras consolas: "
                    "'ps2fpkg ps1|psp|nes|snes|gba|genesis|dc|gc --help'. Instalar por red: 'ps2fpkg instalar --help'.",
    )
    p.add_argument("iso", nargs="+", help="ISO(s) del juego, en orden de disco (también acepta BIN de 2352 bytes/sector)")
    p.add_argument("-e", "--emu", default="",
                   help="carpeta del emulador (PS2 Classic de PS4 extraído); por defecto la de emuladores/ps2")
    p.add_argument("-o", "--output", default=".", help="carpeta de salida (por defecto: la actual)")
    p.add_argument("-t", "--title", default="", help="nombre que se mostrará en el menú de PS4")
    p.add_argument("--serial", default="", help="serial del juego, p. ej. SLUS-20946 (por defecto se lee del disco)")
    p.add_argument("--title-id", default="", help="TITLE_ID del PKG (por defecto el serial sin guion)")
    p.add_argument("--content-id", default="", help="CONTENT_ID del PKG (36 caracteres)")
    _cover_args(p)

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


def parse_fetch(argv):
    p = argparse.ArgumentParser(
        prog="ps2fpkg traer-emulador",
        description="Copia el emulador de un clásico de PS1, PS2 o PSP desde la PS4, por el FTP de GoldHEN: "
                    "activa el servidor FTP de GoldHEN, abre el clásico en la PS4 y ejecuta esto. Se guarda en "
                    "emuladores/<consola> junto a la app y desde entonces se usa solo.",
    )
    p.add_argument("consola", nargs="?", choices=("ps2", "ps1", "psp"), help="consola esperada (opcional)")
    p.add_argument("--ps4", required=True, help="IP de la PS4")
    p.add_argument("--puerto", type=int, default=ps4ftp.PORT, help=f"puerto FTP (por defecto {ps4ftp.PORT})")
    return p.parse_args(argv)


def _progress(done, total):
    print(f"\r  {done * 100 // max(1, total)}%", end="" if done < total else "\n", flush=True)


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
        if argv and argv[0] == "traer-emulador":
            a = parse_fetch(argv[1:])
            ps4ftp.fetch(a.ps4, a.consola, port=a.puerto)
            return 0
        if argv and argv[0] == "instalar":
            a = parse_install(argv[1:])
            run_install(a.pkg, a.ps4, a.puerto, a.ip_pc)
            return 0
        if argv and argv[0] in SYSTEM_COMMANDS and argv[0] != "ps2":
            a = parse_system(argv[0], argv[1:])
            module, opts = system_options(argv[0], a)
            pkg = module.build(opts, progress=_progress)
            if a.instalar_en and not a.gp4_only:
                run_install([pkg], a.instalar_en)
            return 0
        if argv and argv[0] == "ps2":
            argv = argv[1:]
        a = parse_convert(argv)
        opts = builder.Options(
            isos=a.iso, emu_dir=a.emu, output_dir=a.output, title=a.title, serial=a.serial,
            title_id=a.title_id, content_id=a.content_id, icon=a.icon, background=a.background,
            cover=a.caratula, find_cover=a.buscar_caratula, config_lua=a.config_lua, cli_conf=a.cli_conf, emu_args=a.emu_arg, quality=a.calidad,
            widescreen=a.widescreen, no_interlace=a.no_interlace, progressive=a.progressive,
            no_blur=a.no_blur, fps60=a.fps60, official_config=a.official_config,
            patches_dir=a.parches, online=a.online, pkgtool=a.pkgtool, gp4_only=a.gp4_only,
            keep_work=a.keep_work,
        )

        pkg = builder.build(opts, progress=_progress)
        if a.instalar_en and not a.gp4_only:
            run_install([pkg], a.instalar_en)
    except (builder.BuildError, emu.EmuError, iso.DiscError, cue.CueError, ps4ftp.Ps4FtpError, OSError, ValueError,
            RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
