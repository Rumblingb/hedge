import json
import tempfile
import time
import unittest
from pathlib import Path

from scripts.bill_state_unifier import build_report, write_report


class BillStateUnifierTest(unittest.TestCase):
    def test_dry_run_reports_legacy_only_and_newer_duplicates_without_copying(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "legacy"
            canonical = root / "canonical"
            legacy.mkdir()
            canonical.mkdir()
            (legacy / "legacy-only.latest.json").write_text("{}\n")
            (legacy / "duplicate.latest.json").write_text('{"source":"legacy"}\n')
            (canonical / "duplicate.latest.json").write_text('{"source":"canonical"}\n')
            now = time.time()
            (canonical / "duplicate.latest.json").touch()
            (legacy / "duplicate.latest.json").touch()
            time.sleep(0.01)
            newer = now + 10
            (legacy / "duplicate.latest.json").touch()
            import os
            os.utime(legacy / "duplicate.latest.json", (newer, newer))

            report = build_report(legacy, canonical, apply=False)

            self.assertEqual(report["decision"], "dry-run")
            self.assertIn("legacy-only.latest.json", report["legacyOnly"])
            self.assertIn("duplicate.latest.json", report["legacyNewerDuplicates"])
            self.assertFalse((canonical / "legacy-only.latest.json").exists())

    def test_apply_copies_legacy_only_and_archives_before_newer_duplicate_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "legacy"
            canonical = root / "canonical"
            legacy.mkdir()
            canonical.mkdir()
            (legacy / "legacy-only.latest.json").write_text('{"ok":true}\n')
            (legacy / "duplicate.latest.json").write_text('{"source":"legacy"}\n')
            (canonical / "duplicate.latest.json").write_text('{"source":"canonical"}\n')
            import os
            older = time.time()
            newer = older + 10
            os.utime(canonical / "duplicate.latest.json", (older, older))
            os.utime(legacy / "duplicate.latest.json", (newer, newer))

            report = build_report(legacy, canonical, apply=True)
            out = canonical / "bill-state-unifier.latest.json"
            write_report(report, out)

            self.assertEqual(json.loads((canonical / "legacy-only.latest.json").read_text())["ok"], True)
            self.assertEqual(json.loads((canonical / "duplicate.latest.json").read_text())["source"], "legacy")
            self.assertTrue(any("archivedCanonicalTo" in action for action in report["actions"]))
            self.assertTrue(out.exists())
            self.assertFalse(report["writesOrders"])
            self.assertFalse(report["touchesBroker"])


if __name__ == "__main__":
    unittest.main()
