#!/usr/bin/env python3
"""Focused host gates for the R46H Ozone and FBNeo Metal Slug candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import subprocess
import unittest
import zipfile


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-ozone-fbneo"
BASE = REPO / "mainline/gaming-mvp"
RETAINED_ROM_DIR = (
    REPO
    / "mainline/out/.cache/r46h-original-card-import-20260826/easyroms/neogeo"
)
GENERATED_CORE = (
    REPO
    / "mainline/out/r46h-gaming-ozone-fbneo-v0.1/fbneo_neogeo_libretro.so"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OzoneFBNeoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = (ROOT / "retroarch.cfg").read_text(encoding="utf-8")
        cls.runner = (ROOT / "r46h-game-ui").read_text(encoding="utf-8")
        cls.volume_helper = (ROOT / "r46h-volume-keys").read_text(encoding="utf-8")
        cls.volume_unit = (ROOT / "r46h-volume-keys.service").read_text(encoding="utf-8")
        cls.core_options = (ROOT / "FinalBurn Neo (neogeo subset).opt").read_text(
            encoding="utf-8"
        )
        cls.installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        cls.rollback = (ROOT / "rollback.sh").read_text(encoding="utf-8")
        cls.builder = (ROOT / "build-core.py").read_text(encoding="utf-8")
        cls.remote_runbook = (REPO / "mainline/gaming-remote-screen/README.md").read_text(
            encoding="utf-8"
        )
        cls.playlist = json.loads((ROOT / "SNK - Neo Geo.lpl").read_text(encoding="utf-8"))
        cls.lock = json.loads((ROOT / "source-lock.json").read_text(encoding="utf-8"))

    def test_config_is_exact_base_with_ozone_gl_and_content_root(self) -> None:
        expected = (BASE / "retroarch.cfg").read_text(encoding="utf-8").replace(
            'menu_driver = "rgui"', 'menu_driver = "ozone"', 1
        ).replace(
            'video_driver = "sdl2"', 'video_driver = "gl"', 1
        ).replace(
            'rgui_browser_directory = "/roms"',
            'rgui_browser_directory = "/roms"\ncontent_directory = "/roms"',
            1,
        )
        self.assertEqual(self.config, expected)
        self.assertEqual(self.config.count('menu_driver = "ozone"'), 1)
        self.assertNotIn('menu_driver = "rgui"', self.config)
        self.assertEqual(self.config.count('video_driver = "gl"'), 1)
        self.assertNotIn('video_driver = "sdl2"', self.config)

    def test_playlist_is_one_direct_metal_slug_entry(self) -> None:
        self.assertEqual(
            self.playlist,
            {
                "version": "1.0",
                "items": [
                    {
                        "path": "/roms/neogeo/mslug.zip",
                        "label": "Metal Slug",
                        "core_path": "/usr/local/libexec/fbneo_neogeo_libretro.so",
                        "core_name": "FinalBurn Neo (neogeo subset)",
                        "crc32": "DETECT",
                        "db_name": "FBNeo - Arcade Games.lpl",
                    }
                ],
            },
        )

    def test_runner_adds_one_hash_bound_fbneo_mode(self) -> None:
        for token in (
            "fbneo-mslug",
            "FBNEO_CORE=/usr/local/libexec/fbneo_neogeo_libretro.so",
            "MSLUG_ROM=/roms/neogeo/mslug.zip",
            "MSLUG_BIOS=/roms/neogeo/neogeo.zip",
            "FBNEO_CORE_SHA256=8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb",
            "MSLUG_ROM_SHA256=3ebe7ca4166f956a65ae98d86f9172f8b5d4462efa13723a5ea72fcf59adcbf8",
            "MSLUG_BIOS_SHA256=d2d8ab5d5fc5ce41978e40c8db2984d8dd0a37e60c712e20961b80fdbb4c9936",
            "CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835",
            "FEATURE_RECEIPT=/var/lib/r46h/gaming-ozone-fbneo-v0.1-installed",
            'grep -Fqx "config_sha256=$CONFIG_SHA256" "$FEATURE_RECEIPT"',
            "Ozone/FBNeo config identity mismatch",
            'required_mode_paths=("$FBNEO_CORE" "$MSLUG_ROM" "$MSLUG_BIOS")',
            'retroarch_arguments=(-L "$FBNEO_CORE" "$MSLUG_ROM")',
            '[[ ",$(findmnt -rn -o OPTIONS /roms)," == *,ro,* ]]',
            "renderer=$PRODUCT_RENDERER",
            "CORE_OPTIONS_SHA256=4e67299bc6c37cd1ebdfca4e6a42110d5071c62d00e714b952b906ca1fa68976",
            'grep -Fqx "core_options_sha256=$CORE_OPTIONS_SHA256" "$FEATURE_RECEIPT"',
        ):
            self.assertIn(token, self.runner)
        self.assertNotIn("HAVE_NEON", self.runner)
        for forbidden in ("GAME_VOLUME", "VOLUME_CONTROL", "saved_volume"):
            self.assertNotIn(forbidden, self.runner)
        self.assertIn('cset "numid=$MUX_CONTROL" "$GAME_MUX"', self.runner)
        self.assertIn('cset "numid=$MUX_CONTROL" "$saved_mux"', self.runner)

    def test_unibios_masks_garbage_boot_and_volume_is_persistent(self) -> None:
        options = dict(
            line.split(" = ", 1) for line in self.core_options.splitlines() if line
        )
        self.assertEqual(len(options), 47)
        self.assertEqual(options["fbneo-neogeo-mode"], '"UNIBIOS"')
        self.assertEqual(options["fbneo-dipswitch-mslug-Unibios_mode"], '"MVS"')
        self.assertEqual(options["fbneo-allow-depth-32"], '"enabled"')
        for token in (
            "StateDirectory=r46h-volume",
            "StateDirectoryMode=0700",
            "ProtectSystem=strict",
            "User=ark",
        ):
            self.assertIn(token, self.volume_unit)
        for token in (
            "STATE_FILE=$STATE_DIR/level",
            "read_saved_level",
            "persist_level",
            '/usr/bin/mktemp "$STATE_DIR/.level.XXXXXX"',
            '"$(/usr/bin/stat -c \'%u:%g:%a:%h\' "$STATE_FILE")" == 1000:1000:600:1',
            "reason=invalid-saved-level",
            "saved=yes",
        ):
            self.assertIn(token, self.volume_helper)
        self.assertLess(
            self.volume_helper.index('set_level "$next"'),
            self.volume_helper.index('persist_level "$next"'),
        )

    def test_source_build_and_artifact_are_fully_pinned(self) -> None:
        self.assertEqual(self.lock["schema_version"], 1)
        self.assertEqual(
            self.lock["source"],
            {
                "repository": "https://github.com/libretro/FBNeo.git",
                "commit": "26f11fa9e43227a04953e20e8c7e4bf322cd53cb",
                "tree": "b39288c23cadb273a1f02a558687ce5cc6952241",
                "archive_url": "https://github.com/libretro/FBNeo/archive/26f11fa9e43227a04953e20e8c7e4bf322cd53cb.tar.gz",
                "archive_name": "fbneo-26f11fa9e43227a04953e20e8c7e4bf322cd53cb.tar.gz",
                "archive_size": 27119884,
                "archive_sha256": "f8050abc47cd99b46e828aabdbbdba568a4a4122d9c0ce4e0469d1596263d7f1",
                "source_date_epoch": 1787855716,
                "git_version": "26f11fa",
                "git_date": "260827",
            },
        )
        self.assertEqual(self.lock["build"]["make_arguments"], ["SUBSET=neogeo", "REGEN_HEADERS=1"])
        self.assertEqual(
            self.lock["build"]["container_image_id"],
            "sha256:3686fd20408cf746c1171e9345fd6c842a71f87e589f691b2455435b3bdd141a",
        )
        self.assertEqual(
            self.lock["artifact"]["sha256"],
            "8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb",
        )
        self.assertNotIn("HAVE_NEON", self.builder)
        self.assertIn('"SOURCE_DATE_EPOCH=', self.builder)
        self.assertEqual(list(ROOT.glob("*.so")), [])

    def test_transaction_is_exact_v07_p2_only_and_recoverable(self) -> None:
        expected_hashes = {
            "BASE_RECEIPT_SHA256": "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314",
            "BASE_CONFIG_SHA256": sha256(BASE / "retroarch.cfg"),
            "CONFIG_SHA256": sha256(ROOT / "retroarch.cfg"),
            "BASE_RUNNER_SHA256": sha256(BASE / "r46h-game-ui"),
            "RUNNER_SHA256": sha256(ROOT / "r46h-game-ui"),
            "BASE_VOLUME_HELPER_SHA256": sha256(BASE / "r46h-volume-keys"),
            "VOLUME_HELPER_SHA256": sha256(ROOT / "r46h-volume-keys"),
            "BASE_VOLUME_UNIT_SHA256": sha256(BASE / "r46h-volume-keys.service"),
            "VOLUME_UNIT_SHA256": sha256(ROOT / "r46h-volume-keys.service"),
            "CORE_OPTIONS_SHA256": sha256(ROOT / "FinalBurn Neo (neogeo subset).opt"),
            "CORE_SHA256": self.lock["artifact"]["sha256"],
            "PLAYLIST_SHA256": sha256(ROOT / "SNK - Neo Geo.lpl"),
            "LICENSE_SHA256": sha256(ROOT / "FBNEO-LICENSE.txt"),
            "ROLLBACK_SHA256": sha256(ROOT / "rollback.sh"),
            "CORE_INFO_SHA256": "2ba4587c30b2c1a81f76325cce4a04305f72869bf5280d6a3c3c7d7cea51142c",
            "MSLUG_ROM_SHA256": "3ebe7ca4166f956a65ae98d86f9172f8b5d4462efa13723a5ea72fcf59adcbf8",
            "NEOGEO_BIOS_SHA256": "d2d8ab5d5fc5ce41978e40c8db2984d8dd0a37e60c712e20961b80fdbb4c9936",
        }
        for name, digest in expected_hashes.items():
            marker = f"readonly {name}={digest}"
            with self.subTest(name=name):
                self.assertIn(marker, self.installer)
                if name not in ("BASE_RECEIPT_SHA256", "ROLLBACK_SHA256"):
                    self.assertIn(marker, self.rollback)
        for token in (
            "EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007",
            "remote-screen candidate must be rolled back",
            "unexpected payload member set",
            "state_published",
            "automatic restore failed",
            "frontend_was_active",
            "frontend restart count changed",
            "Ozone Neo Geo icon is missing",
            "hard-linked rollback state member",
            "installed FBNeo license directory identity is unsafe",
            "volume service must be active for the guarded update",
            "candidate volume state identity is unsafe",
            '"$(stat -c \'%u:%g:%a\' /home/ark/.config)" == 0:0:755',
            "19",
        ):
            self.assertIn(token, self.installer)
        for forbidden in (
            "/boot",
            "boot.ini",
            "/dev/disk",
            "saveenv",
            "mkfs",
            "dd if=",
            "curl ",
            "wget ",
        ):
            self.assertNotIn(forbidden, self.installer)
            self.assertNotIn(forbidden, self.rollback)
        self.assertLess(
            self.installer.index("validate_runtime_inputs\n\nif [[ -e \"$RECEIPT\""),
            self.installer.index("PASS: R46H Ozone/FBNeo v0.1 is already installed"),
        )
        self.assertIn("frontend_stable_polls >= 20", self.rollback)
        self.assertLess(
            self.rollback.index("systemctl start r46h-gaming-frontend.service"),
            self.rollback.index('rm -f -- "$RECEIPT"'),
        )

    def test_remote_screen_is_rebased_without_replacing_accepted_ozone(self) -> None:
        remote_runbook = " ".join(self.remote_runbook.split())
        for token in (
            "HOST + TARGET + PHYSICAL PASS / STRICT SSH PASS",
            "instead of modifying RetroArch",
            "It does not change BOOT, kernel, packages, p3, ROMs, RetroArch configuration, the Ozone launcher",
            "Neither operation stops or restarts the frontend",
            "First product acceptance",
        ):
            self.assertIn(token, remote_runbook)
        self.assertNotIn("stdin FIFO", remote_runbook)

    def test_shell_and_python_entry_points_are_valid_and_executable(self) -> None:
        for name in ("install.sh", "rollback.sh", "r46h-game-ui", "r46h-volume-keys"):
            path = ROOT / name
            with self.subTest(name=name):
                self.assertEqual(
                    subprocess.run(["/bin/bash", "-n", str(path)], check=False).returncode,
                    0,
                )
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((ROOT / "r46h-volume-keys.service").stat().st_mode), 0o644)
        self.assertEqual(
            stat.S_IMODE((ROOT / "FinalBurn Neo (neogeo subset).opt").stat().st_mode),
            0o644,
        )
        builder = ROOT / "build-core.py"
        compile(self.builder, str(builder), "exec")
        self.assertEqual(stat.S_IMODE(builder.stat().st_mode), 0o755)

    @unittest.skipUnless(RETAINED_ROM_DIR.is_dir(), "retained original-card ROM fixture is unavailable")
    def test_retained_metal_slug_rom_is_the_pinned_fbneo_set(self) -> None:
        rom = RETAINED_ROM_DIR / "mslug.zip"
        bios = RETAINED_ROM_DIR / "neogeo.zip"
        self.assertEqual(sha256(rom), "3ebe7ca4166f956a65ae98d86f9172f8b5d4462efa13723a5ea72fcf59adcbf8")
        self.assertEqual(sha256(bios), "d2d8ab5d5fc5ce41978e40c8db2984d8dd0a37e60c712e20961b80fdbb4c9936")
        expected = {
            "201-c1.c1": (4194304, 0x72813676),
            "201-c2.c2": (4194304, 0x96F62574),
            "201-c3.c3": (4194304, 0x5121456A),
            "201-c4.c4": (4194304, 0xF4AD59A3),
            "201-m1.m1": (131072, 0xC28B3253),
            "201-p1.p1": (2097152, 0x08D8DAA5),
            "201-s1.s1": (131072, 0x2F55958D),
            "201-v1.v1": (4194304, 0x23D22ED1),
            "201-v2.v2": (4194304, 0x472CF9DB),
        }
        with zipfile.ZipFile(rom) as archive:
            actual = {item.filename: (item.file_size, item.CRC) for item in archive.infolist()}
        self.assertEqual(actual, expected)

    def test_generated_core_matches_lock_when_present(self) -> None:
        if not GENERATED_CORE.exists():
            self.skipTest("generated FBNeo core is unavailable")
        self.assertEqual(GENERATED_CORE.stat().st_size, self.lock["artifact"]["size"])
        self.assertEqual(sha256(GENERATED_CORE), self.lock["artifact"]["sha256"])
        self.assertEqual(GENERATED_CORE.read_bytes()[:4], b"\x7fELF")

    def test_full_upstream_license_accompanies_the_core(self) -> None:
        license_path = ROOT / "FBNEO-LICENSE.txt"
        self.assertEqual(
            sha256(license_path),
            "bb2369f1b75f42242968a78191b47ee90f85682224d3ad1ef63044e244b3e202",
        )
        license_text = license_path.read_text(encoding="utf-8", errors="replace")
        self.assertIn("You may not sell, lease, rent", license_text)
        self.assertIn("You must include, verbatim, the full text of this license", license_text)
        self.assertIn("legal right to distribute them", license_text)


if __name__ == "__main__":
    unittest.main()
