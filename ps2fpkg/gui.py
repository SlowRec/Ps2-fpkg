"""Ventana sencilla (tkinter) sobre el mismo motor que la línea de comandos."""

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, builder, install

SETTINGS = os.path.join(os.path.expanduser("~"), ".ps2fpkg.json")
REMEMBERED = ("emu_dir", "pkgtool", "output_dir", "ps4_ip")
QUALITY_LABELS = {
    "Máxima (2x resolución + suavizado)": "maxima",
    "Rendimiento (resolución nativa + suavizado)": "rendimiento",
    "Original (no tocar el emulador)": "original",
}
# (opción de builder.Options, texto, activada por defecto)
PATCH_OPTIONS = (
    ("widescreen", "Pantalla panorámica 16:9", True),
    ("no_interlace", "Sin entrelazado (más nítido)", True),
    ("official_config", "Configuración oficial del juego", True),
    ("progressive", "Modo 480p", False),
    ("no_blur", "Quitar desenfoque", False),
    ("fps60", "60 FPS", False),
)


def _load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_settings(data):
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=12)
        self.root = root
        self.events = queue.Queue()
        self.worker = None
        self.server = None
        settings = _load_settings()
        self.vars = {name: tk.StringVar(value=settings.get(name, "")) for name in
                     ("emu_dir", "pkgtool", "output_dir", "title", "serial", "icon", "background",
                      "config_lua", "cli_conf", "ps4_ip")}
        self.quality = tk.StringVar(value=next(iter(QUALITY_LABELS)))
        self.flags = {key: tk.BooleanVar(value=default) for key, _text, default in PATCH_OPTIONS}
        self.gp4_only = tk.BooleanVar(value=False)
        self.send_after = tk.BooleanVar(value=False)
        self._build_ui()
        self.after(100, self._poll)

    # --- Interfaz -------------------------------------------------------
    def _build_ui(self):
        self.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(self, text="Discos (ISO/BIN, en orden)").grid(row=row, column=0, sticky="nw", pady=2)
        box = ttk.Frame(self)
        box.grid(row=row, column=1, columnspan=2, sticky="ew")
        box.columnconfigure(0, weight=1)
        self.iso_list = tk.Listbox(box, height=4)
        self.iso_list.grid(row=0, column=0, rowspan=4, sticky="nsew")
        for i, (text, cmd) in enumerate((("Agregar…", self._add_iso), ("Quitar", self._remove_iso),
                                         ("Subir", lambda: self._move_iso(-1)), ("Bajar", lambda: self._move_iso(1)))):
            ttk.Button(box, text=text, command=cmd).grid(row=i, column=1, sticky="ew", padx=(6, 0))
        row += 1

        def field(parent, r, label, key, browse=None):
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Entry(parent, textvariable=self.vars[key]).grid(row=r, column=1, sticky="ew", pady=2)
            if browse:
                ttk.Button(parent, text="…", width=3, command=browse).grid(row=r, column=2, padx=(6, 0))

        images = [("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Todos", "*")]
        for label, key, browse in (
            ("Nombre en el menú", "title", None),
            ("Serial (auto)", "serial", None),
            ("Emulador base (carpeta)", "emu_dir", lambda: self._pick_dir("emu_dir")),
            ("Carpeta de salida", "output_dir", lambda: self._pick_dir("output_dir")),
            ("Icono (opcional)", "icon", lambda: self._pick_file("icon", images)),
            ("Fondo (opcional)", "background", lambda: self._pick_file("background", images)),
        ):
            field(self, row, label, key, browse)
            row += 1

        q = ttk.LabelFrame(self, text="Calidad de imagen y sonido", padding=8)
        q.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        q.columnconfigure(1, weight=1)
        ttk.Label(q, text="Perfil").grid(row=0, column=0, sticky="w")
        ttk.Combobox(q, textvariable=self.quality, values=list(QUALITY_LABELS), state="readonly"
                     ).grid(row=0, column=1, columnspan=2, sticky="ew", pady=2)
        checks = ttk.Frame(q)
        checks.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        for i, (key, text, _default) in enumerate(PATCH_OPTIONS):
            ttk.Checkbutton(checks, text=text, variable=self.flags[key]).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 14))
        field(q, 2, "Parche .lua (opcional)", "config_lua",
              lambda: self._pick_file("config_lua", [("Lua", "*.lua"), ("Todos", "*")]))
        field(q, 3, "CLI .conf (opcional)", "cli_conf",
              lambda: self._pick_file("cli_conf", [("Conf", "*.conf"), ("Todos", "*")]))
        ttk.Label(q, text="Args. extra (uno por línea)").grid(row=4, column=0, sticky="nw", pady=2)
        self.emu_args = tk.Text(q, height=2, width=40)
        self.emu_args.grid(row=4, column=1, columnspan=2, sticky="ew", pady=2)
        row += 1

        k = ttk.LabelFrame(self, text="Empaquetado e instalación (GoldHEN)", padding=8)
        k.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        k.columnconfigure(1, weight=1)
        field(k, 0, "PkgTool (auto)", "pkgtool",
              lambda: self._pick_file("pkgtool", [("PkgTool", "PkgTool*"), ("Todos", "*")]))
        field(k, 1, "IP de la PS4", "ps4_ip")
        opts = ttk.Frame(k)
        opts.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Checkbutton(opts, text="Enviar a la PS4 al terminar", variable=self.send_after).grid(row=0, column=0, padx=(0, 14))
        ttk.Checkbutton(opts, text="Solo preparar el proyecto .gp4", variable=self.gp4_only).grid(row=0, column=1, padx=(0, 14))
        ttk.Button(opts, text="Enviar un PKG existente…", command=self._send_existing).grid(row=0, column=2)
        row += 1

        actions = ttk.Frame(self)
        actions.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        actions.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(actions, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.build_btn = ttk.Button(actions, text="Crear fPKG", command=self._start)
        self.build_btn.grid(row=0, column=1, padx=(8, 0))
        row += 1

        self.log = tk.Text(self, height=10, state="disabled", wrap="word")
        self.log.grid(row=row, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(row, weight=1)

    def _pick_dir(self, key):
        path = filedialog.askdirectory(initialdir=self.vars[key].get() or None)
        if path:
            self.vars[key].set(path)

    def _pick_file(self, key, types):
        path = filedialog.askopenfilename(filetypes=types)
        if path:
            self.vars[key].set(path)

    def _add_iso(self):
        paths = filedialog.askopenfilenames(filetypes=[("Imágenes de disco", "*.iso *.bin *.img"), ("Todos", "*")])
        for p in paths:
            self.iso_list.insert("end", p)
        if paths and self.iso_list.size() == len(paths):
            self._autodetect(paths[0])

    def _remove_iso(self):
        for i in reversed(self.iso_list.curselection()):
            self.iso_list.delete(i)

    def _move_iso(self, delta):
        sel = self.iso_list.curselection()
        if not sel:
            return
        i, j = sel[0], sel[0] + delta
        if 0 <= j < self.iso_list.size():
            text = self.iso_list.get(i)
            self.iso_list.delete(i)
            self.iso_list.insert(j, text)
            self.iso_list.selection_set(j)

    def _autodetect(self, path):
        try:
            serial = builder.detect_serial(path)
        except Exception as e:  # noqa: BLE001 — se muestra al usuario
            self._append(f"No se pudo leer el serial de {os.path.basename(path)}: {e}")
            return
        self.vars["serial"].set(serial)
        if not self.vars["title"].get():
            self.vars["title"].set(os.path.splitext(os.path.basename(path))[0])
        self._append(f"Serial detectado: {serial}")

    # --- Ejecución ------------------------------------------------------
    def _values(self):
        return {k: var.get().strip() for k, var in self.vars.items()}

    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        isos = list(self.iso_list.get(0, "end"))
        v = self._values()
        if not isos:
            messagebox.showwarning("Falta la ISO", "Agrega al menos un disco.")
            return
        if not v["emu_dir"]:
            messagebox.showwarning("Falta el emulador", "Indica la carpeta del emulador base (PS2 Classic extraído).")
            return
        if self.send_after.get() and not v["ps4_ip"]:
            messagebox.showwarning("Falta la IP", "Escribe la IP de la PS4 para enviarle el juego.")
            return
        output = v["output_dir"] or os.path.dirname(isos[0])
        _save_settings({k: v[k] for k in REMEMBERED})

        args = [ln.strip() for ln in self.emu_args.get("1.0", "end").splitlines() if ln.strip()]
        opts = builder.Options(
            isos=isos, emu_dir=v["emu_dir"], output_dir=output, title=v["title"], serial=v["serial"],
            icon=v["icon"], background=v["background"], config_lua=v["config_lua"], cli_conf=v["cli_conf"],
            emu_args=args, pkgtool=v["pkgtool"], gp4_only=self.gp4_only.get(),
            quality=QUALITY_LABELS[self.quality.get()],
            **{key: var.get() for key, var in self.flags.items()},
        )
        send_to = v["ps4_ip"] if self.send_after.get() and not self.gp4_only.get() else ""
        self._run_in_background(self._build, opts, send_to)

    def _send_existing(self):
        ip = self._values()["ps4_ip"]
        if not ip:
            messagebox.showwarning("Falta la IP", "Escribe la IP de la PS4 (Remote Package Installer abierto).")
            return
        pkg = filedialog.askopenfilename(filetypes=[("Paquetes PS4", "*.pkg"), ("Todos", "*")])
        if pkg:
            _save_settings({k: self._values()[k] for k in REMEMBERED})
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

    def _build(self, opts, send_to):
        def progress(done, total):
            self.events.put(("progress", done * 100 // max(1, total)))

        try:
            result = builder.build(opts, log=self._log, progress=progress)
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
                    self._append(data)
                elif kind == "progress":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=data)
                else:
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=100 if kind == "done" else 0)
                    self.build_btn.state(["!disabled"])
                    if kind == "done":
                        self._append(data)
                        messagebox.showinfo("Listo", data)
                    else:
                        self._append(f"Error: {data}")
                        messagebox.showerror("Error", data)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main():
    root = tk.Tk()
    root.title(f"PS2 ISO → fPKG PS4  v{__version__}")
    root.minsize(700, 760)
    App(root)
    root.mainloop()
