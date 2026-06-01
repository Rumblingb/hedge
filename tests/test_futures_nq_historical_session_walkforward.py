import unittest

from scripts.futures_nq_historical_session_walkforward import (
    VAULT,
    build_walkforward,
    default_markdown_path,
    render_markdown,
)


def trades(values):
    return [{"date": f"2026-01-{idx + 1:02d}", "netR": value} for idx, value in enumerate(values)]


class FuturesNqHistoricalSessionWalkforwardTests(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, VAULT / "Agent-Hermes")
        self.assertRegex(path.name, r"^futures-nq-historical-session-walkforward-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "research-only",
            "foldCount": 0,
            "positiveFoldShare": None,
            "worstFoldNetR": None,
            "aggregateStats": {},
            "blockers": [],
            "hardRules": [],
        })

        self.assertIn("# Futures NQ Historical Session Walkforward - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_positive_folds_remain_research_only_watch(self):
        payload = build_walkforward(
            replay={
                "decision": "research-only-historical-session-replay-watch",
                "trades": trades([0.4] * 50),
            },
            fold_size=10,
        )

        self.assertEqual(payload["decision"], "research-only-historical-session-walkforward-watch")
        self.assertEqual(payload["foldCount"], 5)
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForExecution"])

    def test_weak_folds_block(self):
        payload = build_walkforward(
            replay={
                "decision": "research-only-historical-session-replay-watch",
                "trades": trades([0.4] * 20 + [-0.6] * 30),
            },
            fold_size=10,
        )

        self.assertEqual(payload["decision"], "research-only-historical-session-walkforward-blocked")
        self.assertIn("positive-fold-share-below-contract", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
