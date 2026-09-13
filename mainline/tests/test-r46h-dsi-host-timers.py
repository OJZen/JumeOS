#!/usr/bin/env python3
"""Source and patch-series tests for the R46H-only DSI host timers."""

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import tempfile
import unittest


MAINLINE = pathlib.Path(__file__).resolve().parents[1]
PATCH_DIR = MAINLINE / "patches"
KERNEL_TARBALL = MAINLINE / ".cache" / "kernel" / "linux-6.12.99.tar.xz"
KERNEL_TARBALL_SHA256 = (
    "6a477222c132033381cda981eb0127f29fbcbba17e820283bc21290f8e408629"
)
PATCH_NAMES = [
    "0001-arm64-dts-rockchip-add-R46H-mainline-bring-up.patch",
    "0002-drm-rockchip-use-r46h-dsi-lane-rate.patch",
    "0003-drm-panel-r46h-enable-backlight-rail-before-init.patch",
    "0004-drm-rockchip-use-r46h-dsi-host-timers.patch",
    "0005-drm-panel-r46h-preserve-bootloader-handoff.patch",
    "0006-input-joystick-adc-use-axis-code-for-inversion.patch",
    "0007-arm64-dts-rockchip-use-r46h-adc-full-range.patch",
    "0008-power-supply-rk817-support-a-board-DC-input.patch",
    "0009-arm64-dts-rockchip-use-rk817-150ma-charge-termination.patch",
    "0010-mmc-dw-log-request-errors.patch",
]
ROCKCHIP_DSI = pathlib.Path(
    "drivers/gpu/drm/rockchip/dw-mipi-dsi-rockchip.c"
)
GENERIC_DSI = pathlib.Path("drivers/gpu/drm/bridge/synopsys/dw-mipi-dsi.c")
PANEL = pathlib.Path("drivers/gpu/drm/panel/panel-r46h.c")
DPHY = pathlib.Path("drivers/phy/rockchip/phy-rockchip-inno-dsidphy.c")
DTS = pathlib.Path("arch/arm64/boot/dts/rockchip/rk3326-r46h.dts")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    open_brace = source.index("{", start)
    depth = 0
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def git_blob_oid(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def apply_patch(source: pathlib.Path, patch: pathlib.Path) -> None:
    with patch.open("rb") as patch_input:
        subprocess.run(
            ["patch", "--directory", str(source), "--strip=1", "--forward"],
            stdin=patch_input,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )


class R46hDsiHostTimerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not KERNEL_TARBALL.is_file():
            raise AssertionError(f"missing cached kernel tarball: {KERNEL_TARBALL}")
        if file_sha256(KERNEL_TARBALL) != KERNEL_TARBALL_SHA256:
            raise AssertionError(f"kernel tarball SHA-256 mismatch: {KERNEL_TARBALL}")

        cls.temporary = tempfile.TemporaryDirectory(
            prefix="r46h-dsi-host-timers.", dir=MAINLINE / ".cache"
        )
        cls.root = pathlib.Path(cls.temporary.name)
        cls.source = cls.root / "linux-6.12.99"
        members = [
            "linux-6.12.99/arch/arm64/boot/dts/rockchip",
            "linux-6.12.99/include/dt-bindings",
            "linux-6.12.99/include/uapi/linux/input-event-codes.h",
            "linux-6.12.99/drivers/gpu/drm/bridge/synopsys/dw-mipi-dsi.c",
            "linux-6.12.99/drivers/gpu/drm/panel/Kconfig",
            "linux-6.12.99/drivers/gpu/drm/panel/Makefile",
            "linux-6.12.99/drivers/gpu/drm/rockchip/dw-mipi-dsi-rockchip.c",
            "linux-6.12.99/drivers/phy/rockchip/phy-rockchip-inno-dsidphy.c",
        ]
        subprocess.run(
            ["tar", "-xJf", str(KERNEL_TARBALL), "-C", str(cls.root), *members],
            check=True,
        )

        for name in PATCH_NAMES[:3]:
            apply_patch(cls.source, PATCH_DIR / name)

        cls.before = (cls.source / ROCKCHIP_DSI).read_bytes()
        cls.before_others = {
            path: (cls.source / path).read_bytes()
            for path in (GENERIC_DSI, PANEL, DPHY, DTS)
        }
        apply_patch(cls.source, PATCH_DIR / PATCH_NAMES[3])
        cls.after = (cls.source / ROCKCHIP_DSI).read_bytes()
        cls.wrapper = cls.after.decode("utf-8")
        cls.generic = (cls.source / GENERIC_DSI).read_text(encoding="utf-8")
        cls.after_0004_others = {
            path: (cls.source / path).read_bytes()
            for path in (GENERIC_DSI, PANEL, DPHY, DTS)
        }
        cls.patch_0005 = PATCH_DIR / PATCH_NAMES[4]
        cls.applied_0005 = cls.patch_0005.is_file()
        if cls.applied_0005:
            apply_patch(cls.source, cls.patch_0005)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_patch_series_is_exact_and_0004_changes_only_rockchip_glue(self) -> None:
        self.assertEqual(
            [path.name for path in sorted(PATCH_DIR.glob("*.patch"))],
            PATCH_NAMES,
        )
        patch = (PATCH_DIR / PATCH_NAMES[3]).read_text(encoding="utf-8")
        changed = re.findall(
            r"^diff --git a/(\S+) b/(\S+)$", patch, re.MULTILINE
        )
        self.assertEqual(changed, [(str(ROCKCHIP_DSI), str(ROCKCHIP_DSI))])

    def test_0005_changes_only_panel_after_0004(self) -> None:
        self.assertTrue(
            self.applied_0005,
            f"missing handoff patch: {self.patch_0005}",
        )
        changed = re.findall(
            r"^diff --git a/(\S+) b/(\S+)$",
            self.patch_0005.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        self.assertEqual(changed, [(str(PANEL), str(PANEL))])
        self.assertNotEqual(
            (self.source / PANEL).read_bytes(), self.after_0004_others[PANEL]
        )
        for path in (GENERIC_DSI, DPHY, DTS):
            self.assertEqual(
                (self.source / path).read_bytes(),
                self.after_0004_others[path],
                path,
            )

    def test_patch_postimage_oid_matches_replayed_source(self) -> None:
        patch = (PATCH_DIR / PATCH_NAMES[3]).read_text(encoding="utf-8")
        match = re.search(
            rf"^diff --git a/{re.escape(str(ROCKCHIP_DSI))} .*?"
            r"^index [0-9a-f]+\.\.([0-9a-f]+) 100644$",
            patch,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), git_blob_oid(self.after)[:7])

    def test_only_wrapper_changes_across_0004(self) -> None:
        self.assertNotEqual(self.before, self.after)
        for path, content in self.before_others.items():
            self.assertEqual(self.after_0004_others[path], content, path)

    def test_lane_rate_path_is_byte_identical_across_0004(self) -> None:
        before = function_body(
            self.before.decode("utf-8"), "dw_mipi_dsi_get_lane_mbps"
        )
        after = function_body(self.wrapper, "dw_mipi_dsi_get_lane_mbps")
        self.assertEqual(before, after)

    def test_timer_override_has_three_exact_r46h_guards(self) -> None:
        guard = function_body(
            self.wrapper, "dw_mipi_dsi_uses_r46h_host_timers"
        )
        self.assertEqual(guard.count("dsi->phy"), 1)
        self.assertEqual(
            guard.count("lane_mbps == R46H_DSI_LANE_MBPS"), 1
        )
        self.assertEqual(
            guard.count(
                'of_machine_is_compatible("rockchip,rk3326-r46h-linux")'
            ),
            1,
        )
        self.assertNotIn('"rockchip,rk3326"', guard)

    def test_upstream_table_is_preserved_and_only_returned_tuple_changes(self) -> None:
        before_text = self.before.decode("utf-8")
        self.assertEqual(before_text.count("HSTT( 400,  61, 30,  50, 20)"), 1)
        self.assertEqual(self.wrapper.count("HSTT( 400,  61, 30,  50, 20)"), 1)
        timing = function_body(self.wrapper, "dw_mipi_dsi_phy_get_timing")
        table_copy = timing.index("*timing = hstt_table[i].timing;")
        override = timing.index("if (dw_mipi_dsi_uses_r46h_host_timers")
        self.assertLess(table_copy, override)
        for assignment in (
            "timing->clk_lp2hs = 0x40;",
            "timing->clk_hs2lp = 0x40;",
            "timing->data_lp2hs = 0x10;",
            "timing->data_hs2lp = 0x14;",
        ):
            self.assertEqual(timing.count(assignment), 1)

    def test_old_and_new_register_images_are_exact(self) -> None:
        def lpclk(clk_hs2lp: int, clk_lp2hs: int) -> int:
            return ((clk_hs2lp & 0x3FF) << 16) | (clk_lp2hs & 0x3FF)

        def data(data_hs2lp: int, data_lp2hs: int) -> int:
            return (
                ((data_hs2lp & 0xFF) << 24)
                | ((data_lp2hs & 0xFF) << 16)
                | 10000
            )

        self.assertEqual(lpclk(30, 61), 0x001E003D)
        self.assertEqual(data(20, 50), 0x14322710)
        self.assertEqual(lpclk(64, 64), 0x00400040)
        self.assertEqual(data(20, 16), 0x14102710)
        self.assertEqual(
            self.wrapper.count(
                "R46H_DSI_PHY_TMR_LPCLK_EXPECTED\t0x00400040"
            ),
            1,
        )
        self.assertEqual(
            self.wrapper.count("R46H_DSI_PHY_TMR_EXPECTED\t0x14102710"),
            1,
        )
        self.assertIn("MAX_RD_TIME(10000)", self.generic)

    def test_readback_is_read_only_and_runs_in_external_phy_init(self) -> None:
        check = function_body(
            self.wrapper, "dw_mipi_dsi_check_r46h_host_timers"
        )
        self.assertEqual(check.count("readl("), 3)
        self.assertNotIn("writel(", check)
        self.assertIn("R46H_DSI_HOST_TIMERS stage=pre-enable status=match", check)
        self.assertIn(
            "R46H_DSI_HOST_TIMERS stage=pre-enable status=mismatch", check
        )

        init = function_body(self.wrapper, "static int dw_mipi_dsi_phy_init")
        external = init.index("if (dsi->phy) {")
        call = init.index("dw_mipi_dsi_check_r46h_host_timers", external)
        early_return = init.index("return 0;", call)
        internal_phy = init.index("Get vco from frequency", early_return)
        self.assertLess(external, call)
        self.assertLess(call, early_return)
        self.assertLess(early_return, internal_phy)

    def test_generic_core_packs_the_callback_fields_into_real_registers(self) -> None:
        timing = function_body(
            self.generic, "static void dw_mipi_dsi_dphy_timing_config"
        )
        compact = re.sub(r"\s+", " ", timing)
        self.assertIn(
            "PHY_HS2LP_TIME(timing.data_hs2lp) | "
            "PHY_LP2HS_TIME(timing.data_lp2hs) | MAX_RD_TIME(10000)",
            compact,
        )
        self.assertIn(
            "PHY_CLKHS2LP_TIME(timing.clk_hs2lp) | "
            "PHY_CLKLP2HS_TIME(timing.clk_lp2hs)",
            compact,
        )

    def test_atomic_pre_enable_programs_timers_before_platform_init(self) -> None:
        pre_enable = function_body(
            self.generic, "static void dw_mipi_dsi_bridge_atomic_pre_enable"
        )
        self.assertIn("dw_mipi_dsi_mode_set(dsi, &dsi->mode);", pre_enable)
        mode_set = function_body(self.generic, "static void dw_mipi_dsi_mode_set")
        timing = mode_set.index("dw_mipi_dsi_dphy_timing_config(dsi);")
        platform_init = mode_set.index("ret = phy_ops->init(priv_data);")
        self.assertLess(timing, platform_init)


if __name__ == "__main__":
    unittest.main()
