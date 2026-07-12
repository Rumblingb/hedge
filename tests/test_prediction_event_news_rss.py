import unittest

from scripts.prediction_event_news_rss import DEFAULT_LIMIT, DEFAULT_PER_QUERY, DEFAULT_QUERIES, build_output, parse_rss


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
  <item>
    <title>Fed inflation path watched before CPI - Reuters</title>
    <description>Markets focus on Federal Reserve inflation data.</description>
    <pubDate>Sat, 30 May 2026 09:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Oil traders watch OPEC supply talks - CNBC</title>
    <description>Crude markets await OPEC signals.</description>
    <pubDate>Sat, 30 May 2026 08:00:00 GMT</pubDate>
  </item>
</channel></rss>
"""


class PredictionEventNewsRssTests(unittest.TestCase):
    def test_default_queries_cover_crypto_books_collected_by_the_recorder(self):
        self.assertTrue(any("Bitcoin" in query and "Ethereum" in query for query in DEFAULT_QUERIES))
        self.assertEqual(DEFAULT_PER_QUERY, 15)
        self.assertEqual(DEFAULT_LIMIT, 60)

    def test_parse_rss_extracts_timestamped_articles(self):
        rows = parse_rss(RSS, "Fed OR CPI", 10)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["headline"], "Fed inflation path watched before CPI")
        self.assertEqual(rows[0]["source"], "Reuters")
        self.assertGreater(rows[0]["datetime"], 0)
        self.assertEqual(rows[0]["query"], "Fed OR CPI")

    def test_build_output_is_research_only_and_fails_closed_when_thin(self):
        payload = build_output(parse_rss(RSS, "Fed OR CPI", 10), {"Fed OR CPI": None})

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["sourceAdapter"], "google_news_rss_fallback")
        self.assertEqual(payload["api_key_status"], "not_required_rss")
        self.assertEqual(payload["news_count"], 2)
        self.assertEqual(payload["newsCount"], 2)
        self.assertEqual(payload["articleCount"], 2)
        self.assertEqual(payload["itemCount"], 2)
        self.assertEqual(payload["decision"], "research-only-event-news-rss-blocked-no-data")
        self.assertEqual(payload["status"], "BLOCKED_NO_DATA")
        self.assertFalse(payload["trading_gate"]["trend_strategies_allowed"])

    def test_build_output_passes_research_context_with_enough_articles(self):
        rows = parse_rss(RSS, "Fed OR CPI", 10) * 5
        payload = build_output(rows, {"Fed OR CPI": None})

        self.assertEqual(payload["news_count"], 10)
        self.assertEqual(payload["decision"], "research-only-event-news-rss-ready")
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["dataUsable"])
        self.assertFalse(payload["readyForExecution"])


if __name__ == "__main__":
    unittest.main()
