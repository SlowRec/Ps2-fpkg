"""PSP con M33 (https://github.com/iHaiDeeZ/M33, GPL-2.0): PPSSPP para PS4, sin nada de Sony.

M33 todavía no puede arrancar un juego indicado al abrirlo, así que no se hace un PKG por juego:
se instala M33 una vez en la PS4 (su .pkg publicado, enviado a Remote Package Installer) y los
juegos se copian por el FTP de GoldHEN a /data/March33/games/, donde M33 los muestra en su lista."""

import hashlib
import os
import re
import urllib.request

from . import db, ps4ftp

VERSION = "1.04"
PKG_URL = f"https://github.com/iHaiDeeZ/M33/releases/download/{VERSION}/M33-v{VERSION}.pkg"
PKG_SHA256 = "1c374eaa9cf3a2739fbdb4b6d9cb04cc0c8f6584c227257e81ccf53344927ffb"
DATA_DIR = "/data/March33"
GAMES_DIR = DATA_DIR + "/games"
EXTENSIONS = (".iso", ".cso", ".chd")


class M33Error(Exception):
    pass


def download_pkg(log=print):
    """Ruta local del .pkg de M33 (se descarga una vez y se comprueba su SHA-256)."""
    path = os.path.join(db.CACHE_DIR, f"M33-v{VERSION}.pkg")
    if os.path.isfile(path) and _sha256(path) == PKG_SHA256:
        return path
    os.makedirs(db.CACHE_DIR, exist_ok=True)
    log(f"Descargando M33 v{VERSION} (112 MB)...")
    tmp = path + ".part"
    with urllib.request.urlopen(PKG_URL, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if _sha256(tmp) != PKG_SHA256:
        os.remove(tmp)
        raise M33Error("El .pkg de M33 descargado no es el esperado (SHA-256 distinto).")
    os.replace(tmp, path)
    return path


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def remote_name(path, title=""):
    """Nombre del juego en la PS4: el título (si se da) con la extensión del archivo."""
    ext = os.path.splitext(path)[1].lower()
    base = title.strip() or os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r'[\\/:*?"<>|]+', "_", base).strip(" .") or "juego"
    return base + ext


def send_games(host, paths, titles=None, log=print, progress=None, port=ps4ftp.PORT):
    """Copia los juegos a /data/March33/games/ de la PS4 por el FTP de GoldHEN."""
    for path in paths:
        if not path.lower().endswith(EXTENSIONS):
            raise M33Error(f"{os.path.basename(path)}: M33 acepta {', '.join(EXTENSIONS)}.")
    conn = ps4ftp.Connection(host, port)
    try:
        for d in (DATA_DIR, GAMES_DIR):
            try:
                conn.ftp.mkd(d)
            except Exception:  # noqa: BLE001 — ya existe
                pass
        sent = []
        for n, path in enumerate(paths):
            name = remote_name(path, (titles or [""] * len(paths))[n])
            total = os.path.getsize(path)
            done = 0
            log(f"Enviando {os.path.basename(path)} a M33 ({total / 1024 ** 2:.0f} MB)...")

            def step(chunk):
                nonlocal done
                done += len(chunk)
                if progress:
                    progress(done, total)

            with open(path, "rb") as f:
                conn.ftp.storbinary(f"STOR {GAMES_DIR}/{name}", f, blocksize=1 << 20, callback=step)
            sent.append(f"{GAMES_DIR}/{name}")
            log(f"Listo: {GAMES_DIR}/{name}")
        return sent
    except (OSError, EOFError) as e:
        raise M33Error(f"Se cortó el envío a la PS4: {e}") from e
    except ps4ftp.ftplib.Error as e:
        raise M33Error(f"El FTP de la PS4 rechazó el envío: {e}") from e
    finally:
        conn.close()
