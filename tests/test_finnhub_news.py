import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import finnhub_news
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
        self.assertFalse(payload["movesFunds"])
        self.assertFalse(payload["executionAuthority"])
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

        self.assertFalse(payload["executionAuthority"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["news_count"], 1)

    def test_reads_finnhub_key_from_secure_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("FINNHUB_API_KEY='abc123'\n")
            with patch.dict("os.environ", {}, clear=True), patch.object(finnhub_news, "ENV_PATHS", [env_path]):
                self.assertEqual(finnhub_news.read_secure_env("FINNHUB_API_KEY"), "abc123")

    def test_economic_calendar_dict_shape_is_supported(self):
        payload = build_output([], [{"event": "CPI", "date": "2026-06-04T12:30:00Z"}], None, None)

        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["dataUsable"])

    def test_dry_run_does_not_write_state_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(finnhub_news, "OUT_PATH", str(root / "news.json")), \
                    patch.object(finnhub_news, "LATEST_PATH", str(root / "latest.json")), \
                    patch.object(finnhub_news, "fetch_finnhub_news", return_value=([
                        {"headline": "Stocks steady", "summary": "", "source": "unit", "datetime": 1}
                    ], None)), \
                    patch.object(finnhub_news, "fetch_economic_calendar", return_value=([], None)), \
                    patch.object(finnhub_news, "parse_args", return_value=type("Args", (), {"compact": True, "dry_run": True})()):
                finnhub_news.main()

            self.assertFalse((root / "news.json").exists())
            self.assertFalse((root / "latest.json").exists())


if __name__ == "__main__":
    unittest.main()
