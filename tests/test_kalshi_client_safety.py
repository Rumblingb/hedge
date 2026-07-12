import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import kalshi_client


class FakeKalshiClient(kalshi_client.KalshiClient):
    def __init__(self):
        super().__init__(demo=True)

    def get_markets(self, status="open", limit=50, category=None):
        return {
            "markets": [
                {
                    "ticker": "KXTEST-1",
                    "title": "Will test resolve?",
                    "yes_bid_dollars": "0.55",
                    "no_bid_dollars": "0.47",
                    "yes_ask_dollars": "0.35",
                    "volume_24h_fp": "2000",
                    "close_time": "2099-01-01T00:00:00Z",
                }
            ]
        }


class KalshiClientSafetyTests(unittest.TestCase):
    def test_scan_is_research_only_and_not_tradable(self):
        result = FakeKalshiClient().scan_opportunities(min_edge=0.01, max_stake=10)

        self.assertTrue(result["researchOnly"])
        self.assertFalse(result["writesOrders"])
        self.assertFalse(result["touchesBroker"])
        self.assertFalse(result["movesFunds"])
        self.assertFalse(result["readyForPaper"])
        self.assertFalse(result["readyForExecution"])
        self.assertFalse(result["tradable_signal"])
        self.assertGreaterEqual(result["count"], 1)
        self.assertTrue(all(opp["paperCandidateOnly"] for opp in result["opportunities"]))

    def test_account_reads_require_explicit_read_only_opt_in(self):
        client = kalshi_client.KalshiClient(demo=True)

        with self.assertRaises(PermissionError):
            client.get_balance()
        with self.assertRaises(PermissionError):
            client.get_positions()

    def test_run_scan_writes_canonical_safety_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(kalshi_client, "STATE_DIR", Path(tmp)):
                with patch.object(kalshi_client, "KalshiClient", lambda demo=True: FakeKalshiClient()):
                    result = kalshi_client.run_kalshi_scan()

            artifact = Path(tmp) / "kalshi-opportunities.latest.json"
            self.assertTrue(artifact.exists())

        self.assertTrue(result["researchOnly"])
        self.assertIn("research sizing reference", result["capitalPlan"])


if __name__ == "__main__":
    unittest.main()
