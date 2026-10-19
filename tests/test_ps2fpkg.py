import os
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ps2fpkg import builder, emu, gp4, images, iso, sfo  # noqa: E402

SYSTEM_CNF = b"BOOT2 = cdrom0:\\SLUS_209.46;1\r\nVER = 1.00\r\nVMODE = NTSC\r\n"


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
    """ISO9660 mínima con archivos en la raíz. raw_mode=1/2 la guarda como BIN de 2352 bytes."""
    sectors = [bytes(2048)] * 16
    pvd = bytearray(2048)
    pvd[0:6] = b"\x01CD001"
    pvd[156:190] = _dir_record(b"\x00", 18, 2048, True)
    sectors += [bytes(pvd), b"\xffCD001" + bytes(2042)]
    root = _dir_record(b"\x00", 18, 2048, True) + _dir_record(b"\x01", 18, 2048, True)
    data_sectors, lba = [], 19
    for name, content in files.items():
        root += _dir_record(name.encode() + b";1", lba, len(content))
        n = (len(content) + 2047) // 2048
        padded = content + bytes(n * 2048 - len(content))
        data_sectors += [padded[i * 2048:(i + 1) * 2048] for i in range(n)]
        lba += n
    sectors += [root + bytes(2048 - len(root))] + data_sectors
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
            text = emu.make_config(d, "SLUS-20946", 2, ["--gs-uprender=2x2", "--host-audio=1"])
        self.assertIn("--ps2-title-id=SLUS-20946\n", text)
        self.assertIn("--max-disc-num=2\n", text)
        self.assertIn("--gs-uprender=2x2\n", text)
        self.assertNotIn("none", text)
        self.assertTrue(text.endswith("--host-audio=1\n"))

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
        make_iso(self.iso1, {"SYSTEM.CNF": SYSTEM_CNF})
        make_iso(self.iso2, {"SYSTEM.CNF": SYSTEM_CNF}, raw_mode=2)
        self.out = os.path.join(self.dir, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def _opts(self, **kw):
        return builder.Options(isos=[self.iso1, self.iso2], emu_dir=self.base, output_dir=self.out,
                               title="Juego de prueba", **kw)

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

if __name__ == "__main__":
    unittest.main()
