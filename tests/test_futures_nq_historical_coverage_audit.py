import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from scripts.futures_nq_historical_coverage_audit import (
    CandidateSpec,
    VAULT,
    build_audit,
    default_markdown_path,
    render_markdown,
)


def write_parquet(path: Path, days: int, cadence_minutes: int = 15) -> None:
    rows = []
    start = datetime(2026, 1, 5, 14, 30)
    for day in range(days):
        day_start = start + timedelta(days=day)
        for bar in range(27):
            ts = day_start + timedelta(minutes=bar * cadence_minutes)
            base = 21000 + day * 10 + bar
            rows.append({
                "ts": ts,
                "open": float(base),
                "high": float(base + 1),
                "low": float(base - 1),
                "close": float(base + 0.25),
                "volume": float(100 + bar),
            })
    pl.DataFrame(rows).write_parquet(path)


def write_csv(path: Path, rows: list[dict]) -> None:
    pl.DataFrame(rows).write_csv(path)


class FuturesNqHistoricalCoverageAuditTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^futures-nq-historical-coverage-audit-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "usableHistoricalOosCount": 0,
            "preferredPromotionDepthCount": 0,
            "currentLocalCsvParityClearedCount": 0,
            "currentLocalCsvParityCheckedCount": 0,
            "bestHistoricalOosCandidate": {},
            "blockers": [],
            "candidates": [],
            "hardRules": [],
        })

        self.assertIn("# Futures NQ Historical Coverage Audit - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_marks_long_source_clean_candidate_as_research_ready_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nq.parquet"
            write_parquet(path, days=25)
            payload = build_audit([
                CandidateSpec(
                    datasetId="unit_nq_15m",
                    path=path,
                    cadenceMinutes=15,
                    source="unit",
                    sourceCsv=None,
                )
            ])

        self.assertEqual(payload["decision"], "research-only-historical-nq-source-ready")
        self.assertEqual(payload["usableHistoricalOosCount"], 1)
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])

    def test_archive_only_candidate_does_not_clear_research_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nq.parquet"
            write_parquet(path, days=25)
            payload = build_audit([
                CandidateSpec(
                    datasetId="unit_archive",
                    path=path,
                    cadenceMinutes=15,
                    source="unit",
                    archiveOnly=True,
                )
            ])

        self.assertEqual(payload["decision"], "research-only-historical-nq-source-blocked")
        self.assertEqual(payload["usableHistoricalOosCount"], 0)
        self.assertIn("archive-only-source-not-demo-evidence", payload["candidates"][0]["blockers"])

    def test_reads_yahoo_style_capitalized_csv_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nq.csv"
            rows = []
            start = datetime(2026, 1, 5, 14, 30)
            for day in range(20):
                for bar in range(27):
                    ts = start + timedelta(days=day, minutes=bar * 15)
                    rows.append({
                        "Datetime": ts.isoformat(),
                        "Open": 1.0,
                        "High": 2.0,
                        "Low": 0.5,
                        "Close": 1.5,
                        "Volume": 10.0,
                    })
            pl.DataFrame(rows).write_csv(path)
            payload = build_audit([
                CandidateSpec(
                    datasetId="unit_yahoo_csv",
                    path=path,
                    cadenceMinutes=15,
                    source="unit",
                )
            ])

        self.assertEqual(payload["candidates"][0]["sessionCount"], 20)
        self.assertEqual(payload["usableHistoricalOosCount"], 1)

    def test_current_local_csv_parity_clears_when_bars_overlap_and_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parquet = root / "nq.parquet"
            local_csv = root / "nq-local.csv"
            rows = []
            start = datetime(2026, 1, 5, 14, 30)
            for day in range(20):
                for bar in range(27):
                    ts = start + timedelta(days=day, minutes=bar * 15)
                    base = 21000 + day * 10 + bar
                    rows.append({
                        "ts": ts,
                        "symbol": "NQ",
                        "open": float(base),
                        "high": float(base + 1),
                        "low": float(base - 1),
                        "close": float(base + 0.25),
                        "volume": float(100 + bar),
                    })
            pl.DataFrame(rows).write_parquet(parquet)
            write_csv(local_csv, [
                {
                    "ts": row["ts"].isoformat() + "Z",
                    "symbol": "NQ",
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": int(row["volume"]),
                }
                for row in rows
            ])

            payload = build_audit([
                CandidateSpec(
                    datasetId="unit_current_parity",
                    path=parquet,
                    cadenceMinutes=15,
                    source="unit",
                    localCsv=local_csv,
                )
            ])

        self.assertEqual(payload["currentLocalCsvParityCheckedCount"], 1)
        self.assertEqual(payload["currentLocalCsvParityClearedCount"], 1)
        self.assertTrue(payload["candidates"][0]["currentLocalCsvParity"]["ok"])
        self.assertNotIn("current-local-csv-parity-not-cleared", payload["candidates"][0]["blockers"])

    def test_current_local_csv_no_overlap_is_visible_but_does_not_block_historical_research(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parquet = root / "nq-old.parquet"
            local_csv = root / "nq-current.csv"
            write_parquet(parquet, days=20)
            write_csv(local_csv, [
                {
                    "ts": (datetime(2027, 1, 5, 14, 30) + timedelta(minutes=bar * 15)).isoformat() + "Z",
                    "symbol": "NQ",
                    "open": 1.0,
                    "high": 2.0,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 10,
                }
                for bar in range(27)
            ])

            payload = build_audit([
                CandidateSpec(
                    datasetId="unit_old_source",
                    path=parquet,
                    cadenceMinutes=15,
                    source="unit",
                    localCsv=local_csv,
                )
            ])

        self.assertEqual(payload["decision"], "research-only-historical-nq-source-ready")
        self.assertEqual(payload["usableHistoricalOosCount"], 1)
        self.assertEqual(payload["currentLocalCsvParityClearedCount"], 0)
        self.assertIn("no-seagate-nq-source-overlaps-current-local-csv-bars", payload["blockers"])
        self.assertIn("current-local-csv-parity-not-cleared", payload["candidates"][0]["blockers"])
        self.assertEqual(
            payload["candidates"][0]["currentLocalCsvParity"]["reason"],
            "no-overlapping-bars-with-current-local-csv",
        )


if __name__ == "__main__":
    unittest.main()
