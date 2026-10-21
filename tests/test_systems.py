import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps2fpkg import (covers, cue, dreamcast, emu, fself, gamecube, images, importer, iso, pkgbuild,  # noqa: E402
                     ps1, ps4ftp, psp, retro, sfo)
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

    def test_uses_saved_emulator_without_asking(self):
        original = emu.app_dir
        app = os.path.join(self.dir, "app")
        emu.app_dir = lambda: app
        try:
            with self.assertRaisesRegex(emu.EmuError, "una sola vez"):
                ps1.build(ps1.Options(discs=[self.cue], emu_dir="", output_dir=self.out, gp4_only=True),
                          log=lambda m: None)
            emu.prepare_default_dirs()
            self.assertTrue(os.path.isfile(os.path.join(app, "emuladores", "LEEME.txt")))
            import shutil
            shutil.copytree(self.base, os.path.join(app, "emuladores", "ps1", "uroot"))
            gp4 = ps1.build(ps1.Options(discs=[self.cue], emu_dir="", output_dir=self.out, gp4_only=True),
                            log=lambda m: None)
            self.assertIn("data/bios.dat", gp4_files(gp4))
        finally:
            emu.app_dir = original

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
        script = os.path.join(self.dir, "falso.py")
        write(script, "import sys\nopen(sys.argv[2], 'wb').write(b'\\x7fELF-descifrado')\n")
        if os.name == "nt":
            self.tool = os.path.join(self.dir, "eboot_decrypt.bat")
            write(self.tool, f'@"{sys.executable}" "{script}" %*\r\n')
        else:
            self.tool = os.path.join(self.dir, "eboot_decrypt")
            write(self.tool, f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
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
            eboot = disc.read_file("PSP_GAME/SYSDIR/EBOOT.BIN")
            self.assertEqual(len(eboot), len(self.eboot))           # tamaño original, como PSP-FPKG
            self.assertTrue(eboot.startswith(b"\x7fELF-descifrado"))
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
        with open(files["sce_sys/param.sfo"], "rb") as f:
            param = sfo.parse(f.read())
        self.assertEqual((param["CATEGORY"], param["SYSTEM_VER"]), ("gde", 0x3FC))   # como pemu

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

    def test_gba_and_game_boy(self):
        gba = os.path.join(self.dir, "Juego GBA (USA).gba")
        header = bytearray(0xC0)
        header[0xB2] = 0x96
        write(gba, bytes(header) + bytes(4 * 1024 * 1024 - 0xC0))
        gp4 = retro.build(retro.Options(system="gba", rom=gba, output_dir=self.out, gp4_only=True), log=lambda m: None)
        files = gp4_files(gp4)
        self.assertIn("eboot.bin", files)
        self.assertEqual(read(files["autoboot/rom.txt"]), "Juego GBA (USA).gba\n")
        self.assertRegex(ET.parse(gp4).getroot().find("volume/package").get("content_id"),
                         r"^IV0001-GBAF\d{5}_00-[0-9A-F]{8}GBAFPKG0$")
        gbc = os.path.join(self.dir, "Juego (USA).gbc")
        write(gbc, bytes(0x104) + bytes.fromhex("CEED6666") + bytes(32 * 1024))
        files = gp4_files(retro.build(retro.Options(system="gba", rom=gbc, output_dir=self.out, gp4_only=True),
                                      log=lambda m: None))
        self.assertIn("autoboot/Juego (USA).gbc", files)
        bad = os.path.join(self.dir, "x.gba")
        write(bad, bytes(1024))
        with self.assertRaisesRegex(pkgbuild.BuildError, "cabecera de GBA"):
            retro.build(retro.Options(system="gba", rom=bad, output_dir=self.out, gp4_only=True))


    def test_genesis_and_master_system(self):
        md = os.path.join(self.dir, "Sonic The Hedgehog (USA, Europe).md")
        write(md, bytes(0x100) + b"SEGA MEGA DRIVE " + bytes(512 * 1024))
        gp4 = retro.build(retro.Options(system="genesis", rom=md, output_dir=self.out, gp4_only=True),
                          log=lambda m: None)
        files = gp4_files(gp4)
        self.assertEqual(read(files["autoboot/rom.txt"]), "Sonic The Hedgehog (USA, Europe).md\n")
        self.assertRegex(ET.parse(gp4).getroot().find("volume/package").get("content_id"),
                         r"^IV0001-MDFP\d{5}_00-[0-9A-F]{8}MDFPKG00$")
        sms = os.path.join(self.dir, "Alex Kidd (USA).sms")
        write(sms, bytes(128 * 1024))
        files = gp4_files(retro.build(retro.Options(system="genesis", rom=sms, output_dir=self.out, gp4_only=True),
                                      log=lambda m: None))
        self.assertIn("autoboot/Alex Kidd (USA).sms", files)


class GameCubeTests(Base):
    def make_disc(self, path, game_id=b"GALE01", wii=False, offset=0):
        head = bytearray(0x400)
        head[offset:offset + 6] = game_id
        if wii:
            head[offset + 0x18:offset + 0x1C] = gamecube.WII_MAGIC
        else:
            head[offset + 0x1C:offset + 0x20] = gamecube.GC_MAGIC
        head[offset + 0x20:offset + 0x20 + 19] = b"Super Smash Bros. M"
        write(path, bytes(head) + bytes(1024 * 1024))

    def test_iso_project(self):
        disc = os.path.join(self.dir, "Super Smash Bros. Melee (USA).iso")
        self.make_disc(disc)
        self.assertEqual(gamecube.read_header(disc), ("GALE01", "Super Smash Bros. M", "gc"))
        gp4 = gamecube.build(gamecube.Options(discs=[disc], output_dir=self.out, gp4_only=True), log=lambda m: None)
        files = gp4_files(gp4)
        for name in ("eboot.bin", "dolphin/eboot.bin", "sce_module/libc.prx", "Sys/codehandler.bin",
                     "autoboot/game/Super Smash Bros. Melee (USA).iso"):
            self.assertIn(name, files)
        self.assertEqual(read(files["xmb/version.txt"]).strip(), "99.99")
        self.assertEqual(read(files["autoboot/dolphin.txt"]),
                         "/app0/autoboot/game/Super Smash Bros. Melee (USA).iso\n")
        with open(files["sce_sys/param.sfo"], "rb") as f:
            param = sfo.parse(f.read())
        self.assertEqual(param["TITLE"], "Super Smash Bros. Melee")
        self.assertRegex(param["CONTENT_ID"], r"^IV0001-GCFP\d{5}_00-[0-9A-F]{8}GCFPKG00$")

    def test_rvz_two_discs_and_wii(self):
        d1, d2 = (os.path.join(self.dir, f"Tales{n}.rvz") for n in (1, 2))
        self.make_disc(d1, b"GTOE8P", offset=0x58)
        self.make_disc(d2, b"GTOE8P", offset=0x58)
        self.assertEqual(gamecube.detect_serial(d1), "GTOE8P")
        files = gp4_files(gamecube.build(gamecube.Options(discs=[d1, d2], output_dir=self.out, gp4_only=True),
                                         log=lambda m: None))
        self.assertIn("autoboot/game/Tales1 (Disc 1).rvz", files)
        self.assertIn("autoboot/game/Tales2 (Disc 2).rvz", files)
        self.assertEqual(read(files["autoboot/dolphin.txt"]), "/app0/autoboot/game/Tales1 (Disc 1).rvz\n")
        wii = os.path.join(self.dir, "Juego Wii.wbfs")
        self.make_disc(wii, b"RSPE01", wii=True, offset=0x200)
        self.assertEqual(gamecube.read_header(wii)[2], "wii")
        with self.assertRaisesRegex(pkgbuild.BuildError, "formato"):
            gamecube.build(gamecube.Options(discs=[self.out + ".nds"], output_dir=self.out, gp4_only=True))

    @unittest.skipUnless(REAL_PKGTOOL, "define PS2FPKG_PKGTOOL")
    def test_real_pkg(self):
        disc = os.path.join(self.dir, "Juego.iso")
        self.make_disc(disc)
        root = self.extract(gamecube.build(gamecube.Options(discs=[disc], output_dir=self.out), log=lambda m: None))
        self.assertEqual(read(os.path.join(root, "dolphin", "eboot.bin"), "rb")[:4], bytes.fromhex("4f153d1d"))
        self.assertTrue(os.path.isfile(os.path.join(root, "autoboot", "game", "Juego.iso")))


class DreamcastTests(Base):
    def setUp(self):
        super().setUp()
        game = os.path.join(self.dir, "Sonic Adventure (USA)")
        os.makedirs(game)
        ip = bytearray(2352)
        ip[16:16 + 16] = b"SEGA SEGAKATANA "
        ip[16 + 0x40:16 + 0x4A] = b"MK-51000  "
        ip[16 + 0x80:16 + 0x80 + 15] = b"SONIC ADVENTURE"
        write(os.path.join(game, "track01.bin"), bytes(2352 * 300))
        write(os.path.join(game, "track02.raw"), bytes(2352 * 150))
        write(os.path.join(game, "track 03.bin"), bytes(ip) + bytes(2352 * 100))
        self.gdi = os.path.join(game, "disc.gdi")
        write(self.gdi, '3\n1 0 4 2352 track01.bin 0\n2 450 0 2352 track02.raw 0\n'
                        '3 45000 4 2352 "track 03.bin" 0\n')

    def test_gdi_project(self):
        gp4 = dreamcast.build(dreamcast.Options(game=self.gdi, output_dir=self.out, gp4_only=True),
                              log=lambda m: None)
        files = gp4_files(gp4)
        for name in ("eboot.bin", "resonance/eboot.bin", "sce_module/libc.prx", "launcher/cacert.pem",
                     "autoboot/game/disc.gdi", "autoboot/game/track02.raw", "autoboot/game/track 03.bin"):
            self.assertIn(name, files)
        self.assertEqual(read(files["version.txt"]).strip(), "99.99")
        args = read(files["autoboot/args.txt"]).splitlines()
        self.assertEqual(args[-1], "/app0/autoboot/game/disc.gdi")
        self.assertIn("config:rend.Resolution=960", args)
        self.assertIn("config:rend.WidescreenGameHacks=yes", args)
        self.assertEqual(args[0], "-config")
        with open(files["sce_sys/param.sfo"], "rb") as f:
            param = sfo.parse(f.read())
        self.assertEqual(param["TITLE"], "Sonic Adventure")   # carpeta, porque disc.gdi es genérico
        self.assertEqual(param["ATTRIBUTE"], 2)
        self.assertRegex(param["CONTENT_ID"], r"^IV0001-DCFP\d{5}_00-[0-9A-F]{8}DCFPKG00$")
        self.assertEqual(dreamcast.read_ip(dreamcast.gdi_files(self.gdi)), ("MK-51000", "SONIC ADVENTURE"))

    def test_options_bios_and_errors(self):
        bios = os.path.join(self.dir, "bios")
        write(os.path.join(bios, "dc_boot.bin"), bytes(2 * 1024 * 1024))
        chd = os.path.join(self.dir, "Crazy Taxi (USA).chd")
        write(chd, b"MComprHD" + bytes(1000))
        gp4 = dreamcast.build(dreamcast.Options(game=chd, output_dir=self.out, gp4_only=True, resolution="original",
                                                widescreen=False, show_fps=True, bios_dir=bios),
                              log=lambda m: None)
        files = gp4_files(gp4)
        self.assertIn("data/dc_boot.bin", files)
        args = read(files["autoboot/args.txt"]).splitlines()
        self.assertEqual(args[-1], "/app0/autoboot/game/Crazy Taxi (USA).chd")
        self.assertFalse(any("rend.Resolution" in a for a in args))
        self.assertIn("config:rend.WidescreenGameHacks=no", args)
        self.assertIn("config:rend.ShowFPS=yes", args)
        os.remove(os.path.join(os.path.dirname(self.gdi), "track02.raw"))
        with self.assertRaisesRegex(pkgbuild.BuildError, "track02.raw"):
            dreamcast.build(dreamcast.Options(game=self.gdi, output_dir=self.out, gp4_only=True))
        with self.assertRaisesRegex(pkgbuild.BuildError, "formato"):
            dreamcast.build(dreamcast.Options(game=self.out + ".iso", output_dir=self.out, gp4_only=True))

    @unittest.skipUnless(REAL_PKGTOOL, "define PS2FPKG_PKGTOOL")
    def test_real_pkg(self):
        pkg = dreamcast.build(dreamcast.Options(game=self.gdi, output_dir=self.out), log=lambda m: None)
        root = self.extract(pkg)
        self.assertEqual(read(os.path.join(root, "eboot.bin"), "rb")[:4], bytes.fromhex("4f153d1d"))  # fSELF
        self.assertEqual(read(os.path.join(root, "resonance", "eboot.bin"), "rb")[:4], bytes.fromhex("4f153d1d"))
        self.assertTrue(os.path.isfile(os.path.join(root, "autoboot", "game", "track 03.bin")))


class CoverTests(Base):
    NAMES = ["Donkey Kong Country (USA)", "Donkey Kong Country 2 - Diddy's Kong Quest (USA) (En,Fr)",
             "Donkey Kong Country 2 - Diddy's Kong Quest (Europe) (En,Fr,De)",
             "Legend of Zelda, The - A Link to the Past (USA)", "Legend of Zelda, The - A Link to the Past (Japan)",
             "Super Mario World (USA)", "Super Mario World (Europe) (Beta)", "Final Fantasy III (USA)"]

    def test_best_match(self):
        m = lambda q: covers.best_match(q, self.NAMES)  # noqa: E731
        self.assertEqual(m("Super Mario World (USA) [!].sfc"), "Super Mario World (USA)")
        self.assertEqual(m("super mario world"), "Super Mario World (USA)")  # sin la beta
        self.assertEqual(m("Donkey Kong Country 2"), "Donkey Kong Country 2 - Diddy's Kong Quest (USA) (En,Fr)")
        self.assertEqual(m("Donkey Kong Country 2 (Europe)"),
                         "Donkey Kong Country 2 - Diddy's Kong Quest (Europe) (En,Fr,De)")
        self.assertEqual(m("Zelda - A Link to the Past"), "Legend of Zelda, The - A Link to the Past (USA)")
        self.assertEqual(m("Final Fantasy 3.smc"), "Final Fantasy III (USA)")
        self.assertIsNone(m("Mario"))
        self.assertIsNone(m("Juego que no existe"))

    def test_resolve_does_not_search_when_given_or_disabled(self):
        opts = retro.Options(system="snes", rom="x.sfc", output_dir=".", cover="mi.png", find_cover=True)
        self.assertEqual(covers.resolve(opts, "snes"), "mi.png")
        opts = retro.Options(system="snes", rom="x.sfc", output_dir=".")
        self.assertEqual(covers.resolve(opts, "snes"), "")

    @unittest.skipIf(images.Image is None, "requiere Pillow")
    def test_package_uses_cover(self):
        cover = os.path.join(self.dir, "caratula.png")
        images.Image.new("RGB", (300, 420), (200, 30, 30)).save(cover)
        rom = os.path.join(self.dir, "Juego (USA).nes")
        write(rom, b"NES\x1a" + bytes(16 * 1024 + 12))
        gp4 = retro.build(retro.Options(system="nes", rom=rom, output_dir=self.out, gp4_only=True, cover=cover,
                                        title="Mi nombre"), log=lambda m: None)
        files = gp4_files(gp4)
        self.assertEqual(images.png_size(files["sce_sys/icon0.png"]), images.ICON_SIZE)
        self.assertEqual(images.png_size(files["sce_sys/pic1.png"]), images.BG_SIZE)
        icon = images.Image.open(files["sce_sys/icon0.png"]).convert("RGB")
        self.assertEqual(icon.getpixel((256, 256)), (200, 30, 30))  # la carátula, en el centro
        with open(files["sce_sys/param.sfo"], "rb") as f:
            self.assertEqual(sfo.parse(f.read())["TITLE"], "Mi nombre")


class EmuConfigTests(unittest.TestCase):
    def test_merge_args_repeated_and_drop(self):
        text = emu.merge_args(['--image="a"', '--image="b"', "--keep=1", "#--x=1"],
                              ["--keep=2", "--x=5"], drop={"--image"}, extra=['--image="c"', '--image="d"'])
        self.assertEqual(text.splitlines(), ["--keep=2", "--x=5", '--image="c"', '--image="d"'])


if __name__ == "__main__":
    unittest.main()


def make_elf(code=b"\x90" * 300, e_type=0xFE10):
    """ELF de PS4 mínimo: cabecera, una cabecera de programa PT_LOAD y el segmento."""
    header = bytearray(0x40)
    header[:4] = b"\x7fELF"
    header[4:7] = bytes([2, 1, 1])
    header[0x10:0x12] = e_type.to_bytes(2, "little")
    header[0x20:0x28] = (0x40).to_bytes(8, "little")      # e_phoff
    header[0x36:0x38] = (0x38).to_bytes(2, "little")      # e_phentsize
    header[0x38:0x3A] = (1).to_bytes(2, "little")         # e_phnum
    import struct as _s
    prog = _s.pack("<IIQQQQQQ", 1, 5, 0x100, 0, 0, len(code), len(code), 0x4000)
    return bytes(header) + prog + bytes(0x100 - 0x40 - len(prog)) + code


class FakeGoldhenFtp:
    """Servidor FTP mínimo como el de GoldHEN: LIST, RETR, PASV y DECRYPT (alterna el descifrado)."""

    def __init__(self, files):
        import socket
        import threading
        self.files = files            # ruta -> bytes (SELF cifrado: (self, elf))
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def dirs(self, path):
        path = path.rstrip("/")
        out = {}
        for f in self.files:
            if f.startswith(path + "/"):
                rest = f[len(path) + 1:]
                name = rest.split("/")[0]
                out[name] = "/" in rest
        return out

    def _serve(self):
        import threading
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._session, args=(conn,), daemon=True).start()

    def _session(self, conn):
        import socket
        decrypt = False
        data_sock = None
        f = conn.makefile("rwb", buffering=0)
        f.write(b"220 GoldHEN FTP\r\n")
        for raw in f:
            line = raw.decode().strip()
            cmd, _, arg = line.partition(" ")
            cmd = cmd.upper()
            if cmd in ("USER", "PASS", "TYPE"):
                f.write(b"230 ok\r\n" if cmd != "TYPE" else b"200 ok\r\n")
            elif cmd == "PASV":
                data_sock = socket.socket()
                data_sock.bind(("127.0.0.1", 0))
                data_sock.listen(1)
                p = data_sock.getsockname()[1]
                f.write(f"227 Entering Passive Mode (127,0,0,1,{p >> 8},{p & 255})\r\n".encode())
            elif cmd == "DECRYPT":
                decrypt = not decrypt
                f.write(f"200 SELF decryption {'enabled' if decrypt else 'disabled'}\r\n".encode())
            elif cmd in ("LIST", "RETR"):
                if cmd == "LIST":
                    entries = self.dirs(arg)
                    if not entries:
                        f.write(b"550 no existe\r\n")
                        continue
                    body = "".join(f"{'d' if d else '-'}rwxr-xr-x 1 root root {0 if d else 10} Jan 01 2020 {n}\r\n"
                                   for n, d in sorted(entries.items())).encode()
                else:
                    content = self.files.get(arg)
                    if content is None:
                        f.write(b"550 no existe\r\n")
                        continue
                    body = content[1] if isinstance(content, tuple) and decrypt else (
                        content[0] if isinstance(content, tuple) else content)
                f.write(b"150 ok\r\n")
                dconn, _ = data_sock.accept()
                dconn.sendall(body)
                dconn.close()
                data_sock.close()
                f.write(b"226 ok\r\n")
            elif cmd == "QUIT":
                f.write(b"221 bye\r\n")
                break
            else:
                f.write(b"502 no\r\n")
        conn.close()

    def close(self):
        self.sock.close()


