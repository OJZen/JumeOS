#!/usr/bin/env python3
"""Focused host tests for the fast Debian-native gaming MVP."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-mvp"
BUILDER = REPO / "mainline/scripts/build-r46h-gaming-mvp.py"
ROM_BUILDER = ROOT / "build-r46h-nes-smoke.py"
RUNBOOK = REPO / "mainline/bringup-tests/GAMING-PRODUCT.md"


def load_builder():
    spec = importlib.util.spec_from_file_location("r46h_gaming_mvp", BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load gaming MVP builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_builder()


def load_rom_builder():
    spec = importlib.util.spec_from_file_location("r46h_nes_smoke", ROM_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load NES smoke builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROM_MODULE = load_rom_builder()


class GamingMvpTests(unittest.TestCase):
    def test_payload_identity_advances_without_overwriting_v05_output(self) -> None:
        self.assertEqual(MODULE.PAYLOAD_ID, "r46h-gaming-mvp-v0.6")
        self.assertEqual(MODULE.ARCHIVE_NAME, "r46h-gaming-mvp-v0.6.tar.gz")
        self.assertEqual(MODULE.RELEASE_ROOT.name, "r46h-gaming-mvp-v0.6")
        self.assertEqual(
            MODULE.FSTAB_SHA256,
            "390d3e67cfaa42aa2781b06c0bb167cae961034d22563584c58ae57e0d5cada5",
        )
        fstab_path = REPO / "mainline/rootfs-debian13/overlay/etc/fstab"
        self.assertEqual(MODULE.sha256_file(fstab_path), MODULE.FSTAB_SHA256)
        fstab = fstab_path.read_text(encoding="utf-8")
        self.assertIn(
            "PARTUUID=c9f931c9-03 /roms exfat ro,noauto,nofail 0 0", fstab
        )

    def test_original_nes_rom_is_deterministic_and_structurally_valid(self) -> None:
        rom = ROM_MODULE.build_rom()
        self.assertEqual(len(rom), 24_592)
        self.assertEqual(rom[:16], b"NES\x1a\x01\x01" + b"\x00" * 10)
        self.assertEqual(
            MODULE.sha256_bytes(rom),
            "f4e911f38aade8353853127e5e45b91aef1333061bdf865ec1775236e72abb0c",
        )
        self.assertEqual(rom[16 + 0x3FFA : 16 + 0x4000], b"\xbe\xc0\x00\xc0\x44\xc1")
        self.assertIn(b"\x8d\x16\x40", rom[: 16 + 0x4000])
        self.assertIn(b"\x8d\x14\x40", rom[: 16 + 0x4000])

    def test_nes_rom_publisher_is_no_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "r46h-nes-smoke.nes"
            ROM_MODULE.write_new(output, ROM_MODULE.build_rom())
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)
            with self.assertRaisesRegex(ValueError, "output already exists"):
                ROM_MODULE.write_new(output, ROM_MODULE.build_rom())

    def test_package_set_is_small_sorted_and_debian_native(self) -> None:
        packages = (ROOT / "packages.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(packages, sorted(set(packages)))
        self.assertEqual(
            packages,
            [
                "kbd",
                "libretro-desmume",
                "libretro-gambatte",
                "libretro-mgba",
                "libretro-nestopia",
                "retroarch",
            ],
        )
        self.assertFalse(any("mali" in package.lower() for package in packages))

    def test_docker_build_is_pinned_and_download_only(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertEqual(dockerfile.count("FROM ${BASE_IMAGE}"), 2)
        self.assertIn(MODULE.BASE_IMAGE, dockerfile)
        self.assertIn("--download-only --no-install-recommends", dockerfile)
        self.assertIn("retroarch-dev", dockerfile)
        self.assertIn("-Wl,--build-id=none", dockerfile)

    def test_smoke_core_exercises_video_audio_and_input(self) -> None:
        source = (ROOT / "r46h-smoke-core.c").read_text(encoding="utf-8")
        for symbol in (
            "retro_run",
            "retro_load_game",
            "RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME",
            "RETRO_PIXEL_FORMAT_XRGB8888",
            "audio_batch_callback",
            "RETRO_DEVICE_ID_JOYPAD_A",
            "RETRO_DEVICE_ID_JOYPAD_LEFT",
            "RETRO_DEVICE_INDEX_ANALOG_LEFT",
            "RETRO_DEVICE_INDEX_ANALOG_RIGHT",
            "RETRO_DEVICE_ID_ANALOG_X",
            "RETRO_DEVICE_ID_ANALOG_Y",
        ):
            self.assertIn(symbol, source)
        self.assertIn("static const uint32_t colors[8]", source)
        self.assertIn('info->library_version = "1.1"', source)
        self.assertIn("color = 0x0000ffffU", source)
        self.assertIn("color = 0x00ff00ffU", source)
        self.assertEqual(source.count("RETRO_DEVICE_ANALOG"), 1)
        self.assertEqual(source.count("analog(RETRO_DEVICE_INDEX_ANALOG_LEFT"), 2)
        self.assertEqual(source.count("analog(RETRO_DEVICE_INDEX_ANALOG_RIGHT"), 2)
        self.assertIn("440U", source)

    def test_product_reuses_the_physically_accepted_bridge_source(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY gaming-input-bridge/r46h-input-bridge.c", dockerfile)
        self.assertIn("r46h-gaming-input-bridge-v0.5", dockerfile)
        self.assertIn(
            "mainline/gaming-input-bridge/r46h-input-bridge.c",
            MODULE.SOURCE_PATHS,
        )

    def test_storage_audit_is_read_only_and_explicit_about_a2_limit(self) -> None:
        audit = (ROOT / "r46h-storage-audit").read_text(encoding="utf-8")
        for token in (
            "mmc0:0001",
            'read_hex_register "$CARD/cid" 32',
            'read_hex_register "$CARD/ssr" 128',
            "actual clock:",
            "a2_label=not-machine-verifiable",
            "a2_command_queue=not-available",
            "EXT4_ERRORS",
        ):
            self.assertIn(token, audit)
        for forbidden in ("dd ", "fio", "mkfs", "discard", "> \"$CARD", "saveenv"):
            self.assertNotIn(forbidden, audit)
        self.assertEqual(audit.count("-F':[[:space:]]*'"), 2)
        ios = (
            "clock:\t\t150000000 Hz\n"
            "actual clock:\t150000000 Hz\n"
            "timing spec:\t6 (sd uhs SDR104)\n"
        )
        timing = subprocess.run(
            [
                "/usr/bin/awk",
                "-F:[[:space:]]*",
                "/^timing spec:/ {print $2; found=1} END {exit found ? 0 : 1}",
            ],
            input=ios,
            text=True,
            capture_output=True,
            check=True,
        )
        clock = subprocess.run(
            [
                "/usr/bin/awk",
                "-F:[[:space:]]*",
                (
                    "/^actual clock:/ {value=$2; sub(/ .*/, \"\", value); "
                    "print value; found=1} END {exit found ? 0 : 1}"
                ),
            ],
            input=ios,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(timing.stdout, "6 (sd uhs SDR104)\n")
        self.assertEqual(clock.stdout, "150000000\n")
        self.assertEqual(
            subprocess.run(["/bin/bash", "-n", str(ROOT / "r46h-storage-audit")], check=False).returncode,
            0,
        )

    def test_retroarch_configuration_uses_native_stack(self) -> None:
        config = (ROOT / "retroarch.cfg").read_text(encoding="utf-8")
        for setting in (
            'menu_driver = "rgui"',
            'video_driver = "sdl2"',
            'audio_driver = "alsa"',
            'audio_device = "hw:0,0"',
            'input_driver = "udev"',
            'input_joypad_driver = "udev"',
            'input_autodetect_enable = "false"',
            'input_player1_joypad_index = "1"',
            'input_player1_a_btn = "1"',
            'input_player1_select_btn = "8"',
            'input_player1_start_btn = "9"',
            'input_player1_up_btn = "10"',
            'input_player1_down_btn = "11"',
            'input_player1_left_btn = "12"',
            'input_player1_right_btn = "13"',
            'input_player1_up_axis = "nul"',
            'input_player1_down_axis = "nul"',
            'input_player1_left_axis = "nul"',
            'input_player1_right_axis = "nul"',
            'input_player1_l_x_plus_axis = "+0"',
            'input_player1_r_y_minus_axis = "-3"',
            'input_player1_analog_dpad_mode = "0"',
            'input_enable_hotkey_btn = "8"',
            'input_menu_toggle_btn = "2"',
            'content_history_directory = "/home/ark/.local/share/retroarch"',
        ):
            self.assertIn(setting, config)
        self.assertNotIn("input_volume_up", config)
        self.assertNotIn("input_volume_down", config)
        self.assertNotIn('video_driver = "gl"', config)
        self.assertNotIn("libMali", config)

    def test_installer_is_a_narrow_transactional_v05_upgrade(self) -> None:
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("EXPECTED_RUNNING_RELEASE=6.12.99-r46h-mainline-v0.15", installer)
        self.assertIn("/var/lib/r46h/gaming-mvp-v0.6-installed", installer)
        self.assertIn("/var/lib/r46h/gaming-mvp-v0.5-installed", installer)
        self.assertIn("/var/lib/r46h/gaming-mvp-v0.6-rollback", installer)
        for digest in (
            "5cdfa424a28858a91e0344f0544e962c5aa0258bb3a7ea41db76df16c77da5d1",
            "3db31b4c205f98377a56822320f2c63dabce685387becdcb4824fec092ce3133",
            "888a44d822030430924b012c81069c117c842e17a5173711d6a85e7d351b6031",
            "fdf2be72c5c12c57e48a3082a51ecc8b6da09188a627ceece698b0d481d7d3db",
        ):
            self.assertIn(digest, installer)
        self.assertIn("unexpected gaming receipt metadata", installer)
        self.assertIn("target fstab mismatch", installer)
        self.assertIn("files/fstab", installer)
        self.assertIn("mounted /roms is writable", installer)
        self.assertIn("gaming frontend must be inactive before install", installer)
        self.assertIn("RetroArch is still running", installer)
        self.assertIn("dpkg-query", installer)
        self.assertNotIn("apt-get", installer)
        self.assertLess(
            installer.index("renderer upgrade is already installed"),
            installer.index("gaming frontend must be inactive before install"),
        )
        self.assertLess(
            installer.index("gaming frontend must be inactive before install"),
            installer.index("install -o root -g root -m 0755 files/r46h-game-ui"),
        )
        self.assertLess(
            installer.index('mv -- "$state_stage" "$ROLLBACK_STATE"'),
            installer.index("rollback_needed=1"),
        )
        self.assertLess(
            installer.index('mv -f -- "$condition_stage" "$CONDITION"'),
            installer.index('mv -f -- "$receipt_stage" "$RECEIPT"'),
        )
        self.assertLess(
            installer.index('mv -f -- "$receipt_stage" "$RECEIPT"'),
            installer.index('"$CONDITION" || die'),
        )
        for changed in (
            "files/r46h-game-ui",
            "files/r46h-gaming-frontend-condition",
            "files/GAMING-PRODUCT.md",
        ):
            self.assertIn(changed, installer)
        for unchanged in (
            "files/r46h-smoke-libretro.so",
            "files/r46h-nes-smoke.nes",
            "files/r46h-input-bridge",
            "files/r46h-storage-audit",
            "files/r46h-volume-keys",
            "files/retroarch.cfg",
        ):
            self.assertNotIn(unchanged, installer)
        self.assertIn("R46H_GAMING_V06_ROLLBACK result=pass", installer)
        self.assertIn("gaming receipt package manifest mismatch", installer)
        self.assertIn("gaming receipt payload manifest mismatch", installer)
        self.assertIn("rollback state checksum mismatch", installer)
        self.assertIn("if (( staging_started == 1 ))", installer)
        self.assertIn("if (( state_stage_created == 1 ))", installer)
        self.assertLess(
            installer.index("staging or rollback path already exists"),
            installer.index("staging_started=1", installer.index("staging or rollback path already exists")),
        )
        self.assertIn("stat -c '%u:%g:%a:%h'", installer)
        for forbidden in ("/boot", "boot.ini", "saveenv", "mkfs", "dd if=", "curl ", "wget "):
            self.assertNotIn(forbidden, installer)

    def test_input_volume_and_frontend_services_are_ordered_and_bounded(self) -> None:
        unit = (ROOT / "r46h-gaming-frontend.service").read_text(encoding="utf-8")
        input_unit = (ROOT / "r46h-gaming-input.service").read_text(encoding="utf-8")
        volume_unit = (ROOT / "r46h-volume-keys.service").read_text(encoding="utf-8")
        volume_keys = (ROOT / "r46h-volume-keys").read_text(encoding="utf-8")
        waiter = (ROOT / "r46h-gaming-input-ready").read_text(encoding="utf-8")
        condition = (ROOT / "r46h-gaming-frontend-condition").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "ExecCondition=/usr/local/libexec/r46h-gaming-frontend-condition",
            unit,
        )
        self.assertIn("ExecStart=/usr/local/sbin/r46h-game-ui menu", unit)
        self.assertIn("Requires=r46h-gaming-input.service", unit)
        self.assertIn("Wants=getty@tty1.service r46h-volume-keys.service", unit)
        self.assertIn("RequiresMountsFor=/roms", unit)
        self.assertIn(
            "After=systemd-user-sessions.service getty@tty1.service "
            "r46h-gaming-input.service r46h-volume-keys.service",
            unit,
        )
        self.assertIn("KillMode=mixed", unit)
        self.assertIn("TimeoutStopSec=10s", unit)
        self.assertIn("Restart=no", unit)
        self.assertIn("WantedBy=multi-user.target", unit)
        self.assertNotIn("ExecStartPre=/bin/sh", unit)
        self.assertIn("6.12.99-r46h-mainline-v0.15-gaming-product", condition)
        self.assertIn("/var/lib/r46h/gaming-mvp-v0.6-installed", condition)
        self.assertIn("0:600:1", condition)
        self.assertIn("payload_id=r46h-gaming-mvp-v0.6", condition)
        self.assertIn("target_release=$EXPECTED_RELEASE", condition)
        self.assertIn("ExecStartPre=/usr/local/libexec/r46h-input-bridge --check", input_unit)
        self.assertIn("ExecStart=/usr/local/libexec/r46h-input-bridge", input_unit)
        self.assertIn("ExecStartPost=/usr/local/libexec/r46h-gaming-input-ready", input_unit)
        self.assertIn("Restart=on-failure", input_unit)
        self.assertIn("ProtectSystem=strict", input_unit)
        self.assertIn("User=ark", volume_unit)
        self.assertIn("SupplementaryGroups=audio input", volume_unit)
        self.assertIn(
            "ExecStartPre=/usr/local/libexec/r46h-volume-keys --check",
            volume_unit,
        )
        self.assertIn("ExecStart=/usr/local/libexec/r46h-volume-keys", volume_unit)
        self.assertIn("Before=r46h-gaming-frontend.service", volume_unit)
        self.assertIn("Restart=on-failure", volume_unit)
        self.assertIn("ProtectSystem=strict", volume_unit)
        for token in (
            "/dev/input/by-path/platform-gpio-keys-vol-event",
            "EXPECTED_NAME=gpio-keys-vol",
            "readonly STEP=16",
            "readonly SAFE_MAX=201",
            "attempt<150",
            "wait_for_mixer",
            "reason=mixer-unavailable",
            "'(KEY_VOLUMEUP), value 1'",
            "'(KEY_VOLUMEDOWN), value 1'",
            'cset "numid=$CONTROL" "$level,$level"',
        ):
            self.assertIn(token, volume_keys)
        self.assertNotIn("--grab", volume_keys)
        self.assertIn("TimeoutStartSec=20s", volume_unit)
        self.assertIn("R46H Combined Gamepad", waiter)
        self.assertEqual(
            subprocess.run(
                ["/bin/sh", "-n", str(ROOT / "r46h-gaming-frontend-condition")],
                check=False,
            ).returncode,
            0,
        )
        self.assertEqual(
            subprocess.run(
                ["/bin/sh", "-n", str(ROOT / "r46h-gaming-input-ready")],
                check=False,
            ).returncode,
            0,
        )
        self.assertEqual(
            subprocess.run(
                ["/bin/bash", "-n", str(ROOT / "install.sh")], check=False
            ).returncode,
            0,
        )
        self.assertEqual(
            subprocess.run(
                ["/bin/bash", "-n", str(ROOT / "r46h-volume-keys")],
                check=False,
            ).returncode,
            0,
        )

    def test_runner_is_attended_and_restores_mixer(self) -> None:
        runner = (ROOT / "r46h-game-ui").read_text(encoding="utf-8")
        self.assertIn(
            "/usr/bin/setsid /usr/bin/openvt -e -c 2 -s -f -- /bin/dash -c",
            runner,
        )
        self.assertNotIn("/bin/sh", runner)
        self.assertIn("exec /usr/sbin/runuser -u ark", runner)
        self.assertIn("readonly SMOKE_RENDERER=software", runner)
        self.assertIn("readonly PRODUCT_RENDERER=opengles2", runner)
        self.assertIn("smoke)\n    renderer=$SMOKE_RENDERER", runner)
        self.assertIn("nes-smoke)\n    renderer=$PRODUCT_RENDERER", runner)
        self.assertIn("menu)\n    renderer=$PRODUCT_RENDERER", runner)
        self.assertIn('SDL_RENDER_DRIVER="$renderer"', runner)
        self.assertIn('"$CONFIG" "$renderer" "${retroarch_arguments[@]}"', runner)
        self.assertIn("renderer=%s", runner)
        self.assertNotIn("SDL_RENDER_DRIVER=software", runner)
        self.assertNotIn("SDL_RENDER_DRIVER=opengles2", runner)
        self.assertIn("readonly GAME_VOLUME=201,201", runner)
        self.assertNotIn("MESA_LOADER_DRIVER_OVERRIDE=panfrost", runner)
        self.assertIn("/usr/bin/mktemp -d /run/r46h-game-ui.XXXXXX", runner)
        self.assertIn("retroarch_log_tail=begin", runner)
        self.assertIn('rm -f -- "$session_log"', runner)
        self.assertIn("amixer -q -c 0 cset", runner)
        self.assertIn("saved_volume", runner)
        mixer_guard = runner.index("mixer_changed=1")
        self.assertLess(
            mixer_guard,
            runner.index('amixer -q -c 0 cset "numid=$VOLUME_CONTROL"', mixer_guard),
        )
        self.assertIn("chvt 1", runner)
        self.assertIn('kill -TERM -- "-$launcher_pid"', runner)
        self.assertIn('kill -KILL -- "-$launcher_pid"', runner)
        self.assertIn('wait "$launcher_pid" 2>/dev/null || true', runner)
        self.assertIn("process_cleanup=%s", runner)
        self.assertIn("runtime is not readable by ark", runner)
        self.assertIn("r46h-game-ui-read-check", runner)
        self.assertIn("/var/lib/r46h/gaming-mvp-v0.6-installed", runner)
        self.assertIn("gaming product install receipt metadata is invalid", runner)
        self.assertIn("payload_id=r46h-gaming-mvp-v0.6", runner)
        self.assertIn("6.12.99-r46h-mainline-v0.15-gaming-product", runner)
        self.assertLess(
            runner.index("stop_launcher_group ||"),
            runner.index('amixer -q -c 0 cset "numid=$VOLUME_CONTROL" "$saved_volume"'),
        )
        self.assertIn("/usr/sbin/runuser", runner)
        self.assertIn('retroarch_arguments=(-L "$CORE")', runner)
        self.assertIn('retroarch_arguments=(-L "$NES_CORE" "$NES_ROM")', runner)
        self.assertIn("retroarch_arguments=(--menu)", runner)

    def test_builder_scope_and_external_cleanup_contract(self) -> None:
        script = BUILDER.read_text(encoding="utf-8")
        for relative in MODULE.SOURCE_PATHS:
            self.assertIn(f'"{relative}"', script)
        self.assertIn('REPO / "mainline/out/.cache/r46h-gaming-mvp-build"', script)
        self.assertIn("shutil.rmtree(work, ignore_errors=True)", script)
        self.assertIn('"--network",\n            "none"', script)
        self.assertIn(
            "systemd-analyze verify /etc/systemd/system/r46h-gaming-input.service",
            script,
        )
        self.assertIn("/etc/systemd/system/r46h-volume-keys.service", script)
        self.assertIn('"mainline/rootfs-debian13/overlay/etc/fstab"', script)
        self.assertIn('"files/fstab"', script)
        self.assertIn("source scope must be committed and clean", script)

    def test_deterministic_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "payload"
            payload.mkdir()
            (payload / "nested").mkdir()
            (payload / "nested/file").write_bytes(b"payload\n")
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            MODULE.deterministic_archive(payload, first)
            MODULE.deterministic_archive(payload, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_published_generation_reopens_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary) / "release"
            generation_name = "build-0123456789ab-abcdef012345"
            generation = release / "builds" / generation_name
            generation.mkdir(parents=True)
            archive = generation / MODULE.ARCHIVE_NAME
            archive.write_bytes(b"archive\n")
            (generation / "SOURCE-MANIFEST.json").write_bytes(b"{}\n")
            (generation / "BUILD-RECEIPT.json").write_bytes(
                MODULE.canonical_json({"archive_sha256": MODULE.sha256_file(archive)})
            )
            sums = MODULE.payload_manifest(
                generation, {"SHA256SUMS", "BUILD-COMPLETE"}
            )
            (generation / "SHA256SUMS").write_bytes(sums)
            (generation / "BUILD-COMPLETE").write_text(
                f"sha256sums_sha256={MODULE.sha256_bytes(sums)}\n",
                encoding="utf-8",
            )
            (release / "CURRENT").write_text(f"{generation_name}\n", encoding="utf-8")
            original = MODULE.RELEASE_ROOT
            try:
                MODULE.RELEASE_ROOT = release
                self.assertEqual(MODULE.validate_generation(), generation)
            finally:
                MODULE.RELEASE_ROOT = original

    def test_runbook_preserves_first_product_boundary(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        self.assertIn("v0.15-gaming-product", text)
        self.assertIn("patches `0001..0008`", normalized)
        self.assertIn("r46h-gaming-frontend.service", text)
        self.assertIn("Select+X", text)
        self.assertIn("cyan lower-left marker", normalized)
        self.assertIn("magenta lower-right marker", normalized)
        self.assertIn("15.3%", text)
        self.assertIn("40%", text)
        self.assertIn("201,201", text)
        self.assertIn("conservative", text)
        self.assertIn("r46h-storage-audit", text)
        self.assertIn("a2_command_queue=not-available", text)
        self.assertIn(
            "CURRENT-CARD V0.6 PRODUCT + RENDERER PAYLOAD PHYSICAL PASS",
            normalized,
        )
        self.assertIn("REPRODUCIBLE FULL-CARD V0.5 RELEASE BASELINE PASS", normalized)
        self.assertIn("SUCCESSOR ARTIFACT + STATISTICAL RELIABILITY OPEN", normalized)
        self.assertIn("../rootfs-debian13-gaming-v06/README.md", text)
        self.assertIn("cold-booted v0.17", normalized)
        self.assertIn("r46h-game-ui smoke", normalized)
        self.assertIn("status 130", normalized)
        self.assertIn("software renderer", normalized)
        self.assertIn("only for `smoke`", normalized)
        for marker in (
            "build-73cd84e30548-4c03d9d621ac",
            "263,537,654-byte",
            "4c03d9d621ac362ce1fdc80628510d1f36e57e7d368eaa600b2f18af44bb31fa",
            "d5ee90bd9b25eeb6dd7253e1adbe1d1f3f6f54fa3a91b4fbba50dc5e820810d4",
            "6987d5a51c9f513a81d37929a26279e6c099d325e7e7789f2a1969ae5bbfcd0a",
            "d9bae68f35741797a15994559b294b4b9bfcdf961ba6f3cee37c1a916e014b3f",
            "e6dca62fe358bc9e3b98b11ee5d789a00dda8e21c7d2477aae8ecc487f84af65",
            "Accepted renderer payload target result",
            "read-only bind-mounted",
            "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314",
            "74dde6dd6c14324af0eb2d570b89096d6fb0414abc3293f648e40265b44a1db9",
            "133829cc11cd437140ef6b57c80623fcc572070041e72c8f663c8a268d52db11",
            "p3 stayed read-only",
        ):
            self.assertIn(marker, normalized)
        self.assertIn("RequiresMountsFor=/roms", text)
        self.assertIn("SDL_RENDER_DRIVER=opengles2", text)
        self.assertIn("r46h-volume-keys.service", text)
        self.assertIn("no UI overlay is implemented", normalized)
        self.assertIn(
            "3b4265849e446ee8566e47fbfb7d7ee4145bdd0d732caa7b5913684b4e4d3034",
            text,
        )
        self.assertIn(
            "c84dccd4bff90421c8a4741ebf5598b9ea7f86e619cb22212fefa6615ee97f70",
            text,
        )
        self.assertIn("PHYSICAL OPEN", text)
        self.assertIn("HOST-ONLY PASS", text)
        self.assertIn(
            "aa83ab8d080226018df9016a9eeee5ad3a14c13ef6ffe05128ab86566dde4e69",
            text,
        )
        self.assertIn("loaded exact persistent v0.15", text)
        self.assertIn("exact v0.10/v0.8 fallbacks", text)
        self.assertIn("systemd-shutdown: Powering off", text)
        self.assertIn("EmulationStation", text)
        self.assertIn("automatic jack reporting", normalized)
        self.assertIn(
            "MEDIA WRITE + DUAL FULL READBACK + LIVE PHYSICAL PASS",
            text,
        )
        self.assertIn("hl-r46h-v22-g92-62534975488-v1", text)
        self.assertIn(
            "e6ca320b5413a6fe224a8a9a89c3d4199d395237d3fc413ef93da50131e481c9",
            text,
        )
        self.assertIn(
            "78d238eb6da8562f8d30ee2fcbea376c0abd24f0b335fa2b3c950eec5826d171",
            text,
        )
        self.assertIn(
            "7d4feea24f12aec1d383d648748dd8af42464c870f24d175650efb8474bb449e",
            text,
        )
        self.assertIn("all 169 expected non-Spotlight files matched", normalized)
        self.assertIn("missing, extra and changed counts all zero", normalized)
        self.assertIn("At audit completion no write had started", normalized)
        self.assertIn("write-debian13-p2-gaming-v0.4", text)
        self.assertIn(
            "f66191f53d4040022bba99d02708301044c78d218c1984491a6563bde2d3e347",
            text,
        )
        self.assertIn(
            "a72335a5ad800f088f0090d07871bcc403427f1e9b49f5da0122fb7328743bcf",
            text,
        )
        self.assertIn("WRITE_COMPLETE", text)
        self.assertIn("safe_to_boot=yes", text)
        self.assertIn("independently reopened complete p2 hash", normalized)
        self.assertIn("p3 was never mounted or written", normalized)
        self.assertIn("macOS ejected the card", normalized)
        self.assertNotIn("physical acceptance remains open", normalized)
        self.assertIn("98ec4d02fbcbd8b11e33e488d4c0811db1b9b67a", text)
        self.assertIn(
            "99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba",
            text,
        )
        self.assertIn(
            "77c302dde8a2f12c9bafc40ea572ef941c8452b87e7a8fc348c56dcdbac3a351",
            text,
        )
        self.assertIn("must not be distributed as if it contains the correction", normalized)
        self.assertIn("without an autoboot interrupt or `saveenv`", normalized)
        self.assertIn("Do not test higher gain, jack GPIO/events", normalized)
        self.assertIn("complete p2 replacement, not a state-preserving update", normalized)
        self.assertIn("explicitly authorized", normalized)
        self.assertIn(
            "ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca",
            text,
        )
        self.assertIn(
            "17bd631ecc04c598b1216d478f580c108af4636701f58d43d3f9e54be8355535",
            text,
        )
        self.assertIn(
            "c7dee8dac10f41593beb9327b8145d8e2b329ab8b0ca619d8b9b00c09a226b3a",
            text,
        )
        self.assertIn("Do not repeat the write or reuse the spent plan", normalized)
        self.assertIn("first captured non-recovery", normalized)
        self.assertIn("stuck-busy `-110` failures at 200 and 100 kHz", normalized)
        self.assertIn(
            "015e571c0f0f4a5ebe967a9543d5b68d58cf1e39ea4c6608c5371ec79d7b522f",
            text,
        )
        self.assertIn(
            "a reset workaround must not be silently promoted",
            normalized.lower(),
        )


if __name__ == "__main__":
    unittest.main()
