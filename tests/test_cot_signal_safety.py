import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cot_signal
from scripts import signal_arbitration
from scripts.new_arsenal_gate import new_arsenal_gate


HEADER = [
    "Market_and_Exchange_Names",
    "FutOnly_or_Combined",
    "Report_Date_as_YYYY-MM-DD",
    "Open_Interest_All",
    "Dealer_Positions_Long_All",
    "Dealer_Positions_Short_All",
    "Dealer_Positions_Spread_All",
    "Asset_Mgr_Positions_Long_All",
    "Asset_Mgr_Positions_Short_All",
    "Lev_Money_Positions_Long_All",
    "Lev_Money_Positions_Short_All",
]


def tff_row(market: str, day: int, dealer_long: int, dealer_short: int, lev_long: int, lev_short: int) -> dict[str, str]:
    return {
        "Market_and_Exchange_Names": market,
        "FutOnly_or_Combined": "FutOnly",
        "Report_Date_as_YYYY-MM-DD": f"2026-05-{day:02d}",
        "Open_Interest_All": "100000",
        "Dealer_Positions_Long_All": str(dealer_long),
        "Dealer_Positions_Short_All": str(dealer_short),
        "Dealer_Positions_Spread_All": "0",
        "Asset_Mgr_Positions_Long_All": "45000",
        "Asset_Mgr_Positions_Short_All": "30000",
        "Lev_Money_Positions_Long_All": str(lev_long),
        "Lev_Money_Positions_Short_All": str(lev_short),
    }


def write_tff(path: Path) -> None:
    market = "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE"
    rows = [
        tff_row(market, 1, 30000, 40000, 20000, 25000),
        tff_row(market, 8, 29000, 41000, 21000, 25000),
        tff_row(market, 15, 28000, 42000, 22000, 25000),
        tff_row(market, 22, 27000, 43000, 23000, 25000),
        tff_row(market, 29, 10000, 60000, 50000, 15000),
    ]
    with path.open("w", newline="") as fh:
        fh.write(",".join(HEADER) + "\n")
        for row in rows:
            fh.write(",".join(row[column] for column in HEADER) + "\n")


class CotSignalSafetyTests(unittest.TestCase):
    def test_cot_signal_prefers_fresh_official_positioning_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / "state"
            state_dir.mkdir()
            positioning_file = state_dir / "cftc-tff-positioning.latest.json"
            positioning_file.write_text(json.dumps({
                "freshForWeeklyResearch": True,
                "markets": {
                    "NQ": {
                        "symbol": "NQ",
                        "reportDate": "2026-05-26",
                        "records": 52,
                        "openInterest": 100000,
                        "dealerNetPct": -10,
                        "assetManagerNetPct": 5,
                        "leveragedMoneyNetPct": 8,
                        "dealerZ52": -1.8,
                        "assetManagerZ52": 0.2,
                        "leveragedMoneyZ52": 1.6,
                        "positioningRegime": "risk-on-confirmed-by-leveraged-money",
                    }
                },
            }))

            with patch.object(cot_signal, "STATE_DIR", state_dir), \
                 patch.object(cot_signal, "STATE_FILE", state_dir / "cot-signal.latest.json"), \
                 patch.object(cot_signal, "CFTC_POSITIONING_FILE", positioning_file), \
                 patch.object(cot_signal, "COT_DIR", root / "missing-cot"):
                output = cot_signal.run()

            self.assertEqual(output["source"], "cot-cftc-positioning-intake")
            self.assertEqual(output["nq_bias"], "bullish")
            self.assertTrue(output["researchOnly"])
            self.assertFalse(output["tradable_signal"])

    def test_cot_signal_writes_shadow_only_canonical_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / "state"
            cot_dir = root / "cot"
            cot_dir.mkdir()
            write_tff(cot_dir / "tff-2026.csv")

            with patch.object(cot_signal, "STATE_DIR", state_dir), \
                 patch.object(cot_signal, "STATE_FILE", state_dir / "cot-signal.latest.json"), \
                 patch.object(cot_signal, "CFTC_POSITIONING_FILE", state_dir / "missing-positioning.json"), \
                 patch.object(cot_signal, "COT_DIR", cot_dir):
                output = cot_signal.run()

            self.assertIsNotNone(output)
            written = json.loads((state_dir / "cot-signal.latest.json").read_text())
            self.assertTrue(written["researchOnly"])
            self.assertFalse(written["writesOrders"])
            self.assertFalse(written["touchesBroker"])
            self.assertFalse(written["promoted_for_execution"])
            self.assertFalse(written["tradable_signal"])
            self.assertEqual(written["evidence_level"], "weekly_cftc_positioning_research_only")
            self.assertIn("NQ", written["markets"])

    def test_new_arsenal_gate_ignores_unpromoted_cot(self):
        with patch("scripts.new_arsenal_gate.read_signal") as read_signal:
            read_signal.side_effect = lambda name: {
                "cot-signal.latest.json": {
                    "nq_bias": "bullish",
                    "promoted_for_execution": False,
                    "tradable_signal": False,
                }
            }.get(name, {})

            result = new_arsenal_gate({"side": "long"})

        self.assertEqual(result["confidence_modifier"], 0.9)
        self.assertIn("COT positioning is weekly research-only", " ".join(result["reasons"]))

    def test_signal_arbitration_ignores_unpromoted_cot(self):
        direction, confidence = signal_arbitration.extract_direction(
            "cot-signal",
            {
                "nq_bias": "bullish",
                "markets": {"NQ": {"direction": "bullish", "dealer": {"z_score": -3}}},
                "promoted_for_execution": False,
                "tradable_signal": False,
            },
        )

        self.assertEqual((direction, confidence), (0, 0))


if __name__ == "__main__":
    unittest.main()
