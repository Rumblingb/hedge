import json
import tempfile
import unittest
from pathlib import Path

from scripts.free_data_feed_audit import build_audit, render_markdown


class FreeDataFeedAuditTests(unittest.TestCase):
    def test_feed_audit_is_research_only_and_keeps_topstep_as_futures_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text(
                "FINNHUB_API_KEY=finnhub-key\n"
                "RH_TOPSTEP_USERNAME=topstep-user\n"
                "RH_TOPSTEP_API_KEY=topstep-key\n"
                "FRED_API_KEY=fred-key\n"
                "ALPHA_VANTAGE_API_KEY=av-key\n"
                "NOUS_API_KEY=possibly-truncated\n"
            )
            audit = build_audit(env_paths=[env])

        self.assertEqual(audit["decision"], "research-feeds-visible-execution-locked")
        self.assertEqual(audit["preferredFuturesDataPath"], "topstepx-projectx")
        self.assertTrue(audit["researchOnly"])
        self.assertFalse(audit["writesOrders"])
        self.assertFalse(audit["touchesBroker"])
        self.assertFalse(audit["movesFunds"])
        self.assertFalse(audit["executionAuthority"])
        self.assertFalse(audit["readyForExecution"])

        by_id = {row["id"]: row for row in audit["providers"]}
        self.assertEqual(by_id["topstepx-projectx"]["mode"], "wired-research")
        self.assertIn("RH_TOPSTEP_USERNAME", by_id["topstepx-projectx"]["env"]["present"])
        self.assertEqual(by_id["finnhub"]["mode"], "wired-research")
        self.assertEqual(by_id["fred"]["mode"], "wired-research")
        self.assertEqual(by_id["alpha-vantage"]["mode"], "configured-not-wired")
        self.assertEqual(by_id["databento"]["mode"], "optional-future")
        self.assertNotIn("databento", audit["summary"]["wiredResearchFeeds"])
        self.assertIn("databento", audit["summary"]["optionalFutureResearch"])
        self.assertEqual(by_id["nous"]["mode"], "configured-not-wired")
        self.assertFalse(by_id["alpaca-paper"]["executionAuthority"])
        self.assertIn("futures broker truth", by_id["finnhub"]["notAllowed"])

    def test_render_markdown_does_not_include_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("FINNHUB_API_KEY=super-secret-value\n")
            audit = build_audit(env_paths=[env])
            markdown = render_markdown(audit)

        self.assertIn("Free Data Feed Audit", markdown)
        self.assertIn("Finnhub", markdown)
        self.assertNotIn("super-secret-value", markdown)

    def test_json_round_trip(self):
        audit = build_audit(env_paths=[])
        encoded = json.dumps(audit)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["summary"]["providerCount"], len(decoded["providers"]))


if __name__ == "__main__":
    unittest.main()
