"""Trae el emulador de un clásico de PS1, PS2 o PSP desde la PS4, por el FTP de GoldHEN.

En la PS4: GoldHEN con el servidor FTP activado (Ajustes de GoldHEN → Servidor FTP, puerto 2121)
y el clásico abierto. Mientras un juego está abierto, sus archivos se ven en
/mnt/sandbox/pfsmnt/<TITLE_ID>-app0/. Los ejecutables (eboot.bin, sce_module/*.prx…) están
cifrados: el comando DECRYPT del FTP de GoldHEN los entrega descifrados (ELF) y aquí se
convierten en fSELF (fself.py) con el PAID y el tipo del original. Los discos del juego no se
copian: solo hace falta el emulador."""

import ftplib
import os
import re
import shutil
import socket

from . import emu, fself

PORT = 2121
PFSMNT = "/mnt/sandbox/pfsmnt"
# Lo que no se copia: los discos del juego original y lo que el paquete no usa.
SKIP_DIRS = ("sce_sys/trophy/", "sce_sys/trophy2/", "image/")
SKIP_FILES = ("sce_sys/keystone",)
DISC_EXT = (".bin", ".cue", ".toc", ".img", ".iso", ".cso", ".ccd", ".sub", ".sbi", ".pbp", ".ecm", ".chd")
LIST_LINE = re.compile(r"^([dl-])\S{9}\s+\d+\s+\S+\s+\S+\s+(\d+)\s+\S+\s+\d+\s+[\d:]+\s+(.+)$")


class Ps4FtpError(Exception):
    pass


def skipped(rel):
    low = rel.lower()
    if low in SKIP_FILES or low.startswith(SKIP_DIRS):
        return True
    return low.startswith("data/") and low.endswith(DISC_EXT)  # disco de PS1/PSP (USER_L0.IMG, discN.bin…)


class Connection:
    def __init__(self, host, port=PORT, timeout=20):
        self.ftp = ftplib.FTP()
        try:
            self.ftp.connect(host, port, timeout=timeout)
            self.ftp.login()
        except (OSError, ftplib.Error) as e:
            raise Ps4FtpError(f"No se pudo conectar al FTP de la PS4 ({host}:{port}): {e}. Revisa la IP y "
                              "que el servidor FTP de GoldHEN esté activado.") from e
        self.ftp.voidcmd("TYPE I")
        self.decrypting = None   # None = no se sabe; el FTP antiguo de GoldHEN siempre descifra

    def close(self):
        try:
            self.ftp.quit()
        except (OSError, ftplib.Error):
            self.ftp.close()

    def listdir(self, path):
        """[(nombre, es_carpeta, tamaño)] de una carpeta (formato de lista de Unix)."""
        lines = []
        self.ftp.retrlines(f"LIST {path}", lines.append)
        out = []
        for line in lines:
            m = LIST_LINE.match(line.rstrip("\r"))
            if m and m.group(3) not in (".", ".."):
                out.append((m.group(3), m.group(1) == "d", int(m.group(2))))
        return out

    def set_decrypt(self, on):
        """Activa o desactiva el descifrado de SELF del servidor (DECRYPT alterna el estado)."""
        for _ in range(2):
            try:
                reply = self.ftp.sendcmd("DECRYPT")
            except ftplib.Error:
                self.decrypting = None
                return False
            self.decrypting = "enabled" in reply.lower()
            if self.decrypting == on:
                return True
        return False

    def read(self, path):
        chunks = []
        self.ftp.retrbinary(f"RETR {path}", chunks.append)
        return b"".join(chunks)


def running_apps(conn):
    """TITLE_ID de los juegos abiertos (montados en /mnt/sandbox/pfsmnt)."""
    try:
        entries = conn.listdir(PFSMNT)
    except ftplib.Error as e:
        raise Ps4FtpError(f"No se pudo leer {PFSMNT} en la PS4: {e}") from e
    return sorted({m.group(1) for name, is_dir, _s in entries if is_dir
                   for m in [re.fullmatch(r"([A-Z]{4}\d{5})-app0", name)] if m})


def detect_system(conn, root):
    """"ps2", "ps1", "psp" o None según los archivos del emulador."""
    names = {n.lower() for n, _d, _s in conn.listdir(root)}
    if "config-emu-ps4.txt" in names:
        return "ps2"
    if "config-title.txt" in names:
        data = {n.lower() for n, _d, _s in conn.listdir(root + "/data")} if "data" in names else set()
        return "psp" if "user_l0.img" in data else "ps1"
    return None


