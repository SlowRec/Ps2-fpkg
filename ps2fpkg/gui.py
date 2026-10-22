"""Ventana (tkinter) con una pestaña por consola, sobre el mismo motor que la línea de comandos."""

import dataclasses
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import subprocess
import sys

from . import __version__, builder, covers, dreamcast, emu, gamecube, images, importer, install, m33, ps1, ps4ftp, psp, retro

SETTINGS = os.path.join(os.path.expanduser("~"), ".ps2fpkg.json")
SHARED = ("pkgtool", "output_dir", "ps4_ip")
IMAGES = [("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Todos", "*")]


@dataclasses.dataclass
class Spec:
    """Descripción de una pestaña: qué archivos pide, qué opciones muestra y cómo construir."""
    key: str
    tab: str
    files_label: str
    file_types: list
    multi: bool
    emu_label: str = ""                 # vacío = no pide emulador base
    detect: object = None               # ruta -> serial (o None)
    quality: dict = dataclasses.field(default_factory=dict)  # texto -> valor
    quality_label: str = "Perfil"
    flags: tuple = ()                   # (opción, texto, por defecto)
    extra_files: tuple = ()             # (opción, texto, tipos)
    emu_args: bool = False
    note: str = ""


def _ps2_options(v, files, flags, quality, args):
    return builder, builder.Options(
        isos=files, emu_dir=v["emu_dir"], output_dir=v["output_dir"], title=v["title"], serial=v["serial"],
        icon=v["icon"], background=v["background"], cover=v["cover"], find_cover=not v["cover"],
        config_lua=v.get("config_lua", ""), cli_conf=v.get("cli_conf", ""), emu_args=args, pkgtool=v["pkgtool"], gp4_only=v["gp4_only"],
        quality=quality, **flags)


def _ps1_options(v, files, flags, quality, args):
    return ps1, ps1.Options(
        discs=files, emu_dir=v["emu_dir"], output_dir=v["output_dir"], title=v["title"], serial=v["serial"],
        icon=v["icon"], background=v["background"], cover=v["cover"], find_cover=not v["cover"],
        config_lua=v.get("config_lua", ""), emu_args=args,
        pkgtool=v["pkgtool"], gp4_only=v["gp4_only"], quality=quality, **flags)


def _psp_options(v, files, flags, quality, args):
    return psp, psp.Options(
        iso=files[0], emu_dir=v["emu_dir"], output_dir=v["output_dir"], title=v["title"], serial=v["serial"],
        icon=v["icon"], background=v["background"], cover=v["cover"], find_cover=not v["cover"],
        emu_args=args, pkgtool=v["pkgtool"],
        gp4_only=v["gp4_only"], quality=quality, **flags)


def _retro_options(system):
    def make(v, files, flags, quality, _args):
        return retro, retro.Options(
            system=system, rom=files[0], output_dir=v["output_dir"], title=v["title"], icon=v["icon"],
            background=v["background"], cover=v["cover"], find_cover=not v["cover"], pkgtool=v["pkgtool"], gp4_only=v["gp4_only"], video=quality, **flags)
    return make


def _dc_options(v, files, flags, quality, _args):
    bios = v.get("bios", "")
    return dreamcast, dreamcast.Options(
        game=files[0], output_dir=v["output_dir"], title=v["title"], icon=v["icon"], background=v["background"],
        cover=v["cover"], find_cover=not v["cover"], bios_dir=os.path.dirname(bios) if bios else "",
        pkgtool=v["pkgtool"], gp4_only=v["gp4_only"], resolution=quality, **flags)


def _gc_options(v, files, _flags, _quality, _args):
    return gamecube, gamecube.Options(
        discs=files, output_dir=v["output_dir"], title=v["title"], serial=v["serial"], icon=v["icon"],
        background=v["background"], cover=v["cover"], find_cover=not v["cover"], pkgtool=v["pkgtool"],
        gp4_only=v["gp4_only"])