class Ps4FtpTests(Base):
    def classic(self, files):
        elf = make_elf()
        prx = make_elf(b"\xcc" * 500, e_type=0xFE18)
        enc_eboot = bytearray(fself.make(elf, paid=0x3100000000000099, ptype=4, app_version=0x100, fw_version=0x5050000))
        enc_eboot[-300:] = bytes(300)      # "cifrado": el segmento no es el ELF
        root = "/mnt/sandbox/pfsmnt/CUSA12345-app0"
        tree = {f"{root}/eboot.bin": (bytes(enc_eboot), elf),
                f"{root}/sce_module/libc.prx": (fself.make(prx, ptype=5), prx),
                f"{root}/sce_sys/param.sfo": b"PSF",
                f"{root}/sce_sys/trophy/trophy00.trp": b"cifrado",
                "/mnt/sandbox/pfsmnt/CUSA12345-app0-nest/pfs_image.dat": b"x"}
        tree.update({f"{root}/{k}": v for k, v in files.items()})
        return elf, prx, tree

    def test_fetch_ps2_emulator(self):
        elf, prx, tree = self.classic({"config-emu-ps4.txt": b"--gs-uprender=none\n", "image/disc01.iso": b"juego",
                                       "feature_data/lua/x.lua": b"-- lua"})
        server = FakeGoldhenFtp(tree)
        self.addCleanup(server.close)
        logs = []
        system, dest = ps4ftp.fetch("127.0.0.1", "ps2", dest_root=self.dir, log=logs.append, port=server.port)
        self.assertEqual((system, dest), ("ps2", os.path.join(self.dir, "ps2")))
        eboot = read(os.path.join(dest, "eboot.bin"), "rb")
        self.assertEqual(eboot[:4], fself.SELF_MAGIC)
        self.assertEqual(fself.read_info(eboot), (0x3100000000000099, 4, 0x100, 0x5050000))
        self.assertEqual(fself.unwrap(eboot)[0], elf[0x100:])
        self.assertEqual(fself.unwrap(read(os.path.join(dest, "sce_module", "libc.prx"), "rb"))[0], prx[0x100:])
        self.assertTrue(os.path.isfile(os.path.join(dest, "feature_data", "lua", "x.lua")))
        self.assertFalse(os.path.exists(os.path.join(dest, "image")))
        self.assertFalse(os.path.exists(os.path.join(dest, "sce_sys", "trophy")))
        self.assertEqual(emu.locate(dest), dest)
        self.assertIn("2 ejecutables", logs[-1])

    def test_detects_other_console_and_errors(self):
        _elf, _prx, tree = self.classic({"config-title.txt": b"--scale=4\n", "data/disc1.bin": b"juego",
                                         "data/disc1.cue": b"cue"})
        server = FakeGoldhenFtp(tree)
        self.addCleanup(server.close)
        system, dest = ps4ftp.fetch("127.0.0.1", "psp", dest_root=self.dir, log=lambda m: None, port=server.port)
        self.assertEqual(system, "ps1")
        self.assertFalse(os.path.exists(os.path.join(dest, "data", "disc1.bin")))
        empty = FakeGoldhenFtp({"/mnt/sandbox/pfsmnt/CUSA00001-app0/eboot.bin": b"x"})
        self.addCleanup(empty.close)
        with self.assertRaisesRegex(ps4ftp.Ps4FtpError, "no es un clásico"):
            ps4ftp.fetch("127.0.0.1", "ps2", dest_root=self.dir, log=lambda m: None, port=empty.port)


