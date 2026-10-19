"""Generación del proyecto GP4 que consumen PkgTool (LibOrbisPkg) y orbis-pub-cmd."""

import datetime
import xml.etree.ElementTree as ET


def build(content_id, files, passcode="0" * 32):
    """files: dict ruta_en_pkg ('image/disc01.iso') -> ruta en disco (absoluta)."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    root = ET.Element("psproject", fmt="gp4", version="1000")

    volume = ET.SubElement(root, "volume")
    ET.SubElement(volume, "volume_type").text = "pkg_ps4_app"
    ET.SubElement(volume, "volume_id").text = "PS4VOLUME"
    ET.SubElement(volume, "volume_ts").text = now
    ET.SubElement(volume, "package", content_id=content_id, passcode=passcode,
                  storage_type="digital50", app_type="full")
    chunk_info = ET.SubElement(volume, "chunk_info", chunk_count="1", scenario_count="1")
    chunks = ET.SubElement(chunk_info, "chunks")
    ET.SubElement(chunks, "chunk", id="0", layer_no="0", label="Chunk #0")
    scenarios = ET.SubElement(chunk_info, "scenarios", default_id="0")
    ET.SubElement(scenarios, "scenario", id="0", type="sp", initial_chunk_count="1",
                  label="Scenario #0").text = "0"

    files_el = ET.SubElement(root, "files", img_no="0")
    for target in sorted(files):
        ET.SubElement(files_el, "file", targ_path=target, orig_path=files[target])

    # Árbol de directorios: cada carpeta usada por algún archivo debe declararse.
    tree = {}
    for target in files:
        node = tree
        for part in target.split("/")[:-1]:
            node = node.setdefault(part, {})
    rootdir = ET.SubElement(root, "rootdir")

    def add_dirs(parent, node):
        for name in sorted(node):
            add_dirs(ET.SubElement(parent, "dir", targ_name=name), node[name])

    add_dirs(rootdir, tree)

    ET.indent(root)
    return b'<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n' + ET.tostring(root, encoding="utf-8")
