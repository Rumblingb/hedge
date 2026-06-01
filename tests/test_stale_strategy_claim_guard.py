import tempfile
import unittest
from pathlib import Path

from scripts.stale_strategy_claim_guard import build_report, default_markdown_path


class StaleStrategyClaimGuardTests(unittest.TestCase):
    def test_blocks_unsuperseded_trade_now_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.md"
            path.write_text("# Strategy\n\nImmediate action: 28 GOOD strategies can trade today.\n")

            report = build_report([path])

        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["findingCount"], 1)
        self.assertEqual(report["findings"][0]["phrase"].lower(), "can trade today")
        self.assertFalse(report["writesOrders"])
        self.assertFalse(report["touchesBroker"])

    def test_allows_superseded_claim_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.md"
            path.write_text(
                "# Strategy\n\n"
                "**Superseded immediate-action note:** the prior can trade today read is obsolete.\n"
                "These rows are research-only and not execution approval.\n"
            )

            report = build_report([path])

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["findingCount"], 0)

    def test_scans_markdown_files_inside_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "safe.md").write_text("Ready for execution: `False`\n")
            (root / "bad.md").write_text("This system is ready for live.\n")
            (root / "ignore.txt").write_text("can trade today\n")

            report = build_report([root])

        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["findingCount"], 1)
        self.assertTrue(report["findings"][0]["path"].endswith("bad.md"))

    def test_skips_its_own_generated_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stale-strategy-claim-guard-2026-05-31.md").write_text(
                "- `/tmp/note.md:1` `Ready for execution` - old generated finding\n"
            )

            report = build_report([root])

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["findingCount"], 0)

    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertRegex(path.name, r"^stale-strategy-claim-guard-\d{4}-\d{2}-\d{2}\.md$")


if __name__ == "__main__":
    unittest.main()