class FselfTests(unittest.TestCase):
    def test_roundtrip(self):
        elf = make_elf(bytes(range(256)) * 100)
        data = fself.make(elf, paid=0x3800000000000011)
        self.assertEqual(data[:4], fself.SELF_MAGIC)
        self.assertEqual(fself.read_info(data), (0x3800000000000011, 1, 0, 0))
        self.assertEqual(fself.unwrap(data)[0], elf[0x100:])
        with self.assertRaises(fself.FselfError):
            fself.make(b"no es un elf")


class ImporterTests(Base):
    def make_base(self, root, system):
        write(os.path.join(root, "eboot.bin"), fself.make(make_elf()))
        write(os.path.join(root, "sce_module", "libc.prx"), make_elf(e_type=0xFE18))   # descifrado: se firma
        write(os.path.join(root, "sce_sys", "param.sfo"), b"PSF")
        if system == "ps2":
            write(os.path.join(root, "config-emu-ps4.txt"), "--gs-uprender=none\n")
            write(os.path.join(root, "image", "disc01.iso"), b"juego")
        else:
            write(os.path.join(root, "config-title.txt"), '--image="data/USER_L0.IMG"\n--antialias=SSAA4x\n'
                  if system == "psp" else '--image="data/disc1.bin"\n--scale=4\n')
            write(os.path.join(root, "data", "USER_L0.IMG" if system == "psp" else "disc1.bin"), b"juego")

    def zip_of(self, folder):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for dirpath, _d, files in os.walk(folder):
                for n in files:
                    full = os.path.join(dirpath, n)
                    z.write(full, os.path.join("psphd", os.path.relpath(full, folder)))
        return buf.getvalue()

    def test_exe_with_embedded_zip(self):
        src = os.path.join(self.dir, "src")
        self.make_base(src, "psp")
        exe = os.path.join(self.dir, "Herramienta.exe")
        write(exe, b"MZ" + bytes(5000) + self.zip_of(src) + bytes(3000))
        system, dest = importer.import_base(exe, "psp", dest_root=os.path.join(self.dir, "emus"), log=lambda m: None)
        self.assertEqual(system, "psp")
        self.assertEqual(emu.locate(dest), dest)
        self.assertFalse(os.path.exists(os.path.join(dest, "data", "USER_L0.IMG")))
        self.assertEqual(read(os.path.join(dest, "sce_module", "libc.prx"), "rb")[:4], fself.SELF_MAGIC)
        self.assertEqual(read(os.path.join(dest, "eboot.bin"), "rb"), read(os.path.join(src, "eboot.bin"), "rb"))

    def test_folder_zip_and_detection(self):
        src = os.path.join(self.dir, "extraido", "uroot")
        self.make_base(src, "ps2")
        system, dest = importer.import_base(os.path.join(self.dir, "extraido"), "ps1",
                                            dest_root=os.path.join(self.dir, "emus"), log=lambda m: None)
        self.assertEqual(system, "ps2")
        self.assertFalse(os.path.exists(os.path.join(dest, "image")))
        ps1 = os.path.join(self.dir, "ps1base")
        self.make_base(ps1, "ps1")
        z = os.path.join(self.dir, "ps1.zip")
        write(z, self.zip_of(ps1))
        self.assertEqual(importer.import_base(z, dest_root=os.path.join(self.dir, "emus"), log=lambda m: None)[0], "ps1")
        bad = os.path.join(self.dir, "nada.exe")
        write(bad, b"MZ" + bytes(100))
        with self.assertRaisesRegex(importer.EmuImportError, "No se encontró un emulador"):
            importer.import_base(bad, dest_root=self.dir, log=lambda m: None)

    @unittest.skipUnless(importlib.util.find_spec("py7zr"), "instala py7zr")
    def test_exe_with_embedded_7z(self):
        import py7zr
        src = os.path.join(self.dir, "src")
        self.make_base(src, "psp")
        archive = os.path.join(self.dir, "base.7z")
        with py7zr.SevenZipFile(archive, "w") as z:
            z.writeall(src, "psphd")
        exe = os.path.join(self.dir, "PSP-FPKG.exe")
        write(exe, b"MZ" + bytes(4000) + read(archive, "rb") + bytes(2000))
        system, dest = importer.import_base(exe, dest_root=os.path.join(self.dir, "emus"), log=lambda m: None)
        self.assertEqual(system, "psp")
        self.assertTrue(os.path.isfile(os.path.join(dest, "config-title.txt")))


