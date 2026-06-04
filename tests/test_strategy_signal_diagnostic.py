import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import strategy_signal_diagnostic as diagnostic
from tests.test_strategy_diagnostic import write_sample_csv


class StrategySignalDiagnosticTest(unittest.TestCase):
    def test_wrapper_exports_research_only_diagnostic_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "nq.csv"
            write_sample_csv(csv_path)

            payload = diagnostic.build_report(csv_path)

        self.assertEqual(payload["command"], "strategy-diagnostic")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["barCount"], 70)
        self.assertIn("orbBreakout", payload["diagnostics"])
        self.assertIn("wqTrendMomentum", payload["diagnostics"])
        self.assertIn("Research-only local CSV diagnostic", payload["operatorRead"])

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "nq.csv"
            output_path = Path(tmp) / "strategy-signal-diagnostic.json"
            write_sample_csv(csv_path)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/strategy_signal_diagnostic.py",
                    "--input",
                    str(csv_path),
                    "--output",
                    str(output_path),
                    "--json",
                ],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                text=True,
                capture_output=True,
            )

            payload = json.loads(result.stdout)
            self.assertTrue(output_path.exists())

        self.assertEqual(payload["command"], "strategy-diagnostic")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["readyForExecution"])


if __name__ == "__main__":
    unittest.main()
