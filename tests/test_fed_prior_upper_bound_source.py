import unittest

from scripts.fed_prior_upper_bound_source import build_payload, parse_level_range, parse_openmarket_rows


FIXTURE_HTML = """
<h4>2026</h4>
<table>
  <tr><th>Date</th><th>Increase</th><th>Decrease</th><th>Level (%)</th></tr>
  <tr><td>June 17</td><td>0</td><td>0</td><td>3.50-3.75</td></tr>
</table>
<h4>2025</h4>
<table>
  <tr><th>Date</th><th>Increase</th><th>Decrease</th><th>Level (%)</th></tr>
  <tr><td>December 11</td><td>0</td><td>25</td><td>3.75-4.00</td></tr>
</table>
"""


class FedPriorUpperBoundSourceTests(unittest.TestCase):
    def test_parse_level_range(self):
        self.assertEqual(parse_level_range("3.50-3.75"), (3.5, 3.75))
        self.assertEqual(parse_level_range("4.25 to 4.50"), (4.25, 4.5))

    def test_parses_latest_target_range_row(self):
        rows = parse_openmarket_rows(FIXTURE_HTML)

        self.assertEqual(rows[0].effectiveDate, "2026-06-17")
        self.assertEqual(rows[0].upperBound, 3.75)
        self.assertEqual(rows[0].lowerBound, 3.5)

    def test_payload_is_research_only_and_uses_official_source(self):
        payload = build_payload(
            rows=parse_openmarket_rows(FIXTURE_HTML),
            source_url="https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
            retrieved_at="2026-05-30T08:30:00+00:00",
        )

        self.assertEqual(payload["decision"], "research-only-fed-prior-upper-bound-source-ready")
        self.assertTrue(payload["dataUsable"])
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["priorUpperBound"], 3.75)
        self.assertIn("federalreserve.gov", payload["source"]["url"])

    def test_payload_blocks_when_official_row_missing(self):
        payload = build_payload(rows=[], source_url="https://www.federalreserve.gov/monetarypolicy/openmarket.htm")

        self.assertEqual(payload["decision"], "research-only-fed-prior-upper-bound-source-blocked")
        self.assertFalse(payload["dataUsable"])
        self.assertIn("official-fed-target-range-row-not-found", payload["blockers"])


if __name__ == "__main__":
    unittest.main()
