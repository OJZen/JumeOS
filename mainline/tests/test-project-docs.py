#!/usr/bin/env python3
"""Structural guards for concise, navigable project documentation."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[2]
LINE_LIMITS = {
    Path("README.md"): 60,
    Path("AGENTS.md"): 70,
    Path("docs/README.md"): 100,
    Path("docs/PROJECT-CONTEXT.md"): 150,
    Path("docs/ARCHITECTURE.md"): 170,
    Path("docs/R46H-BOARD.md"): 160,
    Path("docs/P3-CONTENT-MIGRATION.md"): 120,
    Path("docs/DEVELOPMENT.md"): 180,
    Path("docs/TESTING.md"): 150,
    Path("mainline/README.md"): 100,
    Path("mainline/board/r46h/README.md"): 60,
    Path("mainline/board/r46h/EXPERIMENT-STATUS.md"): 150,
    Path("mainline/bringup-tests/README.md"): 100,
    Path("mainline/bringup-tests/ADAPTATION-READONLY.md"): 130,
}
MAX_LINE_LENGTHS = {
    Path("mainline/board/r46h/EXPERIMENT-STATUS.md"): 120,
}
CHECKPOINT_DOCUMENTS = (
    Path("docs/PROJECT-CONTEXT.md"),
    Path("mainline/board/r46h/EXPERIMENT-STATUS.md"),
)
FROZEN_ENTRY_DOCUMENTS = {
    Path("mainline/rootfs-debian13/README.md"): "历史冻结文档",
    Path("mainline/userspace-probe/README.md"): "历史冻结文档",
    Path("mainline/gaming-rom-workflow/README.md"): "Historical/frozen contract",
}
LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
CHECKPOINT_RE = re.compile(
    r"Current checkpoint(?:\s*[:(])\s*(\d{4}-\d{2}-\d{2})"
)


def source_markdown_documents() -> tuple[Path, ...]:
    documents = []
    for document in REPO.rglob("*.md"):
        relative = document.relative_to(REPO)
        if any(part in {".git", ".cache", "out"} for part in relative.parts):
            continue
        if any(part.startswith(".tmp-r46h-") for part in relative.parts):
            continue
        documents.append(relative)
    return tuple(sorted(documents))


class ProjectDocumentationTests(unittest.TestCase):
    def test_curated_documents_exist_and_stay_scannable(self) -> None:
        for relative, limit in LINE_LIMITS.items():
            with self.subTest(path=relative):
                path = REPO / relative
                self.assertTrue(path.is_file(), relative)
                line_count = len(path.read_text(encoding="utf-8").splitlines())
                self.assertLessEqual(line_count, limit, f"{relative}: {line_count}")
        for relative, limit in MAX_LINE_LENGTHS.items():
            with self.subTest(path=relative, metric="line length"):
                lines = (REPO / relative).read_text(encoding="utf-8").splitlines()
                longest = max(map(len, lines), default=0)
                self.assertLessEqual(longest, limit, f"{relative}: {longest}")

    def test_onboarding_order_and_authorities_are_linked(self) -> None:
        public_readme = (REPO / "README.md").read_text(encoding="utf-8")
        agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        index = (REPO / "docs/README.md").read_text(encoding="utf-8")
        context = (REPO / "docs/PROJECT-CONTEXT.md").read_text(encoding="utf-8")
        context_collapsed = " ".join(context.split())

        self.assertLess(agents.index("docs/README.md"), agents.index("docs/PROJECT-CONTEXT.md"))
        self.assertNotIn("Current checkpoint", agents)
        self.assertLess(public_readme.index("JumeOS is"), public_readme.index("中文简介"))
        for required in ("What works today", "Still in development", "Repository"):
            self.assertIn(required, public_readme)
        for required in (
            "mainline/board/r46h/EXPERIMENT-STATUS.md",
            "docs/DEVELOPMENT.md",
            "docs/TESTING.md",
        ):
            self.assertIn(required, agents)
        for required in (
            "PROJECT-CONTEXT.md",
            "ARCHITECTURE.md",
            "R46H-BOARD.md",
            "P3-CONTENT-MIGRATION.md",
            "DEVELOPMENT.md",
            "TESTING.md",
            "../mainline/board/r46h/EXPERIMENT-STATUS.md",
        ):
            self.assertIn(required, index)
        for required in (
            "Current checkpoint",
            "../mainline/board/r46h/EXPERIMENT-STATUS.md",
            "Immediate next work",
            "full target checksum/readback was skipped",
        ):
            self.assertIn(required, context_collapsed)

    def test_current_checkpoint_documents_stay_synchronized(self) -> None:
        checkpoints = {}
        for relative in CHECKPOINT_DOCUMENTS:
            text = (REPO / relative).read_text(encoding="utf-8")
            matches = CHECKPOINT_RE.findall(text)
            with self.subTest(path=relative, metric="checkpoint"):
                self.assertEqual(len(matches), 1)
            checkpoints[relative] = matches[0]
            for required in ("v0.17", "v0.15", "p2 v0.5", "p3"):
                with self.subTest(path=relative, required=required):
                    self.assertIn(required, text)
            collapsed = " ".join(text.split())
            self.assertRegex(
                collapsed,
                r"full (?:target )?checksum/readback (?:was )?(?:explicitly )?skipped",
            )
        self.assertEqual(len(set(checkpoints.values())), 1, checkpoints)

    def test_historical_entry_points_cannot_masquerade_as_current(self) -> None:
        for relative, marker in FROZEN_ENTRY_DOCUMENTS.items():
            text = (REPO / relative).read_text(encoding="utf-8")
            with self.subTest(path=relative):
                self.assertIn(marker, text)
                self.assertIn("PROJECT-CONTEXT.md", text)
                self.assertIn("EXPERIMENT-STATUS.md", text)

        release = (
            REPO / "mainline/first-version-release/README.md"
        ).read_text(encoding="utf-8")
        release_collapsed = " ".join(
            line.removeprefix("> ").strip() for line in release.splitlines()
        )
        self.assertIn("Historical release convergence", release)
        self.assertIn("not an instruction for the current card", release_collapsed)
        self.assertIn("do not replay the commands below", release_collapsed)

        architecture = (REPO / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
        self.assertIn("Repository scope", architecture)
        self.assertIn("intended: p3 EASYROMS mounted at /roms", architecture)
        self.assertIn("not current physical evidence", architecture)

    def test_every_bringup_runbook_is_indexed(self) -> None:
        runbook_dir = REPO / "mainline/bringup-tests"
        index = (runbook_dir / "README.md").read_text(encoding="utf-8")
        for runbook in sorted(runbook_dir.glob("*.md")):
            if runbook.name == "README.md":
                continue
            with self.subTest(runbook=runbook.name):
                self.assertIn(f"]({runbook.name})", index)

    def test_current_rootfs_and_predecessor_contract_are_indexed(self) -> None:
        index = (REPO / "mainline/README.md").read_text(encoding="utf-8")
        self.assertIn("](rootfs-debian13-gaming-v18/)", index)
        self.assertIn("imports the preceding versioned builders", index)

    def test_all_local_markdown_links_resolve(self) -> None:
        documents = source_markdown_documents()
        self.assertGreater(len(documents), len(LINE_LIMITS))
        for relative in documents:
            document = REPO / relative
            text = document.read_text(encoding="utf-8")
            for raw_target in LINK_RE.findall(text):
                target = raw_target.strip()
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1]
                path_part = target.split("#", 1)[0]
                if not path_part:
                    continue
                resolved = (document.parent / path_part).resolve()
                with self.subTest(document=relative, target=raw_target):
                    self.assertTrue(resolved.exists(), resolved)


if __name__ == "__main__":
    unittest.main()
