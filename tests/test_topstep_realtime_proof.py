import argparse
import json
import unittest
from unittest.mock import patch

from scripts import topstep_realtime_proof as proof


class FakeWebSocket:
    def __init__(self, frames):
        self.frames = list(frames)
        self.sent = []
        self.timeout = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def send(self, value):
        self.sent.append(value)

    def recv(self):
        if not self.frames:
            raise TimeoutError("test timeout")
        return self.frames.pop(0)

    def close(self):
        self.closed = True


class TopstepRealtimeProofTests(unittest.TestCase):
    def test_signalr_record_parser_handles_multiple_records(self):
        raw = (
            json.dumps({"type": 6})
            + proof.RECORD_SEPARATOR
            + json.dumps({"type": 1, "target": "GatewayQuote", "arguments": ["CON", {"lastPrice": 1}]})
            + proof.RECORD_SEPARATOR
        )

        parsed = proof.parse_signalr_records(raw)

        self.assertEqual(parsed[0]["type"], 6)
        self.assertEqual(parsed[1]["target"], "GatewayQuote")

    def test_build_report_counts_quote_events_without_execution_authority(self):
        args = argparse.Namespace(
            search_text="NQ",
            duration_sec=0.01,
            connect_timeout_sec=1,
            recv_timeout_sec=0.01,
            live=False,
        )
        contracts = {
            "NQ": {"id": "CON.F.US.ENQ.M26", "symbolId": "F.US.ENQ", "name": "NQ Jun 2026"},
            "MNQ": {"id": "CON.F.US.MNQ.M26", "symbolId": "F.US.MNQ", "name": "MNQ Jun 2026"},
        }
        frame = (
            json.dumps({
                "type": 1,
                "target": "GatewayQuote",
                "arguments": ["CON.F.US.ENQ.M26", {"lastPrice": 30000, "timestamp": "2026-06-02T19:00:00Z"}],
            })
            + proof.RECORD_SEPARATOR
            + json.dumps({
                "type": 1,
                "target": "GatewayQuote",
                "arguments": ["CON.F.US.MNQ.M26", {"lastPrice": 30001, "timestamp": "2026-06-02T19:00:01Z"}],
            })
            + proof.RECORD_SEPARATOR
        )
        fake = FakeWebSocket([frame])
        connector = lambda url, timeout: fake

        with patch.object(proof.topstep_md, "safety_blockers", return_value=[]), \
            patch.object(proof.topstep_md, "login", return_value="token"), \
            patch.object(proof, "select_contracts", return_value=contracts):
            report = proof.build_report(args, connector=connector)

        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["readyForExecutionDataProof"])
        self.assertTrue(report["researchOnly"])
        self.assertTrue(report["touchesBroker"])
        self.assertEqual(report["brokerTouchMode"], "read-only-market-realtime")
        self.assertFalse(report["writesOrders"])
        self.assertFalse(report["writesRealtimeQuoteState"])
        self.assertFalse(report["readyForExecution"])
        self.assertEqual(report["symbols"]["NQ"]["quotes"], 1)
        self.assertEqual(report["symbols"]["MNQ"]["quotes"], 1)
        self.assertTrue(fake.closed)
        self.assertGreaterEqual(len(fake.sent), 7)  # handshake + 3 subscriptions per contract

    def test_build_realtime_quote_state_requires_nq_and_es(self):
        report = {
            "brokerTouchMode": "read-only-market-realtime",
            "symbols": {
                "NQ": {
                    "lastQuoteTimestamp": "2026-06-02T20:00:01Z",
                    "lastQuoteSample": {"lastPrice": 30000.25, "bestBid": 30000.0, "bestAsk": 30000.25, "volume": 1000},
                },
                "ES": {
                    "lastQuoteTimestamp": "2026-06-02T20:00:00Z",
                    "lastQuoteSample": {"lastPrice": 5400.25, "bestBid": 5400.0, "bestAsk": 5400.25, "volume": 2000},
                },
            },
        }

        state = proof.build_realtime_quote_state(report, "2026-06-02T20:00:02+00:00")

        self.assertEqual(state["source"], "topstep_realtime")
        self.assertTrue(state["execution_grade"])
        self.assertEqual(state["timestamp"], "2026-06-02T20:00:00+00:00")
        self.assertEqual(state["price_nq"], 30000.25)
        self.assertEqual(state["price_es"], 5400.25)
        self.assertFalse(state["writesOrders"])
        self.assertFalse(state["readyForExecution"])


if __name__ == "__main__":
    unittest.main()
