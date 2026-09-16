#!/usr/bin/env python3
"""Security contract for the target-tested NetworkManager polkit rule."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[2]
POLICY = REPO / "mainline/gaming-shell/49-r46h-network.rules"


class ShellNetworkPolicyTests(unittest.TestCase):
    def test_exact_target_tested_policy(self) -> None:
        data = POLICY.read_bytes()
        text = data.decode("utf-8")
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            "842466c1aafc51d187abb1ec3204d7c34579d56149249947619c8967ecccc87e",
        )
        self.assertEqual(
            set(re.findall(r'"(org\.freedesktop\.NetworkManager\.[^"]+)"', text)),
            {
                "org.freedesktop.NetworkManager.network-control",
                "org.freedesktop.NetworkManager.settings.modify.system",
                "org.freedesktop.NetworkManager.wifi.scan",
            },
        )
        self.assertIn('subject.user == "ark"', text)
        self.assertIn("allowed.indexOf(action.id) >= 0", text)
        self.assertNotIn("isInGroup", text)


if __name__ == "__main__":
    unittest.main()
