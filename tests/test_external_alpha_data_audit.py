import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import polars as pl

from scripts.external_alpha_data_audit import (
    build_audit,
    compare_nq_1m_to_local_csv,
    compare_nq_feature_to_source_csv,
    default_markdown_path,
    leading_indicator_readiness,
    render_markdown,
    summarize_json_date_values,
    summarize_parquet,
    HERMES,
)


class ExternalAlphaDataAuditTest(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^external-alpha-data-audit-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "status": "PASS",
            "datasets": [],
            "nqLocalParity": {},
            "nqSourceParity": {},
            "nqHistoricalResearchUsability": {},
            "blockers": [],
            "hardRules": [],
        })

        self.assertIn("# External Alpha Data Audit - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_summarize_parquet_checks_gold_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.parquet"
            pl.DataFrame({
                "ts": [1, 2],
                "close": [10.0, 11.0],
                "volume": [100.0, 200.0],
            }).write_parquet(path)

            summary = summarize_parquet("sample", {"path": str(path), "gold_features": ["close", "volume"]})

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["rowCount"], 2)
        self.assertEqual(summary["missingGoldFeatures"], [])

    def test_summarize_parquet_accepts_known_gold_feature_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "options.parquet"
            pl.DataFrame({
                "quote_date": [datetime(2026, 1, 1).date()],
                "near_atm_call_iv_5_45d": [0.2],
                "near_atm_put_iv_5_45d": [0.21],
                "skew_25d_put_minus_call": [0.01],
            }).write_parquet(path)

            summary = summarize_parquet(
                "options",
                {"path": str(path), "gold_features": ["atm_iv_5_45d", "skew_25d_proxy"]},
            )

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["missingGoldFeatures"], [])
        self.assertEqual(summary["goldFeatureAliasesUsed"]["atm_iv_5_45d"], ["near_atm_call_iv_5_45d", "near_atm_put_iv_5_45d"])

    def test_nq_parity_passes_for_matching_csv_and_parquet(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            parquet = tmp_path / "nq.parquet"
            csv = tmp_path / "nq.csv"
            pl.DataFrame({
                "ts": [datetime(2026, 5, 26, 4 + minute // 60, minute % 60) for minute in range(120)],
                "close": [100.0 + minute for minute in range(120)],
                "volume": [10.0 + minute for minute in range(120)],
            }).write_parquet(parquet)
            csv.write_text(
                "ts,symbol,open,high,low,close,volume\n"
                + "\n".join(
                    f"2026-05-26T04:{minute:02d}:00.000Z,NQ,0,0,0,{100.0 + minute},{10.0 + minute}"
                    for minute in range(60)
                )
                + "\n"
                + "\n".join(
                    f"2026-05-26T05:{minute:02d}:00.000Z,NQ,0,0,0,{160.0 + minute},{70.0 + minute}"
                    for minute in range(60)
                )
                + "\n"
            )

            parity = compare_nq_1m_to_local_csv(parquet, csv)

        self.assertTrue(parity["ok"])
        self.assertEqual(parity["overlapRows"], 120)
        self.assertEqual(parity["maxCloseAbsDiff"], 0.0)

    def test_nq_source_parity_passes_for_matching_feature_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            parquet = tmp_path / "nq.parquet"
            csv = tmp_path / "NQ_in_1_minute.csv"
            pl.DataFrame({
                "ts": [datetime(2025, 10, 5, 22, minute) for minute in range(5)],
                "symbol": ["NQ"] * 5,
                "open": [100.0 + minute for minute in range(5)],
                "high": [101.0 + minute for minute in range(5)],
                "low": [99.0 + minute for minute in range(5)],
                "close": [100.5 + minute for minute in range(5)],
                "volume": [1000.0 + minute for minute in range(5)],
            }).write_parquet(parquet)
            csv.write_text(
                "datetime,symbol,open,high,low,close,volume\n"
                + "\n".join(
                    f"2025-10-05 22:0{minute}:00,CME_MINI:NQ1!,{100.0 + minute},{101.0 + minute},{99.0 + minute},{100.5 + minute},{1000.0 + minute}"
                    for minute in range(5)
                )
                + "\n"
            )

            parity = compare_nq_feature_to_source_csv("nq_futures_1m", parquet, csv)

        self.assertTrue(parity["ok"])
        self.assertEqual(parity["overlapRows"], 5)
        self.assertEqual(parity["sourceRows"], 5)
        self.assertEqual(parity["featureRows"], 5)

    def test_build_audit_includes_local_futures_ranges(self):
        payload = build_audit({"datasets": {}})

        self.assertIn("localFuturesRanges", payload)
        self.assertIn("nq_1m_5d", payload["localFuturesRanges"])
        self.assertIn("nqSourceParity", payload)
        self.assertIn("nqHistoricalResearchUsability", payload)

    def test_build_audit_separates_historical_use_from_execution_parity(self):
        payload = build_audit()

        usability = payload["nqHistoricalResearchUsability"]
        self.assertFalse(usability["usableForExecutionParity"])
        self.assertIn("current/broker parity", usability["read"])
        if payload["nqLocalParity"].get("reason") == "date-range-mismatch-or-no-overlap":
            self.assertIn(
                "execution/current parity is not proven",
                "; ".join(payload["blockers"]),
            )

    def test_json_date_value_summary_reports_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vix.json"
            path.write_text('[{"date":"2026-06-04","value":15.4},{"date":"2026-06-03","value":16.0}]')

            summary = summarize_json_date_values(path)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["rowCount"], 2)
        self.assertEqual(summary["timeRange"]["min"], "2026-06-03")
        self.assertEqual(summary["timeRange"]["max"], "2026-06-04")

    def test_leading_indicator_readiness_stays_research_only(self):
        payload = leading_indicator_readiness(
            {
                "sp500_options_daily_regime": {
                    "ok": True,
                    "rowCount": 903,
                    "timeRange": {"min": "2010-01-04", "max": "2013-08-16"},
                    "path": "/tmp/options.parquet",
                },
                "equities_5m_breadth_2026_03": {
                    "ok": True,
                    "rowCount": 1295,
                    "timeRange": {"min": "2026-03-02", "max": "2026-03-10"},
                    "path": "/tmp/breadth.parquet",
                },
            }
        )

        self.assertEqual(payload["decision"], "research-only-leading-indicator-data-not-execution-ready")
        self.assertFalse(payload["readyForExecution"])
        by_id = {lane["id"]: lane for lane in payload["lanes"]}
        self.assertEqual(by_id["equities-breadth-sector-rotation"]["status"], "prototype-month-only")
        self.assertFalse(by_id["equities-breadth-sector-rotation"]["usableForWalkforward"])
        self.assertFalse(by_id["spx-put-call-options-regime"]["usableForExecution"])
        self.assertIn("pcr-vix-daily-regime-overlay", [item["id"] for item in payload["nextOneVariableTests"]])

    def test_markdown_includes_leading_indicator_readiness(self):
        markdown = render_markdown(
            {
                "generatedAt": "2026-06-06T09:00:00+00:00",
                "status": "PASS",
                "datasets": [],
                "nqLocalParity": {},
                "nqSourceParity": {},
                "nqHistoricalResearchUsability": {},
                "leadingIndicatorReadiness": {
                    "decision": "research-only-leading-indicator-data-not-execution-ready",
                    "readyForExecution": False,
                    "lanes": [
                        {
                            "id": "vix-regime",
                            "status": "mixed-current-and-stale",
                            "usableForWalkforward": True,
                            "usableForExecution": False,
                            "operatorRead": "Use current VIX JSON for recent context.",
                            "blockers": ["vix-daily-csv-stale-ends-2020"],
                        }
                    ],
                    "nextOneVariableTests": [
                        {
                            "id": "pcr-vix-daily-regime-overlay",
                            "oneVariable": "add daily SPX put/call and VIX regime tag",
                        }
                    ],
                },
                "blockers": [],
                "hardRules": [],
            }
        )

        self.assertIn("Leading Indicator Readiness", markdown)
        self.assertIn("research-only-leading-indicator-data-not-execution-ready", markdown)
        self.assertIn("pcr-vix-daily-regime-overlay", markdown)


if __name__ == "__main__":
    unittest.main()
