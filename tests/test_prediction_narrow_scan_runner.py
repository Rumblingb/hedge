import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.prediction_narrow_scan_runner import build_report, build_scan_command, safe_category, summarize_reports


class PredictionNarrowScanRunnerTest(unittest.TestCase):
    def test_builds_deterministic_scan_command(self):
        self.assertEqual(
            build_scan_command(Path("/tmp/crypto.json")),
            ["npx", "tsx", "src/cli.ts", "prediction-scan", "/tmp/crypto.json"],
        )

    def test_safe_category_avoids_path_tricks(self):
        self.assertEqual(safe_category("../Macro Rates!"), "macro-rates")

    def test_summary_is_research_only_even_with_candidates(self):
        summary = summarize_reports([
            {"counts": {"paper-trade": 1, "watch": 2}, "diagnostics": {"viablePairs": 3}},
        ])

        self.assertEqual(summary["paperCandidates"], 1)
        self.assertEqual(summary["watchCandidates"], 2)
        self.assertEqual(summary["viablePairs"], 3)
        self.assertFalse(summary["readyForPaper"])

    def test_missing_snapshot_does_not_write_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "manifest.json"
            manifest.write_text(
                """[
                  {
                    "category": "crypto",
                    "path": "/missing/crypto.json",
                    "marketCount": 44,
                    "researchOnly": true,
                    "writesOrders": false
                  }
                ]"""
            )
            args = argparse.Namespace(
                manifest=str(manifest),
                out_dir=str(tmp_path / "out"),
                limit=6,
                timeout_seconds=1,
                category=[],
            )

            report = build_report(args)

        self.assertTrue(report["researchOnly"])
        self.assertFalse(report["writesOrders"])
        self.assertFalse(report["readyForPaper"])
        self.assertEqual(report["reports"][0]["status"], "missing-snapshot")
        self.assertEqual(report["reports"][0]["snapshotMarketCount"], 44)

    def test_runner_uses_research_journal_per_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot = tmp_path / "crypto.json"
            snapshot.write_text("[]")
            manifest = tmp_path / "manifest.json"
            manifest.write_text(
                f"""[
                  {{
                    "category": "crypto",
                    "path": "{snapshot}",
                    "marketCount": 44,
                    "researchOnly": true,
                    "writesOrders": false
                  }}
                ]"""
            )
            args = argparse.Namespace(
                manifest=str(manifest),
                out_dir=str(tmp_path / "out"),
                limit=6,
                timeout_seconds=1,
                category=[],
            )

            with patch("scripts.prediction_narrow_scan_runner.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = '{"counts":{"reject":0},"diagnostics":{"viablePairs":0,"repairableNearMisses":[{"candidateId":"x"}]},"top10":[]}'
                run.return_value.stderr = ""
                report = build_report(args)

            env = run.call_args.kwargs["env"]
            self.assertTrue(env["BILL_PREDICTION_JOURNAL_PATH"].endswith("crypto.opportunities.jsonl"))
            self.assertEqual(report["reports"][0]["status"], "ok")
            self.assertEqual(report["reports"][0]["snapshotMarketCount"], 44)
            self.assertEqual(report["summary"]["repairableNearMisses"], 1)
            self.assertTrue((tmp_path / "out" / "crypto.report.json").exists())

    def test_category_filter_runs_only_requested_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            crypto = tmp_path / "crypto.json"
            rates = tmp_path / "macro-rates.json"
            crypto.write_text("[]")
            rates.write_text("[]")
            manifest = tmp_path / "manifest.json"
            manifest.write_text(
                f"""[
                  {{
                    "category": "crypto",
                    "path": "{crypto}",
                    "marketCount": 44,
                    "researchOnly": true,
                    "writesOrders": false
                  }},
                  {{
                    "category": "macro-rates",
                    "path": "{rates}",
                    "marketCount": 111,
                    "researchOnly": true,
                    "writesOrders": false
                  }}
                ]"""
            )
            args = argparse.Namespace(
                manifest=str(manifest),
                out_dir=str(tmp_path / "out"),
                limit=6,
                timeout_seconds=1,
                category=["crypto"],
            )

            with patch("scripts.prediction_narrow_scan_runner.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = '{"counts":{"reject":0},"diagnostics":{"viablePairs":0},"top10":[]}'
                run.return_value.stderr = ""
                report = build_report(args)

            self.assertEqual(run.call_count, 1)
            self.assertEqual(report["selectedCategories"], ["crypto"])
            self.assertEqual(report["reports"][0]["category"], "crypto")
            self.assertEqual(report["summary"]["categoryCount"], 1)


if __name__ == "__main__":
    unittest.main()
