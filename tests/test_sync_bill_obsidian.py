import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.sync_bill_obsidian import (
    DAILY_REQUIRED_SECTIONS,
    active_shadow_cron_script_guardrail_summary,
    active_dirty_execution_cron_remediation,
    active_dirty_execution_cron_summary,
    codex_automation_summary_line,
    ensure_daily_plan_contract,
    execution_firewall_evidence_summary,
    diversified_priority_paths,
    futures_nq_research_cycle_summary,
    futures_nq_sizing_overlay_summary,
    futures_open_session_proof_summary,
    fund_os_promotion_contract_summary,
    goal_completion_summary,
    hermes_storage_summary,
    inventory_priority_reason,
    inventory_priority_score,
    latest_operating_log_events,
    lead_one_variable_retest,
    lead_research_action,
    next_obsidian_summary_paths,
    order_reconciliation_markdown,
    prediction_clob_microstructure_summary,
    prediction_event_mapping_summary,
    prediction_forward_capture_command,
    prediction_macro_rates_summary,
    prediction_resolved_review_summary,
    prioritized_resource_paths,
    queued_youtube_source_card_summary,
    rewrite_current_daily_references,
    rewrite_hub_daily_references,
    rewrite_hub_read_first,
    runtime_architecture_summary_line,
    shadow_cron_state_summary,
    source_manual_clearance_markdown,
    source_packet_review_summary_line,
    source_hygiene_lane_packet_markdown,
    source_hygiene_lane_packet_summary,
    status_for,
    trading_day,
)


