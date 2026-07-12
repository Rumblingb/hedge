import tempfile
import unittest
from pathlib import Path

from scripts.futures_nq_current_data_parity import (
    VAULT,
    ParityPair,
    build_audit,
    default_markdown_path,
    render_markdown,
)


def write_csv(path: Path, rows: list[tuple[str, str, float, float, float, float, float]]) -> None:
    path.write_text(
        "ts,symbol,open,high,low,close,volume\n"
        + "\n".join(
            f"{ts},{symbol},{open_},{high},{low},{close},{volume}"
            for ts, symbol, open_, high, low, close, volume in rows
        )
        + "\n"
    )


class FuturesNqCurrentDataParityTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^futures-nq-current-data-parity-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "cleanLocalResearchPairCount": 0,
            "bestCurrentLocalResearchPair": {},
            "blockers": [],
            "comparisons": [],
            "hardRules": [],
        })

        self.assertIn("# Futures NQ Current Data Parity - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_clean_local_pair_is_research_ready_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "NQ-5m.csv"
            right = root / "ALL-5m.csv"
            rows = [
                ("2026-05-29T14:30:00.000Z", "NQ", 100.0, 101.0, 99.0, 100.5, 10.0),
                ("2026-05-29T14:35:00.000Z", "NQ", 100.5, 102.0, 100.0, 101.5, 11.0),
                ("2026-05-29T14:40:00.000Z", "NQ", 101.5, 103.0, 101.0, 102.5, 12.0),
            ]
            write_csv(left, rows)
            write_csv(right, rows + [("2026-05-29T14:45:00.000Z", "ES", 1.0, 1.0, 1.0, 1.0, 1.0)])

            payload = build_audit([ParityPair("clean", 5, left, right)])

        self.assertEqual(payload["decision"], "research-only-current-local-parity-ready")
        self.assertEqual(payload["cleanLocalResearchPairCount"], 1)
        self.assertEqual(payload["bestCurrentLocalResearchPair"]["pairId"], "clean")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["brokerParityChecked"])
        self.assertIn("broker-parity-not-checked-by-this-artifact", payload["blockers"])

    def test_mismatch_blocks_research_source_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "NQ-1m.csv"
            right = root / "ALL-1m.csv"
            write_csv(left, [("2026-05-29T14:30:00.000Z", "NQ", 100.0, 101.0, 99.0, 100.5, 10.0)])
            write_csv(right, [("2026-05-29T14:30:00.000Z", "NQ", 100.0, 101.0, 99.0, 101.0, 12.0)])

            payload = build_audit([ParityPair("mismatch", 1, left, right)])

        comparison = payload["comparisons"][0]
        self.assertEqual(payload["decision"], "research-only-current-local-parity-blocked")
        self.assertEqual(payload["cleanLocalResearchPairCount"], 0)
        self.assertFalse(comparison["ok"])
        self.assertEqual(comparison["reason"], "local-file-parity-mismatch")
        self.assertTrue(comparison["mismatchSample"])
        self.assertIn("no-current-local-nq-file-pair-is-internally-clean", payload["blockers"])

    def test_best_pair_prefers_fresher_current_data_over_larger_stale_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fresh_left = root / "fresh-left.csv"
            fresh_right = root / "fresh-right.csv"
            stale_left = root / "stale-left.csv"
            stale_right = root / "stale-right.csv"
            fresh_rows = [
                ("2026-06-02T12:00:00.000Z", "NQ", 100.0, 101.0, 99.0, 100.5, 10.0),
                ("2026-06-02T12:01:00.000Z", "NQ", 100.5, 102.0, 100.0, 101.5, 11.0),
            ]
            stale_rows = [
                ("2026-05-15T12:00:00.000Z", "NQ", 100.0, 101.0, 99.0, 100.5, 10.0),
                ("2026-05-15T12:01:00.000Z", "NQ", 100.5, 102.0, 100.0, 101.5, 11.0),
                ("2026-05-15T12:02:00.000Z", "NQ", 101.5, 103.0, 101.0, 102.5, 12.0),
            ]
            for path, rows in [
                (fresh_left, fresh_rows),
                (fresh_right, fresh_rows),
                (stale_left, stale_rows),
                (stale_right, stale_rows),
            ]:
                write_csv(path, rows)

            payload = build_audit([
                ParityPair("stale-larger", 5, stale_left, stale_right),
                ParityPair("fresh-smaller", 1, fresh_left, fresh_right),
            ])

        self.assertEqual(payload["bestCurrentLocalResearchPair"]["pairId"], "fresh-smaller")


if __name__ == "__main__":
    unittest.main()