def _walk(conn, root, rel=""):
    for name, is_dir, size in conn.listdir(f"{root}/{rel}" if rel else root):
        child = f"{rel}/{name}" if rel else name
        if skipped(child + ("/" if is_dir else "")):
            continue
        if is_dir:
            yield from _walk(conn, root, child)
        else:
            yield child, size


def fetch(host, system=None, dest_root=None, log=print, port=PORT):
    """Copia el emulador del clásico abierto en la PS4 a emuladores/<consola>/ y devuelve
    (consola, carpeta). `system`: la consola que se espera (si el juego es de otra, se avisa)."""
    conn = Connection(host, port)
    try:
        apps = running_apps(conn)
        found = [(a, detect_system(conn, f"{PFSMNT}/{a}-app0")) for a in apps]
        classics = [(a, s) for a, s in found if s]
        if not classics:
            raise Ps4FtpError("No hay ningún clásico de PS1, PS2 o PSP abierto en la PS4. Abre el juego, "
                              "déjalo en pantalla y vuelve a intentarlo." if not apps else
                              f"El juego abierto ({', '.join(apps)}) no es un clásico de PS1, PS2 ni PSP.")
        title_id, detected = next(((a, s) for a, s in classics if s == system), classics[0])
        if system and detected != system:
            log(f"Aviso: {title_id} es un clásico de {emu.SYSTEM_NAMES[detected]}, no de "
                f"{emu.SYSTEM_NAMES[system]}: se guarda como emulador de {emu.SYSTEM_NAMES[detected]}.")
        root = f"{PFSMNT}/{title_id}-app0"
        dest = os.path.join(dest_root, detected) if dest_root else emu.default_base_dirs(detected)[0]
        tmp = dest + ".descargando"
        shutil.rmtree(tmp, ignore_errors=True)
        files = list(_walk(conn, root))
        total = sum(size for _f, size in files)
        log(f"Copiando el emulador de {emu.SYSTEM_NAMES[detected]} de {title_id} "
            f"({len(files)} archivos, {total / 1024 ** 2:.0f} MB)...")
        conn.set_decrypt(False)
        signed = 0
        for rel, _size in files:
            data = conn.read(f"{root}/{rel}")
            if data[:4] == fself.SELF_MAGIC or (data[:4] == fself.ELF_MAGIC and conn.decrypting is None):
                data = _decrypted_fself(conn, f"{root}/{rel}", data)
                signed += 1
            path = os.path.join(tmp, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        if not os.path.isfile(os.path.join(tmp, "eboot.bin")):
            raise Ps4FtpError("La copia no tiene eboot.bin; vuelve a intentarlo con el juego abierto.")
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.replace(tmp, dest)
        log(f"Listo: emulador de {emu.SYSTEM_NAMES[detected]} guardado en {dest} "
            f"({signed} ejecutables descifrados y firmados como fSELF).")
        return detected, dest
    except (OSError, ftplib.Error, EOFError) as e:
        raise Ps4FtpError(f"Se cortó la copia desde la PS4: {e}") from e
    finally:
        conn.close()


def _decrypted_fself(conn, path, original):
    """El ejecutable descifrado por la PS4, firmado como fSELF con los datos del original."""
    if original[:4] == fself.SELF_MAGIC:
        paid, ptype, app_ver, fw_ver = fself.read_info(original)
        if not conn.set_decrypt(True):
            raise Ps4FtpError("El FTP de la PS4 no puede descifrar los ejecutables. Usa el servidor FTP de "
                              "GoldHEN (actualiza GoldHEN si es antiguo).")
        try:
            elf = conn.read(path)
        finally:
            conn.set_decrypt(False)
    else:  # servidor que siempre descifra: sin los datos del original, valores por defecto
        elf, paid, ptype, app_ver, fw_ver = original, None, None, 0, 0
    if elf[:4] != fself.ELF_MAGIC:
        raise Ps4FtpError(f"{os.path.basename(path)} no llegó descifrado.")
    return fself.make(elf, paid=paid, ptype=ptype, app_version=app_ver, fw_version=fw_ver)


def ps4_reachable(host, port=PORT, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
