import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.bill_source_hygiene_plan import HERMES, build_plan, default_markdown_path, render_markdown


class BillSourceHygienePlanTest(unittest.TestCase):
    def test_builds_read_only_reduction_plan_from_intake_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.json"
            data = tmp_path / "data.json"
            execution = tmp_path / "execution.json"
            worktree = tmp_path / "worktree.json"
            sibling = tmp_path / "sibling.json"
            source.write_text(json.dumps({
                "decision": "source-intake-visible-execution-locked",
                "sourceClean": False,
                "dirtyStatusCount": 11,
                "reviewBacklogCount": 10,
                "classificationCounts": {
                    "validated-research-scaffold": 2,
                    "quarantine-execution-live": 1,
                    "requires-review": 7,
                    "dependency-review": 2,
                    "obsidian-or-ops-review": 3,
                },
                "validationEvidence": {
                    "focusedSuite": ".venv/bin/python -m unittest tests.test_a -v",
                    "fullSuite": [
                        ".venv/bin/python -m unittest discover -s tests -p 'test_*.py'",
                        "npm run --silent test",
                    ],
                    "note": "focused tests passed",
                    "fullSuiteNote": "full tests passed",
                },
                "validatedResearchScaffold": [
                    {"path": "scripts/audit.py"},
                    {"path": "tests/test_audit.py"},
                ],
                "quarantineExecutionLiveFiles": [
                    {"path": "scripts/master_bridge.py"},
                ],
                "requiresReviewSamples": {
                    "requires-review": [{"path": "src/research/foo.ts"}],
                    "dependency-review": [{"path": "package-lock.json"}, {"path": "requirements.bill-alpha.txt"}],
                    "obsidian-or-ops-review": [{"path": "docs/plan.md"}],
                },
            }))
            data.write_text(json.dumps({
                "decision": "data-intake-visible-execution-locked",
                "dirtyDataFileCount": 2,
                "classificationCounts": {"research-refresh-current-window": 2},
                "riskCounts": {"research-only-current-window-not-execution-grade": 2},
                "items": [
                    {"relativePath": "data/free/NQ-1m-5d.csv"},
                    {"relativePath": "data/free/ES-1m-5d.csv"},
                ],
            }))
            execution.write_text(json.dumps({
                "decision": "execution-intake-visible-execution-locked",
                "allFirewallCommandsPassed": True,
                "uncoveredExecutionPaths": [],
                "classificationCounts": {"firewall-covered-still-quarantined": 1},
                "items": [{"relativePath": "scripts/master_bridge.py"}],
            }))
            worktree.write_text(json.dumps({
                "posture": "blocked",
                "sourceCleanBlockers": ["dirty execution-live files"],
                "clearanceQueue": [
                    {
                        "priority": 1,
                        "lane": "execution-live",
                        "dirtyFiles": 3,
                        "sampleFiles": ["scripts/master_bridge.py"],
                        "action": "keep quarantined",
                        "requiredEvidence": ["npm run --silent bill:verify-execution-quarantine"],
                    }
                ],
            }))
            sibling.write_text(json.dumps({
                "decision": "sibling-worktree-intake-visible-quarantine",
                "dirtySiblingWorktreeCount": 1,
                "dirtyFileCount": 4,
                "executionLiveDirtyCount": 2,
                "classificationCounts": {
                    "execution-live-quarantine": 2,
                    "strategy-research-review": 2,
                },
                "blockers": [
                    "dirty-sibling-worktree-requires-selective-intake",
                    "sibling-worktree-has-execution-live-dirty-files",
                ],
                "safeToMergeAutomatically": False,
                "worktrees": [
                    {
                        "path": "/Users/brain/worktrees/hedge-goal-live",
                        "topReviewFirst": [
                            "src/live/demoExecution.ts",
                            "scripts/master_bridge.py",
                        ],
                    }
                ],
            }))

            with patch("scripts.bill_source_hygiene_plan.clearance_status_summary", return_value={
                "present": True,
                "status": "PASS",
                "allCommandsPassed": True,
                "failedCommandIds": [],
                "coveredCommandIds": ["codex-automation-audit", "goal-completion-audit"],
                "readyForExecution": False,
                "writesOrders": False,
                "touchesBroker": False,
            }):
                payload = build_plan(argparse.Namespace(
                    source_intake=str(source),
                    data_intake=str(data),
                    execution_intake=str(execution),
                    worktree=str(worktree),
                    sibling_worktree_intake=str(sibling),
                    dirty_paths=[
                        "scripts/noise_stepforward_analysis.py",
                        "scripts/bill_source_hygiene_plan.py",
                        "tests/test_bill_source_hygiene_plan.py",
                        "scripts/bill_clearance_handoff.py",
                        "tests/test_bill_clearance_handoff.py",
                        "scripts/futures_nq_research_cycle.py",
                        "scripts/futures_broker_parity_plan.py",
                        "scripts/futures_evidence_triage.py",
                        "scripts/futures_nq_historical_session_replay.py",
                        "scripts/futures_nq_sizing_overlay.py",
                        "tests/test_futures_nq_sizing_overlay.py",
                        "scripts/bill_open_session_data_proof.py",
                        "tests/test_bill_open_session_data_proof.py",
                        "scripts/databento_orderflow_feature_smoke.py",
                        "scripts/alpha_frontier_queue.py",
                        "ops/mac-mini/bin/60m-strategy-eval-shadow.sh",
                        "scripts/prediction_evidence_triage.py",
                        "scripts/prediction_macro_rates_cross_source_replay.py",
                        "scripts/prediction_event_capture_cycle.py",
                        "tests/test_prediction_event_capture_cycle.py",
                        "scripts/prediction_event_lag_replay.py",
                        "scripts/prediction_event_lag_sensitivity.py",
                        "tests/test_prediction_event_lag_sensitivity.py",
                        "scripts/prediction_event_lag_watch_review.py",
                        "tests/test_prediction_event_lag_watch_review.py",
                        "scripts/prediction_event_lag_manual_review.py",
                        "tests/test_prediction_event_lag_manual_review.py",
                        "scripts/prediction_event_mapping_refinement.py",
                        "tests/test_prediction_event_mapping_refinement.py",
                        "scripts/polymarket_clob_recorder.mjs",
                        "scripts/polymarket_clob_persistence_lab.mjs",
                        "tests/polymarketClobPersistence.test.ts",
                        "src/prediction/pmBot.ts",
                        "scripts/master_bridge.py",
                        "data/free/NQ-1m-5d.csv",
                    ],
                ))

        self.assertEqual(payload["decision"], "source-hygiene-plan-research-only-execution-locked")
        self.assertFalse(payload["sourceHygieneCleared"])
        self.assertFalse(payload["sourceClean"])
        self.assertFalse(payload["automaticCleanupAllowed"])
        self.assertFalse(payload["safeToStageAutomatically"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["readyForLive"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["movesFunds"])
        self.assertEqual(payload["dirtyStatusCount"], 11)
        self.assertEqual(payload["reviewBacklogCount"], 10)
        self.assertEqual(payload["sourceCleanBlockers"], ["dirty execution-live files"])
        self.assertEqual(payload["worktreeClearanceQueue"][0]["lane"], "execution-live")
        self.assertEqual(payload["worktreeClearanceQueue"][0]["requiredEvidence"], ["npm run --silent bill:verify-execution-quarantine"])
        self.assertEqual(payload["inputs"]["siblingWorktreeIntake"]["decision"], "sibling-worktree-intake-visible-quarantine")
        self.assertEqual(payload["inputs"]["siblingWorktreeIntake"]["dirtyFileCount"], 4)
        self.assertEqual(payload["inputs"]["siblingWorktreeIntake"]["executionLiveDirtyCount"], 2)
        by_id = {item["id"]: item for item in payload["bundles"]}
        by_summary_id = {item["id"]: item for item in payload["bundleSummary"]}
        self.assertEqual(by_id["validated-research-scaffold"]["count"], 2)
        self.assertEqual(by_summary_id["validated-research-scaffold"]["count"], 2)
        self.assertFalse(by_summary_id["validated-research-scaffold"]["safeToStageAutomatically"])
        self.assertFalse(by_summary_id["validated-research-scaffold"]["writesOrders"])
        self.assertEqual(by_id["execution-live-quarantine"]["count"], 1)
        self.assertEqual(by_id["sibling-worktree-quarantine"]["count"], 4)
        self.assertIn("npm run --silent bill:sibling-worktree-intake", by_id["sibling-worktree-quarantine"]["commands"])
        self.assertIn(".venv/bin/python -m unittest tests.test_a -v", by_id["validated-research-scaffold"]["commands"])
        self.assertIn(".venv/bin/python -m unittest discover -s tests -p 'test_*.py'", by_id["validated-research-scaffold"]["commands"])
        self.assertIn("npm run --silent test", by_id["validated-research-scaffold"]["commands"])
        self.assertIn("npm run --silent bill:source-packet-review", by_id["validated-research-scaffold"]["commands"])
        self.assertEqual(payload["latestVerificationEvidence"]["fullSuite"][0], ".venv/bin/python -m unittest discover -s tests -p 'test_*.py'")
        self.assertEqual(payload["latestVerificationEvidence"]["clearanceEvidence"]["status"], "PASS")
        self.assertIn("codex-automation-audit", payload["latestVerificationEvidence"]["clearanceEvidence"]["coveredCommandIds"])
        self.assertIn("npm run --silent bill:verify-execution-quarantine", by_id["execution-live-quarantine"]["commands"])
        self.assertIn("npm run --silent bill:futures-broker-parity-plan", by_id["data-research-refresh"]["commands"])
        self.assertIn("npm run --silent bill:source-packet-review", by_id["strategy-research-review"]["commands"])
        self.assertTrue(all(not item["safeToStageAutomatically"] for item in payload["bundles"]))
        risk = payload["reviewPacketRiskSummary"]
        self.assertEqual(risk["packetCount"], 8)
        self.assertEqual(risk["pathCount"], sum(item["pathCount"] for item in payload["nextReviewPackets"]))
        self.assertIn("packet-01-control-research-scaffold", risk["manualStageEligiblePacketIds"])
        self.assertIn("packet-02-execution-firewall-quarantine", risk["blockedStagePacketIds"])
        expected_dirty_tree = sum(
            item["diffSummary"]["statusCounts"].get("dirty-tree", 0)
            for item in payload["nextReviewPackets"]
        )
        self.assertEqual(risk["statusCounts"]["dirty-tree"], expected_dirty_tree)
        self.assertEqual(risk["statusCounts"]["sibling-worktree-dirty"], 2)
        self.assertIn("never authorize automatic staging", risk["operatorRead"])
        self.assertEqual(payload["nextReductionOrder"][0]["bundleId"], "validated-research-scaffold")
        self.assertEqual(payload["nextReductionOrder"][1]["bundleId"], "execution-live-quarantine")
        self.assertEqual(payload["nextReductionOrder"][2]["bundleId"], "sibling-worktree-quarantine")
        packets = {item["id"]: item for item in payload["nextReviewPackets"]}
        self.assertEqual(packets["packet-01-control-research-scaffold"]["paths"], ["scripts/audit.py", "tests/test_audit.py"])
        self.assertFalse(packets["packet-01-control-research-scaffold"]["safeToStageAutomatically"])
        self.assertEqual(packets["packet-01-control-research-scaffold"]["diffSummary"]["pathCount"], 2)
        self.assertEqual(packets["packet-01-control-research-scaffold"]["pathFootprint"][0]["status"], "status-not-in-intake")
        self.assertEqual(
            packets["packet-01-control-research-scaffold"]["reviewCommands"],
            [
                "git status --short -- scripts/audit.py tests/test_audit.py",
                "git diff -- scripts/audit.py tests/test_audit.py",
            ],
        )
        self.assertEqual(
            packets["packet-01-control-research-scaffold"]["manualStageCommand"],
            "git add -- scripts/audit.py tests/test_audit.py",
        )
        self.assertTrue(packets["packet-01-control-research-scaffold"]["manualStageEligible"])
        self.assertEqual(
            packets["packet-01-control-research-scaffold"]["manualStageWarning"],
            "Manual operator review required; do not run this automatically.",
        )
        self.assertIn(
            "python3 -m py_compile scripts/audit.py tests/test_audit.py",
            packets["packet-01-control-research-scaffold"]["commands"],
        )
        self.assertEqual(packets["packet-02-execution-firewall-quarantine"]["decision"], "quarantine-locked")
        self.assertFalse(packets["packet-02-execution-firewall-quarantine"]["manualStageEligible"])
        self.assertIn("blocked for this packet", packets["packet-02-execution-firewall-quarantine"]["manualStageCommand"])
        self.assertEqual(packets["packet-02-execution-firewall-quarantine"]["pathFootprint"][0]["status"], "dirty-tree")
        self.assertIn("npm run --silent bill:verify-master-bridge-firewall", packets["packet-02-execution-firewall-quarantine"]["commands"])
        self.assertEqual(packets["packet-03-data-provenance-refresh"]["decision"], "research-data-only")
        self.assertFalse(packets["packet-03-data-provenance-refresh"]["manualStageEligible"])
        self.assertIn("blocked for this packet", packets["packet-03-data-provenance-refresh"]["manualStageCommand"])
        self.assertIn("npm run --silent bill:futures-broker-parity-plan", packets["packet-03-data-provenance-refresh"]["commands"])
        self.assertEqual(packets["packet-07-dependency-review"]["decision"], "dependency-review-only")
        self.assertEqual(
            packets["packet-07-dependency-review"]["paths"],
            ["package-lock.json", "requirements.bill-alpha.txt"],
        )
        self.assertIn("npm run --silent bill:alpha-tooling-check", packets["packet-07-dependency-review"]["commands"])
        self.assertIn("npm run --silent typecheck", packets["packet-07-dependency-review"]["commands"])
        self.assertFalse(packets["packet-07-dependency-review"]["safeToStageAutomatically"])
        self.assertFalse(packets["packet-07-dependency-review"]["touchesBroker"])
        self.assertEqual(packets["packet-04-strategy-backlog-sample"]["decision"], "split-before-review")
        self.assertIn("npm run --silent bill:source-packet-review", packets["packet-04-strategy-backlog-sample"]["commands"])
        self.assertEqual(packets["packet-05-futures-strategy-lane"]["decision"], "lane-review-only")
        self.assertEqual(packets["packet-05-futures-strategy-lane"]["paths"][0], "scripts/futures_evidence_triage.py")
        self.assertEqual(packets["packet-05-futures-strategy-lane"]["paths"][1], "scripts/futures_nq_historical_session_replay.py")
        self.assertIn("scripts/bill_open_session_data_proof.py", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertIn("tests/test_bill_open_session_data_proof.py", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertIn("scripts/databento_orderflow_feature_smoke.py", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertIn("scripts/alpha_frontier_queue.py", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertIn("scripts/futures_nq_research_cycle.py", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertIn("scripts/futures_nq_sizing_overlay.py", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertIn("tests/test_futures_nq_sizing_overlay.py", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertIn("scripts/futures_broker_parity_plan.py", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertNotIn("scripts/master_bridge.py", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertNotIn("ops/mac-mini/bin/60m-strategy-eval-shadow.sh", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertNotIn("data/free/NQ-1m-5d.csv", packets["packet-05-futures-strategy-lane"]["paths"])
        self.assertIn("npm run --silent bill:futures-evidence-triage || true", packets["packet-05-futures-strategy-lane"]["commands"])
        self.assertIn("npm run --silent bill:source-packet-review", packets["packet-05-futures-strategy-lane"]["commands"])
        self.assertEqual(packets["packet-06-prediction-market-lane"]["decision"], "lane-review-only")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][0], "scripts/prediction_event_capture_cycle.py")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][1], "tests/test_prediction_event_capture_cycle.py")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][2], "scripts/prediction_event_lag_sensitivity.py")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][3], "tests/test_prediction_event_lag_sensitivity.py")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][4], "scripts/prediction_event_lag_watch_review.py")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][5], "tests/test_prediction_event_lag_watch_review.py")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][6], "scripts/prediction_event_lag_manual_review.py")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][7], "tests/test_prediction_event_lag_manual_review.py")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][8], "scripts/prediction_event_mapping_refinement.py")
        self.assertEqual(packets["packet-06-prediction-market-lane"]["paths"][9], "tests/test_prediction_event_mapping_refinement.py")
        self.assertIn("scripts/prediction_macro_rates_cross_source_replay.py", packets["packet-06-prediction-market-lane"]["paths"])
        self.assertIn("scripts/prediction_event_lag_replay.py", packets["packet-06-prediction-market-lane"]["paths"])
        self.assertIn("scripts/polymarket_clob_recorder.mjs", packets["packet-06-prediction-market-lane"]["paths"])
        self.assertIn("scripts/polymarket_clob_persistence_lab.mjs", packets["packet-06-prediction-market-lane"]["paths"])
        self.assertNotIn("src/prediction/pmBot.ts", packets["packet-06-prediction-market-lane"]["paths"])
        self.assertIn("npm run --silent bill:verify-prediction-funding-firewall", packets["packet-06-prediction-market-lane"]["commands"])
        self.assertIn("npm run --silent bill:source-packet-review", packets["packet-06-prediction-market-lane"]["commands"])
        self.assertFalse(packets["packet-05-futures-strategy-lane"]["touchesBroker"])
        self.assertFalse(packets["packet-06-prediction-market-lane"]["movesFunds"])
        self.assertEqual(packets["packet-08-sibling-worktree-selective-intake"]["decision"], "quarantine-selective-review")
        self.assertFalse(packets["packet-08-sibling-worktree-selective-intake"]["manualStageEligible"])
        self.assertIn("blocked for this packet", packets["packet-08-sibling-worktree-selective-intake"]["manualStageCommand"])
        self.assertIn("npm run --silent bill:sibling-worktree-intake", packets["packet-08-sibling-worktree-selective-intake"]["commands"])

        markdown = render_markdown(payload)
        self.assertIn("Read-only cleanup and review plan", markdown)
        self.assertIn("Sibling Worktree Intake", markdown)
        self.assertIn("sibling-worktree-intake-visible-quarantine", markdown)
        self.assertIn("Latest Verification Evidence", markdown)
        self.assertIn("Next Review Packets", markdown)
        self.assertIn("Packet count: `8`", markdown)
        self.assertIn("Blocked-stage packets", markdown)
        self.assertIn("packet-01-control-research-scaffold", markdown)
        self.assertIn("Clearance evidence: status `PASS`", markdown)
        self.assertIn("packet-05-futures-strategy-lane", markdown)
        self.assertIn("packet-06-prediction-market-lane", markdown)
        self.assertIn("Diff summary", markdown)
        self.assertIn("Dirty status count: `11`", markdown)
        self.assertIn("Review backlog count: `10`", markdown)
        self.assertIn("Source clean blockers: `['dirty execution-live files']`", markdown)
        self.assertIn("## Worktree Clearance Queue", markdown)
        self.assertIn("`execution-live` - dirtyFiles `3`", markdown)
        self.assertIn("No automatic staging, deletion, moves, or reverts.", markdown)
        self.assertIn("Safe to stage automatically: `False`", markdown)
        self.assertIn("Manual stage warning: Manual operator review required; do not run this automatically.", markdown)
        self.assertIn("Manual stage command: `git add -- scripts/audit.py tests/test_audit.py`", markdown)
        self.assertIn("Review commands", markdown)

    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^bill-source-hygiene-plan-\d{4}-\d{2}-\d{2}\.md$")

    def test_missing_inputs_still_do_not_clear_execution_or_source_hygiene(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            missing = tmp_path / "missing.json"
            payload = build_plan(argparse.Namespace(
                source_intake=str(missing),
                data_intake=str(missing),
                execution_intake=str(missing),
                worktree=str(missing),
                dirty_paths=[],
            ))

        self.assertFalse(payload["sourceHygieneCleared"])
        self.assertFalse(payload["sourceClean"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["safeToStageAutomatically"])
        self.assertTrue(payload["researchOnly"])
        self.assertEqual(payload["bundles"][0]["id"], "validated-research-scaffold")

    def test_validated_research_packet_includes_all_validated_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.json"
            data = tmp_path / "data.json"
            execution = tmp_path / "execution.json"
            worktree = tmp_path / "worktree.json"
            validated = [
                {"path": f"scripts/research_{index:02d}.py", "status": "??"}
                for index in range(15)
            ]
            source.write_text(json.dumps({
                "decision": "source-intake-visible-execution-locked",
                "sourceClean": False,
                "dirtyStatusCount": 15,
                "reviewBacklogCount": 0,
                "classificationCounts": {"validated-research-scaffold": 15},
                "validationEvidence": {"focusedSuite": ".venv/bin/python -m unittest tests.test_a -v"},
                "validatedResearchScaffold": validated,
                "requiresReviewSamples": {},
            }))
            data.write_text(json.dumps({"items": [], "classificationCounts": {}, "riskCounts": {}}))
            execution.write_text(json.dumps({"items": [], "classificationCounts": {}}))
            worktree.write_text(json.dumps({"posture": "blocked"}))

            payload = build_plan(argparse.Namespace(
                source_intake=str(source),
                data_intake=str(data),
                execution_intake=str(execution),
                worktree=str(worktree),
                dirty_paths=[],
            ))

        packet = next(item for item in payload["nextReviewPackets"] if item["id"] == "packet-01-control-research-scaffold")

        self.assertEqual(packet["pathCount"], 15)
        self.assertEqual(len(packet["paths"]), 15)
        self.assertEqual(packet["paths"][-1], "scripts/research_14.py")
        self.assertEqual(packet["diffSummary"]["pathCount"], 15)
        self.assertIn("scripts/research_14.py", packet["commands"][1])

    def test_control_packet_prioritizes_codex_and_goal_control_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            data = root / "data.json"
            execution = root / "execution.json"
            worktree = root / "worktree.json"
            validated = [
                {"path": "scripts/research_noise.py", "status": "??"},
                {"path": "tests/test_codex_automation_audit.py", "status": "??"},
                {"path": "scripts/codex_automation_audit.py", "status": "??"},
                {"path": "scripts/bill_source_hygiene_plan.py", "status": "??"},
                {"path": "tests/test_bill_source_hygiene_plan.py", "status": "??"},
                {"path": "scripts/bill_clearance_handoff.py", "status": "??"},
                {"path": "tests/test_bill_clearance_handoff.py", "status": "??"},
                {"path": "scripts/bill_goal_completion_audit.py", "status": "??"},
                {"path": "scripts/bill_runtime_architecture_audit.py", "status": "??"},
                {"path": "tests/test_bill_runtime_architecture_audit.py", "status": "??"},
                {"path": "scripts/bill_fund_os_completion_audit.py", "status": "??"},
                {"path": "tests/test_bill_fund_os_completion_audit.py", "status": "??"},
            ]
            source.write_text(json.dumps({
                "decision": "source-intake-visible-execution-locked",
                "sourceClean": False,
                "dirtyStatusCount": 12,
                "reviewBacklogCount": 0,
                "classificationCounts": {"validated-research-scaffold": 12},
                "validationEvidence": {"focusedSuite": ".venv/bin/python -m unittest tests.test_codex_automation_audit -v"},
                "validatedResearchScaffold": validated,
                "requiresReviewSamples": {},
            }))
            data.write_text(json.dumps({"items": [], "classificationCounts": {}, "riskCounts": {}}))
            execution.write_text(json.dumps({"items": [], "classificationCounts": {}}))
            worktree.write_text(json.dumps({"posture": "blocked"}))

            payload = build_plan(argparse.Namespace(
                source_intake=str(source),
                data_intake=str(data),
                execution_intake=str(execution),
                worktree=str(worktree),
                dirty_paths=[],
            ))

        packet = next(item for item in payload["nextReviewPackets"] if item["id"] == "packet-01-control-research-scaffold")

        self.assertEqual(packet["paths"][0], "scripts/codex_automation_audit.py")
        self.assertEqual(packet["paths"][1], "tests/test_codex_automation_audit.py")
        self.assertEqual(packet["paths"][2], "scripts/bill_source_hygiene_plan.py")
        self.assertEqual(packet["paths"][3], "tests/test_bill_source_hygiene_plan.py")
        self.assertEqual(packet["paths"][4], "scripts/bill_clearance_handoff.py")
        self.assertEqual(packet["paths"][5], "tests/test_bill_clearance_handoff.py")
        self.assertEqual(packet["paths"][6], "scripts/bill_goal_completion_audit.py")
        self.assertEqual(packet["paths"][7], "scripts/bill_runtime_architecture_audit.py")
        self.assertEqual(packet["paths"][8], "tests/test_bill_runtime_architecture_audit.py")
        self.assertEqual(packet["paths"][9], "scripts/bill_fund_os_completion_audit.py")
        self.assertEqual(packet["paths"][10], "tests/test_bill_fund_os_completion_audit.py")
        self.assertEqual(packet["paths"][11], "scripts/research_noise.py")

    def test_control_packet_surfaces_research_seed_refresh_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            data = root / "data.json"
            execution = root / "execution.json"
            worktree = root / "worktree.json"
            source.write_text(json.dumps({
                "decision": "source-intake-visible-execution-locked",
                "sourceClean": False,
                "dirtyStatusCount": 2,
                "reviewBacklogCount": 0,
                "classificationCounts": {"validated-research-scaffold": 2},
                "validationEvidence": {"focusedSuite": ".venv/bin/python -m unittest tests.test_research_seed_target_refresh_plan -v"},
                "validatedResearchScaffold": [
                    {"path": "scripts/research_seed_target_refresh_plan.py", "status": "??"},
                    {"path": "tests/test_research_seed_target_refresh_plan.py", "status": "??"},
                ],
                "requiresReviewSamples": {},
            }))
            data.write_text(json.dumps({"items": [], "classificationCounts": {}, "riskCounts": {}}))
            execution.write_text(json.dumps({"items": [], "classificationCounts": {}}))
            worktree.write_text(json.dumps({"posture": "blocked"}))

            payload = build_plan(argparse.Namespace(
                source_intake=str(source),
                data_intake=str(data),
                execution_intake=str(execution),
                worktree=str(worktree),
                dirty_paths=[],
            ))

        packet = next(item for item in payload["nextReviewPackets"] if item["id"] == "packet-01-control-research-scaffold")
        self.assertIn("scripts/research_seed_target_refresh_plan.py", packet["paths"])
        self.assertIn("tests/test_research_seed_target_refresh_plan.py", packet["paths"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])

    def test_control_packet_surfaces_stale_strategy_claim_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            data = root / "data.json"
            execution = root / "execution.json"
            worktree = root / "worktree.json"
            source.write_text(json.dumps({
                "decision": "source-intake-visible-execution-locked",
                "sourceClean": False,
                "dirtyStatusCount": 3,
                "reviewBacklogCount": 0,
                "classificationCounts": {"validated-research-scaffold": 3},
                "validationEvidence": {"focusedSuite": ".venv/bin/python -m unittest tests.test_stale_strategy_claim_guard tests.test_strategy_evidence_copy -v"},
                "validatedResearchScaffold": [
                    {"path": "scripts/stale_strategy_claim_guard.py", "status": "??"},
                    {"path": "tests/test_stale_strategy_claim_guard.py", "status": "??"},
                    {"path": "tests/test_strategy_evidence_copy.py", "status": "??"},
                ],
                "requiresReviewSamples": {},
            }))
            data.write_text(json.dumps({"items": [], "classificationCounts": {}, "riskCounts": {}}))
            execution.write_text(json.dumps({"items": [], "classificationCounts": {}}))
            worktree.write_text(json.dumps({"posture": "blocked"}))

            payload = build_plan(argparse.Namespace(
                source_intake=str(source),
                data_intake=str(data),
                execution_intake=str(execution),
                worktree=str(worktree),
                dirty_paths=[],
            ))

        packet = next(item for item in payload["nextReviewPackets"] if item["id"] == "packet-01-control-research-scaffold")
        self.assertIn("scripts/stale_strategy_claim_guard.py", packet["paths"])
        self.assertIn("tests/test_stale_strategy_claim_guard.py", packet["paths"])
        self.assertIn("tests/test_strategy_evidence_copy.py", packet["paths"])
        self.assertIn("tests.test_stale_strategy_claim_guard", packet["commands"][0])
        self.assertIn("tests.test_strategy_evidence_copy", packet["commands"][0])
        self.assertFalse(packet["safeToStageAutomatically"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])

    def test_prediction_lane_packet_surfaces_validated_clob_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            data = root / "data.json"
            execution = root / "execution.json"
            worktree = root / "worktree.json"
            source.write_text(json.dumps({
                "decision": "source-intake-visible-execution-locked",
                "sourceClean": False,
                "dirtyStatusCount": 10,
                "reviewBacklogCount": 0,
                "classificationCounts": {"validated-research-scaffold": 10},
                "validationEvidence": {"focusedSuite": ".venv/bin/python -m unittest tests.test_prediction_clob_trade_impact_replay -v"},
                "validatedResearchScaffold": [
                    {"path": "scripts/prediction_event_capture_cycle.py", "status": "??"},
                    {"path": "scripts/prediction_event_lag_sensitivity.py", "status": "??"},
                    {"path": "scripts/prediction_event_lag_watch_review.py", "status": "??"},
                    {"path": "tests/test_prediction_event_lag_watch_review.py", "status": "??"},
                    {"path": "scripts/prediction_event_lag_manual_review.py", "status": "??"},
                    {"path": "tests/test_prediction_event_lag_manual_review.py", "status": "??"},
                    {"path": "scripts/prediction_event_mapping_refinement.py", "status": "??"},
                    {"path": "tests/test_prediction_event_mapping_refinement.py", "status": "??"},
                    {"path": "scripts/polymarket_clob_recorder.mjs", "status": "??"},
                    {"path": "tests/polymarketClobRecorder.test.ts", "status": "??"},
                    {"path": "scripts/prediction_clob_trade_impact_replay.py", "status": "??"},
                    {"path": "tests/test_prediction_clob_trade_impact_replay.py", "status": "??"},
                    {"path": "scripts/bill_next_research_actions.py", "status": "??"},
                    {"path": "tests/test_bill_next_research_actions.py", "status": "??"},
                ],
                "requiresReviewSamples": {},
            }))
            data.write_text(json.dumps({"items": [], "classificationCounts": {}, "riskCounts": {}}))
            execution.write_text(json.dumps({"items": [], "classificationCounts": {}}))
            worktree.write_text(json.dumps({"posture": "blocked"}))

            payload = build_plan(argparse.Namespace(
                source_intake=str(source),
                data_intake=str(data),
                execution_intake=str(execution),
                worktree=str(worktree),
                dirty_paths=[],
            ))

        packets = {item["id"]: item for item in payload["nextReviewPackets"]}
        self.assertIn("packet-06-prediction-market-lane", packets)
        prediction_packet = packets["packet-06-prediction-market-lane"]
        self.assertEqual(prediction_packet["decision"], "lane-review-only")
        self.assertEqual(prediction_packet["paths"][0], "scripts/prediction_event_capture_cycle.py")
        self.assertEqual(prediction_packet["paths"][1], "scripts/prediction_event_lag_sensitivity.py")
        self.assertEqual(prediction_packet["paths"][2], "scripts/prediction_event_lag_watch_review.py")
        self.assertEqual(prediction_packet["paths"][3], "tests/test_prediction_event_lag_watch_review.py")
        self.assertEqual(prediction_packet["paths"][4], "scripts/prediction_event_lag_manual_review.py")
        self.assertEqual(prediction_packet["paths"][5], "tests/test_prediction_event_lag_manual_review.py")
        self.assertEqual(prediction_packet["paths"][6], "scripts/prediction_event_mapping_refinement.py")
        self.assertEqual(prediction_packet["paths"][7], "tests/test_prediction_event_mapping_refinement.py")
        self.assertIn("tests/polymarketClobRecorder.test.ts", prediction_packet["paths"])
        self.assertIn("scripts/prediction_clob_trade_impact_replay.py", prediction_packet["paths"])
        self.assertIn("scripts/bill_next_research_actions.py", prediction_packet["paths"])
        self.assertFalse(prediction_packet["safeToStageAutomatically"])
        self.assertFalse(prediction_packet["writesOrders"])
        self.assertFalse(prediction_packet["touchesBroker"])

    def test_control_packet_prioritizes_research_seed_triage_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            data = root / "data.json"
            execution = root / "execution.json"
            worktree = root / "worktree.json"
            source.write_text(json.dumps({
                "decision": "source-intake-visible-execution-locked",
                "sourceClean": False,
                "dirtyStatusCount": 2,
                "reviewBacklogCount": 0,
                "classificationCounts": {"validated-research-scaffold": 2},
                "validationEvidence": {
                    "focusedSuite": ".venv/bin/python -m unittest tests.test_research_seed_triage -v",
                    "fullSuite": [],
                },
                "validatedResearchScaffold": [
                    {"path": "scripts/research_seed_triage.py", "status": "??"},
                    {"path": "tests/test_research_seed_triage.py", "status": "??"},
                ],
                "requiresReviewSamples": {},
            }))
            data.write_text(json.dumps({"items": [], "classificationCounts": {}, "riskCounts": {}}))
            execution.write_text(json.dumps({"items": [], "classificationCounts": {}}))
            worktree.write_text(json.dumps({"posture": "blocked", "sourceCleanBlockers": ["dirty validated research files"]}))

            with patch("scripts.bill_source_hygiene_plan.clearance_status_summary", return_value={
                "present": True,
                "status": "PASS",
                "allCommandsPassed": True,
                "failedCommandIds": [],
                "coveredCommandIds": [],
                "readyForExecution": False,
                "writesOrders": False,
                "touchesBroker": False,
            }):
                payload = build_plan(argparse.Namespace(
                    source_intake=str(source),
                    data_intake=str(data),
                    execution_intake=str(execution),
                    worktree=str(worktree),
                    dirty_paths=[
                        "scripts/research_seed_triage.py",
                        "tests/test_research_seed_triage.py",
                    ],
                ))

        packet = next(item for item in payload["nextReviewPackets"] if item["id"] == "packet-01-control-research-scaffold")
        self.assertEqual(
            packet["paths"],
            ["scripts/research_seed_triage.py", "tests/test_research_seed_triage.py"],
        )
        self.assertIn(
            "python3 -m py_compile scripts/research_seed_triage.py tests/test_research_seed_triage.py",
            packet["commands"],
        )
        self.assertFalse(packet["safeToStageAutomatically"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])


if __name__ == "__main__":
    unittest.main()
