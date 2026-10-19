"""Instalación por red en la PS4: sirve los PKG por HTTP y pide la instalación a
Remote Package Installer (app de la PS4 con GoldHEN, puerto 12800).

La PS4 descarga el PKG en varias conexiones con peticiones por rangos (Range), así que el
servidor atiende cada conexión en su propio hilo y responde 206 Partial Content.
"""

import http.server
import json
import os
import re
import socket
import socketserver
import threading
import urllib.parse
import urllib.request

RPI_PORT = 12800
CHUNK = 1024 * 1024
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


class PkgHandler(http.server.BaseHTTPRequestHandler):
    """Sirve solo los archivos .pkg registrados (nada más del disco queda expuesto)."""

    protocol_version = "HTTP/1.1"
    files = {}  # nombre -> ruta
    log = staticmethod(lambda msg: None)

    def do_HEAD(self):
        self._serve(body=False)

    def do_GET(self):
        self._serve(body=True)

    def _serve(self, body):
        name = urllib.parse.unquote(self.path.split("?")[0].lstrip("/"))
        path = self.files.get(name)
        if path is None:
            self.send_error(404)
            return
        size = os.path.getsize(path)
        start, end = 0, size - 1
        header = self.headers.get("Range")
        if header:
            m = RANGE_RE.match(header.strip())
            if not m or (not m.group(1) and not m.group(2)):
                self._unsatisfiable(size)
                return
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:  # sufijo: los últimos N bytes
                start = max(0, size - int(m.group(2)))
            if start > end or start >= size:
                self._unsatisfiable(size)
                return
        length = end - start + 1
        self.send_response(206 if header else 200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not body:
            return
        if not header:
            self.log(f"La PS4 empezó a descargar {name}")
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining:
                data = f.read(min(CHUNK, remaining))
                if not data:
                    break
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(data)

    def _unsatisfiable(self, size):
        self.send_response(416)
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def local_ip(target="192.168.0.1"):
    """IP de esta PC en la red local (la ruta hacia `target`; no envía nada)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect((target, 9))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def serve(pkgs, port=8000, host_ip="", ps4_ip="", log=print):
    """Inicia el servidor en segundo plano. Devuelve (servidor, {nombre: url})."""
    handler = type("Handler", (PkgHandler,), {"files": {os.path.basename(p): os.path.abspath(p) for p in pkgs},
                                              "log": staticmethod(log)})
    server = Server(("0.0.0.0", port), handler)
    ip = host_ip or local_ip(ps4_ip or "192.168.0.1")
    urls = {name: f"http://{ip}:{server.server_address[1]}/{urllib.parse.quote(name)}" for name in handler.files}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, urls


def send_to_ps4(ps4_ip, urls, timeout=15, port=RPI_PORT):
    """Pide a Remote Package Installer que descargue e instale los PKG. Devuelve su respuesta."""
    body = json.dumps({"type": "direct", "packages": list(urls)}).encode("utf-8")
    req = urllib.request.Request(f"http://{ps4_ip}:{port}/api/install", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", "replace")
    try:
        answer = json.loads(text)
    except ValueError:
        answer = {"status": "?", "raw": text}
    if answer.get("status") != "success":
        raise RuntimeError(f"La PS4 rechazó la instalación: {text}")
    return answer