class SyncBillObsidianTest(unittest.TestCase):
    def test_trading_day_uses_london_date_not_utc_date(self):
        # 23:30 UTC on May 29 is already May 30 in Europe/London.
        self.assertEqual(trading_day(datetime(2026, 5, 29, 23, 30, tzinfo=timezone.utc)), "2026-05-30")

    def test_trading_day_keeps_intraday_london_date(self):
        self.assertEqual(trading_day(datetime(2026, 5, 30, 14, 30, tzinfo=timezone.utc)), "2026-05-30")

    def test_rewrites_hub_daily_references(self):
        body = "\n".join([
            "## Read First",
            "1. [[daily/2026-05-29-bill-trading-plan]]",
            "",
            "Current daily note: [[daily/2026-05-29-bill-trading-plan]]",
        ])

        updated = rewrite_hub_daily_references(body, "2026-05-30")

        self.assertIn("1. [[daily/2026-05-30-bill-trading-plan]]", updated)
        self.assertIn("Current daily note: [[daily/2026-05-30-bill-trading-plan]]", updated)
        self.assertNotIn("2026-05-29-bill-trading-plan", updated)

    def test_rewrites_current_daily_references_across_control_docs(self):
        body = "\n".join([
            "| Daily orders/fills/mistakes | [[daily/2026-05-29-bill-trading-plan]] |",
            "| [[../Agent-Hermes/daily/2026-05-29-bill-trading-plan]] | Today's orders |",
        ])

        updated = rewrite_current_daily_references(body, "2026-05-30")

        self.assertIn("[[daily/2026-05-30-bill-trading-plan]]", updated)
        self.assertIn("[[../Agent-Hermes/daily/2026-05-30-bill-trading-plan]]", updated)
        self.assertNotIn("2026-05-29-bill-trading-plan", updated)

    def test_queued_youtube_source_card_summary_surfaces_durable_cards(self):
        summary = queued_youtube_source_card_summary({
            "queuedYouTubeSourceCards": {
                "present": True,
                "path": "/vault/Research-Catalog/Youtube-Transcript-Source-Cards-2026-05-30.md",
                "researcherRun": "run-yt",
                "targetsSucceeded": 3,
                "targetsAttempted": 3,
                "rawTranscriptChunksKept": 3,
                "strategyHypothesesPromoted": 0,
                "executionRelevant": False,
                "cards": [
                    {"title": "FaberVaale", "decision": "candidate", "lane": "futures"},
                    {"title": "PEAD", "decision": "candidate-with-caution", "lane": "futures-overlay"},
                ],
            }
        })

        self.assertTrue(summary["present"])
        self.assertEqual(summary["targets"], "3/3")
        self.assertEqual(summary["rawChunks"], 3)
        self.assertEqual(summary["promoted"], 0)
        self.assertFalse(summary["executionRelevant"])
        self.assertEqual(summary["researcherRun"], "run-yt")
        self.assertEqual(summary["cards"][0], ("FaberVaale", "candidate", "futures"))

    def test_fund_os_promotion_contract_summary_surfaces_locked_ladder(self):
        summary = fund_os_promotion_contract_summary({
            "fundPromotionContract": {
                "decision": "fund-promotion-contract-research-only-execution-locked",
                "currentStage": "research-only-control-plane",
                "nextStage": "clear-futures-demo-gates",
                "readyForDemoExpansion": False,
                "readyForPaper": False,
                "portfolioIntent": {
                    "primaryLanes": ["futures", "prediction-markets"],
                    "compoundRule": "Compound only after gates pass and payouts are realized; no-trade days preserve capital and are valid outcomes.",
                },
                "ladder": [
                    {"id": "l0-research-only-control-plane", "status": "pass"},
                    {"id": "l1-futures-topstep-demo", "status": "blocked"},
                    {"id": "l2-prediction-paper", "status": "blocked"},
                ],
            }
        })

        self.assertEqual(summary["decision"], "fund-promotion-contract-research-only-execution-locked")
        self.assertEqual(summary["currentStage"], "research-only-control-plane")
        self.assertEqual(summary["nextStage"], "clear-futures-demo-gates")
        self.assertFalse(summary["readyForDemoExpansion"])
        self.assertFalse(summary["readyForPaper"])
        self.assertEqual(summary["primaryLanes"], ["futures", "prediction-markets"])
        self.assertEqual(summary["stageStatus"], [
            ("l0-research-only-control-plane", "pass"),
            ("l1-futures-topstep-demo", "blocked"),
            ("l2-prediction-paper", "blocked"),
        ])
        self.assertIn("no-trade days", summary["compoundRule"])

    def test_source_packet_review_summary_surfaces_operator_counts(self):
        line = source_packet_review_summary_line(
            {
                "decision": "source-packet-review-visible-execution-locked",
                "reviewedPacketCount": 5,
                "keepResearchCount": 163,
                "shadowOnlyCount": 9,
                "dependencyReviewedCount": 3,
                "reviewBeforeStagingCount": 0,
                "quarantineReviewCount": 13,
                "topQuarantineReview": [
                    "ops/mac-mini/scripts/brain-cycle.sh",
                    "/Users/brain/worktrees/hedge-goal-live:src/live/demoExecution.ts",
                ],
                "sourceCleanBlockers": ["canonical source root has dirty execution/live files"],
                "packetReviewCleared": False,
                "safeToStageAutomatically": False,
                "requiresOperatorDecision": True,
            },
            "2026-05-31",
        )

        self.assertIn("keepResearch `163`", line)
        self.assertIn("reviewBeforeStaging `0`", line)
        self.assertIn("quarantineReview `13`", line)
        self.assertIn("brain-cycle.sh", line)
        self.assertIn("requiresOperatorDecision `True`", line)
        self.assertIn("[[bill-source-packet-review-2026-05-31]]", line)

    def test_codex_automation_summary_surfaces_futures_proof_conflicts(self):
        line = codex_automation_summary_line(
            {
                "status": "PASS",
                "activeBillAutomationCount": 3,
                "activePredictionCaptureIds": ["bill-prediction-forward-clob-capture"],
                "pausedPredictionCaptureIds": ["bill-prediction-event-clob-capture"],
                "activeFuturesOpenSessionProofIds": [
                    "bill-futures-open-session-data-proof",
                    "bill-open-session-data-proof",
                ],
                "activeFuturesOpenSessionProofConflictIds": [],
                "blockers": [],
            },
            "2026-05-31",
        )

        self.assertIn("activeFuturesOpenSessionProofs", line)
        self.assertIn("bill-futures-open-session-data-proof", line)
        self.assertIn("bill-open-session-data-proof", line)
        self.assertIn("futuresProofConflicts `[]`", line)
        self.assertIn("[[codex-automation-audit-2026-05-31]]", line)

    def test_runtime_architecture_summary_surfaces_runtime_actions(self):
        line = runtime_architecture_summary_line(
            {
                "decision": "runtime-architecture-visible-execution-locked",
                "warnings": ["blocked-hermes-kanban-tasks-present"],
                "n8n": {"activeBillWorkflowCount": 0},
                "n8nExportMismatches": [],
                "hermesKanban": {
                    "blockedRelevantTasks": [{"id": "t_1"}],
                    "blockedTaskTriage": {"allBlockedRelevantTasksTriaged": True},
                },
                "hermesCron": {
                    "activeExecutionLikeCount": 13,
                    "validatorReview": {"cleared": True},
                },
                "aiScientistTemplate": {"hardSafetyOk": True},
                "operatorActions": [
                    {"id": "hermes-kanban-blocked-task-triage", "priority": 3},
                    {"id": "execution-like-cron-name-review", "priority": 4},
                ],
            },
            "2026-05-31",
        )

        self.assertIn("n8n Bill active `0`", line)
        self.assertIn("exportMismatches `0`", line)
        self.assertIn("Kanban blocked `1`", line)
        self.assertIn("kanbanTriaged `True`", line)
        self.assertIn("cron execution-like `13`", line)
        self.assertIn("cronValidatorCleared `True`", line)
        self.assertIn("AI-Scientist hardSafety `True`", line)
        self.assertIn("hermes-kanban-blocked-task-triage", line)
        self.assertIn("[[bill-runtime-architecture-audit-2026-05-31]]", line)

    def test_active_shadow_cron_script_guardrail_summary_surfaces_drift(self):
        rows = active_shadow_cron_script_guardrail_summary({
            "cron_trust": {
                "activeShadowCronScriptGuardrails": [
                    {
                        "name": "dom-proxy-ohlcv",
                        "script": "dom_proxy_ohlcv.py",
                        "guardrailPresent": True,
                        "missingTokens": [],
                    },
                    {
                        "name": "rolling-window-optimizer",
                        "script": "rolling_window_optimizer.py",
                        "guardrailPresent": False,
                        "missingTokens": ["NOT A TRADE SIGNAL"],
                    },
                ]
            }
        })

        self.assertEqual(2, len(rows))
        self.assertEqual(("dom-proxy-ohlcv", "dom_proxy_ohlcv.py", True, []), rows[0])
        self.assertEqual("rolling-window-optimizer", rows[1][0])
        self.assertFalse(rows[1][2])
        self.assertEqual(["NOT A TRADE SIGNAL"], rows[1][3])

    def test_rewrite_hub_read_first_splits_operator_and_deep_context(self):
        body = "\n".join([
            "# Bill Control Hub",
            "",
            "## Read First",
            "",
            "1. [[daily/2026-05-29-bill-trading-plan]]",
            "2. [[old-noisy-readme]]",
            "",
            "## Source Of Truth",
            "",
            "Truth table here.",
        ])

        updated = rewrite_hub_read_first(body, "2026-05-30")

        self.assertIn("### Operator Must Read These 3", updated)
        self.assertIn("1. [[daily/2026-05-30-bill-trading-plan]]", updated)
        self.assertIn("### Active Handoff", updated)
        self.assertIn("[[bill-source-hygiene-plan-2026-05-30]]", updated)
        self.assertIn("[[bill-source-packet-review-2026-05-30]]", updated)
        self.assertIn("[[bill-open-session-data-proof-2026-05-30]]", updated)
        self.assertIn("[[bill-source-intake-manifest-2026-05-30]]", updated)
        self.assertIn("[[bill-data-intake-manifest-2026-05-30]]", updated)
        self.assertIn("[[bill-execution-intake-manifest-2026-05-30]]", updated)
        self.assertIn("[[bill-goal-completion-audit-2026-05-30]]", updated)
        self.assertIn("[[bill-clearance-handoff-2026-05-30]]", updated)
        self.assertIn("[[bill-shadow-cron-and-fabervaale-audit-2026-05-30]]", updated)
        self.assertIn("[[bill-dependency-alpha-tooling-review-2026-05-30]]", updated)
        self.assertIn("[[bill-runtime-architecture-audit-2026-05-30]]", updated)
        self.assertIn("[[BILL-HERMES-SYSTEM-ARCHITECTURE-2026-05-30]]", updated)
        self.assertIn("[[current-alpha-watch-2026-05-30]]", updated)
        self.assertIn("[[research-seed-triage-2026-05-30]]", updated)
        self.assertIn("[[../Research-Catalog/Paper-Source-Cards-2026-05-30]]", updated)
        self.assertIn("### Deep Context", updated)
        self.assertIn("## Source Of Truth", updated)
        self.assertNotIn("old-noisy-readme", updated)

    def test_resource_inventory_downranks_archived_readmes_below_signal_sources(self):
        paper = Path("/Users/brain/Downloads/Lintner_Revisited_Quantitative_Analysis.pdf")
        active_script = Path("/Users/brain/hedge/scripts/prediction_event_lag_replay.py")
        archive_readme = Path(
            "/Volumes/Seagate Expansion Drive/hedge-data/local-archives/2026-05-26/"
            "research-repos/firecrawl/examples/demo/README.md"
        )

        ordered = prioritized_resource_paths([archive_readme, active_script, paper])

        self.assertEqual(ordered[-1], archive_readme)
        self.assertIn(ordered[0], {paper, active_script})
        self.assertGreater(inventory_priority_score(paper), inventory_priority_score(archive_readme))
        self.assertGreater(inventory_priority_score(active_script), inventory_priority_score(archive_readme))
        self.assertEqual(inventory_priority_reason(active_script), "active Bill implementation")
        self.assertEqual(
            inventory_priority_reason(archive_readme),
            "archived/retired; low priority unless explicitly revived",
        )

    def test_diversified_priority_paths_caps_single_category_before_other_lanes(self):
        prediction_paths = [
            Path(f"/Users/brain/hedge/scripts/prediction_alpha_{idx}.py")
            for idx in range(3)
        ]
        futures_path = Path("/Users/brain/hedge/scripts/futures_nq_research_cycle.py")

        ordered = diversified_priority_paths(prediction_paths + [futures_path], per_category=2)

        self.assertIn(futures_path, ordered[:3])

    def test_resource_inventory_marks_funding_scripts_for_execution_review(self):
        path = Path("/Users/brain/hedge/scripts/fund-and-trade.ts")

        self.assertEqual(status_for(path), "execution-review")
        self.assertEqual(inventory_priority_reason(path), "execution/funding path; review firewall first")

    def test_resource_inventory_keeps_repo_kronos_strategy_as_implementation(self):
        path = Path("/Users/brain/hedge/src/strategies/kronosDirection.ts")

        self.assertEqual(status_for(path), "implementation")

    def test_next_obsidian_summary_paths_favors_research_objects_over_implementations(self):
        paper = Path("/Users/brain/paper_2502.15757.pdf")
        futures_report = Path("/Users/brain/research_report_futures_alpha_2025_2026.md")
        implementation = Path("/Users/brain/hedge/scripts/prediction_event_lag_replay.py")
        current_artifact = Path("/Users/brain/hedge/.rumbling-hedge/state/backtrader-research.latest.json")
        archived_readme = Path(
            "/Volumes/Seagate Expansion Drive/hedge-data/local-archives/research-repos/foo/README.md"
        )

        queue = next_obsidian_summary_paths(
            [implementation, current_artifact, archived_readme, paper, futures_report]
        )

        self.assertIn(paper, queue)
        self.assertIn(futures_report, queue)
        self.assertNotIn(implementation, queue)
        self.assertNotIn(current_artifact, queue)
        self.assertNotIn(archived_readme, queue)

    def test_daily_plan_contract_sections_are_scaffolded_without_overwriting_existing_notes(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-05-30-bill-trading-plan.md"
            path.write_text("# Bill Trading Plan - 2026-05-30\n\n## Post-Market Mistakes\n\nExisting human note.\n")

            ensure_daily_plan_contract(path)

            updated = path.read_text()
            for heading, _default_body in DAILY_REQUIRED_SECTIONS:
                self.assertIn(f"## {heading}", updated)
            self.assertEqual(updated.count("## Post-Market Mistakes"), 1)
            self.assertIn("Existing human note.", updated)

    def test_latest_operating_log_events_returns_recent_headings(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-05-operating-log.md"
            path.write_text("\n".join([
                "# Log",
                "### Position Check — old",
                "- detail",
                "### Topstep Demo — new",
                "- detail",
                "### EOD Review — latest",
            ]))

            self.assertEqual(
                latest_operating_log_events(path, limit=2),
                ["Topstep Demo — new", "EOD Review — latest"],
            )

    def test_order_reconciliation_markdown_surfaces_broker_and_submission_state(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-05-operating-log.md"
            path.write_text("### Position Check — 2026-05-30T10:00Z\n")

            markdown = order_reconciliation_markdown(
                {
                    "status": "OK",
                    "risk": {"daily_profit": 10, "daily_loss": 0},
                    "broker_reconciliation": {
                        "broker_flat": True,
                        "open_positions": 0,
                        "fills_today": 6,
                        "matched_trades": 2,
                        "local_position_superseded": True,
                    },
                },
                {
                    "submitted": True,
                    "last_signal": "long@pre-trade-check",
                    "detail": {
                        "entry_order_id": 123,
                        "fill_price": None,
                        "message": "submitted_with_oco_brackets",
                    },
                },
                path,
            )

            self.assertIn("| Broker flat | True |", markdown)
            self.assertIn("| Latest submission | submitted=True order=123 result=submitted_with_oco_brackets |", markdown)
            self.assertIn("- Position Check — 2026-05-30T10:00Z", markdown)

    def test_prediction_resolved_review_summary_preserves_blocking_decision(self):
        summary = prediction_resolved_review_summary({
            "resolvedOutcomeReview": {
                "status": "research-only",
                "decision": "do-not-promote-resolved-history-without-paper-review-and-fillability",
                "broadPriorRisk": "high",
                "readyForPaper": False,
                "items": [
                    {
                        "externalId": "558938",
                        "decision": "context-only-not-paper",
                        "resolvedMatchCount": 312,
                        "subjectSpecificMatchCount": 14,
                    }
                ],
            }
        })

        self.assertEqual(summary["status"], "research-only")
        self.assertEqual(
            summary["decision"],
            "do-not-promote-resolved-history-without-paper-review-and-fillability",
        )
        self.assertEqual(summary["broadPriorRisk"], "high")
        self.assertEqual(summary["itemDecisions"][0], ("558938", "context-only-not-paper", 312, 14))
        self.assertFalse(summary["readyForPaper"])

    def test_prediction_macro_rates_summary_surfaces_clean_labels_without_paper_readiness(self):
        summary = prediction_macro_rates_summary(
            fillability={
                "decision": "research-only; fillability evidence only",
                "marketsInspected": 416,
                "executablePublicQuotes": 26,
                "bucketCounts": {"tight": 16, "usable": 10},
                "readyForPaper": False,
            },
            requirements={
                "decision": "research-only-macro-rates-requirements-cleared",
                "passCount": 5,
                "blockedCount": 0,
                "readyForPaper": False,
                "readyForExecution": False,
            },
            labels={
                "officialComparableCount": 35,
                "officialAgreementRate": 1.0,
                "readyForPaper": False,
            },
            replay={
                "decision": "research-only-macro-rates-cross-source-replay-complete",
                "readyForPaper": False,
            },
        )

        self.assertEqual(summary["executablePublicQuotes"], 26)
        self.assertEqual(summary["officialAgreementRate"], 1.0)
        self.assertFalse(summary["readyForPaper"])
        self.assertFalse(summary["readyForExecution"])

    def test_prediction_clob_microstructure_summary_keeps_feature_candidates_research_only(self):
        summary = prediction_clob_microstructure_summary({
            "decision": "research-only-new-feature-audit",
            "readyFeatureCount": 5,
            "repoFeatureCount": 47,
            "readyForPaper": False,
            "nextAction": "Run one ready feature family at a time.",
            "featureCandidates": [
                {"id": "clob-depth-imbalance-persistence"},
                {"id": "clob-quote-update-intensity"},
            ],
        })

        self.assertEqual(summary["readyFeatureCount"], 5)
        self.assertEqual(summary["featureIds"][0], "clob-depth-imbalance-persistence")
        self.assertFalse(summary["readyForPaper"])

    def test_prediction_event_mapping_summary_surfaces_fanout_blocker(self):
        summary = prediction_event_mapping_summary(
            {
                "decision": "research-only-event-market-mapping-blocked",
                "ambiguousHeadlineCount": 1,
                "blockers": ["ambiguous-headline-event-family-fanout"],
                "ambiguousCounterpartyHeadlineCount": 1,
                "ambiguousHeadlineFamilyFanout": [
                    {
                        "headline": "Peace deal with Iran could still spell a Fed rate hike",
                        "headlineEventFamilies": ["geopolitical-agreement", "macro-rates"],
                        "headlineActors": ["fed", "iran"],
                        "marketActorSets": [["iran", "us"], ["iran", "israel"]],
                        "candidateExternalIds": ["2270330", "2270338"],
                    }
                ],
                "ambiguousHeadlineCounterpartyFanout": [
                    {
                        "headline": "Peace deal with Iran could still spell a Fed rate hike",
                        "headlineActors": ["fed", "iran"],
                        "marketActorSets": [["iran", "us"], ["iran", "israel"]],
                        "candidateExternalIds": ["2270330", "2270338"],
                    }
                ],
                "headlineFamilyFanout": [
                    {
                        "headline": "Peace deal with Iran could still spell a Fed rate hike",
                        "headlineEventFamilies": ["geopolitical-agreement", "macro-rates"],
                        "candidateExternalIds": ["2270330", "2270338"],
                    },
                    {
                        "headline": "Fed Governor warns about rates",
                        "headlineEventFamilies": ["macro-rates"],
                        "candidateExternalIds": ["906972"],
                    }
                ],
                "readyForPaper": False,
                "readyForExecution": False,
            },
            {
                "decision": "research-only-mapping-refinement-required",
                "blockers": ["spread-quality-rejected-current-watch-window", "ambiguous-headline-to-market-fanout"],
                "mappingQualityCounts": {"reject-spread-and-ambiguous-fanout": 1},
                "mappingRepairTargetCount": 1,
                "mappingRepairTargets": [
                    {
                        "headline": "Peace deal with Iran could still spell a Fed rate hike",
                        "candidateCount": 2,
                        "candidateFamilyCounts": {"geopolitical-agreement": 2},
                        "candidateCounterpartyCounts": {"iran/us": 1, "iran/israel": 1},
                        "candidateDeadlineCounts": {"june 15, 2026": 1, "july 31, 2026": 1},
                        "blockedUntil": ["single event family selected"],
                    }
                ],
                "publicCaptureReviewLeadCount": 1,
                "publicCaptureReviewLeads": [
                    {
                        "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                        "counterparty": "iran/us",
                        "deadlineText": "june 30",
                        "status": "fillable-live-book",
                        "spread": 0.02,
                    }
                ],
                "headlineReviews": [
                    {
                        "headline": "Peace deal with Iran could still spell a Fed rate hike",
                        "mappingQuality": "reject-spread-and-ambiguous-fanout",
                        "candidateSpecificityRows": [
                            {
                                "headlineEventFamilies": ["geopolitical-agreement", "macro-rates"],
                                "specificityIssues": [
                                    "headline-has-multiple-event-families",
                                    "headline-does-not-identify-counterparty",
                                ],
                            }
                        ],
                    }
                ],
                "readyForPaper": False,
                "readyForExecution": False,
            },
        )

        self.assertEqual(summary["mappingDecision"], "research-only-event-market-mapping-blocked")
        self.assertIn("ambiguous-headline-event-family-fanout", summary["mappingBlockers"])
        self.assertEqual(summary["ambiguousHeadlineCount"], 1)
        self.assertEqual(summary["headlineFamilyFanoutCount"], 2)
        self.assertEqual(summary["ambiguousHeadlineFamilyFanoutCount"], 1)
        self.assertEqual(summary["ambiguousCounterpartyHeadlineCount"], 1)
        self.assertEqual(summary["ambiguousHeadlineCounterpartyFanoutCount"], 1)
        self.assertEqual(summary["headlineFamilyFanoutSample"][0][1], ["geopolitical-agreement", "macro-rates"])
        self.assertEqual(summary["headlineCounterpartyFanoutSample"][0][2], [["iran", "us"], ["iran", "israel"]])
        self.assertIn("ambiguous-headline-to-market-fanout", summary["refinementBlockers"])
        self.assertEqual(summary["mappingQualityCounts"], {"reject-spread-and-ambiguous-fanout": 1})
        self.assertEqual(summary["mappingRepairTargetCount"], 1)
        self.assertEqual(summary["mappingRepairTargetSample"][0][1], 2)
        self.assertEqual(summary["mappingRepairTargetSample"][0][3], {"iran/us": 1, "iran/israel": 1})
        self.assertEqual(summary["publicCaptureReviewLeadCount"], 1)
        self.assertEqual(summary["publicCaptureReviewLeadSample"][0][1], "iran/us")
        self.assertEqual(
            summary["refinementSpecificitySample"][0][2],
            ["geopolitical-agreement", "macro-rates"],
        )
        self.assertIn(
            "headline-has-multiple-event-families",
            summary["refinementSpecificitySample"][0][3],
        )
        self.assertFalse(summary["readyForPaper"])
        self.assertFalse(summary["readyForExecution"])

    def test_hermes_storage_summary_surfaces_archive_plan_without_cleanup_approval(self):
        summary = hermes_storage_summary({
            "totalSize": "19.7GB",
            "archiveCandidateSize": "13.3GB",
            "archiveRoot": "/Volumes/Seagate Expansion Drive/hedge-data/local-archives/hermes-runtime",
            "archiveMount": {"exists": True},
            "movesFiles": False,
            "deletesFiles": False,
            "topCandidates": [
                {"name": "profiles", "size": "10.4GB", "action": "inspect-profile-subdirs-before-archive"},
                {"name": "state-snapshots", "size": "2.0GB", "action": "archive-with-checksum-before-delete"},
            ],
            "cleanupPlan": [
                {"id": "archive-state-snapshots-copy-only"},
                {"id": "active-state-do-not-touch"},
            ],
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
            "nextActions": [
                "Pick an inactive Hermes profile list before moving any profile/model cache.",
                "Archive state-snapshots with checksum verification to Seagate, then review removal separately.",
            ],
        })

        self.assertEqual(summary["archiveCandidateSize"], "13.3GB")
        self.assertFalse(summary["movesFiles"])
        self.assertFalse(summary["deletesFiles"])
        self.assertEqual(summary["topCandidates"][0][0], "profiles")
        self.assertIn("archive-state-snapshots-copy-only", summary["cleanupPlanIds"])
        self.assertTrue(summary["stateSnapshotsArchive"]["archiveCoversSource"])
        self.assertTrue(summary["stateSnapshotsArchive"]["copyLooksComplete"])
        self.assertEqual(summary["stateSnapshotsArchive"]["sourceSize"], "2.0GB")
        self.assertEqual(summary["stateSnapshotsArchive"]["destinationSize"], "3.9GB")

    def test_execution_firewall_evidence_summary_counts_only_firewall_rows(self):
        summary = execution_firewall_evidence_summary({
            "status": "PASS",
            "results": [
                {"lane": "governance-risk", "id": "typecheck", "passed": True},
                {"lane": "execution-live", "id": "verify-master-bridge-firewall", "passed": True},
                {"lane": "execution-live", "id": "verify-signal-router-firewall", "passed": True},
                {"lane": "execution-live", "id": "verify-prediction-funding-firewall", "passed": False},
            ],
        })

        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["failed"], ["verify-prediction-funding-firewall"])

    def test_shadow_cron_state_summary_surfaces_diagnostic_only_flags(self):
        summary = shadow_cron_state_summary({
            "shadow_states": {
                "whale_flow": {
                    "method": "fallback_no_data",
                    "evidenceLevel": "no_live_data_shadow_only",
                    "executionRole": "diagnostic_only",
                    "tradableSignal": False,
                    "promotedForExecution": False,
                },
                "dom_proxy": {
                    "method": "OHLCV_DOM_proxy",
                    "evidenceLevel": "proxy_shadow_only",
                    "executionRole": "diagnostic_only",
                    "tradableSignal": False,
                    "promotedForExecution": False,
                },
            }
        })

        self.assertEqual(summary[0][0], "dom_proxy")
        self.assertIn(
            ("whale_flow", "fallback_no_data", "no_live_data_shadow_only", "diagnostic_only", False, False),
            summary,
        )

    def test_active_dirty_execution_cron_summary_surfaces_firewalled_refs(self):
        summary = active_dirty_execution_cron_summary({
            "cron_trust": {
                "activeDirtyExecutionLiveScriptReferences": [
                    {
                        "name": "60m-lucidflex-execution",
                        "script": "60m_exec_bridge.py",
                        "source": {
                            "relativePath": "scripts/60m_exec_bridge.py",
                            "firewallPassed": True,
                        },
                    }
                ]
            }
        })

        self.assertEqual(
            [("60m-lucidflex-execution", "60m_exec_bridge.py", "scripts/60m_exec_bridge.py", True)],
            summary,
        )

    def test_active_dirty_execution_cron_remediation_surfaces_operator_action(self):
        summary = active_dirty_execution_cron_remediation({
            "cron_trust": {
                "activeDirtyExecutionLiveScriptReferences": [
                    {
                        "name": "agentic-fund-cycle",
                        "operatorRemediation": {
                            "approvalRequired": True,
                            "requiredAction": "operator must disable or clear source",
                            "validationCommands": [
                                "npm run --silent bill:verify-execution-quarantine",
                                "npm run --silent bill:cron-state-validator",
                            ],
                        },
                    }
                ]
            }
        })

        self.assertEqual(summary[0][0], "agentic-fund-cycle")
        self.assertEqual(summary[0][1], "operator must disable or clear source")
        self.assertTrue(summary[0][2])
        self.assertIn("npm run --silent bill:cron-state-validator", summary[0][3])

    def test_goal_completion_summary_surfaces_blocked_ids_and_reasons(self):
        summary = goal_completion_summary({
            "decision": "continue-research-only-locked",
            "goalComplete": False,
            "passCount": 19,
            "checkCount": 24,
            "blockedCount": 5,
            "blockedIds": [
                "cron-control-trust-not-cleared",
                "futures-demo-not-cleared",
            ],
            "promptUncoveredIds": [
                "futures-frontier-wired",
                "source-hygiene-not-faked",
            ],
            "promptToArtifactChecklist": [
                {"id": "futures-frontier-wired", "status": "partial"},
                {"id": "source-hygiene-not-faked", "status": "blocked"},
            ],
            "checklist": [
                {
                    "id": "cron-control-trust-not-cleared",
                    "status": "blocked",
                    "blocker": "cron validator has P0/P1 issues",
                },
                {
                    "id": "futures-demo-not-cleared",
                    "status": "blocked",
                    "blocker": "broker parity missing",
                },
            ],
        })

        self.assertEqual(summary["decision"], "continue-research-only-locked")
        self.assertFalse(summary["goalComplete"])
        self.assertEqual(summary["blockedCount"], 5)
        self.assertEqual(summary["blockedIds"][0], "cron-control-trust-not-cleared")
        self.assertEqual(summary["promptUncoveredCount"], 2)
        self.assertIn(("source-hygiene-not-faked", "blocked"), summary["promptUncovered"])
        self.assertIn(
            ("futures-demo-not-cleared", "broker parity missing"),
            summary["topBlockers"],
        )

    def test_futures_open_session_proof_summary_surfaces_window_and_data_only_commands(self):
        summary = futures_open_session_proof_summary({
            "executionGradeDataProofPassed": False,
            "stateSummary": {
                "readyForExecutionData": False,
                "nextOpenSessionProofWindow": {
                    "nextOpenUtc": "2026-05-31T22:00:00+00:00",
                    "recommendedProofStartUtc": "2026-05-31T22:05:00+00:00",
                    "recommendedProofEndUtc": "2026-05-31T22:35:00+00:00",
                    "reason": "next Sunday 18:00 ET Globex open",
                    "commandsAreDataOnly": True,
                },
            },
            "plannedSteps": [
                {
                    "id": "databento-open-session-smoke",
                    "command": "npm run --silent bill:databento-realtime-smoke -- --timeout-sec 20",
                    "writesOrders": False,
                    "touchesBroker": False,
                    "movesFunds": False,
                },
                {
                    "id": "databento-open-session-bridge-write",
                    "command": ".venv/bin/python scripts/realtime_data_bridge.py --quiet --databento-only",
                    "writesOrders": False,
                    "touchesBroker": False,
                    "movesFunds": False,
                },
                {
                    "id": "read-only-broker-reconciliation",
                    "command": "python3 topstep_demo_fill_check.py",
                    "writesOrders": False,
                    "touchesBroker": True,
                    "movesFunds": False,
                },
            ],
        })

        self.assertEqual(summary["recommendedProofStartUtc"], "2026-05-31T22:05:00+00:00")
        self.assertTrue(summary["commandsAreDataOnly"])
        self.assertFalse(summary["executionGradeDataProofPassed"])
        self.assertEqual(len(summary["dataOnlyCommands"]), 2)
        self.assertIn("databento-realtime-smoke", summary["dataOnlyCommands"][0])

    def test_futures_nq_research_cycle_summary_keeps_watch_result_locked(self):
        summary = futures_nq_research_cycle_summary({
            "decision": "research-only-futures-cycle-ran-still-blocked",
            "mode": "run-local-research",
            "readyForDemoExpansion": False,
            "researchOnly": True,
            "blockers": ["broker-parity-not-checked"],
            "historical": {
                "bestCandidate": "seagate_nq_15m",
                "tradeCount": 70,
                "positiveFoldShare": 0.714286,
                "survivingCaseCount": 4,
                "worstFoldNetR": -2.115559,
                "currentLocalCsvParityClearedCount": 0,
                "currentLocalCsvParityCheckedCount": 3,
                "currentParitySummary": {
                    "candidate": "seagate_nq_15m",
                    "checked": True,
                    "cleared": False,
                    "overlapRows": 0,
                    "reason": "no-overlapping-bars-with-current-local-csv",
                    "operatorRead": "Historical source is usable for research/OOS only; it has no overlapping bars with the current local CSV and cannot prove broker/current parity.",
                },
                "coverageBlockers": ["no-seagate-nq-source-overlaps-current-local-csv-bars"],
            },
            "current": {
                "currentParityDecision": "research-only-current-local-parity-ready",
                "brokerParityChecked": False,
            },
        })

        self.assertEqual(summary["bestCandidate"], "seagate_nq_15m")
        self.assertEqual(summary["tradeCount"], 70)
        self.assertFalse(summary["readyForDemoExpansion"])
        self.assertFalse(summary["brokerParityChecked"])
        self.assertEqual(summary["currentLocalCsvParity"], (0, 3))
        self.assertFalse(summary["historicalCurrentParitySummary"]["cleared"])
        self.assertIn("research/OOS only", summary["historicalCurrentParitySummary"]["operatorRead"])
        self.assertIn("no-seagate-nq-source-overlaps-current-local-csv-bars", summary["coverageBlockers"])
        self.assertIn("broker-parity-not-checked", summary["blockers"])

    def test_futures_nq_sizing_overlay_summary_surfaces_watch_and_blocked_profiles(self):
        summary = futures_nq_sizing_overlay_summary({
            "decision": "research-only-sizing-overlay-watch",
            "bestProfileId": "risk-1000",
            "oneVariable": "position sizing only",
            "assumptions": {"instrument": "MNQ"},
            "readyForDemoExpansion": False,
            "profileResults": [
                {
                    "id": "fixed-1",
                    "decision": "research-only-sizing-watch",
                    "summary": {"netPnl": 3183.0, "maxDrawdown": 738.5},
                    "bestDayPnl": 456.5,
                },
                {
                    "id": "risk-250",
                    "decision": "research-only-sizing-blocked",
                    "blockers": ["some-trades-skipped-by-risk-budget"],
                },
            ],
        })

        self.assertEqual(summary["bestProfileId"], "risk-1000")
        self.assertEqual(summary["watchProfiles"][0], ("fixed-1", 3183.0, 738.5, 456.5))
        self.assertEqual(summary["blockedProfiles"][0][0], "risk-250")
        self.assertFalse(summary["readyForDemoExpansion"])

    def test_lead_research_action_surfaces_first_lane_match(self):
        action = lead_research_action(
            [
                {"id": "control", "lane": "control-plane", "commands": ["control-cmd"]},
                {
                    "id": "crypto-settlement-horizon-parser-retest",
                    "lane": "prediction-markets",
                    "oneVariable": "settlement horizon parser",
                    "selectedCategory": "crypto",
                    "commands": ["npm run --silent bill:prediction-narrow-scan -- --category crypto"],
                },
            ],
            "prediction-markets",
        )

        self.assertEqual(
            action,
            (
                "crypto-settlement-horizon-parser-retest",
                "settlement horizon parser",
                "crypto",
                "npm run --silent bill:prediction-narrow-scan -- --category crypto",
            ),
        )

    def test_lead_research_action_surfaces_mapping_exclusion_context(self):
        action = lead_research_action(
            [
                {
                    "id": "prediction-event-mapping-refinement-after-manual-review",
                    "lane": "prediction-markets",
                    "oneVariable": "event-market mapping quality",
                    "mappingExclusionSummary": {
                        "excludedMappingCandidateCount": 15,
                        "tokenSpecificCandidateCount": 5,
                    },
                    "commands": ["npm run --silent bill:prediction-event-lag-manual-review"],
                    "forwardCapturePlan": {
                        "preferredCommand": (
                            "npm run --silent bill:polymarket-clob-recorder "
                            "-- --duration-sec 900 --token-id deadline-ladder-1"
                        ),
                    },
                },
            ],
            "prediction-markets",
        )

        self.assertEqual(
            action,
            (
                "prediction-event-mapping-refinement-after-manual-review",
                "event-market mapping quality",
                "mappingExcluded=15 tokenSpecific=5",
                "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --token-id deadline-ladder-1",
            ),
        )

    def test_lead_one_variable_retest_prefers_selected_category_action(self):
        action = lead_one_variable_retest(
            [
                {
                    "id": "kalshi-fillability-guided-rates-scan",
                    "lane": "prediction-markets",
                    "oneVariable": "fillable public quote universe",
                    "commands": ["npm run --silent bill:kalshi-fillability-snapshot"],
                },
                {
                    "id": "crypto-settlement-horizon-parser-retest",
                    "lane": "prediction-markets",
                    "oneVariable": "settlement horizon parser",
                    "selectedCategory": "crypto",
                    "replacesTestId": "narrow-cross-venue-normalization",
                    "commands": ["npm run --silent bill:prediction-category-drilldown"],
                    "forwardCapturePlan": {
                        "reviewLeadCommand": "npm run --silent bill:prediction-category-drilldown -- --review-lead",
                    },
                },
            ],
            "prediction-markets",
        )

        self.assertEqual(
            action,
            (
                "crypto-settlement-horizon-parser-retest",
                "settlement horizon parser",
                "crypto",
                "npm run --silent bill:prediction-category-drilldown -- --review-lead",
            ),
        )

    def test_lead_one_variable_retest_skips_no_edge_maintenance(self):
        action = lead_one_variable_retest(
            [
                {
                    "id": "narrow-cross-venue-current-universe-current-form-rejected",
                    "lane": "prediction-markets",
                    "actionKind": "no-edge-maintenance",
                    "oneVariable": "current narrow universe",
                    "selectedCategory": "none-current-form-rejected",
                    "commands": ["npm run --silent bill:prediction-no-edge-ledger"],
                },
                {
                    "id": "crypto-settlement-horizon-parser-retest",
                    "lane": "prediction-markets",
                    "oneVariable": "settlement horizon parser",
                    "selectedCategory": "crypto",
                    "commands": ["npm run --silent bill:prediction-narrow-scan -- --category crypto"],
                },
            ],
            "prediction-markets",
        )

        self.assertEqual(action[0], "crypto-settlement-horizon-parser-retest")

    def test_lead_one_variable_retest_falls_back_to_next_evidence_action(self):
        action = lead_one_variable_retest(
            [
                {
                    "id": "kalshi-fillability-guided-rates-scan",
                    "lane": "prediction-markets",
                    "oneVariable": "fillable public quote universe",
                    "commands": ["npm run --silent bill:kalshi-fillability-snapshot"],
                },
                {
                    "id": "resolved-outcome-join-review",
                    "lane": "prediction-markets",
                    "oneVariable": "resolved-outcome evidence",
                    "commands": ["npm run --silent bill:prediction-resolved-outcome-join"],
                },
                {
                    "id": "narrow-cross-venue-current-universe-current-form-rejected",
                    "lane": "prediction-markets",
                    "actionKind": "no-edge-maintenance",
                    "oneVariable": "current narrow universe",
                    "selectedCategory": "none-current-form-rejected",
                    "commands": ["npm run --silent bill:prediction-no-edge-ledger"],
                },
            ],
            "prediction-markets",
        )

        self.assertEqual(
            action,
            (
                "resolved-outcome-join-review",
                "resolved-outcome evidence",
                "missing",
                "npm run --silent bill:prediction-resolved-outcome-join",
            ),
        )

    def test_prediction_forward_capture_command_prefers_storage_bounded_plan(self):
        command = prediction_forward_capture_command([
            {
                "id": "prediction-news-first-event-lag-study",
                "commands": [
                    "npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15",
                ],
                "forwardCapturePlan": {
                    "command": "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --max-assets 20 --max-output-mb 128 --min-free-gb 20 --terms 'fed,iran'",
                },
            }
        ])

        self.assertIn("bill:polymarket-clob-recorder", command)
        self.assertIn("--max-output-mb 128", command)
        self.assertIn("--min-free-gb 20", command)

    def test_prediction_forward_capture_command_falls_back_to_safe_command_list(self):
        command = prediction_forward_capture_command([
            {
                "id": "prediction-news-first-event-lag-study",
                "commands": [
                    "npm run --silent bill:polymarket-clob-recorder -- --duration-sec 900 --max-assets 20 --max-output-mb 128 --min-free-gb 20 --terms fed",
                ],
            }
        ])

        self.assertIn("--max-output-mb 128", command)

    def test_source_hygiene_lane_packet_summary_surfaces_safe_lane_handoffs(self):
        summary = source_hygiene_lane_packet_summary({
            "nextReviewPackets": [
                {
                    "id": "packet-05-futures-strategy-lane",
                    "decision": "lane-review-only",
                    "pathCount": 3,
                    "safeToStageAutomatically": False,
                    "writesOrders": False,
                    "touchesBroker": False,
                    "movesFunds": False,
                    "paths": [
                        "scripts/futures_nq_research_cycle.py",
                        "scripts/cot_signal.py",
                        "scripts/dom_proxy_ohlcv.py",
                    ],
                    "commands": ["npm run --silent bill:futures-evidence-triage || true"],
                },
                {
                    "id": "packet-06-prediction-market-lane",
                    "decision": "lane-review-only",
                    "pathCount": 2,
                    "safeToStageAutomatically": False,
                    "writesOrders": False,
                    "touchesBroker": False,
                    "movesFunds": False,
                    "paths": [
                        "scripts/prediction_event_lag_replay.py",
                        "scripts/polymarket_clob_recorder.mjs",
                    ],
                    "commands": ["npm run --silent bill:prediction-evidence-triage"],
                },
            ],
        })

        self.assertEqual(summary["futures"]["id"], "packet-05-futures-strategy-lane")
        self.assertEqual(summary["futures"]["firstCommand"], "npm run --silent bill:futures-evidence-triage || true")
        self.assertEqual(summary["futures"]["firstPaths"][0], "scripts/futures_nq_research_cycle.py")
        self.assertFalse(summary["prediction-markets"]["writesOrders"])
        self.assertEqual(summary["prediction-markets"]["firstPaths"][0], "scripts/prediction_event_lag_replay.py")

        markdown = source_hygiene_lane_packet_markdown(summary)

        self.assertIn("research-only handoff", markdown)
        self.assertIn("packet-05-futures-strategy-lane", markdown)
        self.assertIn("packet-06-prediction-market-lane", markdown)
        self.assertIn("do not stage/route/fund", markdown)
        self.assertIn("scripts/polymarket_clob_recorder.mjs", markdown)

    def test_source_manual_clearance_markdown_surfaces_review_only_targets(self):
        markdown = source_manual_clearance_markdown({
            "manualClearanceProposal": {
                "decision": "manual-clearance-proposal-only",
                "laneProposals": [
                    {
                        "lane": "futures",
                        "reviewFirst": ["scripts/cot_signal.py", "scripts/donchian_breakout.py"],
                        "keepResearchCandidates": ["scripts/futures_data_requirements.py"],
                        "shadowOnly": ["scripts/dom_proxy_ohlcv.py"],
                        "quarantineReview": [],
                        "safeToStageAutomatically": False,
                    },
                    {
                        "lane": "prediction-markets",
                        "reviewFirst": ["src/prediction/matcher.ts"],
                        "keepResearchCandidates": ["scripts/kalshi_fillability_snapshot.py"],
                        "shadowOnly": [],
                        "quarantineReview": [],
                        "safeToStageAutomatically": False,
                    },
                ],
            }
        })

        self.assertIn("manual-clearance-proposal-only", markdown)
        self.assertIn("review-only", markdown)
        self.assertIn("scripts/cot_signal.py", markdown)
        self.assertIn("src/prediction/matcher.ts", markdown)
        self.assertIn("safeAutoStage `False`", markdown)


if __name__ == "__main__":
    unittest.main()
