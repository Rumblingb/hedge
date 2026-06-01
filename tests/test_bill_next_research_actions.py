import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scripts.bill_next_research_actions import HERMES, build_actions, default_markdown_path, render_markdown


class BillNextResearchActionsTest(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^bill-next-research-actions-\d{4}-\d{2}-\d{2}\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T08:30:00+00:00",
            "gateSnapshot": {
                "readyForLive": False,
                "readyForDemoExpansion": False,
                "dataFreshnessVerdict": "STALE",
                "dataFreshnessAction": "block_all_trades",
                "liveBlockers": [],
                "sourceCleanBlockers": [],
            },
            "actions": [],
            "hardRules": [],
        })

        self.assertIn("# Bill Next Research Actions - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_builds_research_only_queue_with_exact_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"
            open_session = tmp_path / "open-session.json"
            event_lag_watch = tmp_path / "event-lag-watch.json"
            event_lag_manual = tmp_path / "event-lag-manual.json"

            futures.write_text(json.dumps({
                "decision": "research-only",
                "nextTests": [
                    {
                        "id": "lower-timeframe-vol-regime-current-form-rejected",
                        "oneVariable": "timeframe/data-window",
                        "hypothesis": "sample depth improved but promotion failed",
                        "promotionRule": "require OOS and stressed windows",
                    }
                ],
            }))
            prediction.write_text(json.dumps({
                "decision": "research-only",
                "resolvedOutcomeReview": {
                    "decision": "do-not-promote-resolved-history-without-paper-review-and-fillability"
                },
                "nextTests": [
                    {
                        "id": "kalshi-fillability-guided-rates-scan",
                        "oneVariable": "fillable public quote universe",
                        "hypothesis": "fillable books should guide category selection",
                    },
                    {
                        "id": "narrow-cross-venue-normalization",
                        "oneVariable": "market universe",
                        "hypothesis": "narrower universe may improve match quality",
                    },
                    {
                        "id": "resolved-outcome-join-review",
                        "oneVariable": "resolved-outcome evidence",
                        "hypothesis": "history exists but not paper evidence",
                    },
                    {
                        "id": "targeted-clob-persistence-capture",
                        "oneVariable": "observation time",
                        "hypothesis": "targeted CLOB observation may improve persistence evidence",
                        "eligibleTokens": [
                            {"tokenId": "111"},
                            {"tokenId": "222"},
                        ],
                    }
                ],
            }))
            seeds.write_text(json.dumps({
                "queuedYouTubeResearcherTargets": [
                    {
                        "id": "youtube-queue-pead",
                        "kind": "youtube-transcript",
                        "videos": ["https://youtu.be/EP4ptjamPYA"],
                    }
                ],
                "nextBuildQueue": [
                    {
                        "sourceId": "seed-a",
                        "inferredStrategyId": "wq-trend-mom",
                        "title": "Trend seed",
                        "blockers": ["requires fresh local OOS"],
                    }
                ]
            }))
            live.write_text(json.dumps({
                "readyForLive": False,
                "readyForDemoExpansion": False,
                "blockers": ["source tree has uncommitted source changes"],
            }))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({
                "pass": True,
                "datasets": [
                    {
                        "path": "/tmp/ALL-6MARKETS-15m-60d-normalized.csv",
                        "rows": 27188,
                        "endTs": "2026-05-29T20:45:00Z",
                        "pass": True,
                        "failingChecks": [],
                    }
                ],
                "failingDatasets": [],
            }))
            worktree.write_text(json.dumps({"sourceCleanBlockers": ["dirty execution-live files"]}))
            cftc.write_text(json.dumps({
                "freshForWeeklyResearch": True,
                "latestReportDate": "2026-05-26",
                "researchOnly": True,
                "writesOrders": False,
            }))
            cot.write_text(json.dumps({}))
            category.write_text(json.dumps({
                "readyForPaper": False,
                "writesOrders": False,
                "kalshiFillability": {
                    "executablePublicQuotes": 19,
                    "categories": {
                        "macro-rates": {
                            "executablePublicQuotes": 19,
                            "seriesTickers": {"KXFED": 14, "KXCPI": 5},
                        }
                    },
                    "researchOnly": True,
                    "writesOrders": False,
                },
                "nextTests": [
                    {
                        "id": "geopolitics-narrow-scan",
                        "category": "geopolitics",
                        "oneVariable": "market universe",
                        "marketCount": 226,
                        "venues": ["manifold", "polymarket"],
                    },
                    {
                        "id": "macro-rates-narrow-scan",
                        "category": "macro-rates",
                        "oneVariable": "line parser",
                        "marketCount": 111,
                        "venues": ["kalshi", "polymarket"],
                        "fillabilityGuided": True,
                        "kalshiFillability": {
                            "executablePublicQuotes": 19,
                            "seriesTickers": {"KXFED": 14, "KXCPI": 5},
                        },
                    },
                ],
            }))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            alpha_frontier.write_text(json.dumps({"frontier": []}))
            open_session.write_text(json.dumps({
                "mode": "dry-run",
                "executionGradeDataProofPassed": False,
                "plannedStepIds": ["databento-open-session-smoke", "databento-open-session-bridge-write", "sync-obsidian"],
                "stateSummary": {
                    "nextOpenSessionProofWindow": {
                        "recommendedProofStartUtc": "2026-05-31T22:05:00+00:00",
                        "recommendedProofEndUtc": "2026-05-31T22:35:00+00:00",
                        "commandsAreDataOnly": True,
                    }
                },
            }))
            event_lag_watch.write_text(json.dumps({
                "decision": "research-only-event-lag-watch-review-visible",
                "watchReady": True,
                "readyForPaper": False,
                "readyForExecution": False,
                "blockers": ["manual-review-required-before-forward-capture-or-paper-discussion"],
                "watchWindows": [
                    {
                        "externalId": "2270330",
                        "question": "US x Iran permanent peace deal by June 15, 2026?",
                        "eventIso": "2026-05-30T16:04:20+00:00",
                        "variable": "minimumAbsMove",
                        "value": 0.0025,
                        "horizonMinutes": 15,
                        "midMove": 0.005,
                        "preSpread": 0.01,
                        "postDelaySec": 900.221,
                    },
                    {
                        "externalId": "2354003",
                        "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                        "eventIso": "2026-05-30T16:04:20+00:00",
                        "variable": "minimumAbsMove",
                        "value": 0.0025,
                        "horizonMinutes": 15,
                        "midMove": -0.01,
                        "preSpread": 0.01,
                        "postDelaySec": 901.12,
                    },
                ],
            }))
            event_lag_manual.write_text(json.dumps({}))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
                open_session_data_proof=str(open_session),
                prediction_event_lag_watch_review=str(event_lag_watch),
                prediction_event_lag_manual_review=str(event_lag_manual),
            ))

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForLive"])
        self.assertEqual(payload["decision"], "research-queue-visible-execution-locked")
        self.assertTrue(payload["blocked"])
        self.assertEqual(payload["leadActionId"], "control-plane-clearance-before-demo")
        self.assertEqual(payload["leadLane"], "control-plane")
        self.assertEqual(payload["nextActions"][0]["id"], "control-plane-clearance-before-demo")
        self.assertEqual(payload["nextActions"][0]["firstCommand"], "npm run --silent bill:realtime-data-preflight || true")
        self.assertEqual(payload["nextActions"][0]["command"], "npm run --silent bill:realtime-data-preflight || true")
        self.assertIn("npm run --silent bill:databento-realtime-smoke", payload["nextActions"][0]["commands"])
        self.assertTrue(payload["nextActions"][0]["researchOnly"])
        self.assertFalse(payload["nextActions"][0]["writesOrders"])
        self.assertFalse(payload["nextActions"][0]["touchesBroker"])
        self.assertIn("npm run --silent bill:realtime-data-preflight || true", payload["commands"])
        self.assertEqual(payload["gateSnapshot"]["dataFreshnessAction"], "block_all_trades")
        self.assertTrue(payload["gateSnapshot"]["futuresResearchDataQuality"]["pass"])
        self.assertEqual(
            payload["gateSnapshot"]["futuresResearchDataQuality"]["datasets"][0]["name"],
            "ALL-6MARKETS-15m-60d-normalized.csv",
        )
        self.assertEqual(payload["gateSnapshot"]["futuresResearchDataQuality"]["failingDatasets"], [])
        self.assertTrue(payload["gateSnapshot"]["cftcTffFreshForWeeklyResearch"])
        self.assertEqual(payload["gateSnapshot"]["predictionCategoryLanes"], ["geopolitics", "macro-rates"])
        self.assertTrue(payload["gateSnapshot"]["predictionEventLagWatch"]["watchReady"])
        self.assertEqual(payload["gateSnapshot"]["predictionEventLagWatch"]["watchWindowCount"], 2)
        self.assertFalse(payload["gateSnapshot"]["predictionEventLagManualReview"]["present"])
        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertIn("control-plane-clearance-before-demo", by_id)
        self.assertTrue(all("firstCommand" in item for item in payload["actions"]))
        self.assertEqual(
            by_id["control-plane-clearance-before-demo"]["firstCommand"],
            "npm run --silent bill:realtime-data-preflight || true",
        )
        self.assertEqual(
            by_id["lower-timeframe-vol-regime-current-form-rejected"]["firstCommand"],
            "npm run --silent bill:vol-regime-oos-15m",
        )
        self.assertEqual(
            by_id["kalshi-fillability-guided-rates-scan"]["firstCommand"],
            "npm run --silent bill:kalshi-fillability-snapshot",
        )
        self.assertIn("npm run --silent bill:databento-realtime-smoke", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:open-session-data-proof", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn(
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:open-session-data-proof -- --run-data-only",
            by_id["control-plane-clearance-before-demo"]["commands"],
        )
        self.assertEqual(
            by_id["control-plane-clearance-before-demo"]["nextWindow"]["recommendedProofStartUtc"],
            "2026-05-31T22:05:00+00:00",
        )
        self.assertEqual(
            by_id["control-plane-clearance-before-demo"]["dataOnlyProof"]["plannedStepIds"],
            ["databento-open-session-smoke", "databento-open-session-bridge-write", "sync-obsidian"],
        )
        self.assertFalse(by_id["control-plane-clearance-before-demo"]["dataOnlyProof"]["writesOrders"])
        self.assertFalse(by_id["control-plane-clearance-before-demo"]["dataOnlyProof"]["touchesBroker"])
        self.assertIn("npm run --silent bill:hermes-storage-audit", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:codex-automation-audit", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:source-intake-manifest", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:source-hygiene-plan", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:source-packet-review", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:data-intake-manifest", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:verify-execution-quarantine", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:execution-intake-manifest", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:clearance-evidence", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:clearance-handoff", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:alpha-research-direction-audit", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:current-alpha-watch", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:goal-completion-audit", by_id["control-plane-clearance-before-demo"]["commands"])
        self.assertIn("npm run --silent bill:kalshi-fillability-snapshot", by_id["kalshi-fillability-guided-rates-scan"]["commands"])
        self.assertIn("npm run --silent bill:cftc-tff-positioning || true", by_id["cftc-tff-positioning-regime-filter"]["commands"])
        self.assertIn("npm run --silent bill:cot-regime-filter-research", by_id["cftc-tff-positioning-regime-filter"]["commands"])
        self.assertEqual(by_id["cftc-tff-positioning-regime-filter"]["oneVariable"], "weekly positioning regime")
        self.assertIn("npm run --silent bill:vol-regime-oos-15m", by_id["lower-timeframe-vol-regime-current-form-rejected"]["commands"])
        self.assertIn("npm run --silent bill:kalshi-fillability-snapshot", by_id["narrow-cross-venue-normalization"]["commands"])
        self.assertIn("prediction-event-lag-watch-window-review", by_id)
        self.assertEqual(by_id["prediction-event-lag-watch-window-review"]["watchWindowCount"], 2)
        self.assertEqual(by_id["prediction-event-lag-watch-window-review"]["watchWindowSummary"][0]["externalId"], "2270330")
        self.assertIn("manual-review-required-before-forward-capture-or-paper-discussion", by_id["prediction-event-lag-watch-window-review"]["promotionBlockers"])
        self.assertIn("npm run --silent bill:prediction-event-lag-watch-review", by_id["prediction-event-lag-watch-window-review"]["commands"])
        self.assertIn("npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15 --max-output-mb 128 --min-free-gb 20", by_id["prediction-event-lag-watch-window-review"]["commands"])
        self.assertFalse(by_id["prediction-event-lag-watch-window-review"]["writesOrders"])
        self.assertFalse(by_id["prediction-event-lag-watch-window-review"]["touchesBroker"])
        self.assertEqual(
            [item["category"] for item in by_id["narrow-cross-venue-normalization"]["currentCategoryUniverse"]["categories"]],
            ["geopolitics", "macro-rates"],
        )
        self.assertTrue(by_id["narrow-cross-venue-normalization"]["currentCategoryUniverse"]["categories"][1]["fillabilityGuided"])
        self.assertEqual(
            by_id["narrow-cross-venue-normalization"]["currentCategoryUniverse"]["categories"][1]["kalshiFillability"]["seriesTickers"],
            {"KXFED": 14, "KXCPI": 5},
        )
        self.assertIn("geopolitics, macro-rates", by_id["narrow-cross-venue-normalization"]["commandHint"])
        self.assertIn("Fillability-guided lanes: macro-rates", by_id["narrow-cross-venue-normalization"]["commandHint"])
        self.assertIn("npm run --silent bill:prediction-resolved-outcome-join", by_id["resolved-outcome-join-review"]["commands"])
        self.assertTrue(any("--token-id 111 --token-id 222" in command for command in by_id["targeted-clob-persistence-capture"]["commands"]))
        self.assertFalse(any("--read-only" in command for command in by_id["targeted-clob-persistence-capture"]["commands"]))
        self.assertIn("seed-extract-queued-youtube-transcripts", by_id)
        self.assertEqual(by_id["seed-extract-queued-youtube-transcripts"]["queuedTargetCount"], 1)
        self.assertEqual(by_id["seed-extract-queued-youtube-transcripts"]["sampleTargetIds"], ["youtube-queue-pead"])
        self.assertIn("--targets .rumbling-hedge/state/research-seed-youtube-targets.latest.json", " ".join(by_id["seed-extract-queued-youtube-transcripts"]["commands"]))
        self.assertIn("--target youtube-queue-pead", " ".join(by_id["seed-extract-queued-youtube-transcripts"]["commands"]))
        self.assertFalse(by_id["seed-extract-queued-youtube-transcripts"]["writesOrders"])
        self.assertFalse(by_id["seed-extract-queued-youtube-transcripts"]["touchesBroker"])
        self.assertIn("npm run --silent bill:backtrader-research", by_id["seed-replay-wq-trend-mom-1"]["commands"])
        self.assertTrue(all(not item["writesOrders"] for item in payload["actions"]))
        self.assertTrue(all(not item["touchesBroker"] for item in payload["actions"]))

    def test_manual_event_lag_review_moves_queue_to_mapping_refinement(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"
            event_lag_watch = tmp_path / "event-lag-watch.json"
            event_lag_manual = tmp_path / "event-lag-manual.json"
            event_market_mapping = tmp_path / "event-market-mapping.json"
            event_mapping_refinement = tmp_path / "event-mapping-refinement.json"
            event_clob_targets = tmp_path / "event-clob-targets.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            seeds.write_text(json.dumps({"nextBuildQueue": []}))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({"freshForWeeklyResearch": False}))
            cot.write_text(json.dumps({}))
            category.write_text(json.dumps({"readyForPaper": False, "writesOrders": False, "nextTests": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            alpha_frontier.write_text(json.dumps({"frontier": []}))
            event_lag_watch.write_text(json.dumps({
                "decision": "research-only-event-lag-watch-review-visible",
                "watchReady": True,
                "readyForPaper": False,
                "readyForExecution": False,
                "watchWindows": [
                    {
                        "externalId": "2270330",
                        "question": "US x Iran permanent peace deal by June 15, 2026?",
                        "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                        "eventIso": "2026-05-30T16:04:20+00:00",
                        "variable": "minimumAbsMove",
                        "value": 0.0025,
                        "horizonMinutes": 15,
                        "midMove": 0.005,
                        "preSpread": 0.01,
                        "postDelaySec": 900.221,
                    }
                ],
            }))
            event_lag_manual.write_text(json.dumps({
                "decision": "research-only-manual-review-no-paper",
                "reviewedWindowCount": 1,
                "decisionCounts": {"reject-paper": 1},
                "blockers": [
                    "no-window-clears-manual-review-for-paper-discussion",
                    "event-market-mapping-or-spread-quality-not-paper-grade",
                    "forward-public-clob-capture-observed-but-not-paper-grade",
                ],
                "readyForPaper": False,
                "readyForExecution": False,
            }))
            event_market_mapping.write_text(json.dumps({
                "decision": "research-only-event-market-mapping-blocked",
                "blockers": ["ambiguous-headline-event-family-fanout", "ambiguous-headline-counterparty-fanout"],
                "ambiguousHeadlineCount": 1,
                "ambiguousCounterpartyHeadlineCount": 1,
                "ambiguousHeadlineCounterpartyFanout": [
                    {
                        "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                        "headlineActors": ["fed", "iran"],
                        "marketActorSets": [["iran", "us"], ["iran", "israel"]],
                        "candidateExternalIds": ["2270330", "2279999"],
                    }
                ],
                "headlineFamilyFanout": [
                    {
                        "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                        "headlineEventFamilies": ["geopolitical-agreement", "macro-rates"],
                        "headlineActors": ["fed", "iran"],
                        "marketActorSets": [["iran", "us"], ["iran", "israel"]],
                        "candidateCount": 2,
                        "candidateExternalIds": ["2270330", "2279999"],
                    }
                ],
            }))
            event_mapping_refinement.write_text(json.dumps({
                "decision": "research-only-mapping-refinement-required",
                "blockers": ["spread-quality-rejected-current-watch-window", "ambiguous-headline-to-market-fanout"],
                "mappingQualityCounts": {"reject-spread-and-ambiguous-fanout": 1},
            }))
            event_clob_targets.write_text(json.dumps({
                "targetCount": 0,
                "tokenSpecificCandidateCount": 5,
                "excludedMappingCandidateCount": 15,
                "excludedMappingReasonCounts": {
                    "ambiguous-mapping-status": 15,
                    "headline-has-multiple-event-families": 15,
                    "market-counterparty-not-explicit-in-headline": 15,
                },
                "mappingBlockers": [
                    "ambiguous-headline-event-family-fanout",
                    "ambiguous-headline-counterparty-fanout",
                ],
                "forwardCapturePlan": {
                    "required": True,
                    "reason": "Event-to-market mapping is ambiguous; use standing term capture.",
                    "command": "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --max-assets 20 --max-output-mb 128 --min-free-gb 20 --terms 'fed,iran'",
                    "reviewLeadCommand": "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --max-assets 4 --max-output-mb 128 --min-free-gb 20 --token-id 'ladder-1'",
                },
            }))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
                prediction_event_lag_watch_review=str(event_lag_watch),
                prediction_event_lag_manual_review=str(event_lag_manual),
                prediction_event_market_mapping=str(event_market_mapping),
                prediction_event_mapping_refinement=str(event_mapping_refinement),
                prediction_event_clob_targets=str(event_clob_targets),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertNotIn("prediction-event-lag-watch-window-review", by_id)
        self.assertIn("prediction-event-mapping-refinement-after-manual-review", by_id)
        action = by_id["prediction-event-mapping-refinement-after-manual-review"]
        self.assertEqual(action["priority"], 30)
        self.assertEqual(action["manualReviewDecision"], "research-only-manual-review-no-paper")
        self.assertEqual(action["manualReviewCounts"], {"reject-paper": 1})
        self.assertNotIn("npm run --silent bill:prediction-event-lag-manual-review", action["commands"])
        self.assertEqual(action["firstCommand"], "npm run --silent bill:prediction-event-market-mapping-plan")
        self.assertIn("Manual review is already complete", action["commandHint"])
        self.assertIn("npm run --silent bill:prediction-event-market-mapping-plan", action["commands"])
        self.assertIn("npm run --silent bill:prediction-event-mapping-refinement", action["commands"])
        self.assertNotIn("npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15 --max-output-mb 128 --min-free-gb 20", action["commands"])
        self.assertIn("npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --max-assets 4 --max-output-mb 128 --min-free-gb 20 --token-id 'ladder-1'", action["commands"])
        self.assertNotIn("npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --max-assets 20 --max-output-mb 128 --min-free-gb 20 --terms 'fed,iran'", action["commands"])
        self.assertTrue(action["forwardCapturePlan"]["usedInsteadOfTargetSpecificCapture"])
        self.assertTrue(action["forwardCapturePlan"]["usedReviewLeadCommand"])
        self.assertEqual(
            action["forwardCapturePlan"]["preferredCommand"],
            "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --max-assets 4 --max-output-mb 128 --min-free-gb 20 --token-id 'ladder-1'",
        )
        self.assertIn("forward-public-clob-capture-observed-but-not-paper-grade", action["promotionBlockers"])
        self.assertNotIn("forward-public-clob-capture-still-required", action["promotionBlockers"])
        self.assertIn("deadline-ladder-forward-capture-required-before-paper-review", action["promotionBlockers"])
        self.assertNotIn("standing-forward-capture-required-before-token-specific-capture", action["promotionBlockers"])
        self.assertIn("ambiguous-headline-event-family-fanout", action["promotionBlockers"])
        self.assertIn("ambiguous-headline-counterparty-fanout", action["promotionBlockers"])
        self.assertIn("spread-quality-rejected-current-watch-window", action["promotionBlockers"])
        self.assertEqual(action["mappingPlanDecision"], "research-only-event-market-mapping-blocked")
        self.assertEqual(action["mappingPlanAmbiguousHeadlineCount"], 1)
        self.assertEqual(action["mappingPlanAmbiguousCounterpartyHeadlineCount"], 1)
        self.assertEqual(action["mappingPlanAmbiguousCounterpartyFanoutCount"], 1)
        self.assertEqual(action["mappingExclusionSummary"]["tokenSpecificCandidateCount"], 5)
        self.assertEqual(action["mappingExclusionSummary"]["excludedMappingCandidateCount"], 15)
        self.assertEqual(
            action["mappingExclusionSummary"]["excludedMappingReasonCounts"]["market-counterparty-not-explicit-in-headline"],
            15,
        )
        self.assertEqual(action["headlineFamilyFanoutSample"][0]["headlineEventFamilies"], ["geopolitical-agreement", "macro-rates"])
        self.assertEqual(action["headlineFamilyFanoutSample"][0]["marketActorSets"], [["iran", "us"], ["iran", "israel"]])
        self.assertEqual(action["mappingRefinementQualityCounts"], {"reject-spread-and-ambiguous-fanout": 1})
        self.assertFalse(action["writesOrders"])
        self.assertFalse(action["touchesBroker"])
        self.assertTrue(payload["gateSnapshot"]["predictionEventLagManualReview"]["present"])
        self.assertEqual(payload["gateSnapshot"]["predictionEventLagManualReview"]["decisionCounts"], {"reject-paper": 1})
        self.assertEqual(payload["gateSnapshot"]["predictionEventMarketMapping"]["ambiguousHeadlineCount"], 1)
        self.assertIn("ambiguous-headline-event-family-fanout", payload["gateSnapshot"]["predictionEventMarketMapping"]["blockers"])
        self.assertEqual(payload["gateSnapshot"]["predictionEventMappingRefinement"]["mappingQualityCounts"], {"reject-spread-and-ambiguous-fanout": 1})

    def test_rejected_cot_filter_is_not_requeued_as_same_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"
            open_session = tmp_path / "open-session.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            seeds.write_text(json.dumps({"nextBuildQueue": []}))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({"freshForWeeklyResearch": True, "latestReportDate": "2026-05-26"}))
            cot.write_text(json.dumps({
                "summary": {
                    "decision": "research-only-no-positive-full-sample-improvement",
                    "promotionGate": "No promotion from this artifact.",
                }
            }))
            category.write_text(json.dumps({"readyForPaper": False, "writesOrders": False, "nextTests": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            alpha_frontier.write_text(json.dumps({"frontier": []}))
            open_session.write_text(json.dumps({}))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
                open_session_data_proof=str(open_session),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertIn("cot-positioning-filter-current-form-rejected", by_id)
        self.assertNotIn("cot-regime-filter-research", " ".join(by_id["cot-positioning-filter-current-form-rejected"]["commands"]))
        self.assertNotIn("cftc-tff-positioning-regime-filter", by_id)
        self.assertTrue(by_id["cot-positioning-filter-current-form-rejected"]["researchOnly"])
        self.assertFalse(by_id["cot-positioning-filter-current-form-rejected"]["writesOrders"])

    def test_degraded_youtube_run_suppresses_same_transcript_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"
            open_session = tmp_path / "open-session.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            seeds.write_text(json.dumps({
                "queuedYouTubeResearcherTargets": [
                    {"id": "youtube-queue-a", "kind": "youtube-transcript", "videos": ["https://youtu.be/a"]},
                    {"id": "youtube-queue-b", "kind": "youtube-transcript", "videos": ["https://youtu.be/b"]},
                ],
                "queuedYouTubeLatestRun": {
                    "present": True,
                    "runId": "run-test",
                    "status": "degraded",
                    "chunksCollected": 0,
                    "strategyHypothesesCount": 0,
                    "blockers": ["Selected researcher targets yielded no novel chunks in the latest run."],
                    "targetResults": [
                        {"targetId": "youtube-queue-a", "videosProcessed": 1, "collected": 0, "kept": 0},
                        {"targetId": "youtube-queue-b", "videosProcessed": 1, "collected": 0, "kept": 0},
                    ],
                },
                "nextBuildQueue": [],
            }))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({"freshForWeeklyResearch": False}))
            cot.write_text(json.dumps({}))
            category.write_text(json.dumps({"readyForPaper": False, "writesOrders": False, "nextTests": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            alpha_frontier.write_text(json.dumps({"frontier": []}))
            open_session.write_text(json.dumps({}))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
                open_session_data_proof=str(open_session),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertNotIn("seed-extract-queued-youtube-transcripts", by_id)
        self.assertIn("seed-refresh-youtube-target-list", by_id)
        self.assertEqual(by_id["seed-refresh-youtube-target-list"]["sampleTargetIds"], ["youtube-queue-a", "youtube-queue-b"])
        self.assertEqual(by_id["seed-refresh-youtube-target-list"]["latestRun"]["runId"], "run-test")
        self.assertIn("npm run --silent bill:research-seed-target-refresh-plan", by_id["seed-refresh-youtube-target-list"]["commands"])
        self.assertFalse(by_id["seed-refresh-youtube-target-list"]["writesOrders"])
        self.assertFalse(by_id["seed-refresh-youtube-target-list"]["touchesBroker"])

    def test_reviewed_youtube_frontier_suppresses_redundant_transcript_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"
            open_session = tmp_path / "open-session.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            seeds.write_text(json.dumps({
                "queuedYouTubeResearcherTargets": [
                    {"id": "youtube-queue-pead", "kind": "youtube-transcript", "videos": ["https://youtu.be/EP4ptjamPYA"]}
                ],
                "nextBuildQueue": [],
            }))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({}))
            cot.write_text(json.dumps({}))
            category.write_text(json.dumps({"nextTests": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            alpha_frontier.write_text(json.dumps({
                "frontier": [
                    {
                        "id": "futures-youtube-pead-earnings-regime-overlay",
                        "lane": "futures",
                        "priority": 27,
                        "oneVariable": "top-component earnings regime flag",
                        "hypothesis": "reviewed source card exists",
                        "commands": ["npm run --silent bill:alpha-frontier-queue"],
                        "promotionGate": "research-only",
                        "blockedBy": ["youtube-source-is-hypothesis-only"],
                        "researchOnly": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                    }
                ]
            }))
            open_session.write_text(json.dumps({}))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
                open_session_data_proof=str(open_session),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertIn("futures-youtube-pead-earnings-regime-overlay", by_id)
        self.assertNotIn("seed-extract-queued-youtube-transcripts", by_id)
        self.assertFalse(by_id["futures-youtube-pead-earnings-regime-overlay"]["writesOrders"])
        self.assertFalse(by_id["futures-youtube-pead-earnings-regime-overlay"]["touchesBroker"])

    def test_reviewed_youtube_frontier_still_surfaces_zero_yield_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"
            open_session = tmp_path / "open-session.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            seeds.write_text(json.dumps({
                "queuedYouTubeResearcherTargets": [
                    {"id": "youtube-queue-pead", "kind": "youtube-transcript", "videos": ["https://youtu.be/EP4ptjamPYA"]}
                ],
                "queuedYouTubeLatestRun": {
                    "present": True,
                    "runId": "run-zero",
                    "status": "degraded",
                    "chunksCollected": 0,
                    "strategyHypothesesCount": 0,
                    "targetResults": [
                        {"targetId": "youtube-queue-pead", "videosProcessed": 1, "collected": 0, "kept": 0}
                    ],
                },
                "nextBuildQueue": [],
            }))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({}))
            cot.write_text(json.dumps({}))
            category.write_text(json.dumps({"nextTests": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            alpha_frontier.write_text(json.dumps({
                "frontier": [
                    {
                        "id": "futures-youtube-pead-earnings-regime-overlay",
                        "researchOnly": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                    }
                ]
            }))
            open_session.write_text(json.dumps({}))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
                open_session_data_proof=str(open_session),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertIn("seed-refresh-youtube-target-list", by_id)
        self.assertNotIn("seed-extract-queued-youtube-transcripts", by_id)
        self.assertEqual(by_id["seed-refresh-youtube-target-list"]["latestRun"]["runId"], "run-zero")
        self.assertFalse(by_id["seed-refresh-youtube-target-list"]["writesOrders"])
        self.assertFalse(by_id["seed-refresh-youtube-target-list"]["touchesBroker"])

    def test_cot_no_edge_memory_suppresses_current_form_positioning_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            futures_no_edge = tmp_path / "futures-no-edge.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            seeds.write_text(json.dumps({"nextBuildQueue": []}))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({"freshForWeeklyResearch": True, "latestReportDate": "2026-05-26"}))
            cot.write_text(json.dumps({
                "summary": {
                    "decision": "research-only-no-positive-full-sample-improvement",
                    "promotionGate": "No promotion from this artifact.",
                }
            }))
            futures_no_edge.write_text(json.dumps({
                "entries": [
                    {"id": "cot-tff-regime-filter-current-backtrader-set", "verdict": "no-edge"}
                ]
            }))
            category.write_text(json.dumps({"readyForPaper": False, "writesOrders": False, "nextTests": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            alpha_frontier.write_text(json.dumps({"frontier": []}))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                futures_no_edge=str(futures_no_edge),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertNotIn("cot-positioning-filter-current-form-rejected", by_id)
        self.assertNotIn("cftc-tff-positioning-regime-filter", by_id)

    def test_prediction_news_alpha_action_includes_forward_capture_when_pre_windows_are_unrecoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            futures_no_edge = tmp_path / "futures-no-edge.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"
            capture_targets = tmp_path / "capture-targets.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            seeds.write_text(json.dumps({"nextBuildQueue": []}))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({"freshForWeeklyResearch": True, "latestReportDate": "2026-05-26"}))
            cot.write_text(json.dumps({}))
            futures_no_edge.write_text(json.dumps({"entries": []}))
            category.write_text(json.dumps({"readyForPaper": False, "writesOrders": False, "nextTests": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            alpha_frontier.write_text(json.dumps({
                "frontier": [{
                    "id": "prediction-news-first-event-lag-study",
                    "lane": "prediction-markets",
                    "priority": 34,
                    "oneVariable": "news-to-market lag feature",
                    "hypothesis": "news should lead prediction repricing",
                    "commands": [
                        "npm run --silent bill:prediction-event-clob-capture-targets",
                        "npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15 --max-output-mb 128 --min-free-gb 20",
                    ],
                }]
            }))
            forward_command = "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --max-assets 20 --max-output-mb 128 --min-free-gb 20 --terms 'fed,iran'"
            capture_targets.write_text(json.dumps({
                "forwardCapturePlan": {
                    "required": True,
                    "reason": "past headlines cannot recover pre-event windows",
                    "command": forward_command,
                },
                "unrecoverablePreEventTargetCount": 15,
                "preEventRecoverableTargetCount": 0,
            }))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                futures_no_edge=str(futures_no_edge),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
                prediction_event_clob_targets=str(capture_targets),
            ))

        action = {item["id"]: item for item in payload["actions"]}["prediction-news-first-event-lag-study"]
        self.assertIn(forward_command, action["commands"])
        self.assertEqual(action["firstCommand"], "npm run --silent bill:prediction-event-clob-capture-targets")
        self.assertTrue(action["forwardCapturePlan"]["required"])
        self.assertEqual(action["forwardCapturePlan"]["unrecoverablePreEventTargetCount"], 15)
        self.assertIn("Forward capture is required", action["commandHint"])

    def test_narrow_no_edge_memory_forces_single_variable_category_retest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({
                "decision": "research-only",
                "resolvedOutcomeReview": {"decision": "research-only"},
                "nextTests": [
                    {
                        "id": "narrow-cross-venue-normalization",
                        "oneVariable": "market universe",
                        "hypothesis": "narrowing may help",
                    }
                ],
            }))
            seeds.write_text(json.dumps({"nextBuildQueue": []}))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({"freshForWeeklyResearch": False}))
            cot.write_text(json.dumps({}))
            category.write_text(json.dumps({
                "readyForPaper": False,
                "writesOrders": False,
                "nextTests": [
                    {"id": "crypto-narrow-scan", "category": "crypto", "oneVariable": "market universe", "marketCount": 101},
                    {"id": "macro-rates-narrow-scan", "category": "macro-rates", "oneVariable": "line parser", "marketCount": 111},
                ],
            }))
            prediction_no_edge.write_text(json.dumps({
                "entries": [
                    {
                        "id": "narrow-category-cross-venue-current-universe",
                        "verdict": "needs-more-data",
                        "nextAction": "Retest only one category/parser variable at a time, starting with crypto settlement horizon.",
                        "evidence": {
                            "categoryRejectReasons": {
                                "crypto": {"temporal-mismatch": 39}
                            }
                        },
                    }
                ]
            }))
            alpha_frontier.write_text(json.dumps({"frontier": []}))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertIn("crypto-settlement-horizon-parser-retest", by_id)
        self.assertNotIn("narrow-cross-venue-normalization", by_id)
        action = by_id["crypto-settlement-horizon-parser-retest"]
        self.assertEqual(action["replacesTestId"], "narrow-cross-venue-normalization")
        self.assertEqual(action["selectedCategory"], "crypto")
        self.assertEqual(action["oneVariable"], "settlement horizon parser")
        self.assertIn("npm run --silent bill:prediction-narrow-scan -- --category crypto", action["commands"])
        self.assertFalse(action["writesOrders"])
        self.assertTrue(action["researchOnly"])

    def test_crypto_rejected_memory_moves_single_variable_retest_to_macro_rates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({
                "decision": "research-only",
                "resolvedOutcomeReview": {"decision": "research-only"},
                "nextTests": [
                    {
                        "id": "narrow-cross-venue-normalization",
                        "oneVariable": "market universe",
                        "hypothesis": "narrowing may help",
                    }
                ],
            }))
            seeds.write_text(json.dumps({"nextBuildQueue": []}))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({"freshForWeeklyResearch": False}))
            cot.write_text(json.dumps({}))
            category.write_text(json.dumps({
                "readyForPaper": False,
                "writesOrders": False,
                "nextTests": [
                    {"id": "crypto-narrow-scan", "category": "crypto", "oneVariable": "settlement horizon", "marketCount": 101},
                    {"id": "macro-rates-narrow-scan", "category": "macro-rates", "oneVariable": "line parser", "marketCount": 111},
                ],
            }))
            prediction_no_edge.write_text(json.dumps({
                "entries": [
                    {
                        "id": "narrow-category-cross-venue-current-universe",
                        "verdict": "needs-more-data",
                        "nextAction": "Retest only one category/parser variable at a time, starting with crypto settlement horizon or macro/rates line parsing.",
                        "evidence": {
                            "categoryRejectReasons": {
                                "crypto": {"temporal-mismatch": 39},
                                "macro-rates": {"line-mismatch": 2891},
                            }
                        },
                    },
                    {
                        "id": "crypto-settlement-horizon-parser-current-form",
                        "verdict": "no-edge",
                    },
                ]
            }))
            alpha_frontier.write_text(json.dumps({"frontier": []}))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertNotIn("crypto-settlement-horizon-parser-retest", by_id)
        self.assertIn("macro-rates-line-parser-retest", by_id)
        action = by_id["macro-rates-line-parser-retest"]
        self.assertEqual(action["selectedCategory"], "macro-rates")
        self.assertEqual(action["oneVariable"], "rates line parser")
        self.assertIn("npm run --silent bill:prediction-narrow-scan -- --category macro-rates", action["commands"])
        self.assertEqual(action["previousVariableRejected"], "crypto-settlement-horizon-parser-current-form rejected")
        self.assertFalse(action["writesOrders"])
        self.assertTrue(action["researchOnly"])

    def test_rejected_crypto_and_macro_current_forms_stop_generic_narrow_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({
                "decision": "research-only",
                "resolvedOutcomeReview": {"decision": "research-only"},
                "nextTests": [
                    {
                        "id": "narrow-cross-venue-normalization",
                        "oneVariable": "market universe",
                        "hypothesis": "narrowing may help",
                    }
                ],
            }))
            seeds.write_text(json.dumps({"nextBuildQueue": []}))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({"freshForWeeklyResearch": False}))
            cot.write_text(json.dumps({}))
            category.write_text(json.dumps({
                "readyForPaper": False,
                "writesOrders": False,
                "nextTests": [
                    {"id": "crypto-narrow-scan", "category": "crypto", "oneVariable": "settlement horizon", "marketCount": 101},
                    {"id": "macro-rates-narrow-scan", "category": "macro-rates", "oneVariable": "line parser", "marketCount": 111},
                ],
            }))
            prediction_no_edge.write_text(json.dumps({
                "entries": [
                    {
                        "id": "narrow-category-cross-venue-current-universe",
                        "verdict": "needs-more-data",
                        "nextAction": "Retest only one category/parser variable at a time.",
                        "evidence": {"categoryRejectReasons": {}},
                    },
                    {"id": "crypto-settlement-horizon-parser-current-form", "verdict": "no-edge"},
                    {"id": "macro-rates-line-parser-current-form", "verdict": "no-edge"},
                ]
            }))
            alpha_frontier.write_text(json.dumps({"frontier": []}))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        self.assertIn("narrow-cross-venue-current-universe-current-form-rejected", by_id)
        self.assertNotIn("crypto-settlement-horizon-parser-retest", by_id)
        self.assertNotIn("macro-rates-line-parser-retest", by_id)
        action = by_id["narrow-cross-venue-current-universe-current-form-rejected"]
        self.assertEqual(action["priority"], 39)
        self.assertEqual(action["actionKind"], "no-edge-maintenance")
        self.assertEqual(action["oneVariable"], "current narrow universe")
        self.assertEqual(action["selectedCategory"], "none-current-form-rejected")
        self.assertEqual(action["commands"], [
            "npm run --silent bill:prediction-no-edge-ledger",
            "npm run --silent bill:prediction-evidence-triage",
        ])
        self.assertFalse(action["writesOrders"])
        self.assertTrue(action["researchOnly"])

    def test_alpha_frontier_items_enter_research_queue_without_execution_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            futures = tmp_path / "futures.json"
            prediction = tmp_path / "prediction.json"
            seeds = tmp_path / "seeds.json"
            live = tmp_path / "live.json"
            data = tmp_path / "data.json"
            futures_quality = tmp_path / "futures-quality.json"
            worktree = tmp_path / "worktree.json"
            cftc = tmp_path / "cftc.json"
            cot = tmp_path / "cot.json"
            futures_no_edge = tmp_path / "futures-no-edge.json"
            category = tmp_path / "category.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            alpha_frontier = tmp_path / "alpha-frontier.json"

            futures.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            prediction.write_text(json.dumps({"decision": "research-only", "nextTests": []}))
            seeds.write_text(json.dumps({"nextBuildQueue": []}))
            live.write_text(json.dumps({"readyForLive": False, "readyForDemoExpansion": False, "blockers": []}))
            data.write_text(json.dumps({"verdict": "STALE", "action": "block_all_trades"}))
            futures_quality.write_text(json.dumps({"pass": True, "datasets": [], "failingDatasets": []}))
            worktree.write_text(json.dumps({"sourceCleanBlockers": []}))
            cftc.write_text(json.dumps({"freshForWeeklyResearch": False}))
            cot.write_text(json.dumps({}))
            futures_no_edge.write_text(json.dumps({"entries": []}))
            category.write_text(json.dumps({"readyForPaper": False, "writesOrders": False, "nextTests": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            alpha_frontier.write_text(json.dumps({
                "frontier": [
                    {
                        "id": "prediction-btc-updown-resolved-feature-oos",
                        "lane": "prediction-markets",
                        "priority": 30,
                        "oneVariable": "resolved labeled corpus",
                        "hypothesis": "offline resolved labels",
                        "commands": ["npm run --silent bill:alpha-frontier-queue"],
                        "promotionGate": "must pass walk-forward",
                        "blockedBy": ["current broad scan rejected"],
                        "dataAvailable": True,
                        "dataPaths": ["/tmp/btc.parquet"],
                        "researchSteps": ["Build an offline walk-forward evaluator before promotion review."],
                    }
                ]
            }))

            payload = build_actions(argparse.Namespace(
                futures_triage=str(futures),
                prediction_triage=str(prediction),
                research_seed_triage=str(seeds),
                live_readiness=str(live),
                data_freshness=str(data),
                futures_data_quality=str(futures_quality),
                worktree=str(worktree),
                cftc_positioning=str(cftc),
                cot_regime_filter=str(cot),
                futures_no_edge=str(futures_no_edge),
                prediction_category_drilldown=str(category),
                prediction_no_edge=str(prediction_no_edge),
                alpha_frontier=str(alpha_frontier),
            ))

        by_id = {item["id"]: item for item in payload["actions"]}
        action = by_id["prediction-btc-updown-resolved-feature-oos"]
        self.assertEqual(action["sourceArtifact"], ".rumbling-hedge/state/alpha-frontier-queue.latest.json")
        self.assertEqual(action["oneVariable"], "resolved labeled corpus")
        self.assertTrue(action["dataAvailable"])
        self.assertFalse(action["writesOrders"])
        self.assertTrue(action["researchOnly"])
        self.assertTrue(action["operatorApprovalRequiredBeforeExecution"])
        self.assertEqual(action["researchSteps"], ["Build an offline walk-forward evaluator before promotion review."])
        self.assertIn("Manual one-variable research step required", action["commandHint"])
        self.assertNotEqual(action["commandHint"], "missing")


if __name__ == "__main__":
    unittest.main()