SPECS = [
    (Spec("ps2", "PS2", "Discos (ISO/BIN, en orden)", [("Imágenes de disco", "*.iso *.bin *.img"), ("Todos", "*")],
          True, "emulador de un PS2 Classic de PS4", builder.detect_serial,
          {"Máxima (2x resolución + suavizado)": "maxima", "Rendimiento (resolución nativa + suavizado)": "rendimiento",
           "Original (no tocar el emulador)": "original"}, "Perfil",
          (("widescreen", "Pantalla 16:9", True), ("no_interlace", "Sin entrelazado", True),
           ("official_config", "Config. oficial del juego", True), ("progressive", "Modo 480p", False),
           ("no_blur", "Quitar desenfoque", False), ("fps60", "60 FPS", False)),
          (("config_lua", "Parche .lua", [("Lua", "*.lua"), ("Todos", "*")]),
           ("cli_conf", "CLI .conf", [("Conf", "*.conf"), ("Todos", "*")])), True), _ps2_options),
    (Spec("ps1", "PS1", "Discos (.cue o .bin, en orden)", [("PS1 BIN/CUE", "*.cue *.bin"), ("Todos", "*")],
          True, "emulador de un PS1 Classic de PS4", ps1.detect_serial,
          {"Máxima (resolución 6x)": "maxima", "Alta (resolución 4x)": "alta",
           "Rendimiento (resolución 2x)": "rendimiento", "Original (no tocar el emulador)": "original"}, "Perfil",
          (("graphics_menu", "Menú Gráficos en el juego (Lanczos, AA)", True), ("force_60hz", "Forzar 60 Hz (PAL)", False),
           ("analog", "Simular sticks analógicos", False), ("skip_bios_logo", "Saltar logo de PlayStation", False)),
          (("config_lua", "Script .lua", [("Lua", "*.lua"), ("Todos", "*")]),), True), _ps1_options),
    (Spec("psp", "PSP", "Juego (ISO)", [("PSP ISO", "*.iso"), ("Todos", "*")], False, "emulador de un PSP Classic de PS4",
          psp.detect_serial,
          {"Máxima (antialiasing SSAA 4x)": "maxima", "Equilibrado (MSAA 4x)": "equilibrado",
           "Rendimiento (sin antialiasing)": "rendimiento", "Original (no tocar el emulador)": "original"},
          "Perfil", (), (), True, "El icono y el fondo se toman del propio UMD si no eliges otros."), _psp_options),
    (Spec("nes", "NES", "ROM", [("NES", "*.nes *.fds *.unf *.unif *.zip"), ("Todos", "*")], False,
          quality={v: k for k, v in retro.VIDEO_LABELS.items()}, quality_label="Imagen",
          flags=(("show_fps", "Mostrar FPS", False),),
          note="Emulador incluido (Nestopia). El juego arranca directo desde el menú de la PS4."), _retro_options("nes")),
    (Spec("snes", "SNES", "ROM", [("SNES", "*.sfc *.smc *.fig *.swc *.bs *.zip"), ("Todos", "*")], False,
          quality={v: k for k, v in retro.VIDEO_LABELS.items()}, quality_label="Imagen",
          flags=(("audio_sync", "Sonido sincronizado (sin chasquidos)", True), ("show_fps", "Mostrar FPS", False)),
          note="Emulador incluido (Snes9x). El juego arranca directo desde el menú de la PS4."), _retro_options("snes")),
    (Spec("gba", "GBA", "ROM", [("GBA / Game Boy", "*.gba *.gb *.gbc *.zip"), ("Todos", "*")], False,
          quality={v: k for k, v in retro.VIDEO_LABELS.items()}, quality_label="Imagen",
          flags=(("show_fps", "Mostrar FPS", False),),
          note="Emulador incluido (mGBA); también acepta Game Boy y Game Boy Color. "
               "El juego arranca directo desde el menú de la PS4."), _retro_options("gba")),
    (Spec("genesis", "Genesis", "ROM", [("Sega", "*.md *.gen *.smd *.bin *.mdx *.sms *.gg *.sg *.zip"), ("Todos", "*")],
          False, quality={v: k for k, v in retro.VIDEO_LABELS.items()}, quality_label="Imagen",
          flags=(("show_fps", "Mostrar FPS", False),),
          note="Emulador incluido (Genesis Plus GX); también acepta Master System, Game Gear y SG-1000. "
               "El juego arranca directo desde el menú de la PS4."), _retro_options("genesis")),
    (Spec("dc", "Dreamcast", "Juego (GDI, CHD, CDI o CUE)",
          [("Dreamcast", "*.gdi *.chd *.cdi *.cue"), ("Todos", "*")], False,
          quality={v: k for k, v in dreamcast.RESOLUTION_LABELS.items()}, quality_label="Resolución",
          flags=(("widescreen", "Pantalla ancha (juegos con parche 16:9)", True), ("show_fps", "Mostrar FPS", False)),
          extra_files=(("bios", "BIOS dc_boot.bin", [("BIOS de Dreamcast", "dc_boot.bin *.bin"), ("Todos", "*")]),),
          note="Emulador incluido (Resonance, basado en Flycast). En el juego, L3 + R3 abre el menú de "
               "partidas guardadas y ajustes. La BIOS es opcional."), _dc_options),
    (Spec("gc", "GameCube/Wii", "Discos (en orden)",
          [("GameCube / Wii", "*.rvz *.iso *.gcm *.gcz *.ciso *.wia *.wbfs *.tgc *.wad *.dol *.elf"), ("Todos", "*")],
          True, detect=gamecube.detect_serial,
          note="Emulador incluido (DolphinPS4). Los ajustes de imagen de Dolphin ya vienen probados en PS4; "
               "en el juego, L3 + R3 abre el menú (partidas guardadas, ajustes por juego, trucos)."), _gc_options),
]

