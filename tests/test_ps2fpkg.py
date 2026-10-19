import os
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import http.server  # noqa: E402
import json  # noqa: E402
import threading  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from ps2fpkg import builder, db, emu, gp4, images, install, iso, pnach, sfo  # noqa: E402

SYSTEM_CNF = b"BOOT2 = cdrom0:\\SLUS_209.46;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"
BOOT_ELF = b"\x7fELF" + bytes(range(1, 13)) + b"\xaa\xbb\xcc\xdd"
BOOT_CRC = 0x464C457F ^ 0x04030201 ^ 0x08070605 ^ 0x0C0B0A09 ^ 0xDDCCBBAA
PNACH = """gametitle=Juego de prueba [SLUS-20946]

[Widescreen 16:9]
gsaspectratio=16:9
author=alguien
patch=1,EE,202AF750,extended,3f1f3b64 // zoom
patch=0,EE,0012ABCD,extended,000000E0
patch=1,EE,00400002,short,00001234

[No-Interlacing]
patch=1,EE,002B2014,word,24060000

[60 FPS]
patch=1,EE,E0010001,extended,0012ABCD
patch=1,EE,2012ABCC,extended,00000001
"""


def _dir_record(name, lba, size, is_dir=False):
    rec = bytearray(33 + len(name) + (1 - len(name) % 2))
    rec[0] = len(rec)
    struct.pack_into("<I", rec, 2, lba)
    struct.pack_into(">I", rec, 6, lba)
    struct.pack_into("<I", rec, 10, size)
    struct.pack_into(">I", rec, 14, size)
    rec[25] = 2 if is_dir else 0
    rec[32] = len(name)
    rec[33:33 + len(name)] = name
    return bytes(rec)


