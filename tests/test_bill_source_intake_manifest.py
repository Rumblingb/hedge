import unittest

from scripts.bill_source_intake_manifest import (
    HERMES,
    build_manifest,
    default_markdown_path,
    parse_git_status,
    render_markdown,
)


class BillSourceIntakeManifestTest(unittest.TestCase):
    def test_manifest_classifies_validated_and_quarantined_dirty_files(self):
        rows = parse_git_status(
            "?? scripts/bill_corpus_audit.py\n"
            " M scripts/master_bridge.py\n"
            " M data/free/NQ-1m-5d.csv\n"
            "?? scripts/new_research_probe.py\n"
        )
        payload = build_manifest(
            worktree={
                "sourceCleanBlockers": ["canonical source root has dirty files"],
                "canonicalSource": {
                    "path": "/Users/brain/hedge",
                    "branch": "master",
                    "head": "abc123",
                    "dirtyFiles": 4,
                    "categories": {"execution-live": 1, "strategy-research": 2, "data": 1},
                    "executionLiveFiles": ["scripts/master_bridge.py"],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["decision"], "source-intake-visible-execution-locked")
        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["sourceClean"])
        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 1)
        self.assertEqual(payload["classificationCounts"]["quarantine-execution-live"], 1)
        self.assertEqual(payload["classificationCounts"]["data-needs-manifest"], 1)
        self.assertEqual(payload["reviewBacklogCount"], 2)
        self.assertEqual(payload["executionLiveDirtyCount"], 1)
        self.assertEqual(payload["canonicalExecutionLiveDirtyCount"], 1)
        self.assertEqual(payload["classifiedExecutionLiveDirtyCount"], 1)
        self.assertEqual(payload["quarantineExecutionLiveFiles"][0]["path"], "scripts/master_bridge.py")
        self.assertIn("npm run --silent bill:verify-master-bridge-firewall", payload["nextCommands"])
        self.assertIn("npm run --silent bill:verify-execution-quarantine", payload["nextCommands"])
        self.assertIn("npm run --silent bill:clearance-evidence", payload["nextCommands"])
        self.assertIn("npm run --silent bill:source-packet-review", payload["nextCommands"])
        self.assertIn(".venv/bin/python -m unittest discover -s tests -p 'test_*.py'", payload["validationEvidence"]["fullSuite"])
        self.assertIn("npm run --silent bill:verify-signal-router-firewall", payload["validationEvidence"]["fullSuite"])
        self.assertIn("tests.test_bill_clearance_evidence", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_bill_clearance_handoff", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_bill_source_packet_review", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_realtime_data_preflight", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_signal_quality_advisor", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_signal_source_truth_audit", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_ai_screener", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_ai_scientist_financial_template", payload["validationEvidence"]["focusedSuite"])
        self.assertIn(
            "npm run --silent bill:clearance-evidence",
            payload["validationEvidence"]["fullSuite"],
        )
        self.assertEqual(
            payload["validationCommandSets"]["focusedResearchControlSuite"],
            [payload["validationEvidence"]["focusedSuite"]],
        )
        self.assertIn(
            "npm run --silent bill:source-hygiene-plan",
            payload["validationCommandSets"]["sourceVisibilityRefresh"],
        )
        self.assertIn(
            "npm run --silent bill:source-packet-review",
            payload["validationCommandSets"]["sourceVisibilityRefresh"],
        )

    def test_dependency_files_are_separate_from_validated_scaffold(self):
        rows = parse_git_status(
            " M package.json\n"
            " M package-lock.json\n"
            "?? requirements.bill-alpha.txt\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 3,
                    "categories": {"governance-risk": 3},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["dependency-review"], 3)
        self.assertNotIn("validated-research-scaffold", payload["classificationCounts"])
        self.assertEqual(payload["reviewBacklogCount"], 3)
        self.assertIn("package.json", payload["requiresReviewSamples"]["dependency-review"])
        validated_paths = {row["path"] for row in payload["validatedResearchScaffold"]}
        self.assertNotIn("package.json", validated_paths)

    def test_clearance_evidence_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/bill_clearance_evidence.py\n"
            "?? tests/test_bill_clearance_evidence.py\n"
            "?? scripts/cron_state_validator.py\n"
            "?? tests/test_cron_state_validator.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 4,
                    "categories": {"governance-risk": 4},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 4)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_cron_state_validator", payload["validationEvidence"]["focusedSuite"])

    def test_stale_strategy_claim_guard_is_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/stale_strategy_claim_guard.py\n"
            "?? tests/test_stale_strategy_claim_guard.py\n"
            "?? tests/test_strategy_evidence_copy.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 2,
                    "categories": {"governance-risk": 2},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-31T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 3)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_stale_strategy_claim_guard", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_strategy_evidence_copy", payload["validationEvidence"]["focusedSuite"])
        self.assertIn(
            "npm run --silent bill:stale-strategy-claim-guard",
            payload["validationEvidence"]["fullSuite"],
        )

    def test_bill_package_script_guard_is_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? ops/mac-mini/bin/bill-chatgpt-frontdoor\n"
            "?? ops/activate-bill-workflows.sh\n"
            "?? tests/test_bill_package_scripts.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 3,
                    "categories": {"governance-risk": 3},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-31T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 3)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_bill_package_scripts", payload["validationEvidence"]["focusedSuite"])

    def test_realtime_and_signal_quality_controls_are_validated_scaffold(self):
        rows = parse_git_status(
            "?? scripts/realtime_data_preflight.py\n"
            "?? tests/test_realtime_data_preflight.py\n"
            "?? scripts/signal_quality_advisor.py\n"
            "?? tests/test_signal_quality_advisor.py\n"
            "?? scripts/signal_source_truth_audit.py\n"
            "?? tests/test_signal_source_truth_audit.py\n"
            "?? scripts/topstep_daily_learning.py\n"
            "?? tests/test_topstep_daily_learning.py\n"
            " M scripts/ai_screener.py\n"
            "?? tests/test_ai_screener.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 10,
                    "categories": {"governance-risk": 10},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 10)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_realtime_data_preflight", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_signal_quality_advisor", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_signal_source_truth_audit", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_topstep_daily_learning", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_ai_screener", payload["validationEvidence"]["focusedSuite"])
        validated_paths = {row["path"] for row in payload["validatedResearchScaffold"]}
        self.assertIn("scripts/signal_source_truth_audit.py", validated_paths)
        self.assertIn("scripts/topstep_daily_learning.py", validated_paths)
        self.assertIn("scripts/ai_screener.py", validated_paths)

    def test_ai_scientist_template_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? ai-scientist-templates/financial_strategy/experiment.py\n"
            "?? ai-scientist-templates/financial_strategy/ideas.json\n"
            "?? ai-scientist-templates/financial_strategy/latex/fancyhdr.sty\n"
            "?? ai-scientist-templates/financial_strategy/latex/iclr2024_conference.bst\n"
            "?? ai-scientist-templates/financial_strategy/latex/iclr2024_conference.sty\n"
            "?? ai-scientist-templates/financial_strategy/latex/natbib.sty\n"
            "?? ai-scientist-templates/financial_strategy/latex/template.tex\n"
            "?? ai-scientist-templates/financial_strategy/plot.py\n"
            "?? ai-scientist-templates/financial_strategy/prompt.json\n"
            "?? ai-scientist-templates/financial_strategy/seed_ideas.json\n"
            "?? ai-scientist-templates/financial_strategy/test_run/final_info.json\n"
            "?? ai-scientist-templates/financial_strategy/test_run_15m/final_info.json\n"
            "?? ai-scientist-templates/financial_strategy/test_run_30m/final_info.json\n"
            "?? ai-scientist-templates/financial_strategy/test_run_60m/final_info.json\n"
            "?? ai-scientist-templates/financial_strategy/test_run_known_baselines/final_info.json\n"
            "?? tests/test_ai_scientist_financial_template.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 16,
                    "categories": {"governance-risk": 16},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-06-01T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 16)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_ai_scientist_financial_template", payload["validationEvidence"]["focusedSuite"])
        validated_paths = {row["path"] for row in payload["validatedResearchScaffold"]}
        self.assertIn("ai-scientist-templates/financial_strategy/experiment.py", validated_paths)
        self.assertIn("ai-scientist-templates/financial_strategy/latex/template.tex", validated_paths)
        self.assertIn("ai-scientist-templates/financial_strategy/test_run_known_baselines/final_info.json", validated_paths)

    def test_research_seed_refresh_plan_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/research_seed_target_refresh_plan.py\n"
            "?? tests/test_research_seed_target_refresh_plan.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 2,
                    "categories": {"governance-risk": 2},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 2)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_research_seed_target_refresh_plan", payload["validationEvidence"]["focusedSuite"])

    def test_research_closed_loop_contract_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/bill_research_closed_loop_contract.py\n"
            "?? tests/test_bill_research_closed_loop_contract.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 2,
                    "categories": {"governance-risk": 2},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 2)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_bill_research_closed_loop_contract", payload["validationEvidence"]["focusedSuite"])

    def test_source_packet_review_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/bill_source_packet_review.py\n"
            "?? tests/test_bill_source_packet_review.py\n"
            "?? scripts/bill_clearance_handoff.py\n"
            "?? tests/test_bill_clearance_handoff.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 4,
                    "categories": {"governance-risk": 4},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 4)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_bill_clearance_handoff", payload["validationEvidence"]["focusedSuite"])

    def test_paper_source_cards_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/paper_source_cards.py\n"
            "?? tests/test_paper_source_cards.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 2,
                    "categories": {"strategy-research": 2},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 2)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_paper_source_cards", payload["validationEvidence"]["focusedSuite"])

    def test_current_alpha_watch_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/current_alpha_watch.py\n"
            "?? tests/test_current_alpha_watch.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 2,
                    "categories": {"strategy-research": 2},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 2)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_current_alpha_watch", payload["validationEvidence"]["focusedSuite"])

    def test_futures_strategy_shadow_safety_is_validated_research_scaffold(self):
        rows = parse_git_status(
            " M scripts/cot_signal.py\n"
            "?? tests/test_cot_signal_safety.py\n"
            " M scripts/donchian_breakout.py\n"
            " M scripts/ichimoku_full_system.py\n"
            " M scripts/noise_stepforward_analysis.py\n"
            "?? scripts/noise_area_scalp.py\n"
            " M scripts/session_trader.py\n"
            "?? scripts/probe-60m-signals.ts\n"
            "?? scripts/qrs_session_bias.py\n"
            "?? scripts/refresh_futures_research_data.py\n"
            "?? scripts/vol_noise_scalp.py\n"
            "?? tests/test_futures_strategy_shadow_safety.py\n"
            "?? tests/test_noise_area_scalp_safety.py\n"
            "?? tests/test_qrs_session_bias_safety.py\n"
            "?? tests/test_refresh_futures_research_data.py\n"
            "?? tests/test_vol_noise_scalp_safety.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 16,
                    "categories": {"strategy-research": 16},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 16)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_futures_strategy_shadow_safety", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_cot_signal_safety", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_noise_area_scalp_safety", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_qrs_session_bias_safety", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_refresh_futures_research_data", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_vol_noise_scalp_safety", payload["validationEvidence"]["focusedSuite"])
        validated_paths = {row["path"] for row in payload["validatedResearchScaffold"]}
        self.assertIn("scripts/cot_signal.py", validated_paths)
        self.assertIn("tests/test_cot_signal_safety.py", validated_paths)
        self.assertIn("scripts/session_trader.py", validated_paths)
        self.assertIn("scripts/noise_area_scalp.py", validated_paths)
        self.assertIn("scripts/probe-60m-signals.ts", validated_paths)
        self.assertIn("scripts/qrs_session_bias.py", validated_paths)
        self.assertIn("scripts/refresh_futures_research_data.py", validated_paths)
        self.assertIn("scripts/vol_noise_scalp.py", validated_paths)

    def test_backtrader_and_cot_research_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/backtrader_research_loop.py\n"
            "?? scripts/cftc_tff_positioning_ingest.py\n"
            "?? tests/test_cftc_tff_positioning_ingest.py\n"
            "?? scripts/cot_regime_filter_research.py\n"
            "?? tests/test_cot_regime_filter_research.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 5,
                    "categories": {"strategy-research": 5},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-31T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 5)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_futures_strategy_shadow_safety", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_cftc_tff_positioning_ingest", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_cot_regime_filter_research", payload["validationEvidence"]["focusedSuite"])
        validated_paths = {row["path"] for row in payload["validatedResearchScaffold"]}
        self.assertIn("scripts/backtrader_research_loop.py", validated_paths)
        self.assertIn("scripts/cftc_tff_positioning_ingest.py", validated_paths)
        self.assertIn("scripts/cot_regime_filter_research.py", validated_paths)

    def test_futures_nq_sizing_overlay_is_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/futures_nq_sizing_overlay.py\n"
            "?? tests/test_futures_nq_sizing_overlay.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 2,
                    "categories": {"strategy-research": 2},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-31T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 2)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_futures_nq_sizing_overlay", payload["validationEvidence"]["focusedSuite"])

    def test_prediction_event_capture_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/prediction_event_capture_cycle.py\n"
            "?? tests/test_prediction_event_capture_cycle.py\n"
            "?? scripts/prediction_event_paper_promotion_gate.py\n"
            "?? tests/test_prediction_event_paper_promotion_gate.py\n"
            "?? scripts/prediction_event_lag_sensitivity.py\n"
            "?? tests/test_prediction_event_lag_sensitivity.py\n"
            "?? scripts/prediction_event_lag_watch_review.py\n"
            "?? tests/test_prediction_event_lag_watch_review.py\n"
            "?? scripts/prediction_event_lag_manual_review.py\n"
            "?? tests/test_prediction_event_lag_manual_review.py\n"
            "?? scripts/prediction_event_mapping_refinement.py\n"
            "?? tests/test_prediction_event_mapping_refinement.py\n"
            "?? scripts/prediction_event_market_mapping_plan.py\n"
            "?? tests/test_prediction_event_market_mapping_plan.py\n"
            "?? scripts/prediction_clob_microstructure_feature_audit.py\n"
            "?? tests/test_prediction_clob_microstructure_feature_audit.py\n"
            "?? scripts/polymarket_clob_recorder.mjs\n"
            "?? tests/polymarketClobRecorder.test.ts\n"
            "?? scripts/polymarket_clob_persistence_lab.mjs\n"
            "?? tests/polymarketClobPersistence.test.ts\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 20,
                    "categories": {"strategy-research": 20},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 20)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_prediction_event_capture_cycle", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_event_paper_promotion_gate", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_event_lag_sensitivity", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_event_lag_watch_review", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_event_lag_manual_review", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_event_mapping_refinement", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_event_market_mapping_plan", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_clob_microstructure_feature_audit", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_no_edge_ledger", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_clob_spread_compression_replay", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_clob_latency_staleness_replay", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_prediction_clob_trade_impact_replay", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("npm run --silent test -- tests/polymarketClobRecorder.test.ts", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests/polymarketClobPersistence.test.ts", payload["validationEvidence"]["focusedSuite"])
        validated_paths = {row["path"] for row in payload["validatedResearchScaffold"]}
        self.assertIn("scripts/prediction_event_paper_promotion_gate.py", validated_paths)
        self.assertIn("tests/test_prediction_event_paper_promotion_gate.py", validated_paths)

    def test_codex_automation_audit_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/codex_automation_audit.py\n"
            "?? tests/test_codex_automation_audit.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 2,
                    "categories": {"governance-risk": 2},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 2)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_codex_automation_audit", payload["validationEvidence"]["focusedSuite"])

    def test_runtime_architecture_audit_files_are_validated_research_scaffold(self):
        rows = parse_git_status(
            "?? scripts/bill_runtime_architecture_audit.py\n"
            "?? tests/test_bill_runtime_architecture_audit.py\n"
            "?? scripts/bill_fund_os_completion_audit.py\n"
            "?? tests/test_bill_fund_os_completion_audit.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 4,
                    "categories": {"governance-risk": 4},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 4)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_bill_runtime_architecture_audit", payload["validationEvidence"]["focusedSuite"])
        self.assertIn("tests.test_bill_fund_os_completion_audit", payload["validationEvidence"]["focusedSuite"])
        validated_paths = {row["path"] for row in payload["validatedResearchScaffold"]}
        self.assertIn("scripts/bill_runtime_architecture_audit.py", validated_paths)
        self.assertIn("tests/test_bill_runtime_architecture_audit.py", validated_paths)
        self.assertIn("scripts/bill_fund_os_completion_audit.py", validated_paths)
        self.assertIn("tests/test_bill_fund_os_completion_audit.py", validated_paths)

    def test_research_seed_triage_files_are_validated_control_scaffold(self):
        rows = parse_git_status(
            "?? scripts/research_seed_triage.py\n"
            "?? tests/test_research_seed_triage.py\n"
        )
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 2,
                    "categories": {"governance-risk": 2},
                    "executionLiveFiles": [],
                },
            },
            git_status_rows=rows,
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classificationCounts"]["validated-research-scaffold"], 2)
        self.assertEqual(payload["reviewBacklogCount"], 0)
        self.assertIn("tests.test_research_seed_triage", payload["validationEvidence"]["focusedSuite"])
        validated_paths = {row["path"] for row in payload["validatedResearchScaffold"]}
        self.assertIn("scripts/research_seed_triage.py", validated_paths)
        self.assertIn("tests/test_research_seed_triage.py", validated_paths)

    def test_manifest_uses_conservative_execution_live_count_when_artifact_is_higher(self):
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 4,
                    "categories": {"execution-live": 3},
                    "executionLiveFiles": ["scripts/master_bridge.py"],
                },
            },
            git_status_rows=[{"status": "M", "path": "scripts/master_bridge.py"}],
            generated_at="2026-05-30T00:00:00+00:00",
        )

        self.assertEqual(payload["classifiedExecutionLiveDirtyCount"], 1)
        self.assertEqual(payload["canonicalExecutionLiveDirtyCount"], 3)
        self.assertEqual(payload["executionLiveDirtyCount"], 3)

    def test_manifest_markdown_keeps_execution_locked_language(self):
        payload = build_manifest(
            worktree={
                "canonicalSource": {
                    "dirtyFiles": 1,
                    "categories": {"execution-live": 1},
                    "executionLiveFiles": ["src/live/signalRouter.ts"],
                }
            },
            git_status_rows=[{"status": "M", "path": "src/live/signalRouter.ts"}],
            generated_at="2026-05-30T00:00:00+00:00",
        )

        markdown = render_markdown(payload)
        self.assertIn("This page does not clean, stage, route, fund, or approve orders.", markdown)
        self.assertIn("A visible source intake manifest does not clear the source-hygiene blocker.", markdown)
        self.assertIn("src/live/signalRouter.ts", markdown)

    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^bill-source-intake-manifest-\d{4}-\d{2}-\d{2}\.md$")


if __name__ == "__main__":
    unittest.main()
