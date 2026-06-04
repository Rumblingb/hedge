import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.bill_source_packet_review import (
    HERMES,
    build_review,
    classify_path,
    default_markdown_path,
    render_markdown,
)


class BillSourcePacketReviewTest(unittest.TestCase):
    def test_classifies_execution_shadow_and_research_paths(self):
        self.assertEqual(classify_path("scripts/master_bridge.py", "M")[0], "quarantine-review")
        self.assertEqual(classify_path("scripts/dom_proxy_ohlcv.py", "M")[0], "shadow-only")
        self.assertEqual(classify_path("scripts/dom_edge_bridge.py", "M")[0], "shadow-only")
        self.assertEqual(classify_path("scripts/futures_data_requirements.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_futures_data_requirements.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/futures_nq_research_cycle.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/bill_open_session_data_proof.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/databento_orderflow_feature_smoke.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/alpha_frontier_queue.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/futures_evidence_triage.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_macro_rates_parser_fixture.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_event_capture_cycle.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_event_timestamp_dataset.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_prediction_event_timestamp_dataset.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_evidence_triage.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_event_market_mapping_plan.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_event_lag_watch_review.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_event_lag_manual_review.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_prediction_event_lag_manual_review.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_event_mapping_refinement.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_prediction_event_mapping_refinement.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_event_paper_promotion_gate.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_prediction_event_paper_promotion_gate.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/prediction_event_lag_sensitivity.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_prediction_event_lag_sensitivity.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/bill_next_research_actions.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/bill_clearance_handoff.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/bill_source_hygiene_plan.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("command-center.html", "??")[0], "keep-research")
        self.assertEqual(classify_path("command_center_server.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_command_center_server.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/premarket_risk_brief.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_premarket_risk_brief.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/bill_runtime_architecture_audit.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_bill_runtime_architecture_audit.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/bill_fund_os_completion_audit.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_bill_fund_os_completion_audit.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("ops/activate-bill-workflows.sh", "??")[0], "keep-research")
        self.assertEqual(classify_path("ops/mac-mini/bin/bill-chatgpt-frontdoor", "??")[0], "keep-research")
        self.assertEqual(classify_path("ops/mac-mini/scripts/brain-cycle.sh", "M")[0], "keep-research")
        self.assertEqual(classify_path("scripts/bill_execution_intake_manifest.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/verify_execution_quarantine.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/verify_no_execution_enabled_processes.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_verify_no_execution_processes.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_bill_package_scripts.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/realtime_data_preflight.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_realtime_data_preflight.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/signal_quality_advisor.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_signal_quality_advisor.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/signal_source_truth_audit.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_signal_source_truth_audit.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/topstep_daily_learning.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_topstep_daily_learning.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_topstep_runtime_semantics.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/ai_screener.py", "M")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_ai_screener.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("ai-scientist-templates/financial_strategy/experiment.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("ai-scientist-templates/financial_strategy/ideas.json", "??")[0], "keep-research")
        self.assertEqual(classify_path("ai-scientist-templates/financial_strategy/latex/template.tex", "??")[0], "keep-research")
        self.assertEqual(classify_path("ai-scientist-templates/financial_strategy/seed_ideas.json", "??")[0], "keep-research")
        self.assertEqual(classify_path("ai-scientist-templates/financial_strategy/test_run_known_baselines/final_info.json", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_ai_scientist_financial_template.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/futures_nq_sizing_overlay.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_futures_nq_sizing_overlay.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/bill_research_closed_loop_contract.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/research_seed_target_refresh_plan.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/cron_state_validator.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/paper_source_cards.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/alpha_research_direction_audit.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_alpha_research_direction_audit.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/strategy_factory_one_variable_research.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_strategy_factory_one_variable_research.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/current_alpha_watch.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_current_alpha_watch.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/cot_signal.py", "M")[0], "shadow-only")
        self.assertEqual(classify_path("scripts/donchian_breakout.py", "M")[0], "shadow-only")
        self.assertEqual(classify_path("scripts/ichimoku_full_system.py", "M")[0], "shadow-only")
        self.assertEqual(classify_path("scripts/noise_stepforward_analysis.py", "M")[0], "keep-research")
        self.assertEqual(classify_path("scripts/session_trader.py", "M")[0], "shadow-only")
        self.assertEqual(classify_path("tests/test_futures_strategy_shadow_safety.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_cot_signal_safety.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/backtrader_research_loop.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/cftc_tff_positioning_ingest.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/cot_regime_filter_research.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/noise_area_scalp.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/probe-60m-signals.ts", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_noise_area_scalp_safety.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/qrs_session_bias.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/refresh_futures_research_data.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_qrs_session_bias_safety.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_refresh_futures_research_data.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/vol_noise_scalp.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_vol_noise_scalp_safety.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_cftc_tff_positioning_ingest.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("tests/test_cot_regime_filter_research.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("backtrader_verify.py", "??")[0], "retired-reference")
        self.assertEqual(
            classify_path("docs/TOPSTEP_CLOSED_LOOP_FRAMEWORK_PLAN_2026_05_26.md", "??")[0],
            "historical-reference",
        )
        self.assertEqual(classify_path("scripts/prediction_event_news_rss.py", "??")[0], "keep-research")
        self.assertEqual(classify_path("scripts/new_alpha.py", "??")[0], "review-before-staging")
        self.assertEqual(classify_path("package.json", "M")[0], "dependency-reviewed")
        self.assertEqual(classify_path("package-lock.json", "M")[0], "dependency-reviewed")
        self.assertEqual(classify_path("requirements.bill-alpha.txt", "??")[0], "dependency-reviewed")
        self.assertEqual(
            classify_path("/Users/brain/worktrees/hedge-goal-live:src/live/demoExecution.ts", "sibling-worktree-dirty")[0],
            "quarantine-review",
        )

    def test_runtime_architecture_audit_paths_have_explicit_review_hints(self):
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-01-control-research-scaffold",
                    "paths": [
                        "scripts/bill_runtime_architecture_audit.py",
                        "tests/test_bill_runtime_architecture_audit.py",
                        "scripts/bill_fund_os_completion_audit.py",
                        "tests/test_bill_fund_os_completion_audit.py",
                    ],
                    "pathFootprint": [
                        {"path": "scripts/bill_runtime_architecture_audit.py", "status": "??", "exists": True},
                        {"path": "tests/test_bill_runtime_architecture_audit.py", "status": "??", "exists": True},
                        {"path": "scripts/bill_fund_os_completion_audit.py", "status": "??", "exists": True},
                        {"path": "tests/test_bill_fund_os_completion_audit.py", "status": "??", "exists": True},
                    ],
                    "commands": ["npm run --silent bill:runtime-architecture-audit"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"keep-research": 4})
        self.assertFalse(packet["readyForExecution"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])
        by_path = {row["path"]: row for row in packet["rows"]}
        self.assertEqual(
            by_path["scripts/bill_runtime_architecture_audit.py"]["reviewRecommendation"],
            "keep-runtime-architecture-audit-after-focused-tests",
        )
        self.assertTrue(any(
            "must not mutate n8n DB" in blocker
            for blocker in by_path["scripts/bill_runtime_architecture_audit.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            by_path["tests/test_bill_runtime_architecture_audit.py"]["reviewRecommendation"],
            "keep-runtime-architecture-audit-after-focused-tests",
        )
        self.assertEqual(
            by_path["scripts/bill_fund_os_completion_audit.py"]["reviewRecommendation"],
            "keep-research-fund-os-completion-audit-after-focused-tests",
        )
        self.assertTrue(any(
            "must keep tradingReadinessStatus blocked" in blocker
            for blocker in by_path["scripts/bill_fund_os_completion_audit.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            by_path["tests/test_bill_fund_os_completion_audit.py"]["reviewRecommendation"],
            "keep-research-fund-os-completion-audit-after-focused-tests",
        )

    def test_builds_read_only_packet_review_for_control_futures_and_prediction_lanes(self):
        source_hygiene = {
            "nextReviewPackets": [
                {
                    "id": "packet-01-control-research-scaffold",
                    "title": "Control/research scaffold review packet",
                    "decision": "manual-review-only",
                    "paths": [
                        "scripts/bill_source_intake_manifest.py",
                        "tests/test_bill_source_intake_manifest.py",
                        "scripts/bill_source_packet_review.py",
                        "tests/test_bill_source_packet_review.py",
                        "scripts/alpha_frontier_queue.py",
                        "tests/test_alpha_frontier_queue.py",
                        "scripts/alpha_research_direction_audit.py",
                        "scripts/current_alpha_watch.py",
                        "scripts/bill_source_hygiene_plan.py",
                        "scripts/bill_clearance_handoff.py",
                        "scripts/stale_strategy_claim_guard.py",
                        "tests/test_stale_strategy_claim_guard.py",
                        "tests/test_strategy_evidence_copy.py",
                        "scripts/prediction_no_edge_ledger.py",
                        "tests/test_prediction_no_edge_ledger.py",
                    ],
                    "pathFootprint": [
                        {"path": "scripts/bill_source_intake_manifest.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "tests/test_bill_source_intake_manifest.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/bill_source_packet_review.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "tests/test_bill_source_packet_review.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/alpha_frontier_queue.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "tests/test_alpha_frontier_queue.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/alpha_research_direction_audit.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/current_alpha_watch.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/bill_source_hygiene_plan.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/bill_clearance_handoff.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/stale_strategy_claim_guard.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "tests/test_stale_strategy_claim_guard.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "tests/test_strategy_evidence_copy.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/prediction_no_edge_ledger.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "tests/test_prediction_no_edge_ledger.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                    ],
                    "commands": ["npm run --silent bill:source-intake-manifest"],
                },
                {
                    "id": "packet-05-futures-strategy-lane",
                    "title": "Futures strategy lane packet",
                    "decision": "lane-review-only",
                    "paths": [
                        "scripts/dom_proxy_ohlcv.py",
                        "scripts/futures_data_requirements.py",
                        "scripts/futures_new_alpha.py",
                        "backtrader_verify.py",
                        "docs/TOPSTEP_CLOSED_LOOP_FRAMEWORK_PLAN_2026_05_26.md",
                        "scripts/backtrader_research_loop.py",
                        "scripts/cftc_tff_positioning_ingest.py",
                        "scripts/cot_regime_filter_research.py",
                        "scripts/noise_area_scalp.py",
                        "scripts/probe-60m-signals.ts",
                        "scripts/qrs_session_bias.py",
                        "scripts/refresh_futures_research_data.py",
                        "scripts/vol_noise_scalp.py",
                    ],
                    "pathFootprint": [
                        {"path": "scripts/dom_proxy_ohlcv.py", "status": "M", "exists": True, "trackedDiff": True, "addedLines": 1, "deletedLines": 0},
                        {"path": "scripts/futures_data_requirements.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/futures_new_alpha.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "backtrader_verify.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "docs/TOPSTEP_CLOSED_LOOP_FRAMEWORK_PLAN_2026_05_26.md", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/backtrader_research_loop.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/cftc_tff_positioning_ingest.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/cot_regime_filter_research.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/noise_area_scalp.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/probe-60m-signals.ts", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/qrs_session_bias.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/refresh_futures_research_data.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/vol_noise_scalp.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                    ],
                    "commands": ["npm run --silent bill:futures-evidence-triage || true"],
                },
                {
                    "id": "packet-06-prediction-market-lane",
                    "title": "Prediction-market strategy lane packet",
                    "decision": "lane-review-only",
                    "paths": [
                        "scripts/prediction_event_lag_replay.py",
                        "scripts/prediction_event_mapping_refinement.py",
                        "tests/test_prediction_event_mapping_refinement.py",
                        "scripts/prediction_event_paper_promotion_gate.py",
                        "tests/test_prediction_event_paper_promotion_gate.py",
                        "scripts/prediction_clob_microstructure_feature_audit.py",
                        "tests/test_prediction_clob_microstructure_feature_audit.py",
                        "scripts/polymarket_clob_recorder.mjs",
                    ],
                    "pathFootprint": [
                        {"path": "scripts/prediction_event_lag_replay.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/prediction_event_mapping_refinement.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "tests/test_prediction_event_mapping_refinement.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/prediction_event_paper_promotion_gate.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "tests/test_prediction_event_paper_promotion_gate.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/prediction_clob_microstructure_feature_audit.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "tests/test_prediction_clob_microstructure_feature_audit.py", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                        {"path": "scripts/polymarket_clob_recorder.mjs", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                    ],
                    "commands": ["npm run --silent bill:prediction-evidence-triage"],
                },
                {
                    "id": "packet-07-dependency-review",
                    "title": "Dependency and script wiring review packet",
                    "decision": "dependency-review-only",
                    "paths": ["package.json", "package-lock.json", "requirements.bill-alpha.txt"],
                    "pathFootprint": [
                        {"path": "package.json", "status": "M", "exists": True, "trackedDiff": True, "addedLines": 1, "deletedLines": 0},
                        {"path": "package-lock.json", "status": "M", "exists": True, "trackedDiff": True, "addedLines": 1, "deletedLines": 0},
                        {"path": "requirements.bill-alpha.txt", "status": "??", "exists": True, "trackedDiff": False, "addedLines": 0, "deletedLines": 0},
                    ],
                    "commands": ["npm run --silent bill:alpha-tooling-check"],
                },
                {
                    "id": "packet-08-sibling-worktree-selective-intake",
                    "title": "Sibling worktree selective-intake packet",
                    "decision": "quarantine-selective-review",
                    "paths": [
                        "/Users/brain/worktrees/hedge-goal-live:src/live/demoExecution.ts",
                        "/Users/brain/worktrees/hedge-goal-live:scripts/master_bridge.py",
                    ],
                    "pathFootprint": [
                        {
                            "path": "/Users/brain/worktrees/hedge-goal-live:src/live/demoExecution.ts",
                            "status": "sibling-worktree-dirty",
                            "exists": False,
                            "trackedDiff": False,
                            "addedLines": 0,
                            "deletedLines": 0,
                        },
                        {
                            "path": "/Users/brain/worktrees/hedge-goal-live:scripts/master_bridge.py",
                            "status": "sibling-worktree-dirty",
                            "exists": False,
                            "trackedDiff": False,
                            "addedLines": 0,
                            "deletedLines": 0,
                        },
                    ],
                    "commands": ["npm run --silent bill:sibling-worktree-intake"],
                },
            ],
        }

        payload = build_review(source_hygiene)

        self.assertEqual(payload["decision"], "source-packet-review-visible-execution-locked")
        self.assertFalse(payload["sourceHygieneCleared"])
        self.assertFalse(payload["packetReviewCleared"])
        self.assertFalse(payload["safeToStageAutomatically"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertEqual(payload["missingPackets"], [])
        self.assertEqual(payload["reviewedPacketCount"], 5)
        self.assertEqual(payload["classificationCounts"]["shadow-only"], 1)
        self.assertEqual(payload["classificationCounts"]["keep-research"], 32)
        self.assertEqual(payload["classificationCounts"]["dependency-reviewed"], 3)
        self.assertEqual(payload["classificationCounts"]["review-before-staging"], 1)
        self.assertEqual(payload["classificationCounts"]["retired-reference"], 1)
        self.assertEqual(payload["classificationCounts"]["historical-reference"], 1)
        self.assertEqual(payload["classificationCounts"]["quarantine-review"], 2)
        self.assertEqual(payload["keepResearchCount"], 32)
        self.assertEqual(payload["shadowOnlyCount"], 1)
        self.assertEqual(payload["dependencyReviewedCount"], 3)
        self.assertEqual(payload["reviewBeforeStagingCount"], 1)
        self.assertEqual(payload["quarantineReviewCount"], 2)
        self.assertTrue(payload["requiresOperatorDecision"])
        self.assertEqual(payload["topReviewBeforeStaging"], ["scripts/futures_new_alpha.py"])
        self.assertEqual(
            payload["topQuarantineReview"],
            [
                "/Users/brain/worktrees/hedge-goal-live:src/live/demoExecution.ts",
                "/Users/brain/worktrees/hedge-goal-live:scripts/master_bridge.py",
            ],
        )
        self.assertEqual(len(payload["packetSummaries"]), 5)
        self.assertEqual(payload["packetSummaries"][0]["id"], "packet-01-control-research-scaffold")
        self.assertEqual(payload["packetSummaries"][0]["firstCommand"], "npm run --silent bill:source-intake-manifest")
        self.assertFalse(payload["packetSummaries"][0]["safeToStageAutomatically"])
        self.assertFalse(payload["packetSummaries"][0]["writesOrders"])
        self.assertTrue(payload["packetSummaries"][0]["researchOnly"])
        proposal = payload["manualClearanceProposal"]
        self.assertEqual(proposal["decision"], "manual-clearance-proposal-only")
        self.assertFalse(proposal["safeToStageAutomatically"])
        self.assertFalse(proposal["writesOrders"])
        self.assertFalse(proposal["touchesBroker"])
        self.assertEqual(proposal["laneProposals"][0]["lane"], "control-research")
        self.assertIn("scripts/bill_clearance_handoff.py", proposal["laneProposals"][0]["keepResearchCandidates"])
        self.assertEqual(proposal["laneProposals"][1]["lane"], "futures")
        self.assertEqual(
            proposal["laneProposals"][1]["reviewFirst"],
            ["scripts/futures_new_alpha.py"],
        )
        self.assertIn("scripts/futures_data_requirements.py", proposal["laneProposals"][1]["keepResearchCandidates"])
        self.assertIn("scripts/backtrader_research_loop.py", proposal["laneProposals"][1]["keepResearchCandidates"])
        self.assertIn("scripts/cftc_tff_positioning_ingest.py", proposal["laneProposals"][1]["keepResearchCandidates"])
        self.assertIn("scripts/cot_regime_filter_research.py", proposal["laneProposals"][1]["keepResearchCandidates"])
        self.assertIn("scripts/noise_area_scalp.py", proposal["laneProposals"][1]["keepResearchCandidates"])
        self.assertIn("scripts/probe-60m-signals.ts", proposal["laneProposals"][1]["keepResearchCandidates"])
        self.assertIn("scripts/qrs_session_bias.py", proposal["laneProposals"][1]["keepResearchCandidates"])
        self.assertIn("scripts/refresh_futures_research_data.py", proposal["laneProposals"][1]["keepResearchCandidates"])
        self.assertIn("scripts/vol_noise_scalp.py", proposal["laneProposals"][1]["keepResearchCandidates"])
        self.assertIn("scripts/dom_proxy_ohlcv.py", proposal["laneProposals"][1]["shadowOnly"])
        self.assertEqual(proposal["laneProposals"][2]["lane"], "prediction-markets")
        self.assertIn("scripts/prediction_event_mapping_refinement.py", proposal["laneProposals"][2]["keepResearchCandidates"])
        self.assertIn("tests/test_prediction_event_mapping_refinement.py", proposal["laneProposals"][2]["keepResearchCandidates"])
        self.assertIn("scripts/prediction_event_paper_promotion_gate.py", proposal["laneProposals"][2]["keepResearchCandidates"])
        self.assertIn("tests/test_prediction_event_paper_promotion_gate.py", proposal["laneProposals"][2]["keepResearchCandidates"])
        self.assertEqual(proposal["laneProposals"][2]["classificationCounts"], {"keep-research": 8})
        self.assertEqual(proposal["laneProposals"][2]["omittedCounts"]["keepResearchCandidates"], 0)
        self.assertIn("npm run --silent bill:clearance-evidence", proposal["nextCommands"])
        by_id = {packet["id"]: packet for packet in payload["packets"]}
        self.assertEqual(by_id["packet-01-control-research-scaffold"]["lane"], "control-research")
        control_rows = {
            row["path"]: row
            for row in by_id["packet-01-control-research-scaffold"]["rows"]
        }
        prediction_rows = {
            row["path"]: row
            for row in by_id["packet-06-prediction-market-lane"]["rows"]
        }
        self.assertEqual(
            prediction_rows["scripts/prediction_event_paper_promotion_gate.py"]["reviewRecommendation"],
            "keep-research-paper-gate-after-prediction-gate-tests",
        )
        self.assertTrue(any(
            "fillable live books separate from paper-grade no-lookahead repriced windows" in blocker
            for blocker in prediction_rows["scripts/prediction_event_paper_promotion_gate.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            prediction_rows["tests/test_prediction_event_paper_promotion_gate.py"]["reviewRecommendation"],
            "keep-research-paper-gate-after-prediction-gate-tests",
        )
        self.assertEqual(
            control_rows["scripts/prediction_no_edge_ledger.py"]["reviewRecommendation"],
            "keep-research-no-edge-memory-after-focused-tests",
        )
        self.assertTrue(any(
            "direct polymarket CLOB edge-gate" in blocker
            for blocker in control_rows["scripts/prediction_no_edge_ledger.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            control_rows["tests/test_prediction_no_edge_ledger.py"]["classification"],
            "keep-research",
        )
        self.assertEqual(
            control_rows["scripts/alpha_frontier_queue.py"]["reviewRecommendation"],
            "keep-research-frontier-after-no-edge-and-queue-tests",
        )
        self.assertTrue(any(
            "must not rerun CLOB fixed forms" in blocker
            for blocker in control_rows["scripts/alpha_frontier_queue.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            control_rows["scripts/bill_source_intake_manifest.py"]["reviewRecommendation"],
            "keep-source-visibility-after-intake-and-hygiene-tests",
        )
        self.assertTrue(any(
            "sourceClean must remain false" in blocker
            for blocker in control_rows["scripts/bill_source_intake_manifest.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            control_rows["scripts/bill_source_packet_review.py"]["reviewRecommendation"],
            "keep-source-packet-review-after-focused-tests",
        )
        self.assertTrue(any(
            "must not stage files automatically" in blocker
            for blocker in control_rows["scripts/bill_source_packet_review.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            control_rows["scripts/stale_strategy_claim_guard.py"]["reviewRecommendation"],
            "keep-stale-claim-guard-after-focused-tests",
        )
        self.assertIn(
            "old strategy audits",
            control_rows["scripts/stale_strategy_claim_guard.py"]["reviewReason"],
        )
        self.assertEqual(
            control_rows["tests/test_stale_strategy_claim_guard.py"]["classification"],
            "keep-research",
        )
        self.assertEqual(
            control_rows["tests/test_strategy_evidence_copy.py"]["reviewRecommendation"],
            "keep-strategy-evidence-copy-guard-after-focused-tests",
        )
        self.assertIn(
            "15m/60m",
            control_rows["tests/test_strategy_evidence_copy.py"]["reviewReason"],
        )
        self.assertEqual(by_id["packet-05-futures-strategy-lane"]["lane"], "futures")
        self.assertEqual(by_id["packet-05-futures-strategy-lane"]["firstCommand"], "npm run --silent bill:futures-evidence-triage || true")
        self.assertEqual(by_id["packet-06-prediction-market-lane"]["lane"], "prediction-markets")
        self.assertEqual(by_id["packet-06-prediction-market-lane"]["firstCommand"], "npm run --silent bill:prediction-evidence-triage")
        self.assertEqual(by_id["packet-07-dependency-review"]["lane"], "dependencies")
        self.assertEqual(by_id["packet-07-dependency-review"]["firstCommand"], "npm run --silent bill:alpha-tooling-check")
        self.assertEqual(by_id["packet-07-dependency-review"]["classificationCounts"], {"dependency-reviewed": 3})
        self.assertEqual(by_id["packet-08-sibling-worktree-selective-intake"]["lane"], "sibling-worktree")
        self.assertEqual(by_id["packet-08-sibling-worktree-selective-intake"]["decision"], "quarantine-review-required")
        self.assertEqual(by_id["packet-08-sibling-worktree-selective-intake"]["classificationCounts"], {"quarantine-review": 2})
        self.assertEqual(by_id["packet-05-futures-strategy-lane"]["rows"][0]["classification"], "shadow-only")
        prediction_rows = {
            row["path"]: row
            for row in by_id["packet-06-prediction-market-lane"]["rows"]
        }
        self.assertEqual(
            prediction_rows["scripts/prediction_event_mapping_refinement.py"]["reviewRecommendation"],
            "keep-research-mapping-gate-after-focused-tests",
        )
        self.assertTrue(any(
            "readyForPaper=false" in blocker
            for blocker in prediction_rows["scripts/prediction_event_mapping_refinement.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            prediction_rows["scripts/prediction_clob_microstructure_feature_audit.py"]["reviewRecommendation"],
            "keep-research-clob-feature-audit-after-focused-tests",
        )
        self.assertTrue(any(
            "no-edge ledger" in blocker
            for blocker in prediction_rows["scripts/prediction_clob_microstructure_feature_audit.py"]["reviewBlockers"]
        ))

        markdown = render_markdown(payload)

        self.assertIn("Bill Source Packet Review", markdown)
        self.assertIn("packet-01-control-research-scaffold", markdown)
        self.assertIn("packet-05-futures-strategy-lane", markdown)
        self.assertIn("packet-06-prediction-market-lane", markdown)
        self.assertIn("packet-07-dependency-review", markdown)
        self.assertIn("packet-08-sibling-worktree-selective-intake", markdown)
        self.assertIn("non-canonical sibling worktree path requires selective intake", markdown)
        self.assertIn("Manual Clearance Proposal", markdown)
        self.assertIn("manual-clearance-proposal-only", markdown)
        self.assertIn("Review before staging count", markdown)
        self.assertIn("Quarantine review count", markdown)
        self.assertIn("Requires operator decision", markdown)
        self.assertIn("Hard Blockers", markdown)
        self.assertIn("operator approval required before staging", markdown)
        self.assertIn("Next Commands", markdown)
        self.assertIn("npm run --silent bill:goal-completion-audit", markdown)
        self.assertIn("scripts/futures_new_alpha.py", markdown)
        self.assertIn("retire-or-replace-with-backtrader-research-loop", markdown)
        self.assertIn("keep-as-historical-reference-only", markdown)
        self.assertIn("keep-research-evidence-only-after-backtrader-and-source-tests", markdown)
        self.assertIn("keep-research-evidence-only-after-cftc-ingest-tests", markdown)
        self.assertIn("keep-research-evidence-only-after-cot-filter-tests", markdown)
        self.assertIn("hardcoded absolute data paths", markdown)
        self.assertIn("not a current route approval source", markdown)
        self.assertIn("dependency-and-script-review-before-staging", markdown)
        self.assertIn("keep-research-mapping-gate-after-focused-tests", markdown)
        self.assertIn("keep-research-no-edge-memory-after-focused-tests", markdown)
        self.assertIn("future agents do not threshold-mine", markdown)
        self.assertIn("Shadow/proxy signal files cannot approve execution.", markdown)

    def test_packet_review_preserves_source_hygiene_risk_metadata_without_auto_staging(self):
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-05-futures-strategy-lane",
                    "title": "Futures strategy lane packet",
                    "decision": "lane-review-only",
                    "pathCount": 2,
                    "diffSummary": {
                        "pathCount": 2,
                        "existingPathCount": 2,
                        "trackedDiffPathCount": 0,
                        "addedLines": 0,
                        "deletedLines": 0,
                        "statusCounts": {"??": 2},
                    },
                    "manualStageEligible": True,
                    "manualStageCommand": "git add -- scripts/futures_evidence_triage.py tests/test_futures_evidence_triage.py",
                    "manualStageWarning": "Manual operator review required; do not run this automatically.",
                    "paths": [
                        "scripts/futures_evidence_triage.py",
                        "tests/test_futures_evidence_triage.py",
                    ],
                    "pathFootprint": [
                        {"path": "scripts/futures_evidence_triage.py", "status": "??", "exists": True},
                        {"path": "tests/test_futures_evidence_triage.py", "status": "??", "exists": True},
                    ],
                    "commands": ["npm run --silent bill:futures-evidence-triage"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertTrue(packet["manualStageEligible"])
        self.assertTrue(packet["manualStageOperatorOnly"])
        self.assertFalse(packet["safeToStageAutomatically"])
        self.assertEqual(packet["sourcePacketPathCount"], 2)
        self.assertEqual(packet["diffSummary"]["statusCounts"], {"??": 2})
        self.assertIn("git add --", packet["manualStageCommand"])
        self.assertIn("do not run this automatically", packet["manualStageWarning"])

        summary = payload["packetSummaries"][0]
        self.assertTrue(summary["manualStageEligible"])
        self.assertFalse(summary["safeToStageAutomatically"])
        self.assertEqual(summary["diffSummary"]["trackedDiffPathCount"], 0)

        lane = payload["manualClearanceProposal"]["laneProposals"][0]
        self.assertTrue(lane["manualStageEligible"])
        self.assertEqual(lane["packetDecision"], "lane-review-only")
        self.assertEqual(lane["diffSummary"]["pathCount"], 2)
        self.assertFalse(lane["safeToStageAutomatically"])

        markdown = render_markdown(payload)
        self.assertIn("Manual-stage eligible: `True`", markdown)
        self.assertIn("Safe to stage automatically: `False`", markdown)

    def test_missing_packet_is_visible_and_still_locked(self):
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-05-futures-strategy-lane",
                    "paths": ["scripts/master_bridge.py"],
                    "pathFootprint": [{"path": "scripts/master_bridge.py", "status": "M"}],
                    "commands": ["npm run --silent bill:futures-evidence-triage || true"],
                },
            ],
        })

        self.assertEqual(payload["missingPackets"], ["packet-01-control-research-scaffold", "packet-06-prediction-market-lane"])
        self.assertEqual(payload["packets"][0]["decision"], "quarantine-review-required")
        self.assertFalse(payload["automaticCleanupAllowed"])
        self.assertFalse(payload["movesFunds"])

    def test_prediction_manual_review_and_next_actions_get_precise_review_hints(self):
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-01-control-research-scaffold",
                    "paths": [
                        "scripts/bill_next_research_actions.py",
                        "tests/test_bill_next_research_actions.py",
                    ],
                    "pathFootprint": [
                        {"path": "scripts/bill_next_research_actions.py", "status": "??", "exists": True},
                        {"path": "tests/test_bill_next_research_actions.py", "status": "??", "exists": True},
                    ],
                    "commands": ["npm run --silent bill:next-research-actions"],
                },
                {
                    "id": "packet-06-prediction-market-lane",
                    "paths": [
                        "scripts/prediction_event_lag_manual_review.py",
                        "tests/test_prediction_event_lag_manual_review.py",
                    ],
                    "pathFootprint": [
                        {"path": "scripts/prediction_event_lag_manual_review.py", "status": "??", "exists": True},
                        {"path": "tests/test_prediction_event_lag_manual_review.py", "status": "??", "exists": True},
                    ],
                    "commands": ["npm run --silent bill:prediction-event-lag-manual-review"],
                },
            ],
        })

        self.assertFalse(payload["safeToStageAutomatically"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        by_packet = {packet["id"]: packet for packet in payload["packets"]}
        control_rows = {row["path"]: row for row in by_packet["packet-01-control-research-scaffold"]["rows"]}
        prediction_rows = {row["path"]: row for row in by_packet["packet-06-prediction-market-lane"]["rows"]}

        self.assertEqual(
            prediction_rows["scripts/prediction_event_lag_manual_review.py"]["reviewRecommendation"],
            "keep-research-manual-event-lag-review-after-focused-tests",
        )
        self.assertTrue(any(
            "forwardCaptureObserved from forwardCaptureEvidencePresent" in blocker
            for blocker in prediction_rows["scripts/prediction_event_lag_manual_review.py"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "observed public CLOB capture without fillability" in blocker
            for blocker in prediction_rows["scripts/prediction_event_lag_manual_review.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            prediction_rows["tests/test_prediction_event_lag_manual_review.py"]["reviewRecommendation"],
            "keep-research-manual-event-lag-review-after-focused-tests",
        )
        self.assertEqual(
            control_rows["scripts/bill_next_research_actions.py"]["reviewRecommendation"],
            "keep-research-queue-after-control-tests",
        )
        self.assertTrue(any(
            "forward-public-clob-capture-observed-but-not-paper-grade" in blocker
            for blocker in control_rows["scripts/bill_next_research_actions.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            control_rows["tests/test_bill_next_research_actions.py"]["reviewRecommendation"],
            "keep-research-queue-after-control-tests",
        )

        markdown = render_markdown(payload)
        self.assertIn("keep-research-manual-event-lag-review-after-focused-tests", markdown)
        self.assertIn("forwardCaptureObserved", markdown)
        self.assertIn("forward-public-clob-capture-observed-but-not-paper-grade", markdown)

    def test_prediction_packet_core_paths_have_explicit_review_hints(self):
        prediction_paths = [
            "scripts/prediction_event_capture_cycle.py",
            "tests/test_prediction_event_capture_cycle.py",
            "scripts/prediction_event_lag_sensitivity.py",
            "tests/test_prediction_event_lag_sensitivity.py",
            "scripts/prediction_event_lag_watch_review.py",
            "tests/test_prediction_event_lag_watch_review.py",
            "scripts/prediction_event_lag_manual_review.py",
            "tests/test_prediction_event_lag_manual_review.py",
            "scripts/prediction_event_mapping_refinement.py",
            "tests/test_prediction_event_mapping_refinement.py",
            "scripts/prediction_event_lag_replay.py",
            "tests/test_prediction_event_lag_replay.py",
            "scripts/prediction_evidence_triage.py",
            "tests/test_prediction_evidence_triage.py",
            "scripts/polymarket_clob_recorder.mjs",
            "tests/polymarketClobRecorder.test.ts",
            "scripts/polymarket_clob_persistence_lab.mjs",
            "tests/polymarketClobPersistence.test.ts",
            "scripts/prediction_macro_rates_requirements.py",
            "tests/test_prediction_macro_rates_requirements.py",
            "scripts/prediction_macro_rates_cross_source_replay.py",
            "tests/test_prediction_macro_rates_cross_source_replay.py",
            "scripts/prediction_macro_rates_parser_fixture.py",
            "tests/test_prediction_macro_rates_parser_fixture.py",
        ]
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-06-prediction-market-lane",
                    "paths": prediction_paths,
                    "pathFootprint": [
                        {"path": path, "status": "??", "exists": True}
                        for path in prediction_paths
                    ],
                    "commands": ["npm run --silent bill:prediction-evidence-triage"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"keep-research": len(prediction_paths)})
        self.assertFalse(packet["readyForExecution"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])
        by_path = {row["path"]: row for row in packet["rows"]}
        missing_hints = [
            path
            for path, row in by_path.items()
            if not row["reviewRecommendation"] or not row["reviewBlockers"]
        ]
        self.assertEqual(missing_hints, [])
        self.assertTrue(any(
            "public/read-only endpoints only" in blocker
            for blocker in by_path["scripts/polymarket_clob_recorder.mjs"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "must not rerun rejected fixed CLOB forms" in blocker
            for blocker in by_path["scripts/polymarket_clob_persistence_lab.mjs"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "too-few-source-specific-sample-rows" in blocker
            for blocker in by_path["scripts/prediction_macro_rates_cross_source_replay.py"]["reviewBlockers"]
        ))

        markdown = render_markdown(payload)
        self.assertIn("keep-research-public-clob-recorder-after-node-tests", markdown)
        self.assertIn("keep-research-macro-rates-cross-source-replay-after-focused-tests", markdown)
        self.assertIn("keep-research-event-lag-replay-after-focused-tests", markdown)

    def test_modified_futures_strategy_files_get_review_hints_without_promotion(self):
        futures_paths = [
            "scripts/cot_signal.py",
            "scripts/donchian_breakout.py",
            "scripts/ichimoku_full_system.py",
            "scripts/noise_stepforward_analysis.py",
            "scripts/noise_area_scalp.py",
            "scripts/session_trader.py",
            "scripts/probe-60m-signals.ts",
            "scripts/qrs_session_bias.py",
            "scripts/refresh_futures_research_data.py",
            "scripts/vol_noise_scalp.py",
        ]
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-05-futures-strategy-lane",
                    "paths": futures_paths,
                    "pathFootprint": [
                        {"path": path, "status": "M", "exists": True, "trackedDiff": True}
                        for path in futures_paths
                    ],
                    "commands": ["npm run --silent bill:futures-evidence-triage || true"],
                },
            ],
        })

        futures_packet = payload["packets"][0]
        self.assertEqual(futures_packet["classificationCounts"], {"keep-research": 6, "shadow-only": 4})
        self.assertFalse(futures_packet["safeToStageAutomatically"])
        self.assertFalse(futures_packet["readyForExecution"])
        self.assertEqual(
            payload["manualClearanceProposal"]["laneProposals"][0]["reviewFirst"],
            [],
        )
        self.assertIn(
            "scripts/noise_stepforward_analysis.py",
            payload["manualClearanceProposal"]["laneProposals"][0]["keepResearchCandidates"],
        )
        self.assertIn(
            "scripts/noise_area_scalp.py",
            payload["manualClearanceProposal"]["laneProposals"][0]["keepResearchCandidates"],
        )
        self.assertIn(
            "scripts/probe-60m-signals.ts",
            payload["manualClearanceProposal"]["laneProposals"][0]["keepResearchCandidates"],
        )
        self.assertIn(
            "scripts/qrs_session_bias.py",
            payload["manualClearanceProposal"]["laneProposals"][0]["keepResearchCandidates"],
        )
        self.assertIn(
            "scripts/refresh_futures_research_data.py",
            payload["manualClearanceProposal"]["laneProposals"][0]["keepResearchCandidates"],
        )
        self.assertIn(
            "scripts/vol_noise_scalp.py",
            payload["manualClearanceProposal"]["laneProposals"][0]["keepResearchCandidates"],
        )
        self.assertIn(
            "scripts/cot_signal.py",
            payload["manualClearanceProposal"]["laneProposals"][0]["shadowOnly"],
        )
        by_path = {row["path"]: row for row in futures_packet["rows"]}
        for path in futures_paths:
            self.assertIsNotNone(by_path[path]["reviewRecommendation"])
            self.assertTrue(by_path[path]["reviewBlockers"])

        self.assertEqual(by_path["scripts/cot_signal.py"]["classification"], "shadow-only")
        self.assertEqual(by_path["scripts/donchian_breakout.py"]["classification"], "shadow-only")
        self.assertEqual(by_path["scripts/ichimoku_full_system.py"]["classification"], "shadow-only")
        self.assertEqual(by_path["scripts/noise_stepforward_analysis.py"]["classification"], "keep-research")
        self.assertEqual(by_path["scripts/session_trader.py"]["classification"], "shadow-only")
        self.assertIn("weekly delayed positioning data only", by_path["scripts/cot_signal.py"]["reviewBlockers"])
        self.assertIn("requires fresh NQ data parity proof", by_path["scripts/session_trader.py"]["reviewBlockers"])
        self.assertEqual(
            by_path["scripts/noise_stepforward_analysis.py"]["reviewRecommendation"],
            "keep-research-evidence-only-after-diff-review",
        )
        markdown = render_markdown(payload)
        self.assertIn("keep-research-shadow-only-after-diff-review", markdown)
        self.assertIn("must keep no-trade behavior when recent data is insufficient", markdown)

    def test_premarket_risk_brief_control_pair_is_keep_research_not_review_first(self):
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-01-control-research-scaffold",
                    "paths": [
                        "scripts/premarket_risk_brief.py",
                        "tests/test_premarket_risk_brief.py",
                    ],
                    "pathFootprint": [
                        {
                            "path": "scripts/premarket_risk_brief.py",
                            "status": "M",
                            "exists": True,
                            "trackedDiff": True,
                        },
                        {
                            "path": "tests/test_premarket_risk_brief.py",
                            "status": "M",
                            "exists": True,
                            "trackedDiff": True,
                        },
                    ],
                    "commands": ["npm run --silent bill:premarket-risk-brief"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"keep-research": 2})
        self.assertEqual(payload["reviewBeforeStagingCount"], 0)
        self.assertEqual(payload["topReviewBeforeStaging"], [])
        self.assertFalse(payload["safeToStageAutomatically"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        proposal = payload["manualClearanceProposal"]["laneProposals"][0]
        self.assertEqual(proposal["reviewFirst"], [])
        self.assertIn("scripts/premarket_risk_brief.py", proposal["keepResearchCandidates"])
        self.assertIn("tests/test_premarket_risk_brief.py", proposal["keepResearchCandidates"])
        by_path = {row["path"]: row for row in packet["rows"]}
        self.assertEqual(
            by_path["scripts/premarket_risk_brief.py"]["reviewRecommendation"],
            "keep-research-premarket-risk-brief-after-focused-tests",
        )
        self.assertIn(
            "NO_TRADE_ALGO",
            " ".join(by_path["scripts/premarket_risk_brief.py"]["reviewBlockers"]),
        )

    def test_futures_packet_core_paths_have_explicit_review_hints(self):
        futures_paths = [
            "src/data/csv.ts",
            "src/engine/researchFabric.ts",
            "tests/research.test.ts",
            "scripts/futures_evidence_triage.py",
            "tests/test_futures_evidence_triage.py",
            "scripts/gex_backtest.py",
            "tests/test_gex_backtest.py",
            "scripts/strategy_diagnostic.py",
            "scripts/strategy_signal_diagnostic.py",
            "tests/test_strategy_diagnostic.py",
            "tests/test_strategy_signal_diagnostic.py",
            "scripts/futures_nq_historical_session_replay.py",
            "tests/test_futures_nq_historical_session_replay.py",
            "scripts/futures_nq_historical_session_walkforward.py",
            "tests/test_futures_nq_historical_session_walkforward.py",
            "scripts/futures_nq_historical_session_cost_stress.py",
            "tests/test_futures_nq_historical_session_cost_stress.py",
            "scripts/futures_nq_research_cycle.py",
            "scripts/futures_data_requirements.py",
            "tests/test_futures_data_requirements.py",
            "scripts/futures_cost_slippage_gate.py",
            "scripts/databento_orderflow_feature_smoke.py",
            "tests/test_databento_orderflow_feature_smoke.py",
            "scripts/databento_realtime_smoke.py",
            "tests/test_databento_realtime_smoke.py",
            "scripts/futures_data_quality_snapshot.py",
            "tests/test_futures_data_quality_snapshot.py",
            "scripts/futures_no_edge_ledger.py",
            "tests/test_futures_no_edge_ledger.py",
            "scripts/futures_nq_current_data_parity.py",
            "tests/test_futures_nq_current_data_parity.py",
            "scripts/futures_nq_historical_coverage_audit.py",
            "scripts/futures_nq_session_structure_audit.py",
            "scripts/microstructure_filter.py",
            "scripts/vol_regime_oos_replay.py",
        ]
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-05-futures-strategy-lane",
                    "paths": futures_paths + ["scripts/futures_new_alpha.py"],
                    "pathFootprint": [
                        {"path": path, "status": "??", "exists": True}
                        for path in futures_paths + ["scripts/futures_new_alpha.py"]
                    ],
                    "commands": ["npm run --silent bill:futures-evidence-triage || true"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"keep-research": len(futures_paths), "review-before-staging": 1})
        self.assertFalse(packet["readyForExecution"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])
        by_path = {row["path"]: row for row in packet["rows"]}
        missing_hints = [
            path
            for path in futures_paths
            if not by_path[path]["reviewRecommendation"] or not by_path[path]["reviewBlockers"]
        ]
        self.assertEqual(missing_hints, [])
        self.assertEqual(by_path["scripts/futures_new_alpha.py"]["classification"], "review-before-staging")
        self.assertIsNone(by_path["scripts/futures_new_alpha.py"]["reviewRecommendation"])
        self.assertTrue(any(
            "historical/OOS evidence must stay separate from current broker-grade data parity" in blocker
            for blocker in by_path["scripts/futures_nq_research_cycle.py"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "Databento/order-flow smoke must not approve routing" in blocker
            for blocker in by_path["scripts/databento_orderflow_feature_smoke.py"]["reviewBlockers"]
        ))

        markdown = render_markdown(payload)
        self.assertIn("keep-research-futures-evidence-gate-after-focused-tests", markdown)
        self.assertIn("historical/OOS evidence must stay separate", markdown)

    def test_dependency_files_get_review_hints_without_clearing_source_hygiene(self):
        dependency_paths = ["package.json", "package-lock.json", "requirements.bill-alpha.txt"]
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-01-control-research-scaffold",
                    "paths": dependency_paths,
                    "pathFootprint": [
                        {"path": path, "status": "M", "exists": True, "trackedDiff": True}
                        for path in dependency_paths
                    ],
                    "commands": ["npm run --silent bill:source-intake-manifest"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"dependency-reviewed": 3})
        self.assertFalse(packet["safeToStageAutomatically"])
        self.assertFalse(packet["readyForExecution"])
        self.assertFalse(payload["sourceHygieneCleared"])
        self.assertEqual(payload["manualClearanceProposal"]["laneProposals"][0]["reviewFirst"], [])
        self.assertEqual(
            payload["manualClearanceProposal"]["laneProposals"][0]["dependencyReviewed"],
            dependency_paths,
        )
        by_path = {row["path"]: row for row in packet["rows"]}
        self.assertEqual(
            by_path["package.json"]["reviewRecommendation"],
            "dependency-and-script-review-before-staging",
        )
        self.assertIn("review package-lock.json together with package.json", by_path["package.json"]["reviewBlockers"])
        self.assertIn("review direct ws dependency and transitive resolution changes", by_path["package-lock.json"]["reviewBlockers"])
        self.assertIn("run alpha tooling check in the active venv", by_path["requirements.bill-alpha.txt"]["reviewBlockers"])

        markdown = render_markdown(payload)
        self.assertIn("dependency-and-script-review-before-staging", markdown)
        self.assertIn("tooling success does not approve broker, funding, paper, demo, or live execution", markdown)

    def test_command_center_paths_have_explicit_read_only_review_hints(self):
        paths = ["command-center.html", "command_center_server.py", "tests/test_command_center_server.py"]
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-01-control-research-scaffold",
                    "paths": paths,
                    "pathFootprint": [
                        {"path": path, "status": "??", "exists": True}
                        for path in paths
                    ],
                    "commands": ["python3 -m unittest tests.test_command_center_server -q"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"keep-research": 3})
        self.assertFalse(packet["safeToStageAutomatically"])
        self.assertFalse(packet["readyForExecution"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])
        by_path = {row["path"]: row for row in packet["rows"]}
        self.assertEqual(
            by_path["command-center.html"]["reviewRecommendation"],
            "keep-command-center-observability-after-focused-tests",
        )
        self.assertTrue(any(
            "not expose buttons or flows that submit orders" in blocker
            for blocker in by_path["command-center.html"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "must not write orders" in blocker
            for blocker in by_path["command_center_server.py"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "green tests do not approve broker use" in blocker
            for blocker in by_path["tests/test_command_center_server.py"]["reviewBlockers"]
        ))

        markdown = render_markdown(payload)
        self.assertIn("keep-command-center-observability-after-focused-tests", markdown)
        self.assertIn("dashboard/control-plane view only", markdown)

    def test_ollama_adapter_test_has_explicit_llm_tooling_hint(self):
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-01-control-research-scaffold",
                    "paths": ["tests/ollamaAdapter.test.ts"],
                    "pathFootprint": [
                        {"path": "tests/ollamaAdapter.test.ts", "status": "M", "exists": True}
                    ],
                    "commands": ["npm run --silent test -- tests/ollamaAdapter.test.ts"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"keep-research": 1})
        self.assertFalse(packet["readyForExecution"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])
        row = packet["rows"][0]
        self.assertEqual(row["reviewRecommendation"], "keep-research-llm-adapter-tests-after-node-suite")
        self.assertTrue(any("network calls mocked" in blocker for blocker in row["reviewBlockers"]))
        self.assertTrue(any("must not grant LLM output route" in blocker for blocker in row["reviewBlockers"]))

    def test_topstep_readonly_market_data_paths_have_explicit_review_hints(self):
        paths = [
            "scripts/topstep_market_data_smoke.py",
            "tests/test_topstep_market_data_smoke.py",
            "scripts/topstep_readonly_bar_archive.py",
            "tests/test_topstep_readonly_bar_archive.py",
        ]
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-05-futures-strategy-lane",
                    "paths": paths,
                    "pathFootprint": [
                        {"path": path, "status": "??", "exists": True}
                        for path in paths
                    ],
                    "commands": ["npm run --silent bill:open-session-data-proof -- --run-data-only"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"keep-research": 4})
        self.assertFalse(packet["safeToStageAutomatically"])
        self.assertFalse(packet["readyForExecution"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])
        by_path = {row["path"]: row for row in packet["rows"]}
        self.assertEqual(
            by_path["scripts/topstep_market_data_smoke.py"]["reviewRecommendation"],
            "keep-research-topstep-readonly-market-data-after-focused-tests",
        )
        self.assertEqual(
            by_path["scripts/topstep_readonly_bar_archive.py"]["reviewRecommendation"],
            "keep-research-topstep-readonly-bar-archive-after-focused-tests",
        )
        self.assertTrue(any(
            "RH_TOPSTEP_READ_ONLY=true" in blocker
            for blocker in by_path["scripts/topstep_market_data_smoke.py"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "Topstep session safety is paused" in blocker
            for blocker in by_path["scripts/topstep_market_data_smoke.py"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "never call order" in blocker
            for blocker in by_path["scripts/topstep_market_data_smoke.py"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "session-count depth" in blocker
            for blocker in by_path["scripts/topstep_readonly_bar_archive.py"]["reviewBlockers"]
        ))

        markdown = render_markdown(payload)
        self.assertIn("keep-research-topstep-readonly-market-data-after-focused-tests", markdown)
        self.assertIn("read-only market-data mode", markdown)

    def test_alpha_direction_paths_have_explicit_review_hints(self):
        paths = ["scripts/alpha_research_direction_audit.py", "tests/test_alpha_research_direction_audit.py"]
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-01-control-research-scaffold",
                    "paths": paths,
                    "pathFootprint": [
                        {"path": path, "status": "M", "exists": True}
                        for path in paths
                    ],
                    "commands": ["python3 -m unittest tests.test_alpha_research_direction_audit -q"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"keep-research": 2})
        self.assertFalse(packet["safeToStageAutomatically"])
        self.assertFalse(packet["readyForExecution"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])
        by_path = {row["path"]: row for row in packet["rows"]}
        self.assertEqual(
            by_path["scripts/alpha_research_direction_audit.py"]["reviewRecommendation"],
            "keep-research-direction-after-focused-tests",
        )
        self.assertEqual(
            by_path["tests/test_alpha_research_direction_audit.py"]["reviewRecommendation"],
            "keep-research-direction-after-focused-tests",
        )
        self.assertTrue(any(
            "not broker, paper, demo, live, or funding approval" in blocker
            for blocker in by_path["tests/test_alpha_research_direction_audit.py"]["reviewBlockers"]
        ))

    def test_research_seed_triage_paths_have_explicit_review_hints(self):
        paths = ["scripts/research_seed_triage.py", "tests/test_research_seed_triage.py"]
        payload = build_review({
            "nextReviewPackets": [
                {
                    "id": "packet-01-control-research-scaffold",
                    "paths": paths,
                    "pathFootprint": [
                        {"path": path, "status": "??", "exists": True}
                        for path in paths
                    ],
                    "commands": ["npm run --silent bill:research-seed-triage"],
                },
            ],
        })

        packet = payload["packets"][0]
        self.assertEqual(packet["classificationCounts"], {"keep-research": 2})
        self.assertFalse(packet["readyForExecution"])
        self.assertFalse(packet["writesOrders"])
        self.assertFalse(packet["touchesBroker"])
        by_path = {row["path"]: row for row in packet["rows"]}
        self.assertEqual(
            by_path["scripts/research_seed_triage.py"]["reviewRecommendation"],
            "keep-research-seed-triage-after-focused-tests",
        )
        self.assertTrue(any(
            "source provenance, not strategy edge evidence" in blocker
            for blocker in by_path["scripts/research_seed_triage.py"]["reviewBlockers"]
        ))
        self.assertTrue(any(
            "must keep executableSeeds at zero" in blocker
            for blocker in by_path["scripts/research_seed_triage.py"]["reviewBlockers"]
        ))
        self.assertEqual(
            by_path["tests/test_research_seed_triage.py"]["reviewRecommendation"],
            "keep-research-seed-triage-after-focused-tests",
        )

        markdown = render_markdown(payload)
        self.assertIn("keep-research-seed-triage-after-focused-tests", markdown)
        self.assertIn("hypothesis-only", markdown)

    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^bill-source-packet-review-\d{4}-\d{2}-\d{2}\.md$")

    def test_cli_writes_json_and_markdown(self):
        from scripts import bill_source_packet_review

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.json"
            output = tmp_path / "out.json"
            markdown = tmp_path / "out.md"
            source.write_text(json.dumps({
                "nextReviewPackets": [
                    {
                        "id": "packet-01-control-research-scaffold",
                        "paths": ["scripts/bill_source_hygiene_plan.py"],
                        "pathFootprint": [{"path": "scripts/bill_source_hygiene_plan.py", "status": "??"}],
                        "commands": ["npm run --silent bill:source-hygiene-plan"],
                    },
                    {
                        "id": "packet-05-futures-strategy-lane",
                        "paths": ["scripts/futures_data_requirements.py"],
                        "pathFootprint": [{"path": "scripts/futures_data_requirements.py", "status": "??"}],
                        "commands": ["npm run --silent bill:futures-data-requirements"],
                    },
                    {
                        "id": "packet-06-prediction-market-lane",
                        "paths": ["scripts/prediction_event_lag_replay.py"],
                        "pathFootprint": [{"path": "scripts/prediction_event_lag_replay.py", "status": "??"}],
                        "commands": ["npm run --silent bill:prediction-evidence-triage"],
                    },
                ],
            }))

            with patch("sys.argv", [
                "bill_source_packet_review.py",
                "--source-hygiene",
                str(source),
                "--output",
                str(output),
                "--markdown",
                str(markdown),
            ]):
                with redirect_stdout(StringIO()):
                    rc = bill_source_packet_review.main()

            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(output.read_text())["reviewedPacketCount"], 3)
            self.assertIn("Bill Source Packet Review", markdown.read_text())


if __name__ == "__main__":
    unittest.main()
