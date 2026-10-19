"""Descarga con caché de datos por juego: parches de PCSX2 y configuraciones oficiales del emulador."""

import os
import time
import urllib.error
import urllib.request

PCSX2_PATCHES = "https://raw.githubusercontent.com/PCSX2/pcsx2_patches/main/patches/{name}"
# Configuraciones de los PS2 Classics oficiales (opciones del emulador por juego).
OFFICIAL_CONFIGS = "https://raw.githubusercontent.com/xXxTheDarkprogramerxXx/Playstation-2-Classics-Patches-PS4/master/{name}"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".ps2fpkg", "cache")
MISSING = b"\x00missing"
MISSING_TTL = 7 * 24 * 3600  # volver a consultar ausencias tras una semana


def _fetch(url, cache_name, timeout=20):
    """Contenido de `url` (bytes) o None si no existe. Cachea también las ausencias."""
    path = os.path.join(CACHE_DIR, cache_name)
    if os.path.isfile(path):
        with open(path, "rb") as f:
            data = f.read()
        if data != MISSING:
            return data
        if time.time() - os.path.getmtime(path) < MISSING_TTL:
            return None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ps2-fpkg"}),
                                    timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        data = None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(MISSING if data is None else data)
    return data


def pcsx2_patch(serial, crc, local_dir=""):
    """Texto del .pnach para esta versión exacta del juego, o None.
    `local_dir` permite usar una carpeta de parches propia (p. ej. la de PCSX2) sin internet."""
    name = f"{serial}_{crc:08X}.pnach"
    if local_dir:
        for candidate in (name, name.lower(), f"{crc:08X}.pnach"):
            path = os.path.join(local_dir, candidate)
            if os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as f:
                    return f.read()
        return None
    data = _fetch(PCSX2_PATCHES.format(name=name), os.path.join("pcsx2", name))
    return data.decode("utf-8", "replace") if data else None


def official_cli_conf(serial):
    """Opciones del emulador que Sony usó para este juego en su versión oficial, o None."""
    name = f"{serial}_cli.conf"
    data = _fetch(OFFICIAL_CONFIGS.format(name=name), os.path.join("official", name))
    return data.decode("utf-8", "replace") if data else None
