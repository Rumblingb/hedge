import argparse
import tempfile
import unittest
from pathlib import Path

from scripts.bill_research_closed_loop_contract import build_contract, build_prompt_to_artifact_checklist


class BillResearchClosedLoopContractTest(unittest.TestCase):
    def test_checklist_keeps_research_and_execution_separate(self):
        checklist = build_prompt_to_artifact_checklist()
        steps = [item["step"] for item in checklist]

        self.assertIn("out-of-sample-proof", steps)
        self.assertIn("execution-separation", steps)
        self.assertTrue(any("never submit orders" in item["acceptance"] for item in checklist))

    def test_missing_inputs_remain_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.jsonl"
            args = argparse.Namespace(
                futures_triage="/missing/futures.json",
                prediction_triage="/missing/prediction.json",
                prediction_drilldown="/missing/drilldown.json",
                prediction_narrow_scan="/missing/narrow-scan.json",
                prediction_resolved_join="/missing/resolved-join.json",
                live_readiness="/missing/live.json",
                alpha_tooling="/missing/tooling.json",
                worktree="/missing/worktree.json",
                strategy_zoo="/missing/zoo.json",
                futures_no_edge="/missing/futures-no-edge.json",
                strategy_feed="/missing/strategy-feed.json",
                resource_manifest=str(manifest),
            )

            contract = build_contract(args)

        self.assertTrue(contract["researchOnly"])
        self.assertFalse(contract["writesOrders"])
        self.assertFalse(contract["readyForExecution"])
        self.assertFalse(contract["resourceMemory"]["fullManifestExists"])
        self.assertFalse(contract["executionBoundary"]["llmMayRoute"])
        self.assertEqual(contract["researchStrategyFeed"]["allowedDirectives"], 0)
        self.assertEqual(contract["researchStrategyFeed"]["blockedDirectives"], 0)

    def test_contract_surfaces_no_edge_blocked_strategy_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "manifest.jsonl"
            strategy_feed = tmp_path / "strategy-feed.json"
            strategy_feed.write_text(
                """{
                  "directives": [],
                  "blockedDirectiveCount": 2,
                  "directiveBlockReason": "all machine-testable directive candidates are blocked by no-edge/non-promotable memory",
                  "blockedDirectives": [
                    {"strategyId": "ict-displacement"},
                    {"strategyId": "session-momentum"}
                  ]
                }"""
            )
            args = argparse.Namespace(
                futures_triage="/missing/futures.json",
                prediction_triage="/missing/prediction.json",
                prediction_drilldown="/missing/drilldown.json",
                prediction_narrow_scan="/missing/narrow-scan.json",
                prediction_resolved_join="/missing/resolved-join.json",
                live_readiness="/missing/live.json",
                alpha_tooling="/missing/tooling.json",
                worktree="/missing/worktree.json",
                strategy_zoo="/missing/zoo.json",
                futures_no_edge="/missing/futures-no-edge.json",
                strategy_feed=str(strategy_feed),
                resource_manifest=str(manifest),
            )

            contract = build_contract(args)

        self.assertEqual(contract["researchStrategyFeed"]["allowedDirectives"], 0)
        self.assertEqual(contract["researchStrategyFeed"]["blockedDirectives"], 2)
        self.assertIn("ict-displacement", contract["researchStrategyFeed"]["blockedStrategies"])
        self.assertIn("no-edge", contract["researchStrategyFeed"]["directiveBlockReason"])

    def test_strategy_catalog_preserves_zero_gold_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "manifest.jsonl"
            zoo = tmp_path / "zoo.json"
            zoo.write_text(
                """{
                  "counts": {
                    "total": 59,
                    "classification:SKELETON": 51,
                    "classification:BRONZE": 3,
                    "classification:QUARANTINED": 5
                  }
                }"""
            )
            args = argparse.Namespace(
                futures_triage="/missing/futures.json",
                prediction_triage="/missing/prediction.json",
                prediction_drilldown="/missing/drilldown.json",
                prediction_narrow_scan="/missing/narrow-scan.json",
                prediction_resolved_join="/missing/resolved-join.json",
                live_readiness="/missing/live.json",
                alpha_tooling="/missing/tooling.json",
                worktree="/missing/worktree.json",
                strategy_zoo=str(zoo),
                futures_no_edge="/missing/futures-no-edge.json",
                strategy_feed="/missing/strategy-feed.json",
                resource_manifest=str(manifest),
            )

            contract = build_contract(args)

        self.assertEqual(contract["strategyCatalog"]["total"], 59)
        self.assertEqual(contract["strategyCatalog"]["gold"], 0)

    def test_contract_surfaces_prediction_narrow_snapshot_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "manifest.jsonl"
            drilldown = tmp_path / "drilldown.json"
            drilldown.write_text(
                """{
                  "nextTests": [{"id": "crypto-narrow-scan"}],
                  "narrowSnapshots": [
                    {
                      "category": "crypto",
                      "path": "/tmp/crypto.json",
                      "marketCount": 44,
                      "researchOnly": true,
                      "writesOrders": false,
                      "nextTestId": "crypto-narrow-scan"
                    }
                  ]
                }"""
            )
            args = argparse.Namespace(
                futures_triage="/missing/futures.json",
                prediction_triage="/missing/prediction.json",
                prediction_drilldown=str(drilldown),
                prediction_narrow_scan="/missing/narrow-scan.json",
                prediction_resolved_join="/missing/resolved-join.json",
                live_readiness="/missing/live.json",
                alpha_tooling="/missing/tooling.json",
                worktree="/missing/worktree.json",
                strategy_zoo="/missing/zoo.json",
                futures_no_edge="/missing/futures-no-edge.json",
                strategy_feed="/missing/strategy-feed.json",
                resource_manifest=str(manifest),
            )

            contract = build_contract(args)

        snapshots = contract["predictionMarkets"]["narrowSnapshots"]
        self.assertEqual(snapshots[0]["category"], "crypto")
        self.assertEqual(snapshots[0]["marketCount"], 44)
        self.assertTrue(snapshots[0]["researchOnly"])
        self.assertFalse(snapshots[0]["writesOrders"])

    def test_contract_surfaces_prediction_narrow_scan_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "manifest.jsonl"
            narrow_scan = tmp_path / "narrow-scan.json"
            narrow_scan.write_text(
                """{
                  "researchOnly": true,
                  "writesOrders": false,
                  "readyForPaper": false,
                  "summary": {
                    "categoryCount": 1,
                    "paperCandidates": 0,
                    "watchCandidates": 0,
                    "viablePairs": 0,
                    "repairableNearMisses": 1
                  },
                  "reports": [
                    {
                      "category": "crypto",
                      "status": "ok",
                      "snapshotMarketCount": 44,
                      "journalPath": "/tmp/crypto.opportunities.jsonl"
                    }
                  ]
                }"""
            )
            args = argparse.Namespace(
                futures_triage="/missing/futures.json",
                prediction_triage="/missing/prediction.json",
                prediction_drilldown="/missing/drilldown.json",
                prediction_narrow_scan=str(narrow_scan),
                prediction_resolved_join="/missing/resolved-join.json",
                live_readiness="/missing/live.json",
                alpha_tooling="/missing/tooling.json",
                worktree="/missing/worktree.json",
                strategy_zoo="/missing/zoo.json",
                futures_no_edge="/missing/futures-no-edge.json",
                strategy_feed="/missing/strategy-feed.json",
                resource_manifest=str(manifest),
            )

            contract = build_contract(args)

        scan = contract["predictionMarkets"]["narrowScan"]
        self.assertEqual(scan["categoryCount"], 1)
        self.assertEqual(scan["paperCandidates"], 0)
        self.assertEqual(scan["repairableNearMisses"], 1)
        self.assertEqual(scan["reports"][0]["snapshotMarketCount"], 44)
        self.assertFalse(scan["readyForPaper"])

    def test_contract_surfaces_resolved_outcome_subject_specific_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "manifest.jsonl"
            resolved_join = tmp_path / "resolved-join.json"
            resolved_join.write_text(
                """{
                  "historicalRowsLoaded": 100,
                  "statusCounts": {"joined-research-only": 1},
                  "joinedResearchOnlyCount": 1,
                  "minSpecificMatches": 5,
                  "readyForPaper": false,
                  "items": [
                    {
                      "externalId": "arg-2026",
                      "status": "joined-research-only",
                      "resolvedMatchCount": 312,
                      "subjectSpecificMatchCount": 14,
                      "subjectSpecificWinRate": 0.571429
                    }
                  ]
                }"""
            )
            args = argparse.Namespace(
                futures_triage="/missing/futures.json",
                prediction_triage="/missing/prediction.json",
                prediction_drilldown="/missing/drilldown.json",
                prediction_narrow_scan="/missing/narrow-scan.json",
                prediction_resolved_join=str(resolved_join),
                live_readiness="/missing/live.json",
                alpha_tooling="/missing/tooling.json",
                worktree="/missing/worktree.json",
                strategy_zoo="/missing/zoo.json",
                futures_no_edge="/missing/futures-no-edge.json",
                strategy_feed="/missing/strategy-feed.json",
                resource_manifest=str(manifest),
            )

            contract = build_contract(args)

        resolved = contract["predictionMarkets"]["resolvedOutcomeJoin"]
        self.assertEqual(resolved["historicalRowsLoaded"], 100)
        self.assertEqual(resolved["minSpecificMatches"], 5)
        self.assertEqual(resolved["subjectSpecific"][0]["resolvedMatchCount"], 312)
        self.assertEqual(resolved["subjectSpecific"][0]["subjectSpecificMatchCount"], 14)
        self.assertFalse(resolved["readyForPaper"])

    def test_contract_surfaces_resolved_outcome_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "manifest.jsonl"
            prediction = tmp_path / "prediction.json"
            prediction.write_text(
                """{
                  "resolvedOutcomeReview": {
                    "status": "research-only",
                    "decision": "do-not-promote-resolved-history-without-paper-review-and-fillability",
                    "broadPriorRisk": "high",
                    "readyForPaper": false,
                    "items": [
                      {
                        "externalId": "558938",
                        "decision": "context-only-not-paper"
                      }
                    ],
                    "requiredNextEvidence": [
                      "paper-ready review",
                      "fillability"
                    ]
                  }
                }"""
            )
            args = argparse.Namespace(
                futures_triage="/missing/futures.json",
                prediction_triage=str(prediction),
                prediction_drilldown="/missing/drilldown.json",
                prediction_narrow_scan="/missing/narrow-scan.json",
                prediction_resolved_join="/missing/resolved-join.json",
                live_readiness="/missing/live.json",
                alpha_tooling="/missing/tooling.json",
                worktree="/missing/worktree.json",
                strategy_zoo="/missing/zoo.json",
                futures_no_edge="/missing/futures-no-edge.json",
                strategy_feed="/missing/strategy-feed.json",
                resource_manifest=str(manifest),
            )

            contract = build_contract(args)

        review = contract["predictionMarkets"]["resolvedOutcomeReview"]
        self.assertEqual(review["status"], "research-only")
        self.assertEqual(
            review["decision"],
            "do-not-promote-resolved-history-without-paper-review-and-fillability",
        )
        self.assertEqual(review["broadPriorRisk"], "high")
        self.assertEqual(review["items"][0]["decision"], "context-only-not-paper")
        self.assertFalse(review["readyForPaper"])

    def test_contract_surfaces_research_seed_triage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "manifest.jsonl"
            seed_triage = tmp_path / "seed-triage.json"
            seed_target_refresh = tmp_path / "seed-target-refresh.json"
            next_actions = tmp_path / "next-actions.json"
            seed_triage.write_text(
                """{
                  "researchOnly": true,
                  "writesOrders": false,
                  "readyForExecution": false,
                  "summary": {
                    "totalSeeds": 31,
                    "machineTestableSeeds": 27,
                    "candidateRetestSeeds": 1,
                    "quarantinedNoEdgeSeeds": 24,
                    "unmappedSeeds": 6,
                    "duplicateSourceIds": 2,
                    "executableSeeds": 0
                  },
                  "nextBuildQueue": [
                    {
                      "id": "seed-a#2",
                      "sourceId": "seed-a",
                      "title": "Trend momentum seed",
                      "inferredStrategyId": "wq-trend-mom",
                      "decision": "candidate-retest-research-only",
                      "machineTestable": true,
                      "localExecutable": false,
                      "blockers": ["requires fresh local OOS"],
                      "nextAction": "Run one-variable local replay."
                    }
                  ],
                  "hardRules": ["YT/paper/web 'gold' is a source label, not edge evidence."]
                }"""
            )
            next_actions.write_text(
                """{
                  "researchOnly": true,
                  "writesOrders": false,
                  "readyForExecution": false,
                  "actions": [
                    {
                      "id": "control-plane-clearance-before-demo",
                      "lane": "control-plane",
                      "priority": 1,
                      "commands": ["npm run --silent bill:worktree-consolidation || true"],
                      "promotionGate": "demo/live remains blocked until blockers are empty"
                    }
                  ]
                }"""
            )
            seed_target_refresh.write_text(
                """{
                  "decision": "refresh-required-current-targets-exhausted",
                  "researchOnly": true,
                  "writesOrders": false,
                  "touchesBroker": false,
                  "readyForExecution": false,
                  "summary": {
                    "queuedTargetCount": 2,
                    "retireOrManualConvertCount": 2,
                    "rerunnableTargetCount": 0,
                    "zeroYieldSameTargets": true
                  },
                  "latestQueuedRun": {
                    "runId": "run-test",
                    "status": "degraded",
                    "chunksCollected": 0,
                    "strategyHypothesesCount": 0,
                    "blockers": ["Selected researcher targets yielded no novel chunks in the latest run."]
                  },
                  "targetDecisions": [
                    {
                      "targetId": "youtube-queue-a",
                      "action": "retire-or-manual-convert",
                      "rerunAllowed": false,
                      "reason": "same queued target already produced zero chunks and zero strategy hypotheses"
                    },
                    {
                      "targetId": "youtube-queue-b",
                      "action": "retire-or-manual-convert",
                      "rerunAllowed": false,
                      "reason": "same queued target already produced zero chunks and zero strategy hypotheses"
                    }
                  ],
                  "newTargetRequirements": ["futures or prediction-market source only"]
                }"""
            )
            args = argparse.Namespace(
                futures_triage="/missing/futures.json",
                prediction_triage="/missing/prediction.json",
                prediction_drilldown="/missing/drilldown.json",
                prediction_narrow_scan="/missing/narrow-scan.json",
                prediction_resolved_join="/missing/resolved-join.json",
                live_readiness="/missing/live.json",
                alpha_tooling="/missing/tooling.json",
                worktree="/missing/worktree.json",
                strategy_zoo="/missing/zoo.json",
                futures_no_edge="/missing/futures-no-edge.json",
                strategy_feed="/missing/strategy-feed.json",
                research_seed_triage=str(seed_triage),
                research_seed_target_refresh=str(seed_target_refresh),
                next_research_actions=str(next_actions),
                resource_manifest=str(manifest),
            )

            contract = build_contract(args)

        triage = contract["researchSeedTriage"]
        self.assertEqual(triage["totalSeeds"], 31)
        self.assertEqual(triage["candidateRetestSeeds"], 1)
        self.assertEqual(triage["duplicateSourceIds"], 2)
        self.assertEqual(triage["executableSeeds"], 0)
        self.assertFalse(triage["writesOrders"])
        self.assertEqual(triage["nextBuildQueue"][0]["sourceId"], "seed-a")
        actions = contract["nextResearchActions"]
        self.assertEqual(actions["actionCount"], 1)
        self.assertEqual(actions["topActions"][0]["id"], "control-plane-clearance-before-demo")
        self.assertFalse(actions["writesOrders"])

    def test_contract_uses_current_queue_shape_and_surfaces_degraded_youtube_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest = tmp_path / "manifest.jsonl"
            seed_triage = tmp_path / "seed-triage.json"
            seed_target_refresh = tmp_path / "seed-target-refresh.json"
            next_actions = tmp_path / "next-actions.json"
            seed_triage.write_text(
                """{
                  "researchOnly": true,
                  "writesOrders": false,
                  "readyForExecution": false,
                  "summary": {
                    "totalSeeds": 35,
                    "machineTestableSeeds": 28,
                    "candidateRetestSeeds": 0,
                    "quarantinedNoEdgeSeeds": 26,
                    "unmappedSeeds": 6,
                    "duplicateSourceIds": 13,
                    "executableSeeds": 0,
                    "queuedYouTubeSeeds": 3
                  },
                  "queuedYouTubeResearcherTargets": [
                    {"id": "youtube-queue-a"},
                    {"id": "youtube-queue-b"}
                  ],
                  "queuedYouTubeLatestRun": {
                    "present": true,
                    "runId": "run-test",
                    "status": "degraded",
                    "targetsAttempted": 2,
                    "targetsSucceeded": 2,
                    "chunksCollected": 0,
                    "strategyHypothesesCount": 0,
                    "blockers": ["Selected researcher targets yielded no novel chunks in the latest run."]
                  },
                  "nextBuildQueue": []
                }"""
            )
            next_actions.write_text(
                """{
                  "researchOnly": true,
                  "writesOrders": false,
                  "readyForExecution": false,
                  "queue": [
                    {
                      "id": "seed-refresh-youtube-target-list",
                      "lane": "research-seeds",
                      "priority": 49,
                      "firstCommand": "npm run --silent bill:research-seed-triage",
                      "commandHint": "Refresh target list before rerunning researcher-run",
                      "researchOnly": true,
                      "writesOrders": false,
                      "touchesBroker": false
                    }
                  ]
                }"""
            )
            seed_target_refresh.write_text(
                """{
                  "decision": "refresh-required-current-targets-exhausted",
                  "researchOnly": true,
                  "writesOrders": false,
                  "touchesBroker": false,
                  "readyForExecution": false,
                  "summary": {
                    "queuedTargetCount": 2,
                    "retireOrManualConvertCount": 2,
                    "rerunnableTargetCount": 0,
                    "zeroYieldSameTargets": true
                  },
                  "latestQueuedRun": {
                    "runId": "run-test",
                    "status": "degraded",
                    "chunksCollected": 0,
                    "strategyHypothesesCount": 0,
                    "blockers": ["Selected researcher targets yielded no novel chunks in the latest run."]
                  },
                  "targetDecisions": [
                    {
                      "targetId": "youtube-queue-a",
                      "action": "retire-or-manual-convert",
                      "rerunAllowed": false,
                      "reason": "same queued target already produced zero chunks and zero strategy hypotheses"
                    },
                    {
                      "targetId": "youtube-queue-b",
                      "action": "retire-or-manual-convert",
                      "rerunAllowed": false,
                      "reason": "same queued target already produced zero chunks and zero strategy hypotheses"
                    }
                  ],
                  "newTargetRequirements": ["futures or prediction-market source only"]
                }"""
            )
            args = argparse.Namespace(
                futures_triage="/missing/futures.json",
                prediction_triage="/missing/prediction.json",
                prediction_drilldown="/missing/drilldown.json",
                prediction_narrow_scan="/missing/narrow-scan.json",
                prediction_resolved_join="/missing/resolved-join.json",
                live_readiness="/missing/live.json",
                alpha_tooling="/missing/tooling.json",
                worktree="/missing/worktree.json",
                strategy_zoo="/missing/zoo.json",
                futures_no_edge="/missing/futures-no-edge.json",
                strategy_feed="/missing/strategy-feed.json",
                research_seed_triage=str(seed_triage),
                research_seed_target_refresh=str(seed_target_refresh),
                next_research_actions=str(next_actions),
                resource_manifest=str(manifest),
            )

            contract = build_contract(args)

        triage = contract["researchSeedTriage"]
        self.assertEqual(triage["queuedYouTubeSeeds"], 3)
        self.assertEqual(triage["queuedYouTubeTargetIds"], ["youtube-queue-a", "youtube-queue-b"])
        self.assertEqual(triage["queuedYouTubeLatestRun"]["status"], "degraded")
        self.assertEqual(triage["queuedYouTubeLatestRun"]["chunksCollected"], 0)
        self.assertEqual(triage["queuedYouTubeLatestRun"]["strategyHypothesesCount"], 0)
        refresh = contract["researchSeedTargetRefresh"]
        self.assertEqual(refresh["decision"], "refresh-required-current-targets-exhausted")
        self.assertEqual(refresh["retireOrManualConvertCount"], 2)
        self.assertEqual(refresh["rerunnableTargetCount"], 0)
        self.assertFalse(refresh["targetDecisions"][0]["rerunAllowed"])
        actions = contract["nextResearchActions"]
        self.assertEqual(actions["actionCount"], 1)
        self.assertEqual(actions["topActions"][0]["id"], "seed-refresh-youtube-target-list")
        self.assertEqual(actions["topActions"][0]["lane"], "research-seeds")
        self.assertFalse(actions["topActions"][0]["writesOrders"])


if __name__ == "__main__":
    unittest.main()
