import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.alpha_frontier_queue import build_frontier, parse_simple_catalog, render_markdown


class AlphaFrontierQueueTest(unittest.TestCase):
    def test_frontier_is_research_only_and_preserves_rejected_current_forms(self):
        catalog = {
            "datasets": {
                "nq_futures_1m": {"path": "/tmp/nq_1m.parquet"},
                "nq_futures_5m": {"path": "/tmp/nq_5m.parquet"},
                "nq_futures_15m": {"path": "/tmp/nq_15m.parquet"},
                "sp500_options_daily_regime": {"path": "/tmp/options.parquet"},
                "equities_5m_breadth_2026_03": {"path": "/tmp/breadth.parquet"},
                "polymarket_btc_updown_5m_resolved_all": {"path": "/tmp/btc.parquet"},
            },
            "source_repos": {
                "vol_regime_prediction": {"path": "/tmp/vol_repo"},
                "polymarket_microstructure": {"path": "/tmp/poly_repo"},
            },
        }
        futures_no_edge = {
            "entries": [
                {"id": "wq-vol-regime-60m-current-form", "verdict": "no-edge"},
                {"id": "wq-vol-regime-15m-current-form", "verdict": "needs-new-feature"},
                {"id": "cot-tff-regime-filter-current-backtrader-set", "verdict": "no-edge"},
            ]
        }
        prediction_no_edge = {
            "entries": [
                {"id": "polymarket-clob-drift-persistence-current-thresholds", "verdict": "no-edge"},
                {"id": "macro-rates-line-parser-current-form", "verdict": "no-edge"},
                {"id": "resolved-outcome-current-watchlist-context-only", "verdict": "needs-more-data", "currentFormRejected": True},
            ]
        }

        payload = build_frontier(
            catalog=catalog,
            futures_no_edge=futures_no_edge,
            prediction_no_edge=prediction_no_edge,
            handoff={"decision": "KEEP_EXECUTION_LOCKED", "readyForExecution": False},
            external_alpha_audit={
                "nqLocalParity": {"ok": False, "reason": "date-range-mismatch-or-no-overlap", "overlapRows": 0},
                "nqSourceParity": {"ok": True},
                "nqHistoricalResearchUsability": {
                    "usableForHistoricalResearch": True,
                    "usableForExecutionParity": False,
                    "read": "historical only",
                },
                "localFuturesRanges": {"all_15m_60d_nq": {"min": "2026-03-19T04:00:00.000Z"}},
                "datasets": [
                    {"id": "sp500_options_daily_regime", "timeRange": {"max": "2013-08-16"}},
                    {"id": "equities_5m_breadth_2026_03", "timeRange": {"max": "2026-03-10 19:55:00"}},
                ],
            },
            nq_historical_coverage_audit={
                "decision": "research-only-historical-nq-source-ready",
                "blockers": ["no-seagate-nq-source-overlaps-current-local-csv-bars"],
                "usableHistoricalOosCount": 1,
                "preferredPromotionDepthCount": 1,
                "currentLocalCsvParityCheckedCount": 3,
                "currentLocalCsvParityClearedCount": 0,
                "bestHistoricalOosCandidate": {"datasetId": "seagate_nq_15m", "sessionCount": 70},
            },
            nq_historical_session_replay={
                "decision": "research-only-historical-session-replay-blocked",
                "tradeCount": 70,
                "oosStats": {"trades": 28, "netR": -1.0},
            },
            nq_historical_session_walkforward={
                "decision": "research-only-historical-session-walkforward-blocked",
                "foldCount": 7,
                "positiveFoldShare": 0.57,
                "worstFoldNetR": -2.0,
            },
            nq_historical_session_cost_stress={
                "decision": "research-only-historical-session-cost-stress-blocked",
                "survivingCaseCount": 2,
                "caseCount": 4,
            },
            nq_current_data_parity={
                "decision": "research-only-current-local-parity-ready",
                "cleanLocalResearchPairCount": 1,
                "bestCurrentLocalResearchPair": {"pairId": "nq-5m-60d-vs-all-6markets-5m-60d"},
                "brokerParityChecked": False,
            },
            prediction_macro_rates_requirements={
                "blockedCount": 2,
                "passCount": 2,
                "decision": "research-only-macro-rates-requirements-not-cleared",
            },
        )

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertEqual(payload["gateSnapshot"]["handoffDecision"], "KEEP_EXECUTION_LOCKED")
        ids = [item["id"] for item in payload["frontier"]]
        self.assertIn("futures-paid-nq-1m-session-structure-oos", ids)
        self.assertIn("prediction-btc-updown-resolved-feature-oos", ids)
        self.assertNotIn("wq-vol-regime-60m-current-form", ids)
        self.assertNotIn("polymarket-clob-drift-persistence-current-thresholds", ids)
        futures_memory = {item["id"] for item in payload["negativeMemory"]["futures"]}
        prediction_memory = {item["id"] for item in payload["negativeMemory"]["predictionMarkets"]}
        self.assertIn("wq-vol-regime-60m-current-form", futures_memory)
        self.assertIn("polymarket-clob-drift-persistence-current-thresholds", prediction_memory)
        nq_item = next(item for item in payload["frontier"] if item["id"] == "futures-paid-nq-1m-session-structure-oos")
        self.assertIn("npm run --silent bill:futures-nq-historical-coverage-audit", nq_item["commands"])
        self.assertIn("npm run --silent bill:futures-nq-historical-session-replay", nq_item["commands"])
        self.assertIn("npm run --silent bill:futures-nq-historical-session-cost-stress", nq_item["commands"])
        self.assertIn("npm run --silent bill:futures-nq-current-data-parity", nq_item["commands"])
        self.assertIn("npm run --silent bill:futures-broker-parity-plan", nq_item["commands"])
        self.assertIn("npm run --silent bill:futures-nq-research-cycle -- --run-local-research", nq_item["commands"])
        self.assertIn("/tmp/nq_15m.parquet", nq_item["dataPaths"])
        self.assertFalse(nq_item["dataQuality"]["nqLocalParityOk"])
        self.assertTrue(nq_item["dataQuality"]["nqSourceParityOk"])
        self.assertTrue(nq_item["dataQuality"]["nqHistoricalUsableForResearch"])
        self.assertFalse(nq_item["dataQuality"]["nqUsableForExecutionParity"])
        self.assertEqual(nq_item["dataQuality"]["currentLocalParityDecision"], "research-only-current-local-parity-ready")
        self.assertEqual(nq_item["dataQuality"]["cleanCurrentLocalPairCount"], 1)
        self.assertEqual(nq_item["dataQuality"]["bestCurrentLocalResearchPair"], "nq-5m-60d-vs-all-6markets-5m-60d")
        self.assertFalse(nq_item["dataQuality"]["brokerParityChecked"])
        self.assertEqual(nq_item["dataQuality"]["bestHistoricalOosCandidate"], "seagate_nq_15m")
        self.assertEqual(nq_item["dataQuality"]["bestHistoricalOosSessionCount"], 70)
        self.assertEqual(nq_item["dataQuality"]["historicalSessionReplayTradeCount"], 70)
        self.assertEqual(nq_item["dataQuality"]["historicalSessionWalkforwardFoldCount"], 7)
        self.assertEqual(nq_item["dataQuality"]["historicalSessionCostStressSurvivingCases"], 2)
        self.assertEqual(nq_item["dataQuality"]["currentLocalCsvParityCheckedCount"], 3)
        self.assertEqual(nq_item["dataQuality"]["currentLocalCsvParityClearedCount"], 0)
        self.assertIn("no-seagate-nq-source-overlaps-current-local-csv-bars", nq_item["dataQuality"]["historicalCoverageBlockers"])
        self.assertIn("external-alpha NQ current parity not cleared; historical research only", nq_item["blockedBy"])
        self.assertIn("historical NQ source does not overlap current local CSV bars; not current parity evidence", nq_item["blockedBy"])
        options_item = next(item for item in payload["frontier"] if item["id"] == "futures-options-regime-risk-overlay")
        breadth_item = next(item for item in payload["frontier"] if item["id"] == "futures-equity-breadth-nq-overlay")
        self.assertIn("options regime range does not overlap current NQ OOS data", options_item["blockedBy"])
        self.assertIn("equity breadth range does not overlap current NQ OOS data", breadth_item["blockedBy"])
        macro_item = next(item for item in payload["frontier"] if item["id"] == "prediction-macro-rates-new-source-parser")
        label_item = next(item for item in payload["frontier"] if item["id"] == "prediction-new-resolved-label-source")
        self.assertIn("npm run --silent bill:prediction-label-card-bootstrap", label_item["commands"])
        self.assertIn("npm run --silent bill:prediction-label-card-audit", label_item["commands"])
        self.assertEqual(macro_item["commands"], [
            "npm run --silent bill:kalshi-fillability-snapshot",
            "npm run --silent bill:fed-prior-upper-bound-source",
            "npm run --silent bill:prediction-macro-rates-parser-fixture",
            "npm run --silent bill:prediction-macro-rates-resolved-labels",
            "npm run --silent bill:prediction-macro-rates-requirements",
            "npm run --silent bill:prediction-macro-rates-cross-source-replay",
            "npm run --silent bill:alpha-frontier-queue",
        ])
        self.assertEqual(macro_item["dataQuality"]["blockedCount"], 2)
        self.assertIn("macro-rates requirements not cleared", macro_item["blockedBy"])
        self.assertTrue(all(item["operatorApprovalRequiredBeforeExecution"] for item in payload["frontier"]))
        self.assertTrue(all(not item["writesOrders"] for item in payload["frontier"]))
        self.assertTrue(all(command.startswith("npm ") for item in payload["frontier"] for command in item["commands"]))
        self.assertTrue(any(item.get("researchSteps") for item in payload["frontier"]))

    def test_paper_source_cards_enter_frontier_as_hypothesis_seeds_only(self):
        payload = build_frontier(
            catalog={},
            futures_no_edge={"entries": [{"id": "wq-vol-regime-60m-current-form", "verdict": "no-edge"}]},
            prediction_no_edge={"entries": []},
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
            paper_source_cards={
                "summary": {"decisionCounts": {"candidate": 1, "candidate-with-caution": 1}},
                "cards": [
                    {
                        "id": "managed-futures-paper",
                        "lane": "futures",
                        "decision": "candidate",
                        "path": "/tmp/managed-futures.pdf",
                        "tradableVariable": "trend risk overlay",
                    },
                    {
                        "id": "multimodal-paper",
                        "lane": "futures",
                        "decision": "candidate-with-caution",
                        "path": "/tmp/multimodal.pdf",
                        "tradableVariable": "tail-risk-aware feature gate",
                    },
                    {
                        "id": "risk-only",
                        "lane": "risk-governance",
                        "decision": "research-only",
                        "path": "/tmp/model-risk.pdf",
                    },
                ],
            },
        )

        item = next(item for item in payload["frontier"] if item["id"] == "futures-paper-source-one-variable-tests")

        self.assertEqual(item["lane"], "futures")
        self.assertTrue(item["researchOnly"])
        self.assertFalse(item["writesOrders"])
        self.assertFalse(item["touchesBroker"])
        self.assertEqual(item["commands"], [
            "npm run --silent bill:paper-source-cards",
            "npm run --silent bill:alpha-frontier-queue",
        ])
        self.assertIn("requires-one-variable-oos-before-promotion", item["blockedBy"])
        self.assertEqual(item["dataQuality"]["candidateCount"], 2)
        self.assertEqual(item["dataQuality"]["cautionCount"], 1)
        self.assertEqual(item["dataQuality"]["candidateIds"], ["managed-futures-paper", "multimodal-paper"])
        self.assertIn("Paper-derived ideas require one-variable local replay", item["promotionGate"])

    def test_youtube_source_cards_enter_frontier_as_hypothesis_seeds_only(self):
        with TemporaryDirectory() as temp_dir:
            card_path = Path(temp_dir) / "Youtube-Transcript-Source-Cards-2026-05-30.md"
            card_path.write_text(
                "\n".join([
                    "# YouTube Transcript Source Cards - 2026-05-30",
                    "| [FaberVaale opening range improvement](https://youtu.be/wm6XQFw1GHI) | `candidate` | `futures` | NQ NY opening-range breakout with volatility-targeted sizing | Freeze entry/stop/target/session; compare fixed one-contract sizing against capped volatility-targeted risk sizing. |",
                    "| [PEAD post-earnings announcement drift](https://youtu.be/EP4ptjamPYA) | `candidate-with-caution` | `futures-overlay/equities-research` | top-component earnings regime flag for NQ or direct equities paper study | Freeze NQ intraday entry stack; variable is PEAD top-component breadth flag on/off. |",
                ]),
                encoding="utf8",
            )

            payload = build_frontier(
                catalog={},
                futures_no_edge={"entries": []},
                prediction_no_edge={"entries": []},
                handoff={"decision": "KEEP_EXECUTION_LOCKED"},
                youtube_source_cards_path=card_path,
            )

        faber = next(item for item in payload["frontier"] if item["id"] == "futures-youtube-fabervaale-orb-vol-target-oos")
        pead = next(item for item in payload["frontier"] if item["id"] == "futures-youtube-pead-earnings-regime-overlay")

        self.assertEqual(faber["lane"], "futures")
        self.assertEqual(faber["oneVariable"], "volatility-targeted sizing")
        self.assertTrue(faber["researchOnly"])
        self.assertFalse(faber["writesOrders"])
        self.assertFalse(faber["touchesBroker"])
        self.assertIn("requires-one-variable-oos-before-promotion", faber["blockedBy"])
        self.assertIn("execution-grade-data-not-cleared", faber["blockedBy"])
        self.assertEqual(faber["dataQuality"]["firstVariableAllowed"], "position-sizing-only")
        self.assertIn("npm run --silent bill:futures-nq-sizing-overlay", faber["commands"])
        self.assertIn("sizingOverlayDecision", faber["dataQuality"])
        self.assertIn("delta-filter", faber["dataQuality"]["forbiddenFirstRetestVariables"])
        self.assertTrue(all("2026-05-30" not in command for command in faber["commands"]))
        self.assertEqual(pead["dataQuality"]["sourceDecision"], "candidate-with-caution")
        self.assertIn("not-a-topstep-intraday-oco-strategy", pead["blockedBy"])
        self.assertTrue(pead["dataQuality"]["requiresEventManifest"])
        self.assertTrue(all(command.startswith("npm ") for item in [faber, pead] for command in item["commands"]))

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T08:30:00+00:00",
            "decision": "research-only",
            "gateSnapshot": {},
            "readyForExecution": False,
            "readyForDemoExpansion": False,
            "frontier": [],
            "hardRules": [],
        })

        self.assertIn("# Bill Alpha Frontier Queue - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_simple_catalog_parser_preserves_paths_without_pyyaml(self):
        catalog = parse_simple_catalog(
            """
datasets:
  nq_futures_1m:
    path: /Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_1_minute.parquet
    priority: P0
source_repos:
  polymarket_microstructure:
    path: /Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25/github/polymarket-microstructure
    use: feature implementations
"""
        )

        self.assertEqual(
            catalog["datasets"]["nq_futures_1m"]["path"],
            "/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_1_minute.parquet",
        )
        self.assertEqual(
            catalog["source_repos"]["polymarket_microstructure"]["path"],
            "/Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25/github/polymarket-microstructure",
        )

    def test_rejected_btc_fixed_rules_suppress_same_frontier_item(self):
        catalog = {
            "datasets": {
                "polymarket_btc_updown_5m_resolved_all": {"path": "/tmp/btc.parquet"},
            },
            "source_repos": {},
        }
        payload = build_frontier(
            catalog=catalog,
            futures_no_edge={"entries": []},
            prediction_no_edge={
                "entries": [
                    {
                        "id": "polymarket-btc-resolved-fixed-rules-current-form",
                        "verdict": "needs-more-data",
                        "currentFormRejected": True,
                    }
                ]
            },
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
        )

        ids = [item["id"] for item in payload["frontier"]]
        self.assertNotIn("prediction-btc-updown-resolved-feature-oos", ids)

    def test_rejected_clob_depth_form_is_not_rerun_as_new_feature(self):
        payload = build_frontier(
            catalog={"source_repos": {"polymarket_microstructure": {"path": "/tmp/poly_repo"}}},
            futures_no_edge={"entries": []},
            prediction_no_edge={
                "entries": [
                    {"id": "polymarket-clob-drift-persistence-current-thresholds", "verdict": "no-edge"},
                    {"id": "polymarket-clob-depth-imbalance-current-form", "verdict": "no-edge", "currentFormRejected": True},
                ]
            },
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
        )

        item = next(item for item in payload["frontier"] if item["id"] == "prediction-clob-microstructure-new-features")

        self.assertNotIn("npm run --silent bill:prediction-clob-depth-imbalance", item["commands"])
        self.assertIn("polymarket-clob-depth-imbalance-current-form", item["blockedBy"])

    def test_rejected_clob_quote_intensity_form_is_not_rerun_as_new_feature(self):
        payload = build_frontier(
            catalog={"source_repos": {"polymarket_microstructure": {"path": "/tmp/poly_repo"}}},
            futures_no_edge={"entries": []},
            prediction_no_edge={
                "entries": [
                    {"id": "polymarket-clob-drift-persistence-current-thresholds", "verdict": "no-edge"},
                    {"id": "polymarket-clob-depth-imbalance-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-quote-intensity-current-form", "verdict": "no-edge", "currentFormRejected": True},
                ]
            },
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
        )

        item = next(item for item in payload["frontier"] if item["id"] == "prediction-clob-microstructure-new-features")

        self.assertNotIn("npm run --silent bill:prediction-clob-depth-imbalance", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-quote-intensity", item["commands"])
        self.assertIn("polymarket-clob-quote-intensity-current-form", item["blockedBy"])

    def test_rejected_clob_spread_compression_form_is_not_rerun_as_new_feature(self):
        payload = build_frontier(
            catalog={"source_repos": {"polymarket_microstructure": {"path": "/tmp/poly_repo"}}},
            futures_no_edge={"entries": []},
            prediction_no_edge={
                "entries": [
                    {"id": "polymarket-clob-drift-persistence-current-thresholds", "verdict": "no-edge"},
                    {"id": "polymarket-clob-depth-imbalance-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-quote-intensity-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-spread-compression-current-form", "verdict": "no-edge", "currentFormRejected": True},
                ]
            },
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
        )

        item = next(item for item in payload["frontier"] if item["id"] == "prediction-clob-microstructure-new-features")

        self.assertNotIn("npm run --silent bill:prediction-clob-depth-imbalance", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-quote-intensity", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-spread-compression", item["commands"])
        self.assertIn("polymarket-clob-spread-compression-current-form", item["blockedBy"])

    def test_rejected_clob_latency_staleness_form_is_not_rerun_as_new_feature(self):
        payload = build_frontier(
            catalog={"source_repos": {"polymarket_microstructure": {"path": "/tmp/poly_repo"}}},
            futures_no_edge={"entries": []},
            prediction_no_edge={
                "entries": [
                    {"id": "polymarket-clob-drift-persistence-current-thresholds", "verdict": "no-edge"},
                    {"id": "polymarket-clob-depth-imbalance-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-quote-intensity-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-spread-compression-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-latency-staleness-current-form", "verdict": "no-edge", "currentFormRejected": True},
                ]
            },
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
        )

        item = next(item for item in payload["frontier"] if item["id"] == "prediction-clob-microstructure-new-features")

        self.assertNotIn("npm run --silent bill:prediction-clob-depth-imbalance", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-quote-intensity", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-spread-compression", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-latency-staleness", item["commands"])
        self.assertIn("polymarket-clob-latency-staleness-current-form", item["blockedBy"])

    def test_rejected_clob_trade_impact_form_is_not_rerun_as_new_feature(self):
        payload = build_frontier(
            catalog={"source_repos": {"polymarket_microstructure": {"path": "/tmp/poly_repo"}}},
            futures_no_edge={"entries": []},
            prediction_no_edge={
                "entries": [
                    {"id": "polymarket-clob-drift-persistence-current-thresholds", "verdict": "no-edge"},
                    {"id": "polymarket-clob-depth-imbalance-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-quote-intensity-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-spread-compression-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-latency-staleness-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-trade-impact-current-form", "verdict": "no-edge", "currentFormRejected": True},
                ]
            },
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
        )

        item = next(item for item in payload["frontier"] if item["id"] == "prediction-clob-microstructure-new-features")

        self.assertNotIn("npm run --silent bill:prediction-clob-depth-imbalance", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-quote-intensity", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-spread-compression", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-latency-staleness", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-trade-impact", item["commands"])
        self.assertIn("polymarket-clob-trade-impact-current-form", item["blockedBy"])

    def test_exhausted_clob_fixed_forms_move_frontier_to_capture_and_labels(self):
        payload = build_frontier(
            catalog={"source_repos": {"polymarket_microstructure": {"path": "/tmp/poly_repo"}}},
            futures_no_edge={"entries": []},
            prediction_no_edge={
                "entries": [
                    {"id": "polymarket-clob-drift-persistence-current-thresholds", "verdict": "no-edge"},
                    {"id": "polymarket-clob-depth-imbalance-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-quote-intensity-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-spread-compression-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-latency-staleness-current-form", "verdict": "no-edge", "currentFormRejected": True},
                    {"id": "polymarket-clob-trade-impact-current-form", "verdict": "no-edge", "currentFormRejected": True},
                ]
            },
            clob_microstructure_audit={
                "decision": "research-only-current-fixed-features-exhausted",
                "readyFeatureCount": 0,
                "rawDataReadyFeatureCount": 4,
                "rejectedFixedFeatureCount": 5,
                "capture": {"recordsRead": 12571},
                "rejectedBaseline": {"status": "REJECT_NO_EDGE"},
            },
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
        )

        item = next(item for item in payload["frontier"] if item["id"] == "prediction-clob-microstructure-new-features")

        self.assertNotIn("npm run --silent bill:prediction-clob-depth-imbalance", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-quote-intensity", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-spread-compression", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-latency-staleness", item["commands"])
        self.assertNotIn("npm run --silent bill:prediction-clob-trade-impact", item["commands"])
        self.assertIn("npm run --silent bill:prediction-label-source-manifest", item["commands"])
        self.assertIn("npm run --silent bill:prediction-resolved-outcome-join", item["commands"])
        self.assertTrue(any("bill:polymarket-clob-recorder" in command for command in item["commands"]))
        self.assertEqual(item["dataQuality"]["readyFeatureCount"], 0)
        self.assertEqual(item["dataQuality"]["rejectedFixedFeatureCount"], 5)
        self.assertTrue(any("Do not replay" in step for step in item["researchSteps"]))

    def test_prediction_news_lag_frontier_has_concrete_requirements_command(self):
        payload = build_frontier(
            catalog={},
            futures_no_edge={"entries": []},
            prediction_no_edge={"entries": []},
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
            prediction_event_lag_requirements={
                "blockedCount": 2,
                "passCount": 2,
                "decision": "research-only-event-lag-requirements-not-cleared",
            },
            prediction_event_market_mapping_plan={
                "candidateCount": 4,
                "decision": "research-only-event-market-mapping-candidates-ready",
            },
            prediction_event_timestamp_dataset={
                "decision": "research-only-event-timestamp-dataset-ready",
                "coverageStatusCounts": {"window-range-present": 3},
                "forwardCaptureRequired": False,
            },
            prediction_event_lag_replay={
                "decision": "research-only-event-lag-replay-watch",
                "completeEventCount": 3,
                "repricedWindowCount": 5,
            },
            prediction_event_lag_sensitivity={
                "decision": "research-only-event-lag-sensitivity-watch",
                "bestRepricedWindowCount": 5,
                "watchScenarioCount": 1,
            },
            prediction_event_lag_watch_review={
                "decision": "research-only-event-lag-watch-review-visible",
                "repricedWatchWindowCount": 2,
            },
            prediction_event_clob_capture_targets={
                "decision": "research-only-capture-targets-ready",
                "targetCount": 4,
            },
            prediction_event_capture_cycle={
                "decision": "research-only-capture-cycle-dry-run-ready",
                "mode": "dry-run",
            },
            prediction_event_label_gap_plan={
                "gapCount": 2,
                "eventMappedGapCount": 2,
                "decision": "research-only-label-gaps-remain",
            },
        )

        item = next(item for item in payload["frontier"] if item["id"] == "prediction-news-first-event-lag-study")

        self.assertEqual(item["commands"], [
            "npm run --silent bill:finnhub-news",
            "npm run --silent bill:prediction-event-news-rss",
            "npm run --silent bill:prediction-event-market-mapping-plan",
            "npm run --silent bill:prediction-event-timestamp-dataset",
            "npm run --silent bill:prediction-event-lag-requirements",
            "npm run --silent bill:prediction-event-lag-replay",
            "npm run --silent bill:prediction-event-lag-sensitivity",
            "npm run --silent bill:prediction-event-lag-watch-review",
            "npm run --silent bill:prediction-event-clob-capture-targets",
            "npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15 --max-output-mb 128 --min-free-gb 20",
            "npm run --silent bill:prediction-label-card-bootstrap",
            "npm run --silent bill:prediction-label-card-audit",
            "npm run --silent bill:prediction-label-source-manifest",
            "npm run --silent bill:prediction-event-label-gap-plan",
            "npm run --silent bill:alpha-frontier-queue",
        ])
        self.assertEqual(item["dataQuality"]["mappingCandidateCount"], 4)
        self.assertEqual(item["dataQuality"]["timestampDatasetDecision"], "research-only-event-timestamp-dataset-ready")
        self.assertEqual(item["dataQuality"]["timestampCoverageStatusCounts"], {"window-range-present": 3})
        self.assertEqual(item["dataQuality"]["lagReplayCompleteEventCount"], 3)
        self.assertEqual(item["dataQuality"]["lagSensitivityWatchScenarioCount"], 1)
        self.assertEqual(item["dataQuality"]["lagWatchReviewRepricedWindowCount"], 2)
        self.assertEqual(item["dataQuality"]["captureTargetCount"], 4)
        self.assertEqual(item["dataQuality"]["captureCycleDecision"], "research-only-capture-cycle-dry-run-ready")
        self.assertEqual(item["dataQuality"]["captureCycleMode"], "dry-run")
        self.assertEqual(item["dataQuality"]["blockedCount"], 2)
        self.assertEqual(item["dataQuality"]["gapCount"], 2)

    def test_cleared_macro_requirements_unblock_new_source_parser_frontier(self):
        payload = build_frontier(
            catalog={},
            futures_no_edge={"entries": []},
            prediction_no_edge={
                "entries": [
                    {"id": "macro-rates-line-parser-current-form", "verdict": "no-edge"},
                ]
            },
            handoff={"decision": "KEEP_EXECUTION_LOCKED"},
            prediction_macro_rates_requirements={
                "blockedCount": 0,
                "passCount": 5,
                "decision": "research-only-macro-rates-requirements-cleared",
            },
        )

        item = next(item for item in payload["frontier"] if item["id"] == "prediction-macro-rates-new-source-parser")

        self.assertEqual(item["blockedBy"], [])
        self.assertEqual(item["rejectedBaseline"], "macro-rates-line-parser-current-form")


if __name__ == "__main__":
    unittest.main()
