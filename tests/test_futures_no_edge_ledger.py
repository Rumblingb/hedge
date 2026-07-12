import unittest

from scripts.futures_no_edge_ledger import build_entries, merge_entries


class FuturesNoEdgeLedgerTest(unittest.TestCase):
    def test_records_rejected_vol_regime_and_cost_survivor_false_positive(self):
        triage = {
            "volRegimeOos": {
                "status": "reject-current-oos",
                "aggregate": {"trades": 48, "netR": -29.4, "profitFactor": 0.3},
                "blockers": ["aggregate OOS netR is not positive"],
            },
            "volRegimeInverseOos": {
                "status": "reject-current-oos",
                "aggregate": {"trades": 48, "netR": -27.1, "profitFactor": 0.35},
                "blockers": ["aggregate OOS netR is not positive"],
            },
            "volRegimeLowerTimeframeOos": {
                "15m": {
                    "status": "reject-current-oos",
                    "aggregate": {"trades": 165, "netR": 16.4, "profitFactor": 1.14},
                    "blockers": ["aggregate OOS profit factor below 1.25"],
                }
            },
            "costSlippageGate": {
                "backtraderSurvivors": 19,
                "volRegimeOosSurvivors": 0,
                "readyForDemoExpansion": False,
            },
        }

        entries = build_entries(triage)
        ids = {entry["id"] for entry in entries}

        self.assertIn("wq-vol-regime-60m-current-form", ids)
        self.assertIn("wq-vol-regime-15m-current-form", ids)
        self.assertIn("backtrader-full-sample-survivors-with-zero-vol-oos-survivors", ids)
        self.assertEqual(next(entry for entry in entries if entry["id"] == "wq-vol-regime-15m-current-form")["verdict"], "needs-new-feature")

    def test_no_edge_memory_is_durable_until_explicit_clearance(self):
        previous = [{"id": "x", "verdict": "no-edge", "evidence": {"old": True}}]
        current = [{"id": "x", "verdict": "needs-new-feature"}]

        merged = merge_entries(previous, current)

        self.assertEqual(merged[0]["verdict"], "no-edge")
        self.assertIn("retainedReason", merged[0])

    def test_cot_research_without_positive_rows_becomes_no_edge_memory(self):
        entries = build_entries(
            {},
            {
                "command": "cot-regime-filter-research",
                "summary": {
                    "rows": 72,
                    "improvedPositiveRows": 0,
                    "decision": "research-only-no-positive-full-sample-improvement",
                },
                "inputs": {
                    "releaseLagDays": 3,
                    "oneVariable": "weekly CFTC TFF positioning gate",
                },
            },
        )

        entry = next(item for item in entries if item["id"] == "cot-tff-regime-filter-current-backtrader-set")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertEqual(entry["evidence"]["improvedPositiveRows"], 0)
        self.assertIn("weekly and lagged", " ".join(entry["reasons"]))

    def test_rejected_walkforward_matrix_becomes_no_edge_memory(self):
        entries = build_entries(
            {},
            walkforward_matrix={
                "command": "walkforward-matrix",
                "generatedAt": "2026-06-04T12:08:03.095Z",
                "status": "reject",
                "csvPath": "/Users/brain/hedge/data/free/ALL-6MARKETS-60m-60d-normalized.csv",
                "comparison": {
                    "bestConfigId": "fixed-20d-5d",
                    "robustConfigCount": 0,
                    "commonFailureModes": ["stitched-oos-net-negative", "walkforward-efficiency-below-0.5"],
                },
                "configs": [
                    {
                        "configId": "fixed-20d-5d",
                        "windowsEvaluated": 6,
                        "stitchedOos": {
                            "totalTrades": 21,
                            "netTotalR": -20.0253,
                            "profitFactor": 0.2206,
                            "maxDrawdownR": 21.1546,
                        },
                        "failureModes": ["stitched-oos-net-negative"],
                        "windows": [
                            {"selectedProfileId": "wq-momentum-trend"},
                            {"selectedProfileId": "expiry-flow-index"},
                        ],
                    }
                ],
            },
        )

        entry = next(item for item in entries if item["id"] == "six-market-walkforward-matrix-current-profile-family")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertEqual(entry["evidence"]["robustConfigCount"], 0)
        self.assertEqual(entry["evidence"]["selectedProfileIds"], ["expiry-flow-index", "wq-momentum-trend"])
        self.assertIn("Do not rerun this exact profile family", entry["nextAction"])

    def test_gex_standalone_underperformance_becomes_no_edge_memory(self):
        entries = build_entries(
            {},
            gex_backtest={
                "decision": "research-only-gex-backtest-complete",
                "metrics": {
                    "rows": 3508,
                    "dateRange": {"start": "2010-01-04", "end": "2023-12-29"},
                    "buyHold": {"meanDailyReturn": 0.00052, "sharpe": 0.77, "count": 2966},
                    "signAtmGex": {"meanDailyReturn": 0.00020, "sharpe": 0.29, "count": 2966},
                    "rankGex": {"meanDailyReturn": 0.00034, "sharpe": 0.51, "count": 2966},
                },
            },
        )

        entry = next(item for item in entries if item["id"] == "gex-sign-atm-standalone-index-futures-proxy")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertEqual(entry["evidence"]["rows"], 3508)
        self.assertIn("pre-registered overlay", entry["nextAction"])

    def test_entry_hypothesis_single_slice_winner_becomes_watch_memory(self):
        entries = build_entries(
            {},
            entry_hypothesis_research={
                "command": "entry-hypothesis-research",
                "generatedAt": "2026-06-05T20:00:00Z",
                "decision": "research-only-entry-hypotheses-not-promotable",
                "globalBlockers": ["single-dataset-winners-are-overfit-risk"],
                "datasets": [
                    {
                        "id": "nq_long_2022_2025",
                        "symbol": "NQ",
                        "bars15m": 70685,
                        "bars1m": 589638,
                        "first15m": "2022-12-26T18:00:00+00:00",
                        "last15m": "2025-12-11T20:45:00+00:00",
                        "hypotheses": [
                            {
                                "id": "long_on_1m_red_candle_after_15m_bullish_signal",
                                "coveragePct": 100.0,
                                "evidenceGrade": "research-only-blocked",
                                "oos": {"tradeCount": 570, "netPoints": 16045.64, "profitFactor": 3.72},
                                "blockers": ["not-cross-dataset-robust"],
                            }
                        ],
                    },
                    {
                        "id": "nq_current_60d",
                        "symbol": "NQ",
                        "bars15m": 4509,
                        "bars1m": 6075,
                        "first15m": "2026-03-26T04:00:00+00:00",
                        "last15m": "2026-06-05T13:45:00+00:00",
                        "hypotheses": [
                            {
                                "id": "long_on_1m_red_candle_after_15m_bullish_signal",
                                "coveragePct": 9.2715,
                                "evidenceGrade": "research-only-blocked",
                                "oos": {"tradeCount": 5, "netPoints": 303.1, "profitFactor": 5.76},
                                "blockers": ["too-few-oos-trades", "coverage-too-thin"],
                            }
                        ],
                    },
                ],
            },
        )

        entry = next(item for item in entries if item["id"] == "entry-hypothesis-long_on_1m_red_candle_after_15m_bullish_signal")

        self.assertEqual(entry["verdict"], "needs-new-feature")
        self.assertEqual(entry["status"], "research-only")
        self.assertEqual(entry["evidence"]["positiveDatasetCount"], 1)
        self.assertEqual(entry["evidence"]["robustDatasetCount"], 0)
        self.assertIn("watch-only", entry["nextAction"])

    def test_entry_hypothesis_negative_family_becomes_no_edge_memory(self):
        entries = build_entries(
            {},
            entry_hypothesis_research={
                "command": "entry-hypothesis-research",
                "decision": "research-only-entry-hypotheses-not-promotable",
                "datasets": [
                    {
                        "id": "es_long_2000_2019",
                        "symbol": "ES",
                        "hypotheses": [
                            {
                                "id": "bearish_asymmetry_short_mirror",
                                "coveragePct": 100.0,
                                "evidenceGrade": "research-only-blocked",
                                "oos": {"tradeCount": 2524, "netPoints": -2415.94, "profitFactor": 0.65},
                                "blockers": ["oos-net-not-positive-after-costs"],
                            }
                        ],
                    }
                ],
            },
        )

        entry = next(item for item in entries if item["id"] == "entry-hypothesis-bearish_asymmetry_short_mirror")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertEqual(entry["evidence"]["positiveDatasetCount"], 0)
        self.assertIn("standalone futures entry/exit rule", " ".join(entry["reasons"]))


if __name__ == "__main__":
    unittest.main()