def make_iso(path, files, raw_mode=None):
    """ISO9660 mínima. Las claves 'DIR/NOMBRE' crean un subdirectorio (un nivel).
    raw_mode=1/2 la guarda como BIN de 2352 bytes/sector."""
    dirs = sorted({k.split("/")[0] for k in files if "/" in k})
    dir_lba = {d: 19 + i for i, d in enumerate(dirs)}
    records = {d: [] for d in ["", *dirs]}
    data_sectors, lba = [], 19 + len(dirs)
    for key, content in files.items():
        parent, _, name = key.rpartition("/")
        records[parent].append(_dir_record(name.encode() + b";1", lba, len(content)))
        n = max(1, (len(content) + 2047) // 2048)
        padded = content + bytes(n * 2048 - len(content))
        data_sectors += [padded[i * 2048:(i + 1) * 2048] for i in range(n)]
        lba += n

    def dir_sector(own, parent, recs):
        data = _dir_record(b"\x00", own, 2048, True) + _dir_record(b"\x01", parent, 2048, True) + b"".join(recs)
        return data + bytes(2048 - len(data))

    pvd = bytearray(2048)
    pvd[0:6] = b"\x01CD001"
    pvd[156:190] = _dir_record(b"\x00", 18, 2048, True)
    root_recs = [_dir_record(d.encode(), dir_lba[d], 2048, True) for d in dirs] + records[""]
    sectors = [bytes(2048)] * 16 + [bytes(pvd), b"\xffCD001" + bytes(2042), dir_sector(18, 18, root_recs)]
    sectors += [dir_sector(dir_lba[d], 18, records[d]) for d in dirs] + data_sectors
    with open(path, "wb") as f:
        for s in sectors:
            if raw_mode is None:
                f.write(s)
            else:
                head = iso.SYNC + bytes(3) + bytes([raw_mode]) + (bytes(8) if raw_mode == 2 else b"")
                f.write(head + s + bytes(2352 - len(head) - 2048))


def make_emu_base(path):
    for rel, data in {
        "eboot.bin": b"EBOOT",
        "ps2-emu-compiler.self": b"EMU",
        "config-emu-ps4.txt": b"--ps2-title-id=SCUS-97124\n--max-disc-num=1\n--gs-uprender=none\n",
        "lua_include/common.lua": b"-- lua",
        "image/disc01.iso": b"ISO DEL JUEGO ORIGINAL",
        "sce_sys/param.sfo": b"viejo",
        "sce_sys/keystone": b"viejo",
        "sce_sys/trophy/trophy00.trp": b"trofeos",
        "sce_sys/about/right.sprx": b"about",
    }.items():
        full = os.path.join(path, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)


class IsoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_serial_from_iso(self):
        path = os.path.join(self.dir, "game.iso")
        make_iso(path, {"SYSTEM.CNF": SYSTEM_CNF, "SLUS_209.46": b"elf"})
        self.assertEqual(builder.detect_serial(path), "SLUS-20946")

    def test_raw_bin_is_converted(self):
        for mode in (1, 2):
            raw = os.path.join(self.dir, f"game{mode}.bin")
            make_iso(raw, {"SYSTEM.CNF": SYSTEM_CNF}, raw_mode=mode)
            with iso.DiscImage(raw) as disc:
                self.assertTrue(disc.is_raw)
                self.assertEqual(iso.read_serial(disc), "SLUS-20946")
                out = os.path.join(self.dir, f"out{mode}.iso")
                disc.convert_to_iso(out)
            with iso.DiscImage(out) as disc:
                self.assertFalse(disc.is_raw)
                self.assertEqual(iso.read_serial(disc), "SLUS-20946")

    def test_boot_elf_in_subdirectory_and_crc(self):
        path = os.path.join(self.dir, "game.iso")
        cnf = b"BOOT2 = cdrom0:\\DATA\\SLUS_209.46;1\r\n"
        make_iso(path, {"SYSTEM.CNF": cnf, "DATA/SLUS_209.46": BOOT_ELF, "OTRO.BIN": b"x"})
        with iso.DiscImage(path) as disc:
            self.assertEqual(iso.read_serial(disc), "SLUS-20946")
            elf = iso.read_boot_elf(disc)
            self.assertIsNone(disc.find_file("DATA/NOEXISTE"))
        self.assertEqual(elf, BOOT_ELF)
        self.assertEqual(iso.elf_crc(elf), BOOT_CRC)

    def test_ps1_disc_is_rejected(self):
        with self.assertRaisesRegex(iso.DiscError, "PS1"):
            iso.parse_serial("BOOT = cdrom:\\SLUS_000.01;1\n")

    def test_not_an_iso(self):
        path = os.path.join(self.dir, "x.iso")
        with open(path, "wb") as f:
            f.write(bytes(40000))
        with self.assertRaises(iso.DiscError):
            iso.DiscImage(path)


class FormatTests(unittest.TestCase):
    def test_sfo_roundtrip(self):
        blob = sfo.ps2_classic("Jak & Daxter ñ", "SLUS20946", "UP9000-SLUS20946_00-SLUS20946PS2FPKG")
        values = sfo.parse(blob)
        self.assertEqual(values["TITLE"], "Jak & Daxter ñ")
        self.assertEqual(values["CATEGORY"], "gd")
        self.assertEqual(values["APP_TYPE"], 1)
        self.assertEqual(list(values), sorted(values))
        key_off, data_off = struct.unpack_from("<II", blob, 8)
        self.assertEqual(data_off % 4, 0)

    def test_ids(self):
        tid = builder.title_id_from_serial("SLES-50330")
        cid = builder.content_id_for(tid)
        self.assertEqual(cid, "EP9000-SLES50330_00-SLES50330PS2FPKG")
        builder.validate_ids(tid, cid)
        with self.assertRaises(builder.BuildError):
            builder.validate_ids("SLUS2094", cid)

    def test_gp4_declares_every_dir(self):
        xml = gp4.build("UP9000-SLUS20946_00-SLUS20946PS2FPKG",
                        {"eboot.bin": "/a/eboot.bin", "sce_sys/about/right.sprx": "/a/r", "image/disc01.iso": "/g.iso"})
        root = ET.fromstring(xml)
        dirs = {d.get("targ_name") for d in root.iter("dir")}
        self.assertEqual(dirs, {"sce_sys", "about", "image"})
        self.assertEqual(root.find("volume/package").get("content_id"), "UP9000-SLUS20946_00-SLUS20946PS2FPKG")

    def test_config_patch(self):
        with tempfile.TemporaryDirectory() as d:
            make_emu_base(d)
            with open(os.path.join(d, emu.CONFIG_NAME), "a") as f:
                f.write('#--path-toolingscript="/app0/patches"\n#--path-patches="/x"\n--gs-upscale=gpu\n')
            text = emu.make_config(d, "SLUS-20946", 2,
                                   ["--gs-uprender=2x2", "--host-audio=1", '--path-patches="/app0/patches"',
                                    "--gs-uprender=none"], drop={"--gs-upscale"})
        lines = text.splitlines()
        self.assertIn("--ps2-title-id=SLUS-20946", lines)
        self.assertIn("--max-disc-num=2", lines)
        self.assertIn("--gs-uprender=none", lines)  # el último gana
        self.assertNotIn("--gs-uprender=2x2", lines)
        self.assertIn('--path-patches="/app0/patches"', lines)  # reemplaza la línea comentada
        self.assertIn('--path-toolingscript="/app0/patches"', lines)  # descomentada con 2 discos
        self.assertFalse(any(ln.startswith("--gs-upscale") for ln in lines))  # la manda la config del juego
        self.assertEqual(lines[-1], "--host-audio=1")

    def test_pnach_translation(self):
        meta, sections = pnach.parse(PNACH)
        self.assertEqual(meta["gametitle"], "Juego de prueba [SLUS-20946]")
        ws = pnach.find_section(sections, pnach.WIDESCREEN)
        self.assertEqual(ws.writes, [(1, 4, 0x2AF750, 0x3F1F3B64), (0, 1, 0x12ABCD, 0xE0), (1, 2, 0x400002, 0x1234)])
        self.assertFalse(ws.unsupported)
        self.assertTrue(pnach.find_section(sections, pnach.FPS60).unsupported)  # condicional E0
        self.assertIsNone(pnach.find_section(sections, pnach.PROGRESSIVE))
        lua = pnach.to_lua([ws, pnach.find_section(sections, pnach.NO_INTERLACE)], widescreen=True)
        self.assertIn("apiRequest(1.2)", lua)
        self.assertIn("ps2fpkgEE.WriteMem32(0x002AF750, 0x3F1F3B64)", lua)
        self.assertIn("ps2fpkgEE.WriteMem8(0x0012ABCD, 0xE0)", lua)
        self.assertIn("ps2fpkgEE.WriteMem32(0x00400000, (ps2fpkgEE.ReadMem32(0x00400000) & 0x0000FFFF) | 0x12340000)", lua)
        self.assertIn("ps2fpkgEmu.SetDisplayAspectWide()", lua)
        every = lua.split("ps2fpkgEveryFrame = function()")[1].split("end")[0]
        self.assertNotIn("0x0012ABCD", every)  # lugar 0: solo una vez al iniciar
        self.assertIn("0x002B2014", every)

    def test_images(self):
        with tempfile.TemporaryDirectory() as d:
            icon = os.path.join(d, "icon0.png")
            images.make(icon, images.ICON_SIZE, title="Prueba")
            self.assertEqual(images.png_size(icon), images.ICON_SIZE)
            bg = os.path.join(d, "pic0.png")
            images.make(bg, images.BG_SIZE, source=icon)
            if images.Image is not None:
                self.assertEqual(images.png_size(bg), images.BG_SIZE)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.base = os.path.join(self.dir, "emu")
        make_emu_base(self.base)
        self.iso1 = os.path.join(self.dir, "disc1.iso")
        self.iso2 = os.path.join(self.dir, "disc2.bin")
        make_iso(self.iso1, {"SYSTEM.CNF": SYSTEM_CNF, "SLUS_209.46": BOOT_ELF})
        make_iso(self.iso2, {"SYSTEM.CNF": SYSTEM_CNF}, raw_mode=2)
        self.out = os.path.join(self.dir, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def _opts(self, **kw):
        kw.setdefault("online", False)  # sin red en las pruebas
        return builder.Options(isos=[self.iso1, self.iso2], emu_dir=self.base, output_dir=self.out,
                               title="Juego de prueba", **kw)

    def _project(self, **kw):
        gp4_path = builder.build(self._opts(gp4_only=True, **kw), log=lambda m: None)
        root = ET.parse(gp4_path).getroot()
        files = {f.get("targ_path"): f.get("orig_path") for f in root.iter("file")}
        with open(files["config-emu-ps4.txt"]) as f:
            config = f.read().splitlines()
        return files, config

    def test_gp4_project(self):
        gp4_path = builder.build(self._opts(gp4_only=True), log=lambda m: None)
        root = ET.parse(gp4_path).getroot()
        files = {f.get("targ_path"): f.get("orig_path") for f in root.iter("file")}
        self.assertEqual(files["image/disc01.iso"], os.path.abspath(self.iso1))
        self.assertTrue(files["image/disc02.iso"].endswith("disc02.iso"))  # BIN convertido
        for excluded in ("sce_sys/keystone", "sce_sys/trophy/trophy00.trp"):
            self.assertNotIn(excluded, files)
        for included in ("eboot.bin", "lua_include/common.lua", "sce_sys/about/right.sprx",
                         "sce_sys/param.sfo", "sce_sys/icon0.png", "config-emu-ps4.txt"):
            self.assertIn(included, files)
        with open(files["sce_sys/param.sfo"], "rb") as f:
            self.assertEqual(sfo.parse(f.read())["TITLE_ID"], "SLUS20946")

    def test_max_quality_without_patches(self):
        files, config = self._project()
        for line in ("--gs-uprender=2x2", "--gs-upscale=edgesmooth", "--host-audio=1", "--host-display-mode=normal"):
            self.assertIn(line, config)
        self.assertFalse(any(f.startswith("feature_data/") for f in files))

    def test_pcsx2_patches_applied(self):
        patches = os.path.join(self.dir, "pnach")
        os.makedirs(patches)
        with open(os.path.join(patches, f"SLUS-20946_{BOOT_CRC:08X}.pnach"), "w") as f:
            f.write(PNACH)
        log = []
        opts = self._opts(gp4_only=True, patches_dir=patches, fps60=True)
        files = {f.get("targ_path"): f.get("orig_path")
                 for f in ET.parse(builder.build(opts, log=log.append)).getroot().iter("file")}
        with open(files["feature_data/SLUS-20946_features.lua"]) as f:
            lua = f.read()
        with open(files["config-emu-ps4.txt"]) as f:
            config = f.read().splitlines()
        self.assertIn("SetDisplayAspectWide", lua)
        self.assertIn("0x002B2014", lua)        # sin entrelazado
        self.assertNotIn("0x0012ABCC", lua)     # 60 FPS descartado (código condicional)
        self.assertIn("--host-display-mode=16:9", config)
        self.assertIn('--path-featuredata="/app0/feature_data"', config)
        self.assertTrue(any("60 FPS" in m and "no admite" in m for m in log))

    def test_official_config_wins_over_profile(self):
        original = db.official_cli_conf
        db.official_cli_conf = lambda serial: "--gs-uprender=none\n--gs-upscale=point\n--vu1-mpg-cycles=200\n"
        try:
            files, config = self._project(online=True, widescreen=False, no_interlace=False)
        finally:
            db.official_cli_conf = original
        with open(files["patches/SLUS-20946_cli.conf"]) as f:
            self.assertIn("--gs-upscale=point", f.read())
        self.assertFalse(any(ln.startswith(("--gs-uprender", "--gs-upscale")) for ln in config))
        self.assertIn('--path-patches="/app0/patches"', config)
        self.assertIn("--host-audio=1", config)

    def test_user_args_win(self):
        _files, config = self._project(emu_args=["--gs-upscale=point", "--host-display-mode=full"])
        self.assertIn("--gs-upscale=point", config)
        self.assertNotIn("--gs-upscale=edgesmooth", config)
        self.assertIn("--host-display-mode=full", config)

    def test_original_profile_keeps_base(self):
        _files, config = self._project(quality="original")
        self.assertIn("--gs-uprender=none", config)
        self.assertFalse(any(ln.startswith("--host-display-mode") for ln in config))

    @unittest.skipUnless(os.environ.get("PS2FPKG_PKGTOOL"), "define PS2FPKG_PKGTOOL para la prueba con PkgTool")
    def test_real_pkg(self):
        pkg = builder.build(self._opts(), log=lambda m: None)
        self.assertTrue(pkg.endswith("UP9000-SLUS20946_00-SLUS20946PS2FPKG.pkg"))
        cmd = builder.find_pkgtool()
        extracted = os.path.join(self.dir, "extracted")
        subprocess.run(cmd + ["pkg_extract", "--passcode", "0" * 32, pkg, extracted],
                       check=True, capture_output=True)
        uroot = os.path.join(extracted, "uroot")
        with open(os.path.join(uroot, "image", "disc01.iso"), "rb") as a, open(self.iso1, "rb") as b:
            self.assertEqual(a.read(), b.read())
        with open(os.path.join(uroot, "config-emu-ps4.txt")) as f:
            self.assertIn("--max-disc-num=2", f.read())
        self.assertFalse(os.path.exists(os.path.join(uroot, "sce_sys", "trophy")))

        # param.sfo va como entrada del PKG, no dentro del PFS.
        listing = subprocess.run(cmd + ["pkg_listentries", pkg], check=True, capture_output=True, text=True).stdout
        index = next(ln.split()[-2] for ln in listing.splitlines() if ln.endswith("PARAM_SFO"))
        sfo_path = os.path.join(self.dir, "param.sfo")
        subprocess.run(cmd + ["pkg_extractentry", pkg, index, sfo_path], check=True, capture_output=True)
        with open(sfo_path, "rb") as f:
            values = sfo.parse(f.read())
        self.assertEqual(values["TITLE"], "Juego de prueba")
        self.assertEqual(values["CONTENT_ID"], "UP9000-SLUS20946_00-SLUS20946PS2FPKG")


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pkg = os.path.join(self.tmp.name, "UP9000-SLUS20946_00-SLUS20946PS2FPKG.pkg")
        self.data = os.urandom(3 * 1024 * 1024 + 17)
        with open(self.pkg, "wb") as f:
            f.write(self.data)
        self.server, urls = install.serve([self.pkg], port=0, host_ip="127.0.0.1")
        self.url = next(iter(urls.values()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def _get(self, url, headers=None, method="GET"):
        req = urllib.request.Request(url, headers=headers or {}, method=method)
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()

    def test_full_and_ranges(self):
        status, headers, body = self._get(self.url)
        self.assertEqual((status, body), (200, self.data))
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        status, headers, body = self._get(self.url, {"Range": "bytes=100-199"})
        self.assertEqual((status, body), (206, self.data[100:200]))
        self.assertEqual(headers["Content-Range"], f"bytes 100-199/{len(self.data)}")
        _, _, body = self._get(self.url, {"Range": "bytes=-10"})
        self.assertEqual(body, self.data[-10:])
        _, _, body = self._get(self.url, {"Range": f"bytes={len(self.data) - 5}-"})
        self.assertEqual(body, self.data[-5:])
        status, headers, body = self._get(self.url, method="HEAD")
        self.assertEqual((status, body, headers["Content-Length"]), (200, b"", str(len(self.data))))

    def test_parallel_ranges(self):
        size, parts, results = len(self.data), 4, {}

        def fetch(i):
            a, b = i * size // parts, (i + 1) * size // parts - 1
            results[i] = self._get(self.url, {"Range": f"bytes={a}-{b}"})[2]

        threads = [threading.Thread(target=fetch, args=(i,)) for i in range(parts)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(b"".join(results[i] for i in range(parts)), self.data)

    def test_errors(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self._get(self.url.rsplit("/", 1)[0] + "/otro.pkg")
        self.assertEqual(e.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self._get(self.url, {"Range": f"bytes={len(self.data) + 10}-"})
        self.assertEqual(e.exception.code, 416)

    def test_send_to_ps4(self):
        received = []

        class FakeInstaller(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                body = b'{ "status": "success", "task_id": 7, "title": "Juego" }\n'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        fake = http.server.HTTPServer(("127.0.0.1", 0), FakeInstaller)
        threading.Thread(target=fake.serve_forever, daemon=True).start()
        try:
            answer = install.send_to_ps4("127.0.0.1", [self.url], port=fake.server_address[1])
        finally:
            fake.shutdown()
            fake.server_close()
        self.assertEqual(answer["task_id"], 7)
        self.assertEqual(received, [("/api/install", {"type": "direct", "packages": [self.url]})])

if __name__ == "__main__":
    unittest.main()
