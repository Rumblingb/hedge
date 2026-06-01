import unittest

from scripts.finnhub_news import build_output


class FinnhubNewsTests(unittest.TestCase):
    def test_empty_fetch_fails_closed(self):
        payload = build_output([], [], "HTTP Error 401", "HTTP Error 401")

        self.assertEqual(payload["status"], "BLOCKED_NO_DATA")
        self.assertEqual(payload["command"], "finnhub-news")
        self.assertEqual(payload["sourceAdapter"], "finnhub")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["dataUsable"])
        self.assertFalse(payload["trading_gate"]["trend_strategies_allowed"])
        self.assertEqual(payload["trading_gate"]["max_position_size_pct"], 0.0)

    def test_nonempty_fetch_can_be_usable_research_context(self):
        payload = build_output(
            [{"headline": "Fed rate cut optimism lifts stocks", "summary": "", "source": "unit", "datetime": 1}],
            [],
            None,
            None,
        )

        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["dataUsable"])
        self.assertEqual(payload["news_count"], 1)


if __name__ == "__main__":
    unittest.main()