class ImporterToolTests(Base):
    make_base = ImporterTests.make_base

    def test_tool_zip_with_exe_and_several_bases(self):
        bases = os.path.join(self.dir, "bases")
        self.make_base(os.path.join(bases, "emus", "Rogue v1"), "ps2")
        self.make_base(os.path.join(bases, "emus", "Jak v2"), "ps2")
        write(os.path.join(bases, "emus", "Jak v2", "marca.txt"), "jak")
        self.make_base(os.path.join(bases, "ps1hd"), "ps1")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for dirpath, _d, files in os.walk(bases):
                for n in files:
                    full = os.path.join(dirpath, n)
                    z.write(full, os.path.relpath(full, bases))
        tool = io.BytesIO()
        with zipfile.ZipFile(tool, "w") as z:
            z.writestr("PS2-FPKG/PS2-FPKG.exe", b"MZ" + bytes(3000) + buf.getvalue() + bytes(100))
            z.writestr("PS2-FPKG/readme.txt", "hola")
        archive = os.path.join(self.dir, "PS2-FPKG_v0.7.zip")
        write(archive, tool.getvalue())
        installed = importer.import_all(archive, dest_root=os.path.join(self.dir, "emus"), log=lambda m: None)
        self.assertEqual(set(installed), {"ps1", "ps2"})
        self.assertTrue(os.path.isfile(os.path.join(installed["ps2"], "marca.txt")))   # Jak v2 antes que Rogue
        self.assertFalse(os.path.exists(os.path.join(installed["ps2"], "image")))
