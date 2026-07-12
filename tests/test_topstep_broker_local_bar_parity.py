import argparse
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import topstep_broker_local_bar_parity as parity


def write_csv(path: Path, rows: list[tuple[str, str, float, float, float, float, float]]) -> None:
    path.write_text(
        "ts,symbol,open,high,low,close,volume\n"
        + "\n".join(
            f"{ts},{symbol},{open_},{high},{low},{close},{volume}"
            for ts, symbol, open_, high, low, close, volume in rows
        )
        + "\n"
    )


class TopstepBrokerLocalBarParityTests(unittest.TestCase):
    def test_compare_rows_passes_on_overlapping_ohlc_with_volume_reference_only(self):
        broker = {
            "2026-06-02T12:00:00Z": {
                "ts": "2026-06-02T12:00:00Z",
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 200.0,
            }
        }
        local = {
            "2026-06-02T12:00:00Z": {
                "ts": "2026-06-02T12:00:00Z",
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.5,
                "volume": 1.0,
            }
        }

        result = parity.compare_rows(
            broker=broker,
            local=local,
            path=Path("local.csv"),
            price_tolerance=0.25,
            min_overlap=1,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["overlapRows"], 1)
        self.assertEqual(result["maxVolumeAbsDiffReferenceOnly"], 199.0)

    def test_build_report_is_read_only_and_never_execution_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "NQ-1m-5d.csv"
            write_csv(
                local,
                [
                    ("2026-06-02T12:00:00.000Z", "NQ", 100.0, 101.0, 99.5, 100.5, 10.0),
                    ("2026-06-02T12:01:00.000Z", "NQ", 100.5, 102.0, 100.0, 101.5, 11.0),
                ],
            )
            args = argparse.Namespace(
                search_text="NQ",
                lookback_minutes=120,
                limit=240,
                price_tolerance=0.25,
                min_overlap=2,
                exclude_latest_overlap_bars=1,
                live=False,
                local_csv=[str(local)],
            )
            bars = [
                {"t": "2026-06-02T12:00:00+00:00", "o": 100.0, "h": 101.0, "l": 99.5, "c": 100.5, "v": 50},
                {"t": "2026-06-02T12:01:00+00:00", "o": 100.5, "h": 102.0, "l": 100.0, "c": 101.5, "v": 55},
            ]
            contract = {
                "id": "CON.F.US.ENQ.M26",
                "name": "NQM6",
                "description": "E-mini NASDAQ-100: June 2026",
                "tickSize": 0.25,
                "tickValue": 5,
                "activeContract": True,
                "symbolId": "F.US.ENQ",
            }

            with patch.object(parity.topstep_md, "safety_blockers", return_value=[]), \
                patch.object(parity, "fetch_broker_nq_bars", return_value=(bars, contract)):
                payload = parity.build_report(args)

        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["brokerParityChecked"])
        self.assertTrue(payload["brokerParityPassed"])
        self.assertTrue(payload["researchOnly"])
        self.assertTrue(payload["touchesBroker"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["placesOrders"])
        self.assertFalse(payload["modifiesOrders"])
        self.assertFalse(payload["cancelsOrders"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForLive"])

    def test_parse_ts_normalizes_to_minute_utc(self):
        ts = parity.parse_ts(datetime(2026, 6, 2, 12, 0, 45, tzinfo=timezone.utc).isoformat())

        self.assertEqual(parity.iso_minute(ts), "2026-06-02T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
