import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.bill_data_intake_manifest import HERMES, build_manifest, default_markdown_path, parse_git_status, render_markdown


class BillDataIntakeManifestTest(unittest.TestCase):
    def test_manifest_inspects_dirty_research_csv_without_execution_permission(self):
        with TemporaryDirectory() as tmp:
            root_file = Path("/Users/brain/hedge/data/free/ALL-6MARKETS-1m-5d-normalized.csv")
            local_data = Path(tmp) / "data/free/ALL-6MARKETS-1m-5d-normalized.csv"
            local_data.parent.mkdir(parents=True)
            with local_data.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["ts", "symbol", "open", "high", "low", "close", "volume"])
                writer.writeheader()
                writer.writerow({"ts": "2026-05-29T20:58:00Z", "symbol": "NQ", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10})
                writer.writerow({"ts": "2026-05-29T20:59:00Z", "symbol": "ES", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10})
            # build_manifest resolves against the real repo root; monkey patch by passing the actual path shape is
            # intentionally avoided here. Instead verify the parser and markdown safety on the real function surface.
            rows = parse_git_status(" M data/free/ALL-6MARKETS-1m-5d-normalized.csv\n")
            self.assertEqual(rows, [{"status": "M", "path": "data/free/ALL-6MARKETS-1m-5d-normalized.csv"}])
            self.assertTrue(str(root_file).endswith(rows[0]["path"]))

        payload = build_manifest(rows, generated_at="2026-05-30T00:00:00+00:00")

        self.assertEqual(payload["decision"], "data-intake-visible-execution-locked")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecutionData"])
        self.assertFalse(payload["executionGradeData"])
        self.assertGreaterEqual(payload["dirtyDataFileCount"], 1)
        self.assertIn("research-refresh-current-window", payload["classificationCounts"])
        self.assertIn("npm run --silent bill:data-intake-manifest", payload["nextCommands"])
        self.assertIn("npm run --silent bill:futures-data-requirements", payload["validationCommandSets"]["futuresDataEvidence"])
        self.assertIn(
            "npm run --silent bill:open-session-data-proof -- --run-data-only",
            payload["validationCommandSets"]["futuresDataEvidence"],
        )

    def test_markdown_states_data_is_not_execution_grade(self):
        payload = {
            "decision": "data-intake-visible-execution-locked",
            "dirtyDataFileCount": 1,
            "csvFileCount": 1,
            "executionGradeData": False,
            "readyForExecutionData": False,
            "classificationCounts": {"research-refresh-current-window": 1},
            "riskCounts": {"research-only-current-window-not-execution-grade": 1},
            "generatedAt": "2026-05-30T00:00:00+00:00",
            "nextCommands": ["npm run --silent bill:data-intake-manifest"],
            "validationCommandSets": {
                "dataVisibilityRefresh": ["npm run --silent bill:data-intake-manifest"],
                "futuresDataEvidence": ["npm run --silent bill:futures-data-requirements"],
                "operatorRead": "review only",
            },
            "items": [
                {
                    "relativePath": "data/free/NQ-1m-5d.csv",
                    "gitStatus": "M",
                    "classification": "research-refresh-current-window",
                    "risk": "research-only-current-window-not-execution-grade",
                    "rows": 10,
                    "startTs": "2026-05-29T20:50:00Z",
                    "endTs": "2026-05-29T20:59:00Z",
                    "symbols": ["NQ"],
                }
            ],
            "hardRules": ["Research CSV freshness does not satisfy execution-grade realtime data requirements."],
        }

        markdown = render_markdown(payload)

        self.assertIn("research inputs, not execution-grade routing data", markdown)
        self.assertIn("## Next Commands", markdown)
        self.assertIn("## Validation Command Sets", markdown)
        self.assertIn("Research CSV freshness does not satisfy execution-grade realtime data requirements.", markdown)

    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^bill-data-intake-manifest-\d{4}-\d{2}-\d{2}\.md$")


if __name__ == "__main__":
    unittest.main()
