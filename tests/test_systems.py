import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps2fpkg import cue, emu, iso, pkgbuild, ps1, psp, retro, sfo  # noqa: E402
from test_ps2fpkg import make_iso  # noqa: E402

REAL_PKGTOOL = os.environ.get("PS2FPKG_PKGTOOL")


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
        f.write(data)


def gp4_files(gp4_path):
    return {f.get("targ_path"): f.get("orig_path") for f in ET.parse(gp4_path).getroot().iter("file")}


def read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.out = os.path.join(self.dir, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def extract(self, pkg):
        """Extrae el PFS del PKG con PkgTool y devuelve la carpeta uroot."""
        out = os.path.join(self.dir, "extraido")
        subprocess.run(pkgbuild.find_pkgtool() + ["pkg_extract", "--passcode", "0" * 32, pkg, out],
                       check=True, capture_output=True)
        return os.path.join(out, "uroot")


class Ps1Tests(Base):
    def setUp(self):
        super().setUp()
        game = os.path.join(self.dir, "juego")
        os.makedirs(game)
        # Pista 1 de datos (BIN en bruto) + 2 pistas de audio en archivos aparte (formato Redump).
        make_iso(os.path.join(game, "Juego (Track 1).bin"),
                 {"SYSTEM.CNF": b"BOOT = cdrom:\\SLUS_000.67;1\r\nTCB = 4\r\n"}, raw_mode=2)
        write(os.path.join(game, "Juego (Track 2).bin"), bytes(2352 * 300))
        write(os.path.join(game, "Juego (Track 3).bin"), bytes(2352 * 200))
        self.data_sectors = os.path.getsize(os.path.join(game, "Juego (Track 1).bin")) // 2352
        self.cue = os.path.join(game, "Juego.cue")
        write(self.cue, 'FILE "Juego (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
                        'FILE "Juego (Track 2).bin" BINARY\n  TRACK 02 AUDIO\n    INDEX 00 00:00:00\n'
                        '    INDEX 01 00:02:00\nFILE "Juego (Track 3).bin" BINARY\n  TRACK 03 AUDIO\n'
                        '    INDEX 00 00:00:00\n    INDEX 01 00:02:00\n')
        self.base = os.path.join(self.dir, "ps1base")
        write(os.path.join(self.base, "eboot.bin"), b"EBOOT")
        write(os.path.join(self.base, "config-title.txt"),
              '--image="data/ORIGINAL.bin"\n--ps1-title-id=SCUS94900\n--trophies=1\n--region-dir=SIEA\n--scale=2\n')
        write(os.path.join(self.base, "data/ORIGINAL.bin"), b"disco original")
        write(os.path.join(self.base, "data/ORIGINAL.toc"), b"toc original")
        write(os.path.join(self.base, "data/bios.dat"), b"se conserva")
        write(os.path.join(self.base, "scripts/SCUS94900.lua"), b"-- script del juego original")
        write(os.path.join(self.base, "SIEA/config-region.txt"), b"--region=1\n")

    def test_cue_merge_and_toc(self):
        parsed = cue.parse(self.cue)
        self.assertEqual(parsed.file_starts(), [0, self.data_sectors, self.data_sectors + 300])
        toc = cue.toc(parsed)
        self.assertEqual(len(toc), 30 + 3 * 10)
        self.assertEqual(toc[17], 0x03)  # última pista
        # Pista 2: pregap en el sector data_sectors, INDEX 01 dos segundos después, +2 s de lead-in.
        m, s, f = cue.sectors_to_msf(self.data_sectors + 150 + 150)
        self.assertEqual(toc[47:50], bytes(int(str(v), 16) for v in (m, s, f)))
        self.assertEqual(toc[40], 0x01)  # audio
        text = cue.single_bin_cue(parsed, "disc1.bin")
        self.assertEqual(text.count("FILE"), 1)
        self.assertIn("TRACK 03 AUDIO", text)

    def test_serial(self):
        self.assertEqual(ps1.detect_serial(self.cue), "SLUS-00067")

    def test_project(self):
        log = []
        gp4 = ps1.build(ps1.Options(discs=[self.cue], emu_dir=self.base, output_dir=self.out,
                                    title="Juego PS1", gp4_only=True, force_60hz=True), log=log.append)
        files = gp4_files(gp4)
        self.assertIn("data/disc1.bin", files)
        self.assertEqual(os.path.getsize(files["data/disc1.bin"]), 2352 * (self.data_sectors + 500))
        self.assertIn("data/disc1.toc", files)
        self.assertIn("data/bios.dat", files)
        for gone in ("data/ORIGINAL.bin", "data/ORIGINAL.toc", "scripts/SCUS94900.lua"):
            self.assertNotIn(gone, files)
        config = read(files["config-title.txt"]).splitlines()
        self.assertEqual([ln for ln in config if ln.startswith("--image")], ['--image="data/disc1.bin"'])
        for line in ("--scale=6", "--userui-settings-graphics=1", "--trophies=0", "--region-dir=SIEA",
                     "--gpu-scanout-fps-override=60"):
            self.assertIn(line, config)
        self.assertFalse(any(ln.startswith("--ps1-title-id") for ln in config))
        self.assertIn("UP9000-SLUS00067_00-SLUS00067PS1FPKG", gp4)
        self.assertTrue(any("2 de audio CD" in m for m in log))

    def test_two_discs_and_lua(self):
        lua = os.path.join(self.dir, "juego.lua")
        write(lua, "-- parche")
        gp4 = ps1.build(ps1.Options(discs=[self.cue, self.cue], emu_dir=self.base, output_dir=self.out,
                                    gp4_only=True, config_lua=lua, quality="rendimiento"), log=lambda m: None)
        files = gp4_files(gp4)
        config = read(files["config-title.txt"]).splitlines()
        self.assertEqual(len([ln for ln in config if ln.startswith("--image")]), 2)
        self.assertIn("--enable-change-disc-ui=1", config)
        self.assertIn("--scale=2", config)
        self.assertIn("--ps1-title-id=SLUS00067", config)
        self.assertIn("scripts/SLUS00067.lua", files)

    def test_rejects_iso(self):
        with self.assertRaises(pkgbuild.BuildError):
            ps1.build(ps1.Options(discs=["juego.iso"], emu_dir=self.base, output_dir=self.out))

    @unittest.skipUnless(REAL_PKGTOOL, "define PS2FPKG_PKGTOOL")
    def test_real_pkg(self):
        pkg = ps1.build(ps1.Options(discs=[self.cue], emu_dir=self.base, output_dir=self.out), log=lambda m: None)
        root = self.extract(pkg)
        self.assertEqual(os.path.getsize(os.path.join(root, "data", "disc1.bin")), 2352 * (self.data_sectors + 500))
        self.assertEqual(len(read(os.path.join(root, "data", "disc1.toc"), "rb")), 60)


class PspTests(Base):
    def setUp(self):
        super().setUp()
        self.eboot = b"~PSP" + bytes(range(256)) * 20
        param = sfo.build([("CATEGORY", "UG", 4), ("DISC_ID", "ULUS10041", 16), ("TITLE", "Juego PSP", 128)])
        self.iso = os.path.join(self.dir, "juego.iso")
        make_iso(self.iso, {"UMD_DATA.BIN": b"ULUS-10041|0001|G", "PSP_GAME/PARAM.SFO": param,
                            "PSP_GAME/SYSDIR/EBOOT.BIN": self.eboot, "PSP_GAME/USRDIR/DATA.BIN": b"datos"})
        self.base = os.path.join(self.dir, "pspbase")
        write(os.path.join(self.base, "eboot.bin"), b"EBOOT")
        write(os.path.join(self.base, "config-title.txt"), '--image="data/USER_L0.IMG"\n--trophies=1\n--antialias=off\n')
        write(os.path.join(self.base, "data/USER_L0.IMG"), b"UMD original")
        # Descifrador simulado: escribe un ELF más corto que el EBOOT cifrado.
        self.tool = os.path.join(self.dir, "eboot_decrypt")
        write(self.tool, '#!/bin/sh\nprintf "\\177ELF-descifrado" > "$2"\n')
        os.chmod(self.tool, 0o755)

    def test_info(self):
        self.assertEqual(psp.read_info(self.iso), ("ULUS-10041", "Juego PSP"))

    def test_project_with_decrypted_eboot(self):
        gp4 = psp.build(psp.Options(iso=self.iso, emu_dir=self.base, output_dir=self.out, gp4_only=True,
                                    eboot_decrypt=self.tool), log=lambda m: None)
        files = gp4_files(gp4)
        image = files["data/USER_L0.IMG"]
        self.assertNotEqual(image, os.path.abspath(os.path.join(self.base, "data/USER_L0.IMG")))
        with iso.DiscImage(image) as disc:
            self.assertEqual(disc.read_file("PSP_GAME/SYSDIR/EBOOT.BIN"), b"\x7fELF-descifrado")
            self.assertEqual(disc.read_file("PSP_GAME/USRDIR/DATA.BIN"), b"datos")
        with iso.DiscImage(self.iso) as disc:  # la ISO original no se toca
            self.assertEqual(disc.read_file("PSP_GAME/SYSDIR/EBOOT.BIN"), self.eboot)
        config = read(files["config-title.txt"]).splitlines()
        self.assertIn("--antialias=SSAA4x", config)
        self.assertIn('--image="data/USER_L0.IMG"', config)
        self.assertIn("--trophies=0", config)
        self.assertIn("UP9000-ULUS10041_00-ULUS10041PSPFPKG", gp4)

    def test_missing_tool(self):
        original = pkgbuild.find_tool
        pkgbuild.find_tool = lambda *a, **k: None
        try:
            with self.assertRaisesRegex(pkgbuild.BuildError, "eboot_decrypt"):
                psp.build(psp.Options(iso=self.iso, emu_dir=self.base, output_dir=self.out, gp4_only=True),
                          log=lambda m: None)
        finally:
            pkgbuild.find_tool = original

    def test_real_decrypt_tool_rejects_garbage(self):
        tool = pkgbuild.find_tool(("eboot_decrypt.exe", "eboot_decrypt"))
        if tool is None or tool.endswith(".exe") and os.name != "nt":
            self.skipTest("sin eboot_decrypt para esta plataforma")
        with self.assertRaisesRegex(pkgbuild.BuildError, "descifrar"):
            psp.build(psp.Options(iso=self.iso, emu_dir=self.base, output_dir=self.out, gp4_only=True),
                      log=lambda m: None)


class RetroTests(Base):
    def setUp(self):
        super().setUp()
        self.nes = os.path.join(self.dir, "Super Juego (USA) [!].nes")
        write(self.nes, b"NES\x1a" + bytes(16 * 1024 + 12))
        self.snes = os.path.join(self.dir, "Juego SNES (Europe).sfc")
        write(self.snes, bytes(512 * 1024))

    def test_nes_project(self):
        gp4 = retro.build(retro.Options(system="nes", rom=self.nes, output_dir=self.out, gp4_only=True),
                          log=lambda m: None)
        files = gp4_files(gp4)
        self.assertIn("eboot.bin", files)
        self.assertIn("sce_module/libc.prx", files)
        self.assertIn("NstDatabase.xml", files)
        self.assertEqual(read(files["autoboot/rom.txt"]), "Super Juego (USA) [!].nes\n")
        self.assertEqual(files["autoboot/Super Juego (USA) [!].nes"], os.path.abspath(self.nes))
        options = read(files["autoboot/options.txt"])
        self.assertIn("EFFECT=interpolation-sharp-bilinear", options)
        self.assertNotIn("AUDIO_SYNC", options)
        cid = ET.parse(gp4).getroot().find("volume/package").get("content_id")
        self.assertRegex(cid, r"^IV0001-PNES\d{5}_00-[0-9A-F]{8}NESFPKG0$")

    def test_snes_options_and_title(self):
        gp4 = retro.build(retro.Options(system="snes", rom=self.snes, output_dir=self.out, gp4_only=True,
                                        video="crt"), log=lambda m: None)
        files = gp4_files(gp4)
        options = read(files["autoboot/options.txt"])
        self.assertIn("EFFECT=crt-easymode", options)
        self.assertIn("AUDIO_SYNC=ON", options)
        self.assertEqual(retro.clean_title(self.snes), "Juego SNES")
        with open(files["sce_sys/param.sfo"], "rb") as f:
            self.assertEqual(sfo.parse(f.read())["TITLE"], "Juego SNES")

    def test_bad_roms(self):
        bad = os.path.join(self.dir, "x.nes")
        write(bad, bytes(100))
        with self.assertRaisesRegex(pkgbuild.BuildError, "iNES"):
            retro.build(retro.Options(system="nes", rom=bad, output_dir=self.out, gp4_only=True))
        with self.assertRaisesRegex(pkgbuild.BuildError, "extensión"):
            retro.build(retro.Options(system="snes", rom=self.nes, output_dir=self.out, gp4_only=True))

    def test_same_rom_same_ids(self):
        a = retro.build(retro.Options(system="nes", rom=self.nes, output_dir=self.out, gp4_only=True), log=lambda m: None)
        b = retro.build(retro.Options(system="nes", rom=self.nes, output_dir=self.out, gp4_only=True), log=lambda m: None)
        self.assertEqual(a, b)

    @unittest.skipUnless(REAL_PKGTOOL, "define PS2FPKG_PKGTOOL")
    def test_real_pkg(self):
        pkg = retro.build(retro.Options(system="snes", rom=self.snes, output_dir=self.out), log=lambda m: None)
        root = self.extract(pkg)
        self.assertEqual(read(os.path.join(root, "autoboot", "rom.txt")), "Juego SNES (Europe).sfc\n")
        self.assertEqual(read(os.path.join(root, "eboot.bin"), "rb")[:4], bytes.fromhex("4f153d1d"))  # fSELF
        self.assertEqual(os.path.getsize(os.path.join(root, "autoboot", "Juego SNES (Europe).sfc")), 512 * 1024)


class EmuConfigTests(unittest.TestCase):
    def test_merge_args_repeated_and_drop(self):
        text = emu.merge_args(['--image="a"', '--image="b"', "--keep=1", "#--x=1"],
                              ["--keep=2", "--x=5"], drop={"--image"}, extra=['--image="c"', '--image="d"'])
        self.assertEqual(text.splitlines(), ["--keep=2", "--x=5", '--image="c"', '--image="d"'])


if __name__ == "__main__":
    unittest.main()
