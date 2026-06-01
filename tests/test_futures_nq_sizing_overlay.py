import unittest

from scripts.futures_nq_sizing_overlay import build_overlay, contracts_for_trade, parse_profiles


class FuturesNqSizingOverlayTest(unittest.TestCase):
    def test_risk_budget_contracts_floor_and_cap(self):
        profile = {"kind": "risk_budget", "riskDollars": 500}

        self.assertEqual(
            contracts_for_trade(profile, risk_points=20, point_value=20, max_contracts=10),
            1,
        )
        self.assertEqual(
            contracts_for_trade(profile, risk_points=100, point_value=20, max_contracts=10),
            0,
        )

    def test_overlay_changes_only_sizing_and_blocks_bad_risk_fit(self):
        replay = {
            "decision": "research-only-historical-session-replay-watch",
            "strategy": "fabervaale-orb",
            "tradeCount": 3,
            "trades": [
                {"date": "2026-01-01", "openingRangePoints": 10, "netR": 1.0},
                {"date": "2026-01-02", "openingRangePoints": 10, "netR": -1.0},
                {"date": "2026-01-03", "openingRangePoints": 10, "netR": 1.0},
            ],
        }

        payload = build_overlay(
            replay=replay,
            profiles=parse_profiles("fixed:1,risk:500"),
            point_value=20,
            max_contracts=10,
            daily_loss_limit=2000,
            maximum_loss_limit=3000,
        )

        self.assertEqual(payload["oneVariable"], "position sizing only")
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertEqual(payload["profileResults"][0]["summary"]["netPnl"], 200)
        self.assertEqual(payload["profileResults"][1]["profile"]["riskDollars"], 500)

    def test_default_account_assumptions_are_topstep_50k_mnq(self):
        replay = {
            "decision": "research-only-historical-session-replay-watch",
            "strategy": "fabervaale-orb",
            "trades": [
                {"date": "2026-01-01", "openingRangePoints": 1, "netR": 1.0},
            ],
        }

        payload = build_overlay(
            replay=replay,
            profiles=parse_profiles("fixed:100"),
        )

        self.assertEqual(payload["assumptions"]["accountSize"], "50K")
        self.assertEqual(payload["assumptions"]["profitTarget"], 3000.0)
        self.assertEqual(payload["assumptions"]["dailyLossLimit"], 1000.0)
        self.assertEqual(payload["assumptions"]["maximumLossLimit"], 2000.0)
        self.assertEqual(payload["assumptions"]["bestDayRecommendation"], 1500.0)
        self.assertEqual(payload["assumptions"]["maxContracts"], 50)
        self.assertEqual(payload["profileResults"][0]["realizedSample"][0]["contracts"], 50)


if __name__ == "__main__":
    unittest.main()
