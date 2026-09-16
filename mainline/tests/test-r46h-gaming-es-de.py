#!/usr/bin/env python3
"""Focused host contracts for the R46H ES-DE frontend candidate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-es-de"
OUTPUT = REPO / "mainline/out/r46h-gaming-es-de-v0.1"
VISUAL = REPO / "mainline/gaming-es-de-visual"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_generator():
    path = ROOT / "generate-legacy-media-links.py"
    spec = importlib.util.spec_from_file_location("r46h_es_de_media", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EsDeCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = json.loads((ROOT / "source-lock.json").read_text(encoding="utf-8"))
        cls.dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        cls.builder = (ROOT / "build-runtime.py").read_text(encoding="utf-8")
        cls.collector = (ROOT / "collect-runtime.sh").read_text(encoding="utf-8")
        cls.pacing_patch = (ROOT / "idle-frame-pacing.patch").read_text(encoding="utf-8")
        cls.settings_text = (ROOT / "es_settings.xml").read_text(encoding="utf-8")
        cls.theme = ET.parse(ROOT / "r46h-theme.xml").getroot()
        cls.systems = ET.parse(ROOT / "es_systems.xml").getroot()
        cls.runner = (ROOT / "r46h-es-de-ui").read_text(encoding="utf-8")
        cls.installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        cls.rollback = (ROOT / "rollback.sh").read_text(encoding="utf-8")
        cls.unit = (ROOT / "r46h-gaming-frontend.service").read_text(encoding="utf-8")

    def test_upstream_source_and_target_abi_are_exact(self) -> None:
        self.assertEqual(self.lock["schema_version"], 1)
        self.assertEqual(
            self.lock["source"],
            {
                "repository": "https://gitlab.com/es-de/emulationstation-de.git",
                "tag": "v3.4.1",
                "commit": "5db4e2a32bd5852cc7a3dbeb298d85de86a536d7",
                "tree": "fc0bb596d66ddcc26548edb6a31c075da68e5cd6",
                "archive_url": "https://gitlab.com/es-de/emulationstation-de/-/archive/v3.4.1/emulationstation-de-v3.4.1.tar.gz",
                "archive_name": "emulationstation-de-v3.4.1.tar.gz",
                "archive_size": 77253914,
                "archive_sha256": "58a45eb3f400a3b02d5b994407ba8c5f71807de3c2df571b7abdc21bc6e83be8",
                "source_date_epoch": 1775822834,
            },
        )
        self.assertEqual(
            self.lock["build"]["accepted_target_packages"],
            {
                "kbd": "2.7.1-2",
                "libretro-desmume": "0.9.11+git20160819+dfsg1-2+b2",
                "libretro-gambatte": "0.5.0+git20160522+dfsg1-3",
                "libretro-mgba": "0.10.5+dfsg-1",
                "libretro-nestopia": "1.53.0+20250119.git5b56b6b-1",
                "retroarch": "1.20.0+dfsg-2+b1",
            },
        )
        for option in (
            "-DGL=OFF",
            "-DGLES=ON",
            "-DDEINIT_ON_LAUNCH=ON",
            "-DAPPLICATION_UPDATER=OFF",
            "-DVIDEO_HW_DECODING=OFF",
        ):
            self.assertIn(option, self.lock["build"]["cmake_options"])
            self.assertIn(option, self.dockerfile)
        self.assertEqual(self.lock["build"]["patch"]["name"], "idle-frame-pacing.patch")
        self.assertEqual(
            self.lock["build"]["patch"]["sha256"], sha256(ROOT / "idle-frame-pacing.patch")
        )
        self.assertIn("COPY idle-frame-pacing.patch", self.dockerfile)
        self.assertIn('lock["build"]["patch"]', self.builder)
        self.assertIn("getTimeSinceLastInput() >= 1000", self.pacing_patch)
        self.assertIn("getVideoPlayerCount() == 0", self.pacing_patch)
        self.assertIn("SDL_Delay(33)", self.pacing_patch)
        self.assertLess(self.dockerfile.index("retroarch=1.20.0"), self.dockerfile.index("base-sonames"))
        for package, version in self.lock["build"]["accepted_target_packages"].items():
            self.assertIn(f"{package}={version}", self.dockerfile)
        self.assertIn("--format=posix", self.collector)
        self.assertIn("--pax-option=delete=atime,delete=ctime", self.collector)
        self.assertIn("runtime has unresolved shared libraries", self.collector)
        self.assertIn('VERSION"', self.collector)

    def test_runtime_artifact_is_locked_and_matches_when_present(self) -> None:
        artifact = self.lock["artifact"]
        self.assertEqual(artifact["version_output"], "ES-DE 3.4.1 (r51)")
        self.assertIsInstance(artifact["size"], int)
        self.assertGreater(artifact["size"], 1_000_000)
        self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(artifact["es_de_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn(f'RUNTIME_ARCHIVE_SHA256={artifact["sha256"]}', self.installer)
        self.assertIn(f'RUNTIME_ARCHIVE_SIZE={artifact["size"]}', self.installer)
        for script in (self.installer, self.rollback, self.runner):
            self.assertIn(f'ES_DE_SHA256={artifact["es_de_sha256"]}', script)
        path = OUTPUT / artifact["name"]
        if path.exists():
            self.assertEqual(path.stat().st_size, artifact["size"])
            self.assertEqual(sha256(path), artifact["sha256"])

    def test_system_allowlist_uses_only_accepted_cores(self) -> None:
        entries = {node.findtext("name"): node for node in self.systems.findall("system")}
        self.assertEqual(
            set(entries), {"nes", "famicom", "gb", "gbc", "gba", "nds", "neogeo"}
        )
        core_by_system = {
            "nes": "nestopia_libretro.so",
            "famicom": "nestopia_libretro.so",
            "gb": "gambatte_libretro.so",
            "gbc": "gambatte_libretro.so",
            "gba": "mgba_libretro.so",
            "nds": "desmume_libretro.so",
            "neogeo": "/usr/local/libexec/fbneo_neogeo_libretro.so",
        }
        for name, core in core_by_system.items():
            command = entries[name].findtext("command") or ""
            self.assertIn("--config /etc/r46h/retroarch.cfg", command)
            self.assertIn("--appendconfig /etc/r46h/es-de-retroarch.cfg", command)
            self.assertIn(core, command)
            self.assertTrue((entries[name].findtext("path") or "").startswith("%ROMPATH%/"))

    def test_settings_are_read_only_p3_and_low_overhead(self) -> None:
        body = self.settings_text.split("\n", 1)[1]
        root = ET.fromstring(f"<settings>{body}</settings>")
        values = {node.attrib["name"]: node.attrib["value"] for node in root}
        self.assertEqual(values["ROMDirectory"], "/home/ark/ROMs")
        self.assertEqual(values["SaveGamelistsMode"], "never")
        self.assertEqual(values["LegacyGamelistFileLocation"], "true")
        self.assertEqual(values["ApplicationLanguage"], "zh_CN")
        self.assertEqual(values["Theme"], "linear-es-de")
        self.assertEqual(values["ThemeColorScheme"], "oled")
        self.assertEqual(values["ThemeTransitions"], "builtin-slide")
        self.assertEqual(values["MenuOpeningEffect"], "none")
        self.assertEqual(values["MaxVRAM"], "128")
        self.assertEqual(values["ScreensaverTimer"], "0")
        for name in (
            "NavigationSounds",
            "ViewsVideoAudio",
            "MediaViewerVideoAudio",
            "ScreensaverVideoAudio",
        ):
            self.assertEqual(values[name], "false")

    def test_r46h_theme_uses_bounded_visuals_and_motion(self) -> None:
        self.assertEqual(
            [node.text for node in self.theme.findall("include")],
            [
                "./colors.xml",
                "./languages.xml",
                "./system/metadata/_default.xml",
                "./system/metadata/${system.theme}.xml",
                "./system/metadata-custom/_default.xml",
                "./system/metadata-custom/${system.theme}.xml",
            ],
        )
        common = self.theme.find("./variant/view[@name='system, gamelist']")
        system = self.theme.find("./variant/view[@name='system']")
        self.assertIsNotNone(common)
        self.assertIsNotNone(system)
        self.assertEqual(common.find("image[@name='background']/visible").text, "false")
        self.assertEqual(common.find("image[@name='helpsystemPanel']/visible").text, "false")
        self.assertIsNone(common.find("helpsystem"))
        self.assertIsNone(common.find("systemstatus"))
        self.assertIsNone(common.find("clock"))
        carousel = system.find("carousel[@name='systemCarousel']")
        self.assertIsNotNone(carousel)
        self.assertEqual(carousel.findtext("size"), "1 0.34")
        self.assertEqual(carousel.findtext("staticImage"), "./system/systemart/${system.theme}.webp")
        self.assertEqual(carousel.findtext("itemTransitions"), "animate")
        self.assertEqual(carousel.findtext("maxItemCount"), "3")
        self.assertEqual(carousel.findtext("itemScale"), "1.6")
        self.assertEqual(carousel.findtext("fastScrolling"), "false")
        self.assertTrue(self.theme.findall(".//textlist[@name='gamelistTextlist']"))
        self.assertTrue(self.theme.findall(".//image[@name='gameImage']"))
        game_carousel = self.theme.find(
            "./variant[@name='carousel, simpleCarousel']/view[@name='gamelist']/carousel"
        )
        self.assertIsNotNone(game_carousel)
        self.assertEqual(game_carousel.findtext("maxItemCount"), "3")
        self.assertEqual(game_carousel.findtext("itemScale"), "1.6")

    def test_visual_overlay_is_narrow_and_rollbackable(self) -> None:
        installer = (VISUAL / "install.sh").read_text(encoding="utf-8")
        rollback = (VISUAL / "rollback.sh").read_text(encoding="utf-8")
        builder = (VISUAL / "build-payload.sh").read_text(encoding="utf-8")
        new_theme = sha256(ROOT / "r46h-theme.xml")
        self.assertEqual(new_theme, "2816222c88822a900a01bb966c54e27cfe32d7837edf0062d0edaeb70641736b")
        for script in (installer, rollback):
            self.assertIn("c9f931c9-02", script)
            self.assertIn("d3130007-46a4-4d56-9001-000000000007", script)
            self.assertIn("b3ee1b1283b71ace6bd8bcb91d7c67a937c4008ca422269af32ccec82840e7eb", script)
            self.assertIn(new_theme, script)
            self.assertIn("ThemeColorScheme", script)
            self.assertIn("ThemeTransitions", script)
            self.assertIn("systemctl stop r46h-gaming-frontend.service", script)
        self.assertIn("previous-theme.xml", installer)
        self.assertIn("previous-settings.xml", installer)
        self.assertIn("visual-theme.xml", installer)
        self.assertIn("R46H_ES_DE_VISUAL_ROLLBACK result=pass", rollback)
        self.assertIn("settings_current=/run/.r46h-es-de-visual-current-settings.$$", rollback)
        self.assertLess(
            rollback.rindex("transaction_active=0"),
            rollback.index('rm -f -- "$RECEIPT"'),
        )
        self.assertIn("README.md\\nSHA256SUMS\\ninstall.sh\\nr46h-theme.xml\\nrollback.sh", builder)

    def test_media_manifest_is_deterministic_and_rejects_traversal(self) -> None:
        generator = load_generator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system = root / "nes"
            (system / "images").mkdir(parents=True)
            (system / "videos").mkdir()
            (system / "games/sub").mkdir(parents=True)
            (system / "games/sub/demo.nes").write_bytes(b"NES")
            (system / "images/demo.PNG").write_bytes(b"PNG")
            (system / "videos/demo.mp4").write_bytes(b"MP4")
            (system / "gamelist.xml").write_text(
                "<gameList><game><path>./games/sub/demo.nes</path>"
                "<image>./images/demo.PNG</image><video>./videos/demo.mp4</video>"
                "</game></gameList>",
                encoding="utf-8",
            )
            links, missing = generator.generate(root)
            self.assertEqual(missing, 0)
            self.assertEqual(
                links,
                [
                    ("nes/miximages/games/sub/demo.png", "/roms/nes/images/demo.PNG"),
                    ("nes/videos/games/sub/demo.mp4", "/roms/nes/videos/demo.mp4"),
                ],
            )
            (system / "gamelist.xml").write_text(
                "<gameList><game><path>../../escape.nes</path></game></gameList>",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                generator.generate(root)

            (system / "gamelist.xml").write_text(
                "<gameList><game><path>./games/sub/demo.nes</path>"
                "<image>./images/link.png</image></game></gameList>",
                encoding="utf-8",
            )
            (system / "images/link.png").symlink_to("demo.PNG")
            with self.assertRaises(ValueError):
                generator.generate(root)

    def test_media_manifest_can_append_successor_systems(self) -> None:
        generator = load_generator()
        self.assertEqual(
            generator.SYSTEMS,
            ("nes", "famicom", "gb", "gbc", "gba", "nds", "neogeo"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nes").mkdir()
            system = root / "cps1"
            (system / "media/images").mkdir(parents=True)
            (system / "demo.zip").write_bytes(b"ZIP")
            (system / "media/images/demo.png").write_bytes(b"PNG")
            (system / "gamelist.xml").write_text(
                "<gameList><game><path>./demo.zip</path>"
                "<image>./media/images/demo.png</image></game></gameList>",
                encoding="utf-8",
            )
            links, missing = generator.generate(root, ("nes", "cps1"))
            self.assertEqual(missing, 0)
            self.assertEqual(
                links,
                [("cps1/miximages/demo.png", "/roms/cps1/media/images/demo.png")],
            )
            for systems in (("../cps1",), ("cps1", "./cps1")):
                with self.assertRaises(ValueError):
                    generator.generate(root, systems)

    def test_runtime_archive_matches_target_path_contract(self) -> None:
        path = OUTPUT / self.lock["artifact"]["name"]
        if not path.exists():
            self.skipTest("runtime artifact is not built")
        with tarfile.open(path, "r:gz") as bundle:
            names = [member.name for member in bundle.getmembers()]
        self.assertTrue(names)
        self.assertTrue(
            all(
                name in ("opt", "opt/", "opt/r46h", "opt/r46h/")
                or name == "opt/r46h/es-de"
                or name.startswith("opt/r46h/es-de/")
                for name in names
            )
        )
        self.assertIn('$0 != "opt/" && $0 != "opt/r46h/"', self.installer)

    def test_assembled_payload_manifest_matches(self) -> None:
        manifest = OUTPUT / "SHA256SUMS"
        if not manifest.exists():
            self.skipTest("payload is not assembled")
        expected = {
            "README.md", "es-de-retroarch.cfg", "es_settings.xml", "es_systems.xml",
            "install.sh", "legacy-media-links.tsv", self.lock["artifact"]["name"],
            "r46h-es-de-ui", "r46h-gaming-frontend.service", "rollback.sh",
            "r46h-theme.xml", "system-links.tsv",
        }
        self.assertEqual({path.name for path in OUTPUT.iterdir()}, expected | {"SHA256SUMS"})
        entries = {}
        for line in manifest.read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            entries[name] = digest
        self.assertEqual(set(entries), expected)
        for name, digest in entries.items():
            path = OUTPUT / name
            self.assertEqual(sha256(path), digest)

    def test_launcher_owns_kms_audio_input_and_cleanup(self) -> None:
        for token in (
            "SDL_VIDEODRIVER=kmsdrm",
            "SDL_AUDIODRIVER=alsa",
            "SDL_GAMECONTROLLERCONFIG",
            "LD_LIBRARY_PATH=/opt/r46h/es-de/lib/aarch64-linux-gnu",
            "--resolution 1024 768 --no-splash",
            "06004e84465200004800000001000000,R46H Combined Gamepad",
            "BASE_RECEIPT_SHA256=8acac2c8b8e4295c0235ad1fc7e396e341dcc4b1ba771a053355a98cf8fb73ec",
            "FBNEO_CORE_SHA256=8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb",
            "FBNEO_OPTIONS_SHA256=4e67299bc6c37cd1ebdfca4e6a42110d5071c62d00e714b952b906ca1fa68976",
            "findmnt -rn -o PARTUUID /",
            "findmnt -rn -o UUID /",
            "findmnt -rn -o OPTIONS /roms",
            "cset \"numid=$MUX_CONTROL\" \"$saved_mux\"",
            "stop_launcher_group",
        ):
            self.assertIn(token, self.runner)
        append_config = (ROOT / "es-de-retroarch.cfg").read_text()
        self.assertIn('input_exit_emulator_btn = "9"', append_config)
        self.assertIn('user_language = "12"', append_config)
        self.assertIn(
            'core_options_path = "/home/ark/.config/retroarch/r46h-es-de-core-options.cfg"',
            append_config,
        )
        self.assertIn('global_core_options = "true"', append_config)
        self.assertIn('game_specific_options = "false"', append_config)
        self.assertIn("ES_CORE_OPTIONS=/home/ark/.config/retroarch/r46h-es-de-core-options.cfg", self.runner)
        self.assertIn("ES-DE core options metadata is unsafe", self.runner)
        for token in (
            "DroidSansFallbackFull.ttf",
            "chinese-fallback-font.ttf",
            "RetroArch Chinese font alias changed",
        ):
            self.assertIn(token, self.runner)
        self.assertNotIn("TO_BE_LOCKED", self.runner)

    def test_transaction_is_p2_only_and_restores_ozone(self) -> None:
        for text in (self.installer, self.rollback):
            for forbidden in ("/boot", "boot.ini", "/dev/disk", "mkfs", "saveenv"):
                self.assertNotIn(forbidden, text)
            for token in (
                "EXPECTED_ROOT_PARTUUID=c9f931c9-02",
                "EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007",
                "OZONE_RECEIPT_SHA256=8acac2c8b8e4295c0235ad1fc7e396e341dcc4b1ba771a053355a98cf8fb73ec",
                "PREVIOUS_UNIT_SHA256=2fec9c8cb0be8ee724c5e9d44d78971ab83e57a4d5cbba9d3931d457262ff9ed",
                "SYSTEM_LINKS_SHA256=bd5e496ab9bb54f0b9d45b461262b70fd5758d763ea4ff4fb9d06c26c936d73d",
                "MEDIA_LINKS_SHA256=9358e316d0b5436108c4a460a6654c5437341e4c85b86dcc2d5ae32abfbb9a9f",
                "findmnt -rn -o OPTIONS /roms",
                "EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count",
            ):
                self.assertIn(token, text)
            self.assertNotIn("TO_BE_LOCKED", text)
        runner_sha256 = sha256(ROOT / "r46h-es-de-ui")
        append_sha256 = sha256(ROOT / "es-de-retroarch.cfg")
        self.assertIn(f"RUNNER_SHA256={runner_sha256}", self.installer)
        self.assertIn(f"RUNNER_SHA256={runner_sha256}", self.rollback)
        self.assertIn(f"RETROARCH_APPEND_SHA256={append_sha256}", self.installer)
        self.assertIn(f"RETROARCH_APPEND_SHA256={append_sha256}", self.rollback)
        self.assertIn(f"RETROARCH_APPEND_SHA256={append_sha256}", self.runner)
        theme_sha256 = sha256(ROOT / "r46h-theme.xml")
        settings_sha256 = sha256(ROOT / "es_settings.xml")
        self.assertIn(f"SETTINGS_SHA256={settings_sha256}", self.installer)
        self.assertIn(f"THEME_SHA256={theme_sha256}", self.installer)
        self.assertIn('"$PAYLOAD_DIR/r46h-theme.xml:$THEME_SHA256"', self.installer)
        self.assertIn('"$runtime_tree/$THEME_RELATIVE"', self.installer)
        self.assertIn(f"ROLLBACK_SHA256={sha256(ROOT / 'rollback.sh')}", self.installer)
        self.assertIn("cjk_alias_installed=1", self.installer)
        self.assertIn('install -o ark -g ark -m 0600 "$FBNEO_OPTIONS" "$ES_CORE_OPTIONS"', self.installer)
        self.assertIn("core_options_seeded=$core_options_seeded", self.installer)
        self.assertNotIn('rm -f -- "$ES_CORE_OPTIONS"', self.rollback)
        self.assertIn('rm -f -- "$CJK_ALIAS"', self.rollback)
        self.assertIn("automatic restore incomplete", self.installer)
        self.assertIn("runtime cannot execute on the accepted p2", self.installer)
        self.assertIn("unsafe payload directory identity", self.installer)
        self.assertIn("unexpected payload member set", self.installer)
        self.assertIn("unsafe payload member identity", self.installer)
        self.assertIn("appdata=preserved", self.rollback)
        self.assertIn("find \"$RUNTIME\" -depth -delete", self.rollback)
        self.assertIn("ExecStart=/usr/local/sbin/r46h-es-de-ui", self.unit)
        self.assertNotIn("r46h-game-ui menu", self.unit)

    def test_scripts_parse(self) -> None:
        for path in (
            ROOT / "collect-runtime.sh",
            ROOT / "r46h-es-de-ui",
            ROOT / "install.sh",
            ROOT / "rollback.sh",
        ):
            subprocess.run(["bash", "-n", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
