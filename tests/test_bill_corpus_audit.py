import tempfile
import unittest
from pathlib import Path

from scripts import bill_corpus_audit as audit


class BillCorpusAuditTests(unittest.TestCase):
    def test_status_for_keeps_risky_artifacts_quarantined(self):
        item = {
            "kind": "strategy_signal",
            "path": "/tmp/dom_proxy_ohlcv.py",
            "tags": ["strategy", "risk"],
            "risk_terms": ["proxy"],
        }

        self.assertEqual(audit.status_for(item), "quarantine")

    def test_status_for_marks_strategy_seed_candidate(self):
        item = {
            "kind": "strategy_signal",
            "path": "/tmp/orb_strategy.py",
            "tags": ["strategy"],
            "risk_terms": [],
        }

        self.assertEqual(audit.status_for(item), "candidate")

    def test_status_for_keeps_blocked_control_notes_active(self):
        item = {
            "kind": "note",
            "path": "/Users/brain/Documents/memorybrain/Agent-Hermes/BILL-CONTROL-HUB.md",
            "tags": ["risk", "vision"],
            "risk_terms": ["blocked"],
        }

        self.assertEqual(audit.status_for(item), "active")

    def test_write_obsidian_markdown_includes_status_and_safety_note(self):
        report = {
            "counts": {
                "artifacts": 2,
                "riskArtifacts": 1,
                "byKind": {"strategy_signal": 1, "note": 1},
                "byTag": {"strategy": 1, "risk": 1},
            },
            "importantArtifacts": [
                {
                    "kind": "strategy_signal",
                    "path": "/tmp/orb_strategy.py",
                    "tags": ["strategy"],
                    "risk_terms": [],
                    "summary": "ORB strategy seed",
                }
            ],
            "riskArtifacts": [
                {
                    "kind": "note",
                    "path": "/tmp/fallback_signal.md",
                    "tags": ["risk"],
                    "risk_terms": ["fallback_no_data"],
                    "summary": "Fallback signal must not trade",
                }
            ],
            "roots": [{"label": "tmp", "path": "/tmp", "present": True}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "Bill-Corpus-Audit.md"

            written = audit.write_obsidian_markdown(report, path)

            text = written.read_text()
            self.assertIn("Execution note: this is memory/navigation only.", text)
            self.assertIn("`candidate`", text)
            self.assertIn("fallback_no_data", text)


if __name__ == "__main__":
    unittest.main()
