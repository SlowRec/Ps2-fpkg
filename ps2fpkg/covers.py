"""Búsqueda de carátulas: por serial (PS1/PS2, colecciones de xlenore que usan PCSX2 y
DuckStation; GameCube/Wii, GameTDB como Dolphin) y por nombre en las carátulas de libretro
(todas las consolas)."""

import difflib
import os
import re
import urllib.parse

from . import db

LIBRETRO = "https://thumbnails.libretro.com/{system}/Named_Boxarts/"
LIBRETRO_SYSTEMS = {
    "nes": "Nintendo - Nintendo Entertainment System",
    "snes": "Nintendo - Super Nintendo Entertainment System",
    "gba": "Nintendo - Game Boy Advance",
    "gb": "Nintendo - Game Boy",
    "gbc": "Nintendo - Game Boy Color",
    "dc": "Sega - Dreamcast",
    "genesis": "Sega - Mega Drive - Genesis",
    "sms": "Sega - Master System - Mark III",
    "gg": "Sega - Game Gear",
    "sg1000": "Sega - SG-1000",
    "gc": "Nintendo - GameCube",
    "wii": "Nintendo - Wii",
    "ps1": "Sony - PlayStation",
    "ps2": "Sony - PlayStation 2",
    "psp": "Sony - PlayStation Portable",
}
SERIAL_COVERS = {
    "ps2": "https://raw.githubusercontent.com/xlenore/ps2-covers/main/covers/default/{serial}.jpg",
    "ps1": "https://raw.githubusercontent.com/xlenore/psx-covers/main/covers/default/{serial}.jpg",
    "gc": "https://art.gametdb.com/wii/cover/{region}/{serial}.png",
    "wii": "https://art.gametdb.com/wii/cover/{region}/{serial}.png",
}
# Región de GameTDB según la 4.ª letra del ID de GameCube/Wii (GALE01 -> E -> US).
GAMETDB_REGIONS = {"E": "US", "N": "US", "J": "JA", "K": "KO", "W": "ZH", "D": "DE", "F": "FR", "S": "ES",
                   "I": "IT", "H": "NL", "U": "AU"}
INDEX_MAX_AGE = 7 * 24 * 3600
REGION_ORDER = ("usa", "world", "europe", "spain", "japan")
BAD_TAGS = ("beta", "proto", "demo", "sample", "kiosk", "pirate", "unl", "hack")


def base_name(name):
    """'Super Mario World (USA) [!].sfc' -> 'super mario world'. Quita etiquetas, extensión y signos."""
    name = os.path.splitext(name)[0] if re.search(r"\.[A-Za-z0-9]{2,4}$", name) else name
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)
    name = name.lower().replace("&", " and ")
    m = re.match(r"^(.*), (the|a|an)$", name.strip())  # 'Legend of Zelda, The' -> 'the legend of zelda'
    if m:
        name = f"{m.group(2)} {m.group(1)}"
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name).split())


def tags(name):
    return {t.strip().lower() for group in re.findall(r"\(([^)]*)\)", name) for t in group.split(",")}


def _rank(candidate, wanted_tags):
    """Menor es mejor: comparte etiquetas con la búsqueda, región preferida, sin betas/demos."""
    t = tags(candidate)
    bad = any(any(b in x for b in BAD_TAGS) for x in t)
    region = min((REGION_ORDER.index(r) for r in REGION_ORDER if r in t), default=len(REGION_ORDER))
    return (bad, -len(t & wanted_tags), region, len(candidate))


ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}


def _numbers(base):
    """Números de un nombre (también romanos): distinguen secuelas."""
    return {ROMAN.get(w, w) for w in base.split() if w.isdigit() or w in ROMAN}


def best_match(query, names, cutoff=0.86):
    """Nombre del índice que mejor corresponde a `query` (nombre de archivo o título), o None."""
    wanted = base_name(query)
    if not wanted:
        return None
    by_base = {}
    for n in names:
        by_base.setdefault(base_name(n), []).append(n)
    if wanted not in by_base:
        words = set(wanted.split())
        # 1) Todas las palabras buscadas aparecen en el nombre ('Jak and Daxter' ->
        #    'Jak and Daxter - The Precursor Legacy'): el que menos palabras añade.
        containing = [b for b in by_base if words <= set(b.split())] if len(words) >= 2 else []
        if containing:
            wanted = min(containing, key=lambda b: (len(b.split()) - len(words),
                                                    min(_rank(n, tags(query)) for n in by_base[b]), b))
        else:
            # 2) Nombre muy parecido, pero con los mismos números (no confundir secuelas).
            same_numbers = [b for b in by_base if _numbers(b) == _numbers(wanted)]
            close = difflib.get_close_matches(wanted, same_numbers, n=1, cutoff=cutoff)
            if not close:
                return None
            wanted = close[0]
    return min(by_base[wanted], key=lambda n: _rank(n, tags(query)))


def libretro_index(system):
    """Nombres (sin .png) de las carátulas de libretro para la consola."""
    html = db._fetch(LIBRETRO.format(system=urllib.parse.quote(LIBRETRO_SYSTEMS[system])),
                     os.path.join("covers", f"{system}-index.html"), timeout=60, max_age=INDEX_MAX_AGE)
    if not html:
        return []
    hrefs = re.findall(r'href="([^"?/]+)\.png"', html.decode("utf-8", "replace"))
    return [urllib.parse.unquote(h) for h in hrefs]


def _save(data, name):
    path = os.path.join(db.CACHE_DIR, "covers", "img", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def find(system, serial="", names=(), log=print):
    """Descarga la carátula y devuelve su ruta local, o None. `names`: nombres a probar
    (nombre del archivo del juego, título…), del más fiable al menos."""
    if serial and system in SERIAL_COVERS:
        url = SERIAL_COVERS[system].format(serial=serial, region=GAMETDB_REGIONS.get(serial[3:4], "EN"))
        name = serial + os.path.splitext(url)[1]
        data = db._fetch(url, os.path.join("covers", "serial", name))
        if data:
            log(f"Carátula: encontrada por serial ({serial}).")
            return _save(data, name)
    if system not in LIBRETRO_SYSTEMS:
        return None
    index = libretro_index(system)
    for name in names:
        match = best_match(name, index) if name else None
        if match:
            url = LIBRETRO.format(system=urllib.parse.quote(LIBRETRO_SYSTEMS[system])) + urllib.parse.quote(match) + ".png"
            data = db._fetch(url, os.path.join("covers", system, match + ".png"), timeout=60)
            if data:
                log(f"Carátula: «{match}».")
                return _save(data, f"{system}-{re.sub(r'[^A-Za-z0-9]+', '_', match)}.png")
    log("Carátula: no se encontró; usa una imagen propia.")
    return None


def resolve(opts, system, serial="", names=(), log=print):
    """Carátula a usar: la indicada, o la buscada si opts.find_cover. Nunca hace fallar la conversión."""
    if opts.cover or not opts.find_cover:
        return opts.cover
    try:
        return find(system, serial, names, log) or ""
    except OSError as e:
        log(f"Carátula: no se pudo buscar ({e}).")
        return ""
