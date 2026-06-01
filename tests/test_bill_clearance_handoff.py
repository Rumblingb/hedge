import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scripts.bill_clearance_handoff import (
    OBSIDIAN,
    build_handoff,
    default_daily_plan_path,
    default_obsidian_md_path,
    render_markdown,
)


class BillClearanceHandoffTest(unittest.TestCase):
    def test_default_paths_use_current_utc_date(self):
        daily = default_daily_plan_path()
        handoff = default_obsidian_md_path()

        self.assertEqual(daily.parent, OBSIDIAN / "daily")
        self.assertRegex(daily.name, r"^\d{4}-\d{2}-\d{2}-bill-trading-plan\.md$")
        self.assertEqual(handoff.parent, OBSIDIAN)
        self.assertRegex(handoff.name, r"^bill-clearance-handoff-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T08:21:35+00:00",
            "decision": "KEEP_EXECUTION_LOCKED",
            "readyForExecution": False,
            "readyForDemoExpansion": False,
            "readyForLive": False,
            "gates": {
                "liveReadinessBlockers": [],
                "realtimeDataDecision": "research-only",
                "realtimeDataReady": False,
                "realtimeDataBlockers": [],
                "databentoStatus": "not-run",
                "databentoReadyForExecutionDataProof": False,
                "sourceCleanBlockers": [],
                "cronValidator": "not-run",
            },
            "lanes": {
                "futures": {
                    "decision": "research-only",
                    "researchDataQuality": {},
                    "dataRequirements": {},
                    "brokerParityPlan": {},
                    "nqResearchCycle": {},
                    "laneNextActions": [],
                },
                "predictionMarkets": {
                    "decision": "research-only",
                    "laneNextActions": [],
                    "macroRatesRequirements": {},
                    "macroRatesCrossSourceReplay": {},
                    "eventLagRequirements": {},
                    "eventMarketMappingPlan": {},
                    "eventLagReplay": {},
                    "eventClobCaptureTargets": {},
                    "eventCaptureCycle": {},
                    "eventLabelGapPlan": {},
                    "eventPaperPromotionGate": {},
                    "finnhubNews": {},
                    "eventNewsRss": {},
                    "labelCardAudit": {},
                    "labelManifest": {},
                    "clobMicrostructure": {},
                },
                "tooling": {"status": "PASS", "readyForResearchLoop": True},
                "sourceHygiene": {
                    "plan": {"present": False},
                    "packetReview": {"present": False},
                },
                "strategyResearch": {
                    "sourcePacketReview": {},
                    "sourceHygienePlan": {},
                    "researchSeedTriage": {},
                    "alphaResearchDirection": {},
                    "strategyZooAudit": {},
                    "executionIntake": {},
                },
                "storage": {"archiveCandidateSize": "0B", "movesFiles": False, "deletesFiles": False},
                "clearanceEvidence": {"status": "PASS", "allCommandsPassed": True},
                "goalCompletionAudit": {},
                "cronControl": {},
                "signalQuality": {},
            },
            "nextActions": [],
            "hardRules": [],
            "obsidian": {
                "dailyRouteApproval": "BLOCKED",
                "brokerReconciliation": "UNKNOWN",
            },
        })

        self.assertIn("# Bill/Hermes Clearance Handoff - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_handoff_keeps_execution_locked_and_surfaces_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "daily.md"
            hub = root / "hub.md"
            live = root / "live.json"
            fund = root / "fund.json"
            worktree = root / "worktree.json"
            realtime = root / "realtime.json"
            databento = root / "databento.json"
            futures = root / "futures.json"
            prediction = root / "prediction.json"
            actions = root / "actions.json"
            tooling = root / "tooling.json"
            storage = root / "storage.json"
            evidence = root / "evidence.json"
            futures_data_quality = root / "futures_data_quality.json"
            futures_data_requirements = root / "futures_data_requirements.json"
            futures_broker_parity_plan = root / "futures_broker_parity_plan.json"
            futures_nq_research_cycle = root / "futures_nq_research_cycle.json"
            signal_quality = root / "signal_quality.json"
            prediction_macro_rates_requirements = root / "prediction_macro_rates_requirements.json"
            prediction_macro_rates_cross_source_replay = root / "prediction_macro_rates_cross_source_replay.json"
            prediction_event_lag_requirements = root / "prediction_event_lag_requirements.json"
            prediction_event_market_mapping_plan = root / "prediction_event_market_mapping_plan.json"
            prediction_event_lag_replay = root / "prediction_event_lag_replay.json"
            prediction_event_clob_capture_targets = root / "prediction_event_clob_capture_targets.json"
            prediction_event_capture_cycle = root / "prediction_event_capture_cycle.json"
            prediction_event_label_gap_plan = root / "prediction_event_label_gap_plan.json"
            prediction_event_paper_promotion_gate = root / "prediction_event_paper_promotion_gate.json"
            finnhub_news = root / "finnhub_news.json"
            prediction_event_news_rss = root / "prediction_event_news_rss.json"
            prediction_label_card_audit = root / "prediction_label_card_audit.json"
            prediction_label_manifest = root / "prediction_label_manifest.json"
            prediction_clob_microstructure = root / "prediction_clob_microstructure.json"
            goal_completion_audit = root / "goal_completion_audit.json"
            source_packet_review = root / "source_packet_review.json"
            source_hygiene_plan = root / "source_hygiene_plan.json"
            research_seed_triage = root / "research_seed_triage.json"
            alpha_research_direction = root / "alpha_research_direction.json"
            strategy_zoo_audit = root / "strategy_zoo_audit.json"
            execution_intake_manifest = root / "execution_intake_manifest.json"
            cron = root / "cron.json"

            daily.write_text("No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\nBROKER_RECONCILIATION: UNKNOWN\n")
            hub.write_text("**Mode:** research / shadow / broker-flat monitoring.\n")
            live.write_text(json.dumps({
                "readyForLive": False,
                "readyForDemoExpansion": False,
                "blockers": ["source tree has uncommitted source changes"],
            }))
            fund.write_text(json.dumps({
                "tradingReadinessStatus": "BLOCKED_BY_EVIDENCE",
                "warnings": [{"requirement": "Realtime execution data remains blocked"}],
            }))
            worktree.write_text(json.dumps({"sourceCleanBlockers": ["dirty execution-live files"]}))
            realtime.write_text(json.dumps({
                "decision": "block-execution-data",
                "readyForExecutionData": False,
                "blockers": ["fallback quote is delayed/research-only"],
            }))
            databento.write_text(json.dumps({"status": "NO_QUOTES_MARKET_CLOSED", "readyForExecutionDataProof": False}))
            futures.write_text(json.dumps({"decision": "research-only", "nextTests": ["one"]}))
            prediction.write_text(json.dumps({"decision": "research-only", "readyForPaper": False, "nextTests": ["two"]}))
            actions.write_text(json.dumps({
                "actions": [
                    {
                        "id": "control-plane-clearance-before-demo",
                        "lane": "control-plane",
                        "oneVariable": "none",
                        "firstCommand": "npm run --silent bill:realtime-data-preflight || true",
                        "commands": ["npm run --silent bill:realtime-data-preflight || true"],
                    },
                    *[
                        {
                            "id": f"futures-placeholder-{idx}",
                            "lane": "futures",
                            "oneVariable": "placeholder",
                            "commands": ["npm run --silent bill:alpha-frontier-queue"],
                        }
                        for idx in range(7)
                    ],
                    {
                        "id": "prediction-macro-rates-new-source-parser",
                        "lane": "prediction-markets",
                        "oneVariable": "new macro market source",
                        "commands": ["npm run --silent bill:prediction-macro-rates-requirements"],
                    },
                    {
                        "id": "prediction-news-first-event-lag-study",
                        "lane": "prediction-markets",
                        "oneVariable": "news-to-market lag feature",
                        "commands": ["npm run --silent bill:prediction-event-lag-requirements"],
                    },
                ]
            }))
            tooling.write_text(json.dumps({"status": "PASS", "readyForResearchLoop": True, "readyForExecution": False}))
            storage.write_text(json.dumps({
                "totalSize": "19.0GB",
                "archiveCandidateSize": "12.7GB",
                "movesFiles": False,
                "deletesFiles": False,
                "topCandidates": [],
                "archiveVerification": {
                    "stateSnapshots": {
                        "archiveCoversSource": True,
                        "copyLooksComplete": True,
                        "checksumManifestExists": True,
                        "source": {"size": "2.0GB"},
                        "destination": {"size": "3.9GB"},
                        "missingFromArchiveCount": 0,
                        "sizeMismatchCount": 0,
                    }
                },
            }))
            evidence.write_text(json.dumps({
                "status": "PASS",
                "allCommandsPassed": True,
                "failedCommandIds": [],
                "generatedAt": "2026-05-30T00:00:00+00:00",
            }))
            futures_data_quality.write_text(json.dumps({
                "pass": True,
                "failingDatasets": [],
                "datasets": [{
                    "path": "/Users/brain/hedge/data/free/ALL-6MARKETS-60m-60d-normalized.csv",
                    "rows": 6804,
                    "endTs": "2026-05-29T20:00:00Z",
                    "pass": True,
                    "failingChecks": [],
                }],
            }))
            futures_data_requirements.write_text(json.dumps({
                "decision": "research-only-data-requirements-not-cleared",
                "researchOnly": True,
                "readyForDemoExpansion": False,
                "passCount": 3,
                "blockedCount": 3,
                "requirements": [
                    {"id": "nq-historical-session-oos-depth", "status": "pass"},
                    {"id": "nq-current-local-or-broker-parity", "status": "blocked"},
                    {"id": "futures-execution-grade-realtime", "status": "blocked"},
                ],
            }))
            futures_broker_parity_plan.write_text(json.dumps({
                "decision": "research-only-futures-broker-parity-not-cleared",
                "researchOnly": True,
                "readyForDemoExpansion": False,
                "missingProofs": ["broker-reconciled-current-nq-bars", "open-session-execution-grade-realtime-proof"],
                "current": {
                    "blockedRequirementIds": ["nq-current-local-or-broker-parity", "futures-execution-grade-realtime"],
                    "dailyRouteBlocked": True,
                    "dataOnlyReady": False,
                },
            }))
            futures_nq_research_cycle.write_text(json.dumps({
                "decision": "research-only-futures-cycle-dry-run-ready",
                "mode": "dry-run",
                "researchOnly": True,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "historical": {
                    "bestCandidate": "seagate_nq_15m",
                    "walkforwardDecision": "research-only-historical-session-walkforward-watch",
                    "costStressDecision": "research-only-historical-session-cost-stress-watch",
                },
                "current": {
                    "currentParityDecision": "research-only-current-local-parity-ready",
                    "dataRequirementsDecision": "research-only-data-requirements-not-cleared",
                },
                "blockers": ["broker-parity-not-checked"],
            }))
            signal_quality.write_text(json.dumps({
                "decision": "advisory-only; cannot approve, size, or route trades",
                "researchOnly": True,
                "readyForExecution": False,
                "overallRating": 5.35,
                "blockers": ["stale inputs: vol_regime_gate"],
                "warnings": ["proxy shadow input cannot confirm execution: dom_proxy"],
                "shadowSignalRows": [{
                    "name": "dom_proxy",
                    "direction": "neutral",
                    "confidence": 0,
                    "shadowOnly": True,
                    "proxyOnly": True,
                    "promotedForExecution": False,
                    "tradableSignal": False,
                    "disconnectedComponents": [],
                }],
            }))
            prediction_macro_rates_requirements.write_text(json.dumps({
                "decision": "research-only-macro-rates-requirements-cleared",
                "researchOnly": True,
                "readyForPaper": False,
                "passCount": 2,
                "blockedCount": 0,
                "requirements": [
                    {"id": "public-macro-quotes-fillable-enough-for-research", "status": "pass"},
                    {"id": "macro-rates-resolved-label-history", "status": "pass"},
                ],
            }))
            prediction_macro_rates_cross_source_replay.write_text(json.dumps({
                "decision": "research-only-macro-rates-cross-source-replay-complete",
                "researchOnly": True,
                "readyForPaper": False,
                "readyForExecution": False,
                "rowCount": 2,
                "watchResearchCount": 0,
                "maxSpreadPct": 5.0,
                "minEdgePct": 3.0,
                "rows": [
                    {
                        "ticker": "KXFED-26JUN-T3.50",
                        "meetingDate": "2026-06-17",
                        "thresholdUpperBound": 3.5,
                        "kalshiSpreadPct": 1.0,
                        "yesEdgePctVsAsk": 1.8488,
                        "noEdgePctVsNoAsk": -2.8488,
                        "paperStatus": "blocked",
                        "blockers": ["research-only", "not-paper-ready", "fees-and-fillability-not-stressed"],
                    }
                ],
            }))
            prediction_event_lag_requirements.write_text(json.dumps({
                "decision": "research-only-event-lag-requirements-not-cleared",
                "researchOnly": True,
                "readyForPaper": False,
                "passCount": 1,
                "blockedCount": 3,
                "requirements": [
                    {"id": "fresh-timestamped-news-source", "status": "blocked"},
                    {"id": "clob-around-event-window", "status": "pass"},
                ],
            }))
            prediction_event_market_mapping_plan.write_text(json.dumps({
                "decision": "research-only-event-market-mapping-candidates-ready",
                "researchOnly": True,
                "readyForPaper": False,
                "candidateCount": 4,
                "minimumCandidates": 3,
                "categories": {"geopolitics": 4},
                "blockers": [],
            }))
            prediction_event_lag_replay.write_text(json.dumps({
                "decision": "research-only-event-lag-replay-watch",
                "researchOnly": True,
                "readyForPaper": False,
                "readyForExecution": False,
                "completeEventCount": 3,
                "completeWindowCount": 5,
                "repricedWindowCount": 2,
                "blockers": [],
            }))
            prediction_event_clob_capture_targets.write_text(json.dumps({
                "decision": "research-only-capture-targets-ready",
                "researchOnly": True,
                "readyForPaper": False,
                "readyForExecution": False,
                "targetCount": 4,
                "existingAssetsWithQuotes": 9,
                "coverageStatusCounts": {"no-quotes-for-clob-token": 4},
                "blockers": [],
            }))
            prediction_event_capture_cycle.write_text(json.dumps({
                "decision": "research-only-capture-cycle-ran",
                "mode": "run-recorder",
                "captureMode": "review-lead-token",
                "executedCaptureMode": "token-targets",
                "captureCycleEvidencePassed": True,
                "paperPromotionEvidencePassed": False,
                "paperPromotionBlockers": [
                    "paper-review-requires-positive-fillability-and-spread-adjusted-replay",
                ],
                "executedRecorder": {
                    "present": True,
                    "status": "pass",
                    "mode": "token-targets",
                    "tokenIds": ["selected-review-token"],
                    "publicMarketDataOnly": True,
                    "writesOrders": False,
                    "touchesBroker": False,
                },
                "researchOnly": True,
                "readyForPaper": False,
                "readyForExecution": False,
                "targetCount": 4,
                "reviewLeadTargetCount": 1,
                "completeEventCount": 5,
                "completeWindowCount": 5,
                "repricedWindowCount": 1,
                "eventLagReplayDecision": "research-only-event-lag-replay-watch",
                "eventLagSensitivity": {
                    "present": True,
                    "decision": "research-only-event-lag-sensitivity-watch",
                    "watchReady": True,
                    "watchScenarioCount": 2,
                    "bestRepricedWindowCount": 2,
                    "readyForPaper": False,
                    "readyForExecution": False,
                    "blockers": ["watch-only-scenario-found-manual-review-required"],
                },
                "blockers": ["dry-run-only; pass --run-recorder to collect public CLOB data"],
            }))
            prediction_event_label_gap_plan.write_text(json.dumps({
                "decision": "research-only-label-gaps-remain",
                "researchOnly": True,
                "readyForPaper": False,
                "gapCount": 2,
                "eventMappedGapCount": 2,
                "labelStatusCounts": {"needs-family-label-source": 2},
                "blockedRequirements": ["event-to-market-mapping", "resolved-label-coverage"],
            }))
            prediction_event_paper_promotion_gate.write_text(json.dumps({
                "decision": "research-only-paper-promotion-blocked",
                "researchOnly": True,
                "readyForPaper": False,
                "readyForPaperReview": False,
                "readyForExecution": False,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "passCount": 3,
                "blockedCount": 4,
                "blockedIds": [
                    "no-lookahead-event-window",
                    "resolved-label-paper-coverage",
                    "event-market-mapping-clean",
                    "post-spread-clob-edge",
                ],
            }))
            finnhub_news.write_text(json.dumps({
                "command": "finnhub-news",
                "sourceAdapter": "finnhub",
                "status": "BLOCKED_NO_DATA",
                "api_key_status": "demo_limited",
                "dataUsable": False,
                "news_count": 0,
                "fetchErrors": {"news": "HTTP Error 401", "calendar": "HTTP Error 401"},
                "trading_gate": {
                    "trend_strategies_allowed": False,
                    "active_alerts": 0,
                },
                "readyForExecution": False,
                "researchOnly": True,
            }))
            prediction_event_news_rss.write_text(json.dumps({
                "command": "prediction-event-news-rss",
                "sourceAdapter": "google_news_rss_fallback",
                "status": "PASS",
                "decision": "research-only-event-news-rss-ready",
                "api_key_status": "not_required_rss",
                "dataUsable": True,
                "news_count": 30,
                "fetchErrors": {"Fed OR CPI": None},
                "trading_gate": {
                    "trend_strategies_allowed": False,
                    "active_alerts": 0,
                },
                "readyForPaper": False,
                "readyForExecution": False,
                "researchOnly": True,
            }))
            prediction_label_card_audit.write_text(json.dumps({
                "decision": "research-only-label-cards-not-ready",
                "researchOnly": True,
                "readyForPaper": False,
                "cardCount": 1,
                "validResolvedLabelRows": 0,
                "incompleteRows": 1,
                "blockers": ["no-valid-label-card-rows", "incomplete-label-card-rows"],
            }))
            prediction_label_manifest.write_text(json.dumps({
                "decision": "research-only; build better resolved labels before paper/demo promotion",
                "researchOnly": True,
                "readyForPaper": False,
                "watchCount": 3,
                "historicalRowsLoaded": 59821,
                "usableForResearchJoinCount": 1,
                "itemsNeedingNewLabelSource": 2,
                "statusCounts": {"needs-family-label-source": 2, "usable-for-research-join": 1},
                "coverage": [
                    {
                        "externalId": "2364500",
                        "category": "geopolitics",
                        "subjectKey": "iran",
                        "status": "usable-for-research-join",
                        "subjectResolvedCount": 24,
                        "familyResolvedCount": 24,
                        "labelCardSubjectRows": 24,
                        "blockers": ["research-only", "not-paper-ready"],
                    }
                ],
            }))
            prediction_clob_microstructure.write_text(json.dumps({
                "decision": "research-only-new-feature-audit",
                "researchOnly": True,
                "readyFeatureCount": 4,
                "rejectedBaseline": {"status": "REJECT_NO_EDGE", "watchResearchGroups": 0},
                "capture": {"recordsRead": 2852, "assetsObserved": 27, "medianObservedSpread": 0.01},
            }))
            goal_completion_audit.write_text(json.dumps({
                "decision": "continue-research-only-locked",
                "goalComplete": False,
                "checkCount": 13,
                "passCount": 9,
                "blockedCount": 4,
                "blockedIds": ["futures-demo-not-cleared", "prediction-paper-not-cleared"],
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
            }))
            source_packet_review.write_text(json.dumps({
                "decision": "source-packet-review-visible-execution-locked",
                "reviewedPacketCount": 2,
                "missingPackets": [],
                "classificationCounts": {
                    "keep-research": 20,
                    "review-before-staging": 24,
                    "shadow-only": 4,
                },
                "packetReviewCleared": False,
                "safeToStageAutomatically": False,
                "writesOrders": False,
                "touchesBroker": False,
                "packets": [
                    {
                        "id": "packet-05-futures-strategy-lane",
                        "lane": "futures",
                        "decision": "manual-review-only",
                        "pathCount": 24,
                        "classificationCounts": {"keep-research": 9, "review-before-staging": 11, "shadow-only": 4},
                    },
                    {
                        "id": "packet-06-prediction-market-lane",
                        "lane": "prediction-markets",
                        "decision": "manual-review-only",
                        "pathCount": 24,
                        "classificationCounts": {"keep-research": 11, "review-before-staging": 13},
                    },
                ],
            }))
            source_hygiene_plan.write_text(json.dumps({
                "decision": "source-hygiene-plan-research-only-execution-locked",
                "sourceHygieneCleared": False,
                "sourceClean": False,
                "dirtyStatusCount": 317,
                "reviewBacklogCount": 235,
                "sourceCleanBlockers": [
                    "canonical source root has 303 dirty files",
                    "canonical source root has 27 dirty execution/live files",
                ],
                "worktreeClearanceQueue": [
                    {
                        "priority": 1,
                        "lane": "governance-risk",
                        "dirtyFiles": 25,
                        "action": "Review first as the control-plane lane",
                        "requiredEvidence": ["npm run --silent typecheck"],
                        "sampleFiles": ["src/cli.ts"],
                    },
                    {
                        "priority": 2,
                        "lane": "execution-live",
                        "dirtyFiles": 27,
                        "action": "Keep quarantined",
                        "requiredEvidence": ["npm run --silent bill:verify-execution-quarantine"],
                        "sampleFiles": ["scripts/master_bridge.py"],
                    },
                ],
                "safeToStageAutomatically": False,
                "automaticCleanupAllowed": False,
                "reviewPacketRiskSummary": {
                    "packetCount": 8,
                    "pathCount": 223,
                    "trackedDiffPathCount": 42,
                    "untrackedPathCount": 169,
                    "modifiedPathCount": 42,
                    "statusCounts": {"??": 169, "M": 42, "sibling-worktree-dirty": 12},
                    "manualStageEligiblePacketIds": [
                        "packet-01-control-research-scaffold",
                        "packet-06-prediction-market-lane",
                    ],
                    "blockedStagePacketIds": [
                        "packet-02-execution-firewall-quarantine",
                        "packet-08-sibling-worktree-selective-intake",
                    ],
                    "operatorRead": "Risk summary only. Packets still require manual review.",
                },
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
            }))
            research_seed_triage.write_text(json.dumps({
                "summary": {
                    "totalSeeds": 32,
                    "youtubeSeeds": 28,
                    "queuedYouTubeSeeds": 3,
                    "paperSeeds": 18,
                    "machineTestableSeeds": 28,
                    "executableSeeds": 0,
                    "candidateRetestSeeds": 0,
                    "quarantinedNoEdgeSeeds": 26,
                    "unmappedSeeds": 6,
                },
                "nextBuildQueue": [],
                "localBacktraderRejections": {
                    "wq-trend-mom": {"bestTotalR": -1.69},
                },
                "researchOnly": True,
                "writesOrders": False,
                "readyForExecution": False,
            }))
            alpha_research_direction.write_text(json.dumps({
                "decision": "research-direction-clear-execution-locked",
                "queueSafe": True,
                "continueLanes": [
                    {"id": "futures-paid-nq-session-structure"},
                    {"id": "prediction-news-event-lag-forward-clob"},
                    {"id": "futures-options-regime-risk-overlay"},
                ],
                "retireOrQuarantineLanes": [
                    {"id": "generic-yt-gold-strategy-reruns"},
                    {"id": "current-fixed-prediction-clob-forms"},
                    {"id": "current-futures-wq-orb-parameter-sweeps"},
                ],
                "nextOneVariableTest": {
                    "id": "futures-paid-nq-session-structure-oos",
                    "lane": "futures",
                    "oneVariable": "data source/cadence only",
                    "command": "npm run --silent bill:external-alpha-data-audit",
                    "parallelWatch": {
                        "id": "prediction-forward-public-clob-capture",
                        "oneVariable": "capture duration/window only",
                    },
                },
                "missingEvidence": [
                    {"id": "futures-open-session-current-parity"},
                    {"id": "prediction-paper-promotion-gate"},
                ],
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForPaper": False,
            }))
            strategy_zoo_audit.write_text(json.dumps({
                "counts": {
                    "total": 59,
                    "registered": 59,
                    "classification:SKELETON": 51,
                    "classification:BRONZE": 3,
                    "classification:QUARANTINED": 5,
                },
                "items": [
                    {
                        "strategyId": "daily-range-breakout",
                        "classification": "BRONZE",
                        "phase": "candidate-retest",
                        "testable": True,
                        "executable": False,
                        "evidence": {"bestPropFirmStatus": None, "blockers": []},
                    },
                    {
                        "strategyId": "donchian-breakout",
                        "classification": "BRONZE",
                        "phase": "candidate-retest",
                        "testable": True,
                        "executable": False,
                        "evidence": {
                            "bestPropFirmStatus": "reject",
                            "blockers": ["negative-worst-fold-net-edge"],
                        },
                    },
                    {
                        "strategyId": "ict-displacement",
                        "classification": "QUARANTINED",
                        "phase": "quarantine",
                    },
                ],
            }))
            execution_intake_manifest.write_text(json.dumps({
                "decision": "execution-intake-visible-execution-locked",
                "activeCronDiffReview": [
                    {
                        "relativePath": "scripts/60m_exec_bridge.py",
                        "gitStatus": "M",
                        "classification": "firewall-covered-still-quarantined",
                        "firewallId": "verify-60m-bridge-firewall",
                        "firewallPassed": True,
                        "diffStats": {"addedLines": 106, "deletedLines": 12},
                        "activeCronReferences": [{"name": "60m-lucidflex-execution"}],
                        "operatorAction": "Manual operator review required",
                        "safeAutomaticAction": False,
                        "readyForExecution": False,
                        "researchOnly": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                    }
                ],
            }))
            cron.write_text(json.dumps({
                "summary": "2 issues flagged",
                "cronTrustCleared": False,
                "blockingIssueCount": 2,
                "activeDirtyExecutionLiveScriptReferenceCount": 2,
                "activeDirtyExecutionLiveScriptReferences": [
                    {
                        "id": "dfb37c334ae0",
                        "name": "60m-lucidflex-execution",
                        "script": "60m_exec_bridge.py",
                        "lastStatus": "ok",
                        "source": {
                            "classification": "firewall-covered-still-quarantined",
                            "firewallId": "verify-60m-bridge-firewall",
                        },
                        "operatorRemediation": {
                            "requiredAction": "operator must pause or clear the dirty execution-live source",
                            "safeAutomaticAction": False,
                        },
                    },
                    {
                        "id": "df75ca6970c3",
                        "name": "agentic-fund-cycle",
                        "script": "agentic_fund.sh",
                        "lastStatus": "ok",
                        "source": {
                            "classification": "firewall-covered-still-quarantined",
                            "firewallId": "verify-execution-quarantine",
                        },
                        "operatorRemediation": {
                            "requiredAction": "operator must pause or clear the dirty execution-live source",
                            "safeAutomaticAction": False,
                        },
                    },
                ],
                "blockingIssues": [
                    {
                        "id": "dfb37c334ae0",
                        "job": "60m-lucidflex-execution",
                        "severity": "P1",
                        "type": "active_cron_references_dirty_execution_live_script",
                    },
                    {
                        "id": "df75ca6970c3",
                        "job": "agentic-fund-cycle",
                        "severity": "P1",
                        "type": "active_cron_references_dirty_execution_live_script",
                    },
                ],
                "activeTradingAgentBackedCount": 0,
                "noAgentMetadataMismatchCount": 0,
            }))

            payload = build_handoff(argparse.Namespace(
                daily_plan=str(daily),
                control_hub=str(hub),
                live_readiness=str(live),
                fund_os_audit=str(fund),
                worktree=str(worktree),
                realtime_preflight=str(realtime),
                databento_smoke=str(databento),
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                next_actions=str(actions),
                alpha_tooling=str(tooling),
                hermes_storage=str(storage),
                clearance_evidence=str(evidence),
                futures_data_quality=str(futures_data_quality),
                futures_data_requirements=str(futures_data_requirements),
                futures_broker_parity_plan=str(futures_broker_parity_plan),
                futures_nq_research_cycle=str(futures_nq_research_cycle),
                signal_quality=str(signal_quality),
                prediction_macro_rates_requirements=str(prediction_macro_rates_requirements),
                prediction_macro_rates_cross_source_replay=str(prediction_macro_rates_cross_source_replay),
                prediction_event_lag_requirements=str(prediction_event_lag_requirements),
                prediction_event_market_mapping_plan=str(prediction_event_market_mapping_plan),
                prediction_event_lag_replay=str(prediction_event_lag_replay),
                prediction_event_clob_capture_targets=str(prediction_event_clob_capture_targets),
                prediction_event_capture_cycle=str(prediction_event_capture_cycle),
                prediction_event_label_gap_plan=str(prediction_event_label_gap_plan),
                prediction_event_paper_promotion_gate=str(prediction_event_paper_promotion_gate),
                finnhub_news=str(finnhub_news),
                prediction_event_news_rss=str(prediction_event_news_rss),
                prediction_label_card_audit=str(prediction_label_card_audit),
                prediction_label_manifest=str(prediction_label_manifest),
                prediction_clob_microstructure=str(prediction_clob_microstructure),
                goal_completion_audit=str(goal_completion_audit),
                source_packet_review=str(source_packet_review),
                source_hygiene_plan=str(source_hygiene_plan),
                research_seed_triage=str(research_seed_triage),
                alpha_research_direction=str(alpha_research_direction),
                strategy_zoo_audit=str(strategy_zoo_audit),
                execution_intake_manifest=str(execution_intake_manifest),
                cron_validator=str(cron),
                obsidian_md="",
            ))

        self.assertEqual(payload["decision"], "KEEP_EXECUTION_LOCKED")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertEqual(payload["obsidian"]["dailyRouteApproval"], "BLOCKED")
        self.assertEqual(payload["gates"]["realtimeDataDecision"], "block-execution-data")
        self.assertIn("source tree has uncommitted source changes", payload["gates"]["liveReadinessBlockers"])
        self.assertFalse(payload["lanes"]["cronControl"]["cronTrustCleared"])
        self.assertEqual(payload["lanes"]["cronControl"]["blockingIssueCount"], 2)
        self.assertEqual(payload["lanes"]["cronControl"]["activeDirtyExecutionLiveScriptReferenceCount"], 2)
        self.assertEqual(
            payload["lanes"]["cronControl"]["activeDirtyExecutionLiveScriptReferences"][0]["name"],
            "60m-lucidflex-execution",
        )
        self.assertFalse(payload["lanes"]["cronControl"]["writesOrders"])
        self.assertEqual(
            payload["lanes"]["cronControl"]["activeCronDiffReview"][0]["relativePath"],
            "scripts/60m_exec_bridge.py",
        )
        self.assertEqual(
            payload["lanes"]["cronControl"]["activeCronDiffReview"][0]["diffStats"]["addedLines"],
            106,
        )
        self.assertEqual(payload["lanes"]["tooling"]["status"], "PASS")
        self.assertEqual(payload["lanes"]["clearanceEvidence"]["status"], "PASS")
        self.assertTrue(payload["lanes"]["futures"]["researchDataQuality"]["pass"])
        self.assertEqual(payload["lanes"]["futures"]["dataRequirements"]["blockedCount"], 3)
        self.assertIn("nq-current-local-or-broker-parity", payload["lanes"]["futures"]["dataRequirements"]["blockedRequirementIds"])
        self.assertEqual(payload["lanes"]["futures"]["brokerParityPlan"]["decision"], "research-only-futures-broker-parity-not-cleared")
        self.assertIn("broker-reconciled-current-nq-bars", payload["lanes"]["futures"]["brokerParityPlan"]["missingProofs"])
        self.assertEqual(payload["lanes"]["futures"]["nqResearchCycle"]["bestHistoricalCandidate"], "seagate_nq_15m")
        self.assertEqual(payload["lanes"]["futures"]["nqResearchCycle"]["mode"], "dry-run")
        self.assertFalse(payload["lanes"]["futures"]["nqResearchCycle"]["readyForExecution"])
        futures_lane_action_ids = [item["id"] for item in payload["lanes"]["futures"]["laneNextActions"]]
        self.assertIn("futures-placeholder-0", futures_lane_action_ids)
        self.assertEqual(len(payload["lanes"]["futures"]["laneNextActions"]), 6)
        self.assertEqual(payload["lanes"]["signalQuality"]["overallRating"], 5.35)
        self.assertIn("proxy shadow input cannot confirm execution: dom_proxy", payload["lanes"]["signalQuality"]["warnings"])
        self.assertFalse(payload["lanes"]["signalQuality"]["readyForExecution"])
        self.assertEqual(payload["lanes"]["predictionMarkets"]["macroRatesRequirements"]["blockedCount"], 0)
        self.assertEqual(payload["lanes"]["predictionMarkets"]["macroRatesCrossSourceReplay"]["rowCount"], 2)
        self.assertEqual(payload["lanes"]["predictionMarkets"]["macroRatesCrossSourceReplay"]["watchResearchCount"], 0)
        self.assertEqual(
            payload["lanes"]["predictionMarkets"]["macroRatesCrossSourceReplay"]["sampleRows"][0]["ticker"],
            "KXFED-26JUN-T3.50",
        )
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventLagRequirements"]["blockedCount"], 3)
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventMarketMappingPlan"]["candidateCount"], 4)
        self.assertFalse(payload["lanes"]["predictionMarkets"]["eventMarketMappingPlan"]["readyForPaper"])
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventLagReplay"]["completeEventCount"], 3)
        self.assertFalse(payload["lanes"]["predictionMarkets"]["eventLagReplay"]["readyForExecution"])
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventClobCaptureTargets"]["targetCount"], 4)
        self.assertFalse(payload["lanes"]["predictionMarkets"]["eventClobCaptureTargets"]["readyForExecution"])
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["targetCount"], 4)
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["mode"], "run-recorder")
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["executedCaptureMode"], "token-targets")
        self.assertTrue(payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["captureCycleEvidencePassed"])
        self.assertFalse(payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["paperPromotionEvidencePassed"])
        self.assertEqual(
            payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["executedRecorder"]["tokenIds"],
            ["selected-review-token"],
        )
        self.assertIn(
            "paper-review-requires-positive-fillability-and-spread-adjusted-replay",
            payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["paperPromotionBlockers"],
        )
        self.assertEqual(
            payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["eventLagSensitivity"]["watchScenarioCount"],
            2,
        )
        self.assertFalse(payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["eventLagSensitivity"]["readyForPaper"])
        self.assertFalse(payload["lanes"]["predictionMarkets"]["eventCaptureCycle"]["readyForExecution"])
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventLabelGapPlan"]["gapCount"], 2)
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventLabelGapPlan"]["eventMappedGapCount"], 2)
        self.assertEqual(
            payload["lanes"]["predictionMarkets"]["eventPaperPromotionGate"]["decision"],
            "research-only-paper-promotion-blocked",
        )
        self.assertFalse(payload["lanes"]["predictionMarkets"]["eventPaperPromotionGate"]["readyForPaper"])
        self.assertIn(
            "post-spread-clob-edge",
            payload["lanes"]["predictionMarkets"]["eventPaperPromotionGate"]["blockedIds"],
        )
        self.assertFalse(payload["lanes"]["predictionMarkets"]["eventPaperPromotionGate"]["writesOrders"])
        self.assertEqual(payload["lanes"]["predictionMarkets"]["finnhubNews"]["status"], "BLOCKED_NO_DATA")
        self.assertFalse(payload["lanes"]["predictionMarkets"]["finnhubNews"]["dataUsable"])
        self.assertEqual(payload["lanes"]["predictionMarkets"]["eventNewsRss"]["status"], "PASS")
        self.assertTrue(payload["lanes"]["predictionMarkets"]["eventNewsRss"]["dataUsable"])
        self.assertEqual(payload["lanes"]["predictionMarkets"]["labelCardAudit"]["validResolvedLabelRows"], 0)
        self.assertIn("no-valid-label-card-rows", payload["lanes"]["predictionMarkets"]["labelCardAudit"]["blockers"])
        self.assertEqual(payload["lanes"]["predictionMarkets"]["labelManifest"]["usableForResearchJoinCount"], 1)
        self.assertEqual(
            payload["lanes"]["predictionMarkets"]["labelManifest"]["decision"],
            "research-only; build better resolved labels before paper/demo promotion",
        )
        self.assertFalse(payload["lanes"]["predictionMarkets"]["labelManifest"]["readyForPaper"])
        self.assertEqual(
            payload["lanes"]["predictionMarkets"]["labelManifest"]["coverage"][0]["subjectKey"],
            "iran",
        )
        self.assertEqual(
            payload["lanes"]["predictionMarkets"]["labelManifest"]["coverage"][0]["subjectResolvedCount"],
            24,
        )
        self.assertEqual(payload["lanes"]["predictionMarkets"]["clobMicrostructure"]["rejectedBaselineStatus"], "REJECT_NO_EDGE")
        prediction_lane_action_ids = [item["id"] for item in payload["lanes"]["predictionMarkets"]["laneNextActions"]]
        self.assertIn("prediction-macro-rates-new-source-parser", prediction_lane_action_ids)
        self.assertIn("prediction-news-first-event-lag-study", prediction_lane_action_ids)
        self.assertEqual(payload["lanes"]["goalCompletionAudit"]["decision"], "continue-research-only-locked")
        self.assertFalse(payload["lanes"]["goalCompletionAudit"]["goalComplete"])
        self.assertIn("futures-demo-not-cleared", payload["lanes"]["goalCompletionAudit"]["blockedIds"])
        self.assertEqual(payload["lanes"]["sourceHygiene"]["plan"]["dirtyStatusCount"], 317)
        self.assertEqual(payload["lanes"]["sourceHygiene"]["plan"]["reviewPacketRiskSummary"]["pathCount"], 223)
        self.assertEqual(payload["lanes"]["sourceHygiene"]["plan"]["reviewPacketRiskSummary"]["untrackedPathCount"], 169)
        self.assertIn(
            "packet-02-execution-firewall-quarantine",
            payload["lanes"]["sourceHygiene"]["plan"]["reviewPacketRiskSummary"]["blockedStagePacketIds"],
        )
        self.assertEqual(payload["lanes"]["sourceHygiene"]["plan"]["worktreeClearanceQueue"][0]["lane"], "governance-risk")
        self.assertEqual(payload["lanes"]["sourceHygiene"]["plan"]["worktreeClearanceQueue"][1]["dirtyFiles"], 27)
        self.assertFalse(payload["lanes"]["sourceHygiene"]["plan"]["safeToStageAutomatically"])
        self.assertEqual(payload["lanes"]["sourceHygiene"]["packetReview"]["reviewedPacketCount"], 2)
        self.assertEqual(payload["lanes"]["sourceHygiene"]["packetReview"]["classificationCounts"]["shadow-only"], 4)
        self.assertFalse(payload["lanes"]["sourceHygiene"]["packetReview"]["safeToStageAutomatically"])
        self.assertEqual(payload["lanes"]["strategyResearch"]["researchSeedTriage"]["totalSeeds"], 32)
        self.assertEqual(payload["lanes"]["strategyResearch"]["researchSeedTriage"]["queuedYouTubeSeeds"], 3)
        self.assertEqual(payload["lanes"]["strategyResearch"]["researchSeedTriage"]["executableSeeds"], 0)
        self.assertEqual(
            payload["lanes"]["strategyResearch"]["alphaResearchDirection"]["decision"],
            "research-direction-clear-execution-locked",
        )
        self.assertEqual(
            payload["lanes"]["strategyResearch"]["alphaResearchDirection"]["continueLanes"],
            [
                "futures-paid-nq-session-structure",
                "prediction-news-event-lag-forward-clob",
                "futures-options-regime-risk-overlay",
            ],
        )
        self.assertIn(
            "current-fixed-prediction-clob-forms",
            payload["lanes"]["strategyResearch"]["alphaResearchDirection"]["retireOrQuarantineLanes"],
        )
        self.assertEqual(
            payload["lanes"]["strategyResearch"]["alphaResearchDirection"]["nextOneVariableTest"]["oneVariable"],
            "data source/cadence only",
        )
        self.assertIn(
            "wq-trend-mom",
            payload["lanes"]["strategyResearch"]["researchSeedTriage"]["localBacktraderRejectedFamilies"],
        )
        self.assertEqual(payload["lanes"]["strategyResearch"]["strategyZooAudit"]["registeredCount"], 59)
        self.assertEqual(
            payload["lanes"]["strategyResearch"]["strategyZooAudit"]["candidateRetest"][1]["strategyId"],
            "donchian-breakout",
        )
        self.assertIn("ict-displacement", payload["lanes"]["strategyResearch"]["strategyZooAudit"]["quarantined"])
        self.assertTrue(payload["lanes"]["storage"]["stateSnapshotsArchive"]["archiveCoversSource"])
        self.assertTrue(payload["lanes"]["storage"]["stateSnapshotsArchive"]["copyLooksComplete"])
        next_action_ids = [item["id"] for item in payload["nextActions"]]
        self.assertIn("prediction-macro-rates-new-source-parser", next_action_ids)
        self.assertIn("prediction-news-first-event-lag-study", next_action_ids)
        by_action_id = {item["id"]: item for item in payload["nextActions"]}
        self.assertEqual(
            by_action_id["control-plane-clearance-before-demo"]["firstCommand"],
            "npm run --silent bill:realtime-data-preflight || true",
        )
        self.assertEqual(
            by_action_id["prediction-macro-rates-new-source-parser"]["firstCommand"],
            "npm run --silent bill:prediction-macro-rates-requirements",
        )

        markdown = render_markdown(payload)
        self.assertIn("KEEP_EXECUTION_LOCKED", markdown)
        self.assertIn("first `npm run --silent bill:realtime-data-preflight || true`", markdown)
        self.assertIn("source tree has uncommitted source changes", markdown)
        self.assertIn("Futures research data quality", markdown)
        self.assertIn("Futures data requirements", markdown)
        self.assertIn("Futures broker parity plan", markdown)
        self.assertIn("Futures NQ research cycle", markdown)
        self.assertIn("Futures lane next actions", markdown)
        self.assertIn("`futures-placeholder-0` one-variable `placeholder`", markdown)
        self.assertIn("`npm run --silent bill:alpha-frontier-queue`", markdown)
        self.assertIn("Signal quality", markdown)
        self.assertIn("Cron control", markdown)
        self.assertIn("trustCleared `False`", markdown)
        self.assertIn("60m-lucidflex-execution", markdown)
        self.assertIn("agentic-fund-cycle", markdown)
        self.assertIn("Active cron diff review", markdown)
        self.assertIn("scripts/60m_exec_bridge.py", markdown)
        self.assertNotIn("Cron control: `{'present'", markdown)
        self.assertIn("Prediction macro/rates requirements", markdown)
        self.assertIn("Prediction macro/rates cross-source replay", markdown)
        self.assertIn("KXFED-26JUN-T3.50", markdown)
        self.assertIn("watchResearch `0`", markdown)
        self.assertNotIn("Prediction macro/rates cross-source replay: `{'present'", markdown)
        self.assertIn("Prediction lane next actions", markdown)
        self.assertIn("`prediction-news-first-event-lag-study` one-variable `news-to-market lag feature`", markdown)
        self.assertIn("Prediction event-lag requirements", markdown)
        self.assertIn("Prediction event-market mapping plan", markdown)
        self.assertIn("Prediction event-lag replay", markdown)
        self.assertIn("Prediction event CLOB capture targets", markdown)
        self.assertIn("Prediction event capture cycle", markdown)
        self.assertIn("Prediction event-lag sensitivity", markdown)
        self.assertIn("bestRepricedWindowCount", markdown)
        self.assertIn("Prediction event label gaps", markdown)
        self.assertIn("Prediction Finnhub news source", markdown)
        self.assertIn("BLOCKED_NO_DATA", markdown)
        self.assertIn("Prediction RSS news source", markdown)
        self.assertIn("Prediction label card audit", markdown)
        self.assertIn("Research seed triage", markdown)
        self.assertIn("queuedYT `3`", markdown)
        self.assertIn("Strategy zoo audit", markdown)
        self.assertIn("quarantinedNoEdge `26`", markdown)
        self.assertIn("Local Backtrader rejected families", markdown)
        self.assertIn("Candidate retest queue", markdown)
        self.assertIn("donchian-breakout", markdown)
        self.assertIn("Source hygiene plan", markdown)
        self.assertIn("Review packet risk", markdown)
        self.assertIn("untracked `169`", markdown)
        self.assertIn("Worktree clearance queue", markdown)
        self.assertIn("`governance-risk` priority `1` dirty `25`", markdown)
        self.assertIn("`execution-live` priority `2` dirty `27`", markdown)
        self.assertIn("Source packet review", markdown)
        self.assertIn("stateSnapshotsArchive", markdown)
        self.assertIn("archiveCoversSource", markdown)
        self.assertIn("usable-for-research-join", markdown)
        self.assertIn("subjectResolvedCount", markdown)
        self.assertIn("packet-05-futures-strategy-lane", markdown)
        self.assertIn("packet-06-prediction-market-lane", markdown)
        self.assertNotIn("Source packet review: `{'present'", markdown)
        self.assertNotIn("Research seed triage: `{'present'", markdown)
        self.assertNotIn("Strategy zoo audit: `{'present'", markdown)


if __name__ == "__main__":
    unittest.main()
