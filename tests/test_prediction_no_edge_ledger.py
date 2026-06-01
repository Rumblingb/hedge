import unittest

from scripts.prediction_no_edge_ledger import build_entries, merge_entries


class PredictionNoEdgeLedgerTests(unittest.TestCase):
    def test_broad_scan_entry_preserves_resolved_outcome_context(self):
        entries = build_entries({
            "review": {
                "counts": {"paper-trade": 0, "watch": 0, "reject": 0},
                "venueCounts": {"polymarket": 10, "kalshi": 8},
                "blockers": ["no-paper-candidates"],
            },
            "resolvedOutcomeJoin": {
                "statusCounts": {"joined-research-only": 1},
                "joinedResearchOnlyCount": 1,
                "minSpecificMatches": 5,
                "readyForPaper": False,
                "subjectSpecificCounts": [
                    {
                        "externalId": "arg-2026",
                        "resolvedMatchCount": 312,
                        "subjectSpecificMatchCount": 14,
                    }
                ],
            },
        })

        broad_entry = next(item for item in entries if item["id"] == "broad-cross-venue-prediction-scan-current-normalization")
        resolved = broad_entry["evidence"]["resolvedOutcomeJoin"]

        self.assertEqual(resolved["joinedResearchOnlyCount"], 1)
        self.assertEqual(resolved["minSpecificMatches"], 5)
        self.assertEqual(resolved["subjectSpecificCounts"][0]["subjectSpecificMatchCount"], 14)
        self.assertIn("subject-specific", " ".join(broad_entry["reasons"]))

    def test_resolved_outcome_context_only_review_is_recorded_without_promotion(self):
        entries = build_entries({
            "review": {"counts": {"paper-trade": 0}},
            "resolvedOutcomeReview": {
                "decision": "do-not-promote-resolved-history-without-paper-review-and-fillability",
                "broadPriorRisk": "high",
                "joinedResearchOnlyCount": 1,
                "readyForPaper": False,
                "marketSpecificCoverage": {"historicalRowsLoaded": 59821, "minSpecificMatches": 5},
                "items": [
                    {
                        "externalId": "2364500",
                        "decision": "insufficient-market-family-history",
                        "resolvedMatchCount": 0,
                        "subjectSpecificMatchCount": 0,
                    },
                    {
                        "externalId": "558938",
                        "decision": "context-only-not-paper",
                        "resolvedMatchCount": 312,
                        "subjectSpecificMatchCount": 14,
                        "subjectSpecificWinRate": 0.571429,
                    },
                ],
            },
        })

        entry = next(item for item in entries if item["id"] == "resolved-outcome-current-watchlist-context-only")

        self.assertEqual(entry["verdict"], "needs-more-data")
        self.assertTrue(entry["currentFormRejected"])
        self.assertFalse(entry["evidence"]["readyForPaper"])
        self.assertIn("Do not rerun the same resolved-outcome review", entry["nextAction"])

    def test_narrow_scan_zero_candidates_is_recorded_without_calling_it_promotable(self):
        entries = build_entries(
            {"review": {"counts": {"paper-trade": 0}}},
            {
                "readyForPaper": False,
                "summary": {
                    "categoryCount": 6,
                    "watchCandidates": 0,
                    "paperCandidates": 0,
                    "viablePairs": 0,
                    "repairableNearMisses": 20,
                },
                "selectedCategories": [],
                "reports": [
                    {
                        "category": "crypto",
                        "diagnostics": {
                            "rejectReasons": {
                                "temporal-mismatch": 39,
                                "line-mismatch": 87,
                            }
                        },
                    }
                ],
            },
        )

        narrow_entry = next(item for item in entries if item["id"] == "narrow-category-cross-venue-current-universe")

        self.assertEqual(narrow_entry["verdict"], "needs-more-data")
        self.assertEqual(narrow_entry["evidence"]["categoryCount"], 6)
        self.assertEqual(narrow_entry["evidence"]["repairableNearMisses"], 20)
        self.assertEqual(narrow_entry["evidence"]["categoryRejectReasons"]["crypto"]["temporal-mismatch"], 39)
        self.assertIn("do not broaden thresholds", narrow_entry["nextAction"])

    def test_crypto_only_temporal_retest_records_no_edge_and_next_variable(self):
        entries = build_entries(
            {"review": {"counts": {"paper-trade": 0}}},
            {
                "readyForPaper": False,
                "selectedCategories": ["crypto"],
                "summary": {
                    "categoryCount": 1,
                    "watchCandidates": 0,
                    "paperCandidates": 0,
                    "viablePairs": 0,
                    "repairableNearMisses": 20,
                },
                "reports": [
                    {
                        "category": "crypto",
                        "diagnostics": {
                            "rejectReasons": {
                                "temporal-mismatch": 39,
                                "line-mismatch": 87,
                            }
                        },
                    }
                ],
            },
        )

        crypto_entry = next(item for item in entries if item["id"] == "crypto-settlement-horizon-parser-current-form")

        self.assertEqual(crypto_entry["verdict"], "no-edge")
        self.assertEqual(crypto_entry["evidence"]["selectedCategories"], ["crypto"])
        self.assertEqual(crypto_entry["evidence"]["cryptoRejectReasons"]["temporal-mismatch"], 39)
        self.assertIn("Do not relax crypto settlement horizon parsing", crypto_entry["nextAction"])

    def test_macro_rates_line_parser_retest_records_no_edge_when_no_repairable_pairs(self):
        entries = build_entries(
            {"review": {"counts": {"paper-trade": 0}}},
            {
                "readyForPaper": False,
                "selectedCategories": ["macro-rates"],
                "summary": {
                    "categoryCount": 1,
                    "watchCandidates": 0,
                    "paperCandidates": 0,
                    "viablePairs": 0,
                    "repairableNearMisses": 0,
                },
                "reports": [
                    {
                        "category": "macro-rates",
                        "diagnostics": {
                            "rejectReasons": {
                                "market-type-mismatch": 3068,
                                "outcome-mismatch": 3068,
                                "weak-relatedness": 3068,
                                "line-mismatch": 2891,
                            }
                        },
                    }
                ],
            },
        )

        macro_entry = next(item for item in entries if item["id"] == "macro-rates-line-parser-current-form")

        self.assertEqual(macro_entry["verdict"], "no-edge")
        self.assertEqual(macro_entry["evidence"]["repairableNearMisses"], 0)
        self.assertEqual(macro_entry["evidence"]["macroRatesRejectReasons"]["market-type-mismatch"], 3068)
        self.assertIn("Do not retest macro/rates line parsing", macro_entry["nextAction"])

    def test_macro_rates_fee_stressed_cross_source_replay_records_no_edge(self):
        entries = build_entries(
            {"review": {"counts": {"paper-trade": 0}}},
            macro_rates_cross_source_replay={
                "decision": "research-only-macro-rates-cross-source-replay-blocked",
                "rowCount": 2,
                "watchResearchCount": 0,
                "minSampleRows": 20,
                "blockers": ["too-few-source-specific-sample-rows"],
                "rows": [
                    {
                        "blockers": [
                            "research-only",
                            "not-paper-ready",
                            "no-positive-net-edge-after-fee-stress",
                        ],
                        "feeStress": {
                            "yesNetEdgePctVsAsk": 1.0882,
                            "noNetEdgePctVsNoAsk": -3.6745,
                        },
                    },
                    {
                        "blockers": [
                            "research-only",
                            "not-paper-ready",
                            "no-positive-net-edge-after-fee-stress",
                        ],
                        "feeStress": {
                            "yesNetEdgePctVsAsk": -1.986,
                            "noNetEdgePctVsNoAsk": -0.3195,
                        },
                    },
                ],
            },
        )

        macro_entry = next(item for item in entries if item["id"] == "macro-rates-cross-source-fee-stressed-current-form")

        self.assertEqual(macro_entry["verdict"], "no-edge")
        self.assertTrue(macro_entry["currentFormRejected"])
        self.assertEqual(macro_entry["evidence"]["feeBlockedRows"], 2)
        self.assertEqual(macro_entry["evidence"]["maxYesNetEdgePct"], 1.0882)
        self.assertIn("Do not rerun the same macro/rates cross-source current form", macro_entry["nextAction"])

    def test_prior_no_edge_entry_is_retained_without_explicit_clearance(self):
        previous = [
            {
                "id": "clob-drift",
                "verdict": "no-edge",
                "evidence": {"rowsRead": 100},
            }
        ]
        current = [
            {
                "id": "clob-drift",
                "verdict": "needs-more-data",
                "evidence": {"rowsRead": 10},
            }
        ]

        merged = merge_entries(previous, current)

        self.assertEqual(merged[0]["verdict"], "no-edge")
        self.assertIn("retainedReason", merged[0])

    def test_direct_clob_edge_gate_updates_stale_triage_clob_memory(self):
        entries = build_entries(
            {
                "clobEdgeGate": {
                    "status": "REJECT_NO_EDGE",
                    "rowsRead": 0,
                    "scoredGroups": 0,
                    "watchResearchGroups": 0,
                    "blockerCounts": {},
                }
            },
            clob_edge_gate={
                "command": "polymarket-clob-edge-gate",
                "status": "REJECT_NO_EDGE",
                "rowsRead": 85746,
                "scoredGroups": 40,
                "watchResearchGroups": 0,
                "readyForPaper": False,
                "blockerCounts": {
                    "net-drift-below-threshold": 40,
                    "directional-hit-rate-too-low": 40,
                },
            },
        )

        entry = next(item for item in entries if item["id"] == "polymarket-clob-drift-persistence-current-thresholds")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertEqual(entry["evidence"]["rowsRead"], 85746)
        self.assertEqual(entry["evidence"]["scoredGroups"], 40)
        self.assertEqual(entry["evidence"]["blockerCounts"]["net-drift-below-threshold"], 40)

    def test_current_narrow_rejections_update_broad_and_narrow_next_actions(self):
        previous = [
            {
                "id": "crypto-settlement-horizon-parser-current-form",
                "verdict": "no-edge",
            },
            {
                "id": "narrow-category-cross-venue-current-universe",
                "verdict": "needs-more-data",
                "nextAction": "Retest only one category/parser variable at a time.",
            },
        ]
        current = [
            {
                "id": "broad-cross-venue-prediction-scan-current-normalization",
                "verdict": "needs-more-data",
                "nextAction": "Run narrow category scans.",
            },
            {
                "id": "macro-rates-line-parser-current-form",
                "verdict": "no-edge",
            },
        ]

        merged = merge_entries(previous, current)
        by_id = {item["id"]: item for item in merged}

        self.assertTrue(by_id["broad-cross-venue-prediction-scan-current-normalization"]["currentFormRejected"])
        self.assertTrue(by_id["narrow-category-cross-venue-current-universe"]["currentFormRejected"])
        self.assertIn("Do not rerun the current broad/narrow", by_id["broad-cross-venue-prediction-scan-current-normalization"]["nextAction"])
        self.assertEqual(
            by_id["narrow-category-cross-venue-current-universe"]["rejectedBy"],
            ["crypto-settlement-horizon-parser-current-form", "macro-rates-line-parser-current-form"],
        )

    def test_btc_resolved_fixed_rules_record_needs_more_data_memory(self):
        entries = build_entries(
            {},
            {},
            {
                "command": "prediction-btc-resolved-oos",
                "decision": "research-only-no-fixed-rule-edge",
                "rows": 232725,
                "markets": 616,
                "watchResearchCount": 0,
                "rules": [
                    {
                        "id": "book-depth-up",
                        "side": "up",
                        "oneVariable": "order-book depth imbalance",
                        "oos": {"trades": 10, "avgPnlPerShare": 0.48},
                        "decision": "reject-current-fixed-rule",
                    }
                ],
            },
        )

        entry = next(item for item in entries if item["id"] == "polymarket-btc-resolved-fixed-rules-current-form")

        self.assertEqual(entry["verdict"], "needs-more-data")
        self.assertTrue(entry["currentFormRejected"])
        self.assertEqual(entry["evidence"]["bestRule"]["id"], "book-depth-up")
        self.assertIn("too few OOS trades", " ".join(entry["reasons"]))

    def test_clob_depth_imbalance_replay_records_no_edge_memory(self):
        entries = build_entries(
            {},
            {},
            {},
            {
                "command": "prediction-clob-depth-imbalance-replay",
                "decision": "research-only-no-depth-imbalance-edge",
                "recordsRead": 2852,
                "bookFeatureRows": 64,
                "watchResearchCount": 0,
                "fixedThresholds": {"imbalanceThreshold": 0.2, "maxStartSpread": 0.05},
                "results": [{"windowSec": 15, "samples": 0, "verdict": "reject"}],
            },
        )

        entry = next(item for item in entries if item["id"] == "polymarket-clob-depth-imbalance-current-form")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertTrue(entry["currentFormRejected"])
        self.assertEqual(entry["evidence"]["fixedThresholds"]["maxStartSpread"], 0.05)
        self.assertIn("Do not rerun this exact depth-imbalance", entry["nextAction"])

    def test_clob_quote_intensity_replay_records_no_edge_memory(self):
        entries = build_entries(
            {},
            {},
            {},
            {},
            None,
            {
                "command": "prediction-clob-quote-intensity-replay",
                "decision": "research-only-no-quote-intensity-edge",
                "recordsRead": 107137,
                "quoteFeatureRows": 208507,
                "watchResearchCount": 0,
                "fixedThresholds": {"lookbackSec": 60, "minUpdates": 20},
                "results": [{"windowSec": 15, "samples": 330, "verdict": "reject"}],
            },
        )

        entry = next(item for item in entries if item["id"] == "polymarket-clob-quote-intensity-current-form")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertTrue(entry["currentFormRejected"])
        self.assertEqual(entry["evidence"]["fixedThresholds"]["minUpdates"], 20)
        self.assertIn("Do not rerun this exact quote-intensity", entry["nextAction"])

    def test_clob_spread_compression_replay_records_no_edge_memory(self):
        entries = build_entries(
            {},
            {},
            {},
            {},
            None,
            {},
            {
                "command": "prediction-clob-spread-compression-replay",
                "decision": "research-only-no-spread-compression-edge",
                "recordsRead": 107137,
                "quoteFeatureRows": 208507,
                "watchResearchCount": 0,
                "fixedThresholds": {"lookbackSec": 60, "minSpreadCompression": 0.003},
                "results": [{"windowSec": 15, "samples": 330, "verdict": "reject"}],
            },
        )

        entry = next(item for item in entries if item["id"] == "polymarket-clob-spread-compression-current-form")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertTrue(entry["currentFormRejected"])
        self.assertEqual(entry["evidence"]["fixedThresholds"]["minSpreadCompression"], 0.003)
        self.assertIn("Do not rerun this exact spread-compression", entry["nextAction"])

    def test_clob_latency_staleness_replay_records_no_edge_memory(self):
        entries = build_entries(
            {},
            {},
            {},
            {},
            None,
            {},
            {},
            {
                "command": "prediction-clob-latency-staleness-replay",
                "decision": "research-only-no-latency-staleness-edge",
                "recordsRead": 107137,
                "quoteFeatureRows": 208507,
                "watchResearchCount": 0,
                "fixedThresholds": {"maxLatencyMs": 10000, "maxStalenessMs": 30000},
                "results": [{"windowSec": 15, "samples": 330, "verdict": "reject"}],
            },
        )

        entry = next(item for item in entries if item["id"] == "polymarket-clob-latency-staleness-current-form")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertTrue(entry["currentFormRejected"])
        self.assertEqual(entry["evidence"]["fixedThresholds"]["maxLatencyMs"], 10000)
        self.assertIn("Do not rerun this exact latency/staleness", entry["nextAction"])

    def test_clob_trade_impact_replay_records_no_edge_memory(self):
        entries = build_entries(
            {},
            {},
            {},
            {},
            None,
            {},
            {},
            {},
            {
                "command": "prediction-clob-trade-impact-replay",
                "decision": "research-only-no-trade-impact-edge",
                "recordsRead": 107137,
                "tradeFeatureRows": 279,
                "watchResearchCount": 0,
                "fixedThresholds": {"minTradeSize": 10, "maxQuoteAgeMs": 30000},
                "results": [{"windowSec": 15, "samples": 40, "verdict": "reject"}],
            },
        )

        entry = next(item for item in entries if item["id"] == "polymarket-clob-trade-impact-current-form")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertTrue(entry["currentFormRejected"])
        self.assertEqual(entry["evidence"]["fixedThresholds"]["minTradeSize"], 10)
        self.assertIn("Do not rerun this exact trade-impact", entry["nextAction"])

    def test_event_lag_replay_records_no_edge_after_complete_windows_without_repricing(self):
        entries = build_entries(
            {},
            {},
            {},
            {},
            {
                "command": "prediction-event-lag-replay",
                "decision": "research-only-event-lag-replay-blocked",
                "completeEventCount": 5,
                "completeWindowCount": 5,
                "repricedWindowCount": 0,
                "assetQuoteCount": 200373,
                "assetsWithQuotes": 105,
                "missingReasonCounts": {"no-post-event-quote-30m": 5},
                "byHorizon": {"15": {"windows": 5, "repricedCount": 0}},
                "readyForPaper": False,
            },
        )

        entry = next(item for item in entries if item["id"] == "prediction-news-event-lag-current-form")

        self.assertEqual(entry["verdict"], "no-edge")
        self.assertTrue(entry["currentFormRejected"])
        self.assertEqual(entry["evidence"]["completeWindowCount"], 5)
        self.assertEqual(entry["evidence"]["repricedWindowCount"], 0)
        self.assertIn("zero repriced windows", " ".join(entry["reasons"]))
        self.assertIn("Do not rerun the same event-lag replay form", entry["nextAction"])


if __name__ == "__main__":
    unittest.main()
