import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from scripts.futures_nq_session_structure_audit import as_new_york, build_report, in_ny_session, session_date


class FuturesNqSessionStructureAuditTests(unittest.TestCase):
    def test_session_audit_is_research_only_and_blocks_thin_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parquet = root / "nq.parquet"
            rows = []
            start = datetime(2025, 10, 6, 13, 30)
            for day in range(3):
                day_start = start + timedelta(days=day)
                for minute in range(180):
                    ts = day_start + timedelta(minutes=minute)
                    base = 25000 + day * 100 + minute * 0.25
                    rows.append({
                        "ts": ts,
                        "open": base,
                        "high": base + 2,
                        "low": base - 2,
                        "close": base + 0.5,
                        "volume": 100 + minute,
                    })
            pl.DataFrame(rows).write_parquet(parquet)
            external = root / "external.json"
            external.write_text(json.dumps({
                "nqSourceParity": {"ok": True},
                "nqLocalParity": {"ok": False, "reason": "date-range-mismatch-or-no-overlap"},
            }))

            payload = build_report(Namespace(
                input=str(parquet),
                input_was_explicit=True,
                external_audit=str(external),
                current_parity=str(root / "missing-current.json"),
                cadence_minutes=1,
                opening_range_minutes=30,
                min_session_rows=120,
                min_oos_sessions=20,
            ))

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertTrue(payload["sourceParityOk"])
        self.assertFalse(payload["localParityOk"])
        self.assertEqual(payload["sessionCount"], 3)
        self.assertIn("too-few-sessions-for-oos-research-contract", payload["blockers"])
        self.assertEqual(payload["decision"], "research-only-insufficient-history-for-oos")

    def test_prefers_clean_current_local_pair_for_session_depth_without_broker_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv = root / "nq-5m.csv"
            rows = ["ts,symbol,open,high,low,close,volume"]
            start = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)
            for day in range(25):
                day_start = start + timedelta(days=day)
                for bar in range(78):
                    ts = day_start + timedelta(minutes=bar * 5)
                    base = 25000 + day * 10 + bar
                    rows.append(f"{ts.isoformat().replace('+00:00', 'Z')},NQ,{base},{base+2},{base-2},{base+1},100")
            csv.write_text("\n".join(rows) + "\n")
            external = root / "external.json"
            external.write_text(json.dumps({
                "nqSourceParity": {"ok": False},
                "nqLocalParity": {"ok": False, "reason": "broker-parity-missing"},
            }))
            current = root / "current.json"
            current.write_text(json.dumps({
                "cleanLocalResearchPairCount": 1,
                "brokerParityChecked": False,
                "bestCurrentLocalResearchPair": {
                    "leftPath": str(csv),
                    "pairId": "test-nq-5m",
                    "cadenceMinutes": 5,
                    "researchClean": True,
                },
            }))

            payload = build_report(Namespace(
                input=str(root / "unused-default.parquet"),
                input_was_explicit=False,
                external_audit=str(external),
                current_parity=str(current),
                cadence_minutes=0,
                opening_range_minutes=30,
                min_session_rows=0,
                min_oos_sessions=20,
            ))

        self.assertEqual(payload["inputSource"]["kind"], "current-local-clean-pair")
        self.assertEqual(payload["bestCurrentLocalResearchPair"], "test-nq-5m")
        self.assertEqual(payload["cadenceMinutes"], 5)
        self.assertGreaterEqual(payload["sessionCount"], 20)
        self.assertTrue(payload["sourceParityOk"])
        self.assertTrue(payload["currentInternalParityOk"])
        self.assertFalse(payload["brokerParityChecked"])
        self.assertFalse(payload["localParityOk"])
        self.assertNotIn("too-few-sessions-for-oos-research-contract", payload["blockers"])
        self.assertIn("current-local-or-broker-parity-not-cleared", payload["blockers"])
        self.assertEqual(payload["decision"], "research-only-insufficient-history-for-oos")

    def test_session_filter_uses_new_york_timezone_and_dst(self):
        summer_open_utc = datetime(2025, 10, 6, 13, 30, tzinfo=timezone.utc)
        winter_open_utc = datetime(2025, 12, 1, 14, 30, tzinfo=timezone.utc)

        self.assertEqual(as_new_york(summer_open_utc).strftime("%H:%M"), "09:30")
        self.assertEqual(as_new_york(winter_open_utc).strftime("%H:%M"), "09:30")
        self.assertTrue(in_ny_session(summer_open_utc))
        self.assertTrue(in_ny_session(winter_open_utc))
        self.assertEqual(session_date(datetime(2025, 10, 6, 1, 0, tzinfo=timezone.utc)), "2025-10-05")


if __name__ == "__main__":
    unittest.main()
