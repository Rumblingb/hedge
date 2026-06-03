import unittest
from pathlib import Path


ROOT = Path("/Users/brain/hedge")


class PredictionFundingQuarantineTest(unittest.TestCase):
    def assert_helper_default_denied(self, relative):
        text = (ROOT / relative).read_text()
        self.assertIn("HERMES_ALLOW_POLYMARKET_FUNDING", text)
        self.assertIn("I_UNDERSTAND_THIS_MOVES_FUNDS", text)
        self.assertIn("process.exit(2)", text)
        self.assertIn("BLOCKED", text)

    def test_active_polymarket_funding_helpers_are_default_denied(self):
        for relative in [
            "scripts/wire-up.ts",
            "scripts/swap-and-fund.ts",
        ]:
            with self.subTest(path=relative):
                self.assert_helper_default_denied(relative)

    def test_retired_polymarket_funding_helpers_are_quarantined(self):
        for relative in [
            ".retired/deposit-clob.ts",
            ".retired/deposit-simple.ts",
            ".retired/fund-and-trade.ts",
        ]:
            with self.subTest(path=relative):
                self.assert_helper_default_denied(relative)

    def test_legacy_funding_helpers_are_not_active_source(self):
        for relative in [
            "scripts/deposit-clob.ts",
            "scripts/deposit-simple.ts",
            "scripts/fund-and-trade.ts",
        ]:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists())

    def test_no_hardcoded_polymarket_relayer_api_keys(self):
        for relative in [
            ".retired/fund-and-trade.ts",
            "scripts/swap-and-fund.ts",
        ]:
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text()
                self.assertNotRegex(text, r"RELAYER_KEY\\s*=\\s*['\"][0-9a-f]{8}-")
                self.assertIn("POLYMARKET_RELAYER_API_KEY", text)


if __name__ == "__main__":
    unittest.main()
