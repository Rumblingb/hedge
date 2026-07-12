import unittest

from scripts.futures_nq_historical_session_cost_stress import (
    VAULT,
    build_cost_stress,
    default_markdown_path,
    render_markdown,
)


def replay_with_trades(gross_r: float, risk: float = 20.0, count: int = 30):
    return {
        "decision": "research-only-historical-session-replay-watch",
        "trades": [
            {"date": f"2026-01-{idx + 1:02d}", "grossR": gross_r, "openingRangePoints": risk}
            for idx in range(count)
        ],
    }


class FuturesNqHistoricalSessionCostStressTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^futures-nq-historical-session-cost-stress-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "survivingCaseCount": 0,
            "caseCount": 0,
            "blockers": [],
            "cases": [],
            "hardRules": [],
        })

        self.assertIn("# Futures NQ Historical Session Cost Stress - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_surviving_cost_cases_remain_research_only(self):
        payload = build_cost_stress(
            replay=replay_with_trades(0.8),
            cost_points_cases=[2.0, 4.0],
        )

        self.assertEqual(payload["decision"], "research-only-historical-session-cost-stress-watch")
        self.assertEqual(payload["survivingCaseCount"], 2)
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])

    def test_blocks_when_wider_cost_case_breaks_oos(self):
        payload = build_cost_stress(
            replay=replay_with_trades(0.15),
            cost_points_cases=[2.0, 6.0],
        )

        self.assertEqual(payload["decision"], "research-only-historical-session-cost-stress-blocked")
        self.assertIn("not-all-cost-cases-survive-oos-contract", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