PS3_NOTE = ("PlayStation 3 no está disponible: todavía no existe un emulador de PS3 que funcione en PS4. "
            "El port de RPCS3 anunciado en octubre de 2026 solo arranca el firmware de la PS3, no juegos. "
            "Si llega a correr juegos, se podrá añadir aquí.")
N64_NOTE = ("Nintendo 64 no está disponible: no existe un emulador de N64 para PS4, ni oficial de Sony "
            "ni homebrew, con el que crear paquetes. Si aparece uno, se podrá añadir aquí.")


def _load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if "emu_dir" in data and "emu_dir_ps2" not in data:  # ajustes de la versión anterior
        data["emu_dir_ps2"] = data["emu_dir"]
    return data


def _save_settings(data):
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


class SystemTab(ttk.Frame):
    def __init__(self, parent, app, spec, make_options):
        super().__init__(parent, padding=10)
        self.app, self.spec, self.make_options = app, spec, make_options
        self.vars = {k: tk.StringVar() for k in ("title", "serial", "emu_dir", "icon", "background", "single", "cover")}
        self.preview_image = None
        self.vars["emu_dir"].set(app.settings.get(f"emu_dir_{spec.key}", ""))
        for key, _text, _types in spec.extra_files:
            self.vars[key] = tk.StringVar()
        self.quality = tk.StringVar(value=next(iter(spec.quality), ""))
        self.flags = {key: tk.BooleanVar(value=default) for key, _t, default in spec.flags}
        self.columnconfigure(1, weight=1)
        self._build()

    def _field(self, row, label, key, browse=None, parent=None):
        parent = parent or self
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", pady=2)
        if browse:
            ttk.Button(parent, text="…", width=3, command=browse).grid(row=row, column=2, padx=(6, 0))

    def _build(self):
        s, row = self.spec, 0
        if s.multi:
            ttk.Label(self, text=s.files_label).grid(row=row, column=0, sticky="nw", pady=2)
            box = ttk.Frame(self)
            box.grid(row=row, column=1, columnspan=3, sticky="ew")
            box.columnconfigure(0, weight=1)
            self.listbox = tk.Listbox(box, height=3)
            self.listbox.grid(row=0, column=0, rowspan=4, sticky="nsew")
            for i, (text, cmd) in enumerate((("Agregar…", self._add), ("Quitar", self._remove),
                                             ("Subir", lambda: self._move(-1)), ("Bajar", lambda: self._move(1)))):
                ttk.Button(box, text=text, command=cmd).grid(row=i, column=1, sticky="ew", padx=(6, 0))
        else:
            self._field(row, s.files_label, "single", self._pick_single)
        row += 1
        first_row = row
        self._field(row, "Nombre del juego", "title")
        row += 1
        if s.detect:
            self._field(row, "Serial (auto)", "serial")
            row += 1
        if s.emu_label:
            # El emulador se configura una sola vez (carpeta emuladores/<consola> junto a la app):
            # aquí solo se muestra si está listo, sin pedirlo en cada conversión.
            ttk.Label(self, text="Emulador").grid(row=row, column=0, sticky="w", pady=2)
            self.emu_status = ttk.Label(self, text="")
            self.emu_status.grid(row=row, column=1, sticky="w", pady=2)
            buttons = ttk.Frame(self)
            buttons.grid(row=row, column=2, columnspan=2, sticky="w", padx=(6, 0))
            ttk.Button(buttons, text="Traer de mi PS4", command=self._fetch_emu).grid(row=0, column=0)
            ttk.Button(buttons, text="Abrir carpeta", command=self._open_emu_dir).grid(row=0, column=1, padx=(4, 0))
            ttk.Button(buttons, text="Importar…", command=self._import_emu).grid(row=0, column=2, padx=(4, 0))
            self.refresh_emu()
            row += 1
        self._field(row, "Carátula", "cover", lambda: self._pick_file("cover", IMAGES))
        ttk.Button(self, text="Buscar", command=self.search_cover).grid(row=row, column=3, padx=(6, 0))
        row += 1
        self._field(row, "Icono propio (opcional)", "icon", lambda: self._pick_file("icon", IMAGES))
        row += 1
        self._field(row, "Fondo propio (opcional)", "background", lambda: self._pick_file("background", IMAGES))
        row += 1
        self.preview = ttk.Label(self, anchor="center", text="Sin carátula", width=16)
        self.preview.grid(row=first_row, column=4, rowspan=row - first_row, padx=(10, 0), sticky="n")
        self.vars["cover"].trace_add("write", lambda *_: self._show_preview())

        q = ttk.LabelFrame(self, text="Calidad de imagen y sonido", padding=8)
        if s.quality or s.flags or s.extra_files or s.emu_args:
            q.grid(row=row, column=0, columnspan=5, sticky="ew", pady=(8, 2))
        q.columnconfigure(1, weight=1)
        if s.quality:
            ttk.Label(q, text=s.quality_label).grid(row=0, column=0, sticky="w")
            ttk.Combobox(q, textvariable=self.quality, values=list(s.quality), state="readonly"
                         ).grid(row=0, column=1, columnspan=2, sticky="ew", pady=2)
        if s.flags:
            checks = ttk.Frame(q)
            checks.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
            for i, (key, text, _d) in enumerate(s.flags):
                ttk.Checkbutton(checks, text=text, variable=self.flags[key]).grid(
                    row=i // 3, column=i % 3, sticky="w", padx=(0, 14))
        qrow = 2
        for key, text, types in s.extra_files:
            self._field(qrow, f"{text} (opcional)", key, lambda k=key, t=types: self._pick_file(k, t), parent=q)
            qrow += 1
        if s.emu_args:
            ttk.Label(q, text="Args. extra (uno por línea)").grid(row=qrow, column=0, sticky="nw", pady=2)
            self.emu_args = tk.Text(q, height=2, width=40)
            self.emu_args.grid(row=qrow, column=1, columnspan=2, sticky="ew", pady=2)
        row += 1
        if s.note:
            ttk.Label(self, text=s.note, foreground="#555", wraplength=820, justify="left").grid(row=row, column=0, columnspan=5, sticky="w", pady=(6, 0))
        if s.key == "psp":
            alt = ttk.LabelFrame(self, text="Alternativa sin el emulador de Sony: M33 (PPSSPP para PS4)", padding=8)
            alt.grid(row=row + 1, column=0, columnspan=5, sticky="ew", pady=(8, 0))
            ttk.Label(alt, wraplength=800, justify="left", text=(
                "M33 se instala una vez como app en la PS4 y los juegos se le envían por red: aparecen en su "
                "lista (no como iconos sueltos). Necesita la IP de la PS4 y el FTP de GoldHEN activado.")
                      ).grid(row=0, column=0, columnspan=3, sticky="w")
            ttk.Button(alt, text="1. Instalar M33 en la PS4", command=self._install_m33).grid(
                row=1, column=0, sticky="w", pady=(6, 0))
            ttk.Button(alt, text="2. Enviar este juego a M33", command=self._send_m33).grid(
                row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))

    # --- Selección de archivos -----------------------------------------
    def _pick_dir(self, key):
        path = filedialog.askdirectory(initialdir=self.vars[key].get() or None)
        if path:
            self.vars[key].set(path)

    # --- Emulador (se configura una vez) --------------------------------
    def emu_base(self):
        """Carpeta del emulador a usar (la elegida o la encontrada sola), o None."""
        chosen = self.vars["emu_dir"].get().strip()
        if chosen:
            try:
                return emu.locate(chosen)
            except emu.EmuError:
                pass
        return emu.find_base(self.spec.key)

    def refresh_emu(self):
        base = self.emu_base()
        if base:
            try:
                shown = os.path.relpath(base, emu.app_dir())
            except ValueError:  # otra unidad en Windows
                shown = base
            if shown.startswith(".."):
                shown = base
            if len(shown) > 50:
                shown = "…" + shown[-49:]
            self.emu_status.configure(text=f"✓ Listo ({shown})", foreground="#1a7f37")
        else:
            self.emu_status.configure(text="Falta: usa «Traer de mi PS4» (una sola vez)", foreground="#b42318")

    def _open_emu_dir(self):
        folder = emu.default_base_dirs(self.spec.key)[0]
        os.makedirs(folder, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # noqa: S606 — abre el Explorador de Windows
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", folder])
        except OSError:
            messagebox.showinfo("Carpeta del emulador", folder)
        messagebox.showinfo("Emulador", f"Copia en esta carpeta, una sola vez, el contenido del {self.spec.emu_label} "
                                        f"(la carpeta que tiene eboot.bin):\n{folder}\n\nDespués la app lo usará sola.")
        self.refresh_emu()

    def _fetch_emu(self):
        """Copia el emulador desde la PS4 por el FTP de GoldHEN (ps4ftp.py)."""
        name = emu.SYSTEM_NAMES[self.spec.key]
        if not messagebox.askokcancel(
                "Traer el emulador de tu PS4",
                f"En la PS4:\n"
                f"1. Activa el FTP de GoldHEN (Ajustes → GoldHEN → Servidor FTP).\n"
                f"2. Abre un clásico de {name} que tengas instalado y déjalo abierto.\n\n"
                f"La app copiará su emulador (sin el juego) a la carpeta emuladores\\{self.spec.key}. "
                "Tarda uno o dos minutos. ¿Continuar?"):
            return
        ip = self.app.vars["ps4_ip"].get().strip() or (simpledialog.askstring(
            "IP de la PS4", "IP de la PS4 (Ajustes → Red → Ver estado de la conexión):") or "").strip()
        if not ip:
            return
        self.app.vars["ps4_ip"].set(ip)
        self.app.remember()

        def work():
            try:
                system, dest = ps4ftp.fetch(ip, self.spec.key, log=self.app.log_threadsafe)
                for tab in self.app.tabs:
                    if tab.spec.key == system:
                        self.app.events.put(("call", tab.refresh_emu))
                self.app.events.put(("done", f"Emulador de {emu.SYSTEM_NAMES[system]} listo:\n{dest}\n\n"
                                             "Ya puedes cerrar el juego en la PS4."))
            except Exception as e:  # noqa: BLE001 — se muestra al usuario
                self.app.events.put(("error", str(e)))

        self.app._run_in_background(work)

    def _ps4_ip(self):
        ip = self.app.vars["ps4_ip"].get().strip() or (simpledialog.askstring(
            "IP de la PS4", "IP de la PS4 (Ajustes → Red → Ver estado de la conexión):") or "").strip()
        if ip:
            self.app.vars["ps4_ip"].set(ip)
            self.app.remember()
        return ip

    def _install_m33(self):
        """Descarga M33 y lo manda a Remote Package Installer (m33.py)."""
        if not messagebox.askokcancel("Instalar M33", "Abre Remote Package Installer en la PS4 (con GoldHEN) "
                                      "y pulsa Aceptar. La app descargará M33 y lo enviará a la consola."):
            return
        ip = self._ps4_ip()
        if not ip:
            return

        def work():
            try:
                pkg = m33.download_pkg(log=self.app.log_threadsafe)
            except Exception as e:  # noqa: BLE001 — se muestra al usuario
                self.app.events.put(("error", f"No se pudo descargar M33: {e}"))
                return
            self.app._send(pkg, ip)

        self.app._run_in_background(work)

    def _send_m33(self):
        """Copia el juego elegido a /data/March33/games de la PS4 por FTP."""
        files = self.files()
        if not files:
            messagebox.showinfo("M33", "Elige el juego primero.")
            return
        ip = self._ps4_ip()
        if not ip:
            return
        title = self.vars["title"].get().strip()

        def progress(done, total):
            self.app.events.put(("progress", done * 100 // max(1, total)))

        def work():
            try:
                m33.send_games(ip, files[:1], [title], log=self.app.log_threadsafe, progress=progress)
                self.app.events.put(("done", "Juego enviado. Abre M33 en la PS4: aparece en su lista de juegos."))
            except Exception as e:  # noqa: BLE001 — se muestra al usuario
                self.app.events.put(("error", f"{e}\nRevisa la IP y que el FTP de GoldHEN esté activado "
                                              "(y abre M33 una vez antes)."))

        self.app._run_in_background(work)

    def _import_emu(self):
        """Instala el emulador desde un archivo del usuario: .exe de otra herramienta que lo lleve
        dentro (p. ej. PSP-FPKG), .pkg de un clásico, .zip o .7z (importer.py)."""
        path = filedialog.askopenfilename(
            title=f"Emulador de {emu.SYSTEM_NAMES[self.spec.key]}: .exe, .pkg, .zip o .7z",
            filetypes=[("Emulador", "*.exe *.pkg *.zip *.7z"), ("Todos", "*")])
        if not path:
            return

        def work():
            try:
                installed = importer.import_all(path, log=self.app.log_threadsafe)
                for tab in self.app.tabs:
                    if tab.spec.key in installed:
                        tab.vars["emu_dir"].set("")
                        self.app.events.put(("call", tab.refresh_emu))
                self.app.events.put(("call", self.app.remember))
                listed = "\n".join(f"{emu.SYSTEM_NAMES[k]}: {v}" for k, v in installed.items())
                self.app.events.put(("done", f"Emulador listo:\n{listed}"))
            except Exception as e:  # noqa: BLE001 — se muestra al usuario
                self.app.events.put(("error", str(e)))

        self.app._run_in_background(work)

    def _pick_file(self, key, types):
        path = filedialog.askopenfilename(filetypes=types)
        if path:
            self.vars[key].set(path)

    def _pick_single(self):
        path = filedialog.askopenfilename(filetypes=self.spec.file_types)
        if path:
            self.vars["single"].set(path)
            self._autodetect(path)

    def _add(self):
        paths = filedialog.askopenfilenames(filetypes=self.spec.file_types)
        for p in paths:
            self.listbox.insert("end", p)
        if paths and self.listbox.size() == len(paths):
            self._autodetect(paths[0])

    def _remove(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)

    def _move(self, delta):
        sel = self.listbox.curselection()
        if not sel:
            return
        i, j = sel[0], sel[0] + delta
        if 0 <= j < self.listbox.size():
            text = self.listbox.get(i)
            self.listbox.delete(i)
            self.listbox.insert(j, text)
            self.listbox.selection_set(j)

    def _autodetect(self, path):
        if not self.vars["title"].get():
            if self.spec.key == "psp":
                try:
                    self.vars["title"].set(psp.read_info(path)[1])
                except Exception:  # noqa: BLE001 — el título es opcional
                    pass
            if not self.vars["title"].get():
                title = {"dc": dreamcast.default_title, "gc": gamecube.default_title}.get(
                    self.spec.key, retro.clean_title)(path)
                self.vars["title"].set(title)
        if self.spec.detect:
            try:
                serial = self.spec.detect(path)
            except Exception as e:  # noqa: BLE001 — se muestra al usuario
                self.app.append(f"No se pudo leer el serial de {os.path.basename(path)}: {e}")
                serial = None
            if serial:
                self.vars["serial"].set(serial)
                self.app.append(f"Serial detectado: {serial}")
        if not self.vars["cover"].get():
            self.search_cover(quiet=True)

    # --- Carátula -------------------------------------------------------
    def search_cover(self, quiet=False):
        """Busca la carátula en segundo plano (por serial y por nombre)."""
        files = self.files()
        names = [os.path.basename(files[0])] if files else []
        names.append(self.vars["title"].get().strip())
        serial = self.vars["serial"].get().strip().upper()
        if not any(names) and not serial:
            if not quiet:
                messagebox.showinfo("Carátula", "Elige el juego o escribe su nombre primero.")
            return
        self.app.append("Buscando carátula...")

        def work():
            try:
                path = covers.find(self.spec.key, serial, [n for n in names if n], log=self.app.log_threadsafe)
            except OSError as e:
                self.app.log_threadsafe(f"Carátula: no se pudo buscar ({e}).")
                path = None
            if path:
                self.app.events.put(("call", lambda: self.vars["cover"].set(path)))

        threading.Thread(target=work, daemon=True).start()

    def _show_preview(self):
        path = self.vars["cover"].get().strip()
        if not path or not os.path.isfile(path):
            self.preview.configure(image="", text="Sin carátula")
            return
        if images.Image is None:
            self.preview.configure(image="", text="(instala Pillow\npara la vista previa)")
            return
        try:
            from PIL import ImageTk
            img = images.Image.open(path)
            img.thumbnail((150, 190))
            self.preview_image = ImageTk.PhotoImage(img)
            self.preview.configure(image=self.preview_image, text="")
        except Exception:  # noqa: BLE001 — una imagen inválida no debe romper la ventana
            self.preview.configure(image="", text="Imagen no válida")

    # --- Opciones ------------------------------------------------------
    def files(self):
        if self.spec.multi:
            return list(self.listbox.get(0, "end"))
        single = self.vars["single"].get().strip()
        return [single] if single else []

    def options(self, shared):
        files = self.files()
        if not files:
            raise ValueError("Elige el juego primero.")
        v = {k: var.get().strip() for k, var in self.vars.items()}
        if self.spec.emu_label:
            base = self.emu_base()
            if base is None:
                self.refresh_emu()
                raise ValueError(f"Falta el emulador. Usa «Traer de mi PS4» con un clásico de "
                                 f"{emu.SYSTEM_NAMES[self.spec.key]} abierto en la PS4, o copia el "
                                 f"{self.spec.emu_label} (la carpeta con eboot.bin) en:\n"
                                 f"{emu.default_base_dirs(self.spec.key)[0]}")
            v["emu_dir"] = base
        v.update(shared)
        v["output_dir"] = shared["output_dir"] or os.path.dirname(files[0])
        args = []
        if self.spec.emu_args:
            args = [ln.strip() for ln in self.emu_args.get("1.0", "end").splitlines() if ln.strip()]
        flags = {key: var.get() for key, var in self.flags.items()}
        return self.make_options(v, files, flags, self.spec.quality.get(self.quality.get()), args)


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=10)
        self.root = root
        self.events = queue.Queue()
        self.worker = None
        self.server = None
        self.settings = _load_settings()
        emu.prepare_default_dirs()
        self.vars = {name: tk.StringVar(value=self.settings.get(name, "")) for name in SHARED}
        self.gp4_only = tk.BooleanVar(value=False)
        self.send_after = tk.BooleanVar(value=False)
        self._build_ui()
        self.after(100, self._poll)

    def _build_ui(self):
        self.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.tabs = []
        for spec, make in SPECS:
            tab = SystemTab(self.notebook, self, spec, make)
            self.notebook.add(tab, text=f"  {spec.tab}  ")
            self.tabs.append(tab)
        for name, note in (("N64", N64_NOTE), ("PS3", PS3_NOTE)):
            frame = ttk.Frame(self.notebook, padding=20)
            ttk.Label(frame, text=note, wraplength=560, justify="left").grid(sticky="w")
            self.notebook.add(frame, text=f"  {name}  ")
        last = self.settings.get("tab")
        for i, tab in enumerate(self.tabs):
            if tab.spec.key == last:
                self.notebook.select(i)

        k = ttk.LabelFrame(self, text="Empaquetado e instalación (GoldHEN)", padding=8)
        k.grid(row=1, column=0, sticky="ew", pady=(8, 2))
        k.columnconfigure(1, weight=1)
        for row, (label, key, browse) in enumerate((
            ("Carpeta de salida", "output_dir", lambda: self._pick_dir("output_dir")),
            ("PkgTool (auto)", "pkgtool", lambda: self._pick_file("pkgtool")),
            ("IP de la PS4", "ps4_ip", None),
        )):
            ttk.Label(k, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(k, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", pady=2)
            if browse:
                ttk.Button(k, text="…", width=3, command=browse).grid(row=row, column=2, padx=(6, 0))
        opts = ttk.Frame(k)
        opts.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Checkbutton(opts, text="Enviar a la PS4 al terminar", variable=self.send_after).grid(row=0, column=0, padx=(0, 14))
        ttk.Checkbutton(opts, text="Solo preparar el proyecto .gp4", variable=self.gp4_only).grid(row=0, column=1, padx=(0, 14))
        ttk.Button(opts, text="Enviar un PKG existente…", command=self._send_existing).grid(row=0, column=2)

        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, sticky="ew", pady=(8, 4))
        actions.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(actions, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.build_btn = ttk.Button(actions, text="Crear fPKG", command=self._start)
        self.build_btn.grid(row=0, column=1, padx=(8, 0))

        self.log = tk.Text(self, height=9, state="disabled", wrap="word")
        self.log.grid(row=3, column=0, sticky="nsew")
        self.rowconfigure(3, weight=1)

    def _pick_dir(self, key):
        path = filedialog.askdirectory(initialdir=self.vars[key].get() or None)
        if path:
            self.vars[key].set(path)

    def _pick_file(self, key):
        path = filedialog.askopenfilename(filetypes=[("PkgTool", "PkgTool*"), ("Todos", "*")])
        if path:
            self.vars[key].set(path)

    def _current_tab(self):
        index = self.notebook.index(self.notebook.select())
        return self.tabs[index] if index < len(self.tabs) else None

    def remember(self, tab=None):
        data = dict(self.settings)
        data.update({k: self.vars[k].get().strip() for k in SHARED})
        for t in self.tabs:
            if t.spec.emu_label:
                data[f"emu_dir_{t.spec.key}"] = t.vars["emu_dir"].get().strip()
        if tab:
            data["tab"] = tab.spec.key
        self.settings = data
        _save_settings(data)

    # --- Ejecución ------------------------------------------------------
    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        tab = self._current_tab()
        if tab is None:
            messagebox.showinfo("No disponible", N64_NOTE)
            return
        shared = {k: v.get().strip() for k, v in self.vars.items()}
        shared["gp4_only"] = self.gp4_only.get()
        if self.send_after.get() and not shared["ps4_ip"]:
            messagebox.showwarning("Falta la IP", "Escribe la IP de la PS4 para enviarle el juego.")
            return
        try:
            module, opts = tab.options(shared)
        except ValueError as e:
            messagebox.showwarning("Faltan datos", str(e))
            return
        self.remember(tab)
        send_to = shared["ps4_ip"] if self.send_after.get() and not self.gp4_only.get() else ""
        self._run_in_background(self._build, module, opts, send_to)

    def _send_existing(self):
        ip = self.vars["ps4_ip"].get().strip()
        if not ip:
            messagebox.showwarning("Falta la IP", "Escribe la IP de la PS4 (Remote Package Installer abierto).")
            return
        pkg = filedialog.askopenfilename(filetypes=[("Paquetes PS4", "*.pkg"), ("Todos", "*")])
        if pkg:
            self.remember()
            self._run_in_background(self._send, pkg, ip)

    def _run_in_background(self, target, *args):
        if self.worker and self.worker.is_alive():
            return
        self.build_btn.state(["disabled"])
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.worker = threading.Thread(target=target, args=args, daemon=True)
        self.worker.start()

    def _log(self, msg):
        self.events.put(("log", msg))

    log_threadsafe = _log

    def _build(self, module, opts, send_to):
        def progress(done, total):
            self.events.put(("progress", done * 100 // max(1, total)))

        try:
            result = module.build(opts, log=self._log, progress=progress)
            if send_to:
                self._send(result, send_to)
                return
            self.events.put(("done", f"Archivo creado:\n{result}"))
        except Exception as e:  # noqa: BLE001 — se muestra al usuario
            self.events.put(("error", str(e)))

    def _send(self, pkg, ip):
        try:
            if self.server:
                self.server.shutdown()
                self.server.server_close()
            self.server, urls = install.serve([pkg], ps4_ip=ip, log=self._log)
            url = next(iter(urls.values()))
            self._log(f"Sirviendo {url}")
            answer = install.send_to_ps4(ip, [url])
            self.events.put(("done", f"La PS4 está descargando «{answer.get('title', '')}».\n"
                                     "Deja esta ventana abierta hasta que termine la instalación."))
        except Exception as e:  # noqa: BLE001 — se muestra al usuario
            self.events.put(("error", f"No se pudo enviar a la PS4 ({ip}): {e}\n"
                                      "Comprueba que Remote Package Installer esté abierto en la PS4 "
                                      "y que el firewall permita conexiones a esta app."))

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self.append(data)
                elif kind == "call":
                    data()
                elif kind == "progress":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=data)
                else:
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=100 if kind == "done" else 0)
                    self.build_btn.state(["!disabled"])
                    if kind == "done":
                        self.append(data)
                        messagebox.showinfo("Listo", data)
                    else:
                        self.append(f"Error: {data}")
                        messagebox.showerror("Error", data)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main():
    root = tk.Tk()
    root.title(f"PS Classics → fPKG PS4  v{__version__}")
    root.minsize(760, 780)
    App(root)
    root.mainloop()
