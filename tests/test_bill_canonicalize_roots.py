import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import bill_canonicalize_roots


class BillCanonicalizeRootsTest(unittest.TestCase):
    def test_merge_then_retire_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canonical_base = root / "canonical"
            legacy_base = root / "legacy"
            (canonical_base / "state").mkdir(parents=True)
            (legacy_base / "state").mkdir(parents=True)
            (canonical_base / "brain").mkdir(parents=True)
            (legacy_base / "brain" / "cycles").mkdir(parents=True)

            (canonical_base / "state" / "dup.json").write_text('{"v":"canonical"}\n')
            (legacy_base / "state" / "dup.json").write_text('{"v":"legacy"}\n')
            older = time.time()
            newer = older + 10
            os.utime(canonical_base / "state" / "dup.json", (older, older))
            os.utime(legacy_base / "state" / "dup.json", (newer, newer))
            (legacy_base / "brain" / "cycles" / "old.json").write_text("{}\n")

            with patch.object(bill_canonicalize_roots, "CANONICAL_BASE", canonical_base), \
                 patch.object(bill_canonicalize_roots, "LEGACY_BASE", legacy_base):
                report = bill_canonicalize_roots.build_report(apply=True)

            self.assertEqual(report["decision"], "applied-canonical-roots")
            self.assertEqual(json.loads((canonical_base / "state" / "dup.json").read_text())["v"], "legacy")
            self.assertTrue((canonical_base / "brain" / "cycles" / "old.json").exists())
            self.assertTrue((legacy_base / "state").is_symlink())
            self.assertEqual((legacy_base / "state").resolve(), (canonical_base / "state").resolve())
            self.assertFalse(report["writesOrders"])
            self.assertFalse(report["touchesBroker"])


if __name__ == "__main__":
    unittest.main()
