"""Ventana sencilla (tkinter) sobre el mismo motor que la línea de comandos."""

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, builder

SETTINGS = os.path.join(os.path.expanduser("~"), ".ps2fpkg.json")
REMEMBERED = ("emu_dir", "pkgtool", "output_dir")


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
        settings = _load_settings()
        self.vars = {name: tk.StringVar(value=settings.get(name, "")) for name in
                     ("emu_dir", "pkgtool", "output_dir", "title", "serial", "icon", "background",
                      "config_lua", "cli_conf")}
        self.gp4_only = tk.BooleanVar(value=False)
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

        def field(label, key, browse=None):
            nonlocal row
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(self, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", pady=2)
            if browse:
                ttk.Button(self, text="…", width=3, command=browse).grid(row=row, column=2, padx=(6, 0))
            row += 1

        field("Nombre en el menú", "title")
        field("Serial (auto)", "serial")
        field("Emulador base (carpeta)", "emu_dir", lambda: self._pick_dir("emu_dir"))
        field("PkgTool", "pkgtool", lambda: self._pick_file("pkgtool", [("PkgTool", "PkgTool*"), ("Todos", "*")]))
        field("Carpeta de salida", "output_dir", lambda: self._pick_dir("output_dir"))
        images = [("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp"), ("Todos", "*")]
        field("Icono (opcional)", "icon", lambda: self._pick_file("icon", images))
        field("Fondo (opcional)", "background", lambda: self._pick_file("background", images))
        field("Parche .lua (opcional)", "config_lua", lambda: self._pick_file("config_lua", [("Lua", "*.lua"), ("Todos", "*")]))
        field("CLI .conf (opcional)", "cli_conf", lambda: self._pick_file("cli_conf", [("Conf", "*.conf"), ("Todos", "*")]))

        ttk.Label(self, text="Args. extra del emulador\n(uno por línea)").grid(row=row, column=0, sticky="nw", pady=2)
        self.emu_args = tk.Text(self, height=3, width=40)
        self.emu_args.grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)
        row += 1

        ttk.Checkbutton(self, text="Solo preparar el proyecto .gp4 (no crear el PKG)",
                        variable=self.gp4_only).grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        actions = ttk.Frame(self)
        actions.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 4))
        actions.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(actions, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.build_btn = ttk.Button(actions, text="Crear fPKG", command=self._start)
        self.build_btn.grid(row=0, column=1, padx=(8, 0))
        row += 1

        self.log = tk.Text(self, height=12, state="disabled", wrap="word")
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
    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        isos = list(self.iso_list.get(0, "end"))
        v = {k: var.get().strip() for k, var in self.vars.items()}
        if not isos:
            messagebox.showwarning("Falta la ISO", "Agrega al menos un disco.")
            return
        if not v["emu_dir"]:
            messagebox.showwarning("Falta el emulador", "Indica la carpeta del emulador base (PS2 Classic extraído).")
            return
        output = v["output_dir"] or os.path.dirname(isos[0])
        _save_settings({k: v[k] for k in REMEMBERED})

        args = [ln.strip() for ln in self.emu_args.get("1.0", "end").splitlines() if ln.strip()]
        opts = builder.Options(
            isos=isos, emu_dir=v["emu_dir"], output_dir=output, title=v["title"], serial=v["serial"],
            icon=v["icon"], background=v["background"], config_lua=v["config_lua"], cli_conf=v["cli_conf"],
            emu_args=args, pkgtool=v["pkgtool"], gp4_only=self.gp4_only.get(),
        )
        self.build_btn.state(["disabled"])
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.worker = threading.Thread(target=self._run, args=(opts,), daemon=True)
        self.worker.start()

    def _run(self, opts):
        def log(msg):
            self.events.put(("log", msg))

        def progress(done, total):
            self.events.put(("progress", done * 100 // max(1, total)))

        try:
            result = builder.build(opts, log=log, progress=progress)
            self.events.put(("done", result))
        except Exception as e:  # noqa: BLE001 — se muestra al usuario
            self.events.put(("error", str(e)))

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
                        messagebox.showinfo("Listo", f"Archivo creado:\n{data}")
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
    root.minsize(640, 560)
    App(root)
    root.mainloop()
