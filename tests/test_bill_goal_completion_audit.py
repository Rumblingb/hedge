import json
import unittest

from scripts.bill_goal_completion_audit import HERMES, build_audit, default_daily_path, default_markdown_path, render_markdown


def safe_codex_automation_audit():
    return {
        "status": "PASS",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForPaper": False,
        "readyForDemoExpansion": False,
        "activeBillAutomationCount": 3,
        "activeFuturesOpenSessionProofCount": 2,
        "activeFuturesOpenSessionProofIds": [
            "bill-futures-open-session-data-proof",
            "bill-open-session-data-proof",
        ],
        "activeFuturesOpenSessionProofConflictIds": [],
        "activePredictionCaptureIds": ["bill-prediction-forward-clob-capture"],
        "pausedPredictionCaptureIds": ["bill-prediction-event-clob-capture"],
        "blockers": [],
    }


def safe_runtime_architecture_audit():
    return {
        "decision": "runtime-architecture-visible-execution-locked",
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "movesFunds": False,
        "readyForExecution": False,
        "readyForPaper": False,
        "readyForDemoExpansion": False,
        "warnings": ["n8n-export-live-db-mismatch"],
        "n8n": {
            "workflowCount": 3,
            "activeCount": 1,
            "billWorkflowCount": 1,
            "activeBillWorkflowCount": 0,
        },
        "hermesKanban": {
            "taskCount": 5,
            "statusCounts": {"running": 2, "blocked": 1, "done": 2},
        },
        "hermesCron": {
            "jobCount": 59,
            "activeCount": 39,
            "activeExecutionLikeCount": 13,
        },
        "aiScientistTemplate": {
            "decision": "research-only-template-blocked",
            "hardSafetyOk": True,
            "promotionBlockers": ["template-output-is-not-paper-demo-or-execution-promotion"],
            "safety": {
                "research_only": True,
                "writes_orders": False,
                "touches_broker": False,
                "moves_funds": False,
            },
        },
    }


class BillGoalCompletionAuditTest(unittest.TestCase):
    def test_default_markdown_path_uses_current_utc_date(self):
        path = default_markdown_path()

        self.assertEqual(path.parent, HERMES)
        self.assertRegex(path.name, r"^bill-goal-completion-audit-\d{4}-\d{2}-\d{2}\.md$")

    def test_default_daily_path_uses_current_utc_date(self):
        path = default_daily_path()

        self.assertEqual(path.parent, HERMES / "daily")
        self.assertRegex(path.name, r"^\d{4}-\d{2}-\d{2}-bill-trading-plan\.md$")

    def test_markdown_header_uses_payload_generated_date(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T02:33:18+00:00",
            "decision": "continue-research-only-locked",
            "goalComplete": False,
            "passCount": 0,
            "checkCount": 0,
            "blockedCount": 0,
            "blockedIds": [],
            "objective": "test",
            "promptToArtifactChecklist": [],
            "checklist": [],
        })

        self.assertIn("# Bill Goal Completion Audit - 2026-05-31", markdown)
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])

    def test_audit_stays_incomplete_when_evidence_gates_are_blocked(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
                "gates": {
                    "liveReadinessBlockers": ["walk-forward gate is not deployable"],
                    "sourceCleanBlockers": ["canonical source root has dirty files"],
                    "realtimeDataBlockers": ["data freshness gate is STALE"],
                },
            },
            tooling={"status": "PASS", "readyForResearchLoop": True, "blockers": []},
            next_actions={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "actions": [
                    {
                        "id": "control-plane-clearance-before-demo",
                        "commands": [
                            "npm run --silent bill:realtime-data-preflight || true",
                            "npm run --silent bill:open-session-data-proof",
                            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:open-session-data-proof -- --run-data-only",
                            "BILL_INCLUDE_DATABENTO_OPTIONAL_PROOF=true BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:open-session-data-proof -- --run-data-only --include-databento-optional-proof",
                            "npm run --silent bill:live-readiness-gate || true",
                            "npm run --silent bill:source-intake-manifest",
                            "npm run --silent bill:source-hygiene-plan",
                            "npm run --silent bill:data-intake-manifest",
                            "npm run --silent bill:verify-execution-quarantine",
                            "npm run --silent bill:execution-intake-manifest",
                            "npm run --silent bill:clearance-handoff",
                            "npm run --silent bill:goal-completion-audit",
                            "npm run --silent bill:obsidian-sync",
                        ],
                        "dataOnlyProof": {
                            "plannedStepIds": [
                            "topstep-realtime-proof",
                            "topstep-realtime-bridge-write",
                            "topstep-readonly-bar-archive",
                            "sync-obsidian",
                        ],
                            "writesOrders": False,
                            "touchesBroker": False,
                            "movesFunds": False,
                        },
                        "nextWindow": {
                            "recommendedProofStartUtc": "2026-05-31T22:05:00+00:00",
                        },
                    },
                    {
                        "id": "futures-paid-nq-1m-session-structure-oos",
                        "commands": [
                            "npm run --silent bill:futures-nq-historical-session-replay",
                            "npm run --silent bill:futures-nq-current-data-parity",
                            "npm run --silent bill:futures-data-requirements",
                            "npm run --silent bill:futures-broker-parity-plan",
                            "npm run --silent bill:futures-nq-research-cycle",
                        ],
                    },
                    {
                        "id": "futures-paper-source-one-variable-tests",
                        "commands": [
                            "npm run --silent bill:paper-source-cards",
                            "npm run --silent bill:alpha-frontier-queue",
                        ],
                        "researchOnly": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "operatorApprovalRequiredBeforeExecution": True,
                        "promotionGate": "Paper-derived ideas require one-variable local replay, purged OOS, cost/slippage, no-edge review, and broker/data gates before any demo-shadow discussion.",
                        "promotionBlockers": [
                            "paper-source-is-hypothesis-only",
                            "requires-one-variable-oos-before-promotion",
                        ],
                        "dataPaths": ["/tmp/managed-futures.pdf"],
                    },
                    {
                        "id": "prediction-news-first-event-lag-study",
                        "commands": [
                            "npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15",
                        ],
                    },
                ],
            },
            futures_cycle={
                "decision": "research-only-futures-cycle-ran-still-blocked",
                "mode": "run-local-research",
                "researchOnly": True,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "historical": {
                    "currentParitySummary": {
                        "candidate": "seagate_nq_15m",
                        "checked": True,
                        "cleared": False,
                        "overlapRows": 0,
                        "reason": "no-overlapping-bars-with-current-local-csv",
                        "operatorRead": "Historical source is usable for research/OOS only; it has no overlapping bars with the current local CSV and cannot prove broker/current parity.",
                    }
                },
                "blockers": ["execution-grade-realtime-not-cleared"],
            },
            futures_requirements={
                "decision": "research-only-data-requirements-not-cleared",
                "researchOnly": True,
                "readyForDemoExpansion": False,
            },
            futures_broker_parity={
                "decision": "research-only-futures-broker-parity-not-cleared",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "missingProofs": [
                    "current-session-depth-from-broker-relevant-source",
                    "open-session-execution-grade-realtime-proof",
                ],
                "safeEnv": {
                    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                    "RH_TOPSTEP_READ_ONLY": "true",
                    "RH_LIVE_EXECUTION_ENABLED": "false",
                },
                "current": {"dailyRouteBlocked": True},
                "nextOpenSessionProofWindow": {"commandsAreDataOnly": True},
                "proofSequence": [
                    {"step": "refresh-state-with-locks", "commands": ["npm run --silent bill:futures-data-requirements"]},
                    {"step": "open-session-data-only-smoke", "commands": [
                        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-proof",
                        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-bridge",
                        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-readonly-bar-archive",
                        "npm run --silent bill:databento-realtime-smoke -- --timeout-sec 20",
                    ]},
                    {"step": "read-only-broker-reconciliation", "commands": ["RH_TOPSTEP_READ_ONLY=true BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false python3 /Users/brain/.hermes/scripts/topstep_demo_fill_check.py"]},
                    {"step": "read-only-broker-market-data-smoke", "commands": ["BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-market-data-smoke"]},
                    {"step": "regenerate-clearance-artifacts", "commands": ["npm run --silent bill:clearance-handoff"]},
                ],
                "validationCommandSets": {
                    "openSessionDataOnlyProof": [
                        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-proof",
                        "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-realtime-bridge",
                    ],
                    "optionalSecondaryDatabentoProof": [
                        "BILL_INCLUDE_DATABENTO_OPTIONAL_PROOF=true BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:open-session-data-proof -- --run-data-only --include-databento-optional-proof",
                    ],
                    "readOnlyBrokerMarketData": ["BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_TOPSTEP_READ_ONLY=true RH_LIVE_EXECUTION_ENABLED=false npm run --silent bill:topstep-market-data-smoke"],
                    "readOnlyBrokerReconciliation": ["RH_TOPSTEP_READ_ONLY=true BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false python3 /Users/brain/.hermes/scripts/topstep_demo_fill_check.py"],
                },
            },
            prediction_capture={
                "decision": "research-only-capture-cycle-ran",
                "mode": "run-recorder",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "readyForPaper": False,
                "captureCycleEvidencePassed": True,
                "paperPromotionEvidencePassed": False,
                "paperPromotionBlockers": [
                    "paper-review-requires-separate-human-and-model-evidence-gate",
                    "paper-review-requires-positive-fillability-and-spread-adjusted-replay",
                    "paper-review-requires-no-lookahead-event-windows-with-resolved-outcome-labels",
                ],
                "executedRecorder": {
                    "mode": "token-targets",
                    "publicMarketDataOnly": True,
                    "tokenIds": ["selected-review-token"],
                    "writesOrders": False,
                    "touchesBroker": False,
                },
                "completeEventCount": 5,
                "completeWindowCount": 5,
                "repricedWindowCount": 1,
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
                "eventLagReplayDecision": "research-only-event-lag-replay-blocked",
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
                "eventLagResearchWatchReady": True,
                "eventLagWatchReview": {
                    "present": True,
                    "decision": "research-only-event-lag-watch-review-visible",
                    "watchReady": True,
                    "repricedWatchWindowCount": 2,
                    "readyForPaper": False,
                    "readyForExecution": False,
                    "blockers": ["manual-review-required-before-forward-capture-or-paper-discussion"],
                },
                "blockers": ["event-lag-replay-not-watch-ready"],
                "latestRecorder": {
                    "writesOrders": False,
                    "liveQualityDiagnostics": {
                        "readyForPaperEvidence": False,
                        "fillableLiveBookCount": 0,
                    },
                },
            },
            prediction_market_mapping={
                "decision": "research-only-event-market-mapping-blocked",
                "candidateCount": 20,
                "ambiguousHeadlineCount": 1,
                "ambiguousCounterpartyHeadlineCount": 1,
                "blockers": ["ambiguous-headline-event-family-fanout", "ambiguous-headline-counterparty-fanout"],
                "ambiguousHeadlineFamilyFanout": [
                    {
                        "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                        "headlineEventFamilies": ["geopolitical-agreement", "macro-rates"],
                        "candidateExternalIds": ["2270330"],
                        "ambiguous": True,
                    }
                ],
                "ambiguousHeadlineCounterpartyFanout": [
                    {
                        "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                        "headlineActors": ["fed", "iran"],
                        "marketActorSets": [["iran", "us"], ["iran", "israel"]],
                        "candidateExternalIds": ["2270330"],
                        "counterpartyAmbiguous": True,
                    }
                ],
                "headlineFamilyFanout": [
                    {
                        "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                        "headlineEventFamilies": ["geopolitical-agreement", "macro-rates"],
                        "candidateExternalIds": ["2270330"],
                        "ambiguous": True,
                    },
                    {
                        "headline": "Fed Governor warns about rates",
                        "headlineEventFamilies": ["macro-rates"],
                        "candidateExternalIds": ["906972"],
                        "ambiguous": False,
                    }
                ],
            },
            prediction_mapping_refinement={
                "decision": "research-only-mapping-refinement-required",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForPaper": False,
                "readyForExecution": False,
                "readyForForwardCapture": False,
                "reviewedWindowCount": 2,
                "mappingCandidateCount": 20,
                "mappingRepairTargetCount": 1,
                "mappingRepairTargets": [
                    {
                        "headline": "With inflation at 3-year high, a peace deal with Iran could still spell a Fed rate hike",
                        "candidateCount": 15,
                        "candidateFamilyCounts": {"geopolitical-agreement": 15},
                        "candidateCounterpartyCounts": {"iran/us": 6, "iran/israel": 2},
                        "candidateDeadlineCounts": {"june 15, 2026": 1},
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
                        "reviewUseOnly": "public-capture-fillability-lead; not a mapping override, signal, or paper approval",
                    }
                ],
                "deadlineLadderCaptureCandidateCount": 1,
                "deadlineLadderCaptureCandidates": [
                    {
                        "question": "US announces new Iran agreement/ceasefire extension by June 30?",
                        "deadlineText": "june 30",
                        "deadlineDate": "2026-06-30",
                        "spreadPct": 1,
                        "topBookDepth": 2651.82,
                        "reviewUseOnly": (
                            "deadline-ladder-forward-capture-only; not a mapping override, "
                            "paper approval, signal, or execution approval"
                        ),
                    }
                ],
                "mappingQualityCounts": {"reject-spread-quality": 1},
                "blockers": [
                    "spread-quality-rejected-current-watch-window",
                    "ambiguous-headline-to-market-fanout",
                ],
            },
            prediction_event_lag_manual_review={
                "decision": "research-only-manual-review-no-paper",
                "reviewedWindowCount": 2,
                "decisionCounts": {"reject-paper": 1, "keep-research": 1},
                "readyForPaper": False,
                "readyForExecution": False,
                "blockers": [
                    "no-window-clears-manual-review-for-paper-discussion",
                    "event-market-mapping-or-spread-quality-not-paper-grade",
                    "forward-public-clob-capture-still-required",
                ],
            },
            prediction_paper_promotion_gate={
                "decision": "research-only-paper-promotion-blocked",
                "passCount": 2,
                "blockedCount": 4,
                "blockedIds": [
                    "no-lookahead-event-window",
                    "resolved-label-paper-coverage",
                    "event-market-mapping-clean",
                    "post-spread-clob-edge",
                ],
                "readyForPaper": False,
                "readyForPaperReview": False,
                "readyForExecution": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            realtime_preflight={
                "decision": "block-execution-data",
                "readyForExecutionData": False,
            },
            databento_smoke={
                "status": "NO_QUOTES_MARKET_CLOSED",
                "readyForExecutionDataProof": False,
            },
            worktree={"sourceCleanBlockers": ["dirty execution-live files"]},
            source_intake={
                "decision": "source-intake-visible-execution-locked",
                "sourceClean": False,
                "sourceIntakeVisible": True,
                "executionLiveDirtyCount": 1,
                "reviewBacklogCount": 8,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "validationCommandSets": {
                    "focusedResearchControlSuite": [
                        ".venv/bin/python -m unittest tests.test_bill_source_intake_manifest tests.test_bill_clearance_evidence -v"
                    ],
                    "fullLocalSuiteAndFirewalls": [
                        "npm run --silent typecheck",
                        "npm run --silent test",
                        "npm run --silent bill:verify-execution-quarantine",
                        "npm run --silent bill:clearance-evidence",
                    ],
                    "sourceVisibilityRefresh": [
                        "npm run --silent bill:source-intake-manifest",
                        "npm run --silent bill:source-hygiene-plan",
                        "npm run --silent bill:source-packet-review",
                        "npm run --silent bill:obsidian-sync",
                    ],
                },
            },
            data_intake={
                "decision": "data-intake-visible-execution-locked",
                "dirtyDataFileCount": 9,
                "csvFileCount": 8,
                "executionGradeData": False,
                "readyForExecutionData": False,
                "writesOrders": False,
                "touchesBroker": False,
                "validationCommandSets": {
                    "dataVisibilityRefresh": [
                        "npm run --silent bill:data-intake-manifest",
                        "npm run --silent bill:obsidian-sync",
                    ],
                    "futuresDataEvidence": [
                        "npm run --silent bill:data-freshness-gate || true",
                        "npm run --silent bill:futures-data-requirements",
                        "npm run --silent bill:futures-broker-parity-plan",
                        "npm run --silent bill:open-session-data-proof -- --run-data-only",
                    ],
                },
            },
            execution_intake={
                "decision": "execution-intake-visible-execution-locked",
                "dirtyExecutionFileCount": 23,
                "canonicalExecutionLiveDirtyCount": 23,
                "executionAdjacentFileCount": 18,
                "classificationCounts": {"firewall-covered-still-quarantined": 5},
                "allFirewallCommandsPassed": True,
                "uncoveredExecutionPaths": [],
                "executionLocked": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
                "validationCommandSets": {
                    "executionFirewallEvidence": [
                        "npm run --silent bill:verify-master-bridge-firewall",
                        "npm run --silent bill:verify-60m-bridge-firewall",
                        "npm run --silent bill:verify-topstep-demo-bridge-firewall",
                        "npm run --silent bill:verify-signal-router-firewall",
                        "npm run --silent bill:verify-prediction-funding-firewall",
                        "npm run --silent bill:verify-execution-quarantine",
                        "npm run --silent bill:clearance-evidence",
                    ],
                    "executionVisibilityRefresh": [
                        "npm run --silent bill:execution-intake-manifest",
                        "npm run --silent bill:goal-completion-audit",
                        "npm run --silent bill:obsidian-sync",
                    ],
                },
            },
            signal_quality={
                "command": "signal-quality-advisor",
                "researchOnly": True,
                "writesOrders": False,
                "readyForExecution": False,
                "overallRating": 7.1,
                "blockers": [],
                "warnings": ["proxy shadow input cannot confirm execution: dom_proxy"],
                "shadowSignalRows": [
                    {
                        "name": "dom_proxy",
                        "shadowOnly": True,
                        "proxyOnly": True,
                        "promotedForExecution": False,
                        "tradableSignal": False,
                    }
                ],
            },
            signal_source_truth={
                "command": "signal-source-truth-audit",
                "decision": "source-truth-visible-execution-locked",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
                "issueCount": 1,
                "issues": [
                    {
                        "file": "alpha-lab.latest.json",
                        "issue": "coexists-with-60m-signal-source; keep research and advisory lanes separate",
                    }
                ],
                "sources": [
                    {
                        "file": "alpha-lab.latest.json",
                        "role": "research-candidates",
                        "authority": "never-route",
                        "promotedLikeExecution": False,
                    },
                    {
                        "file": "60m-signals-latest.json",
                        "role": "advisory-shadow-signal",
                        "authority": "never-route-unless-promoted",
                        "promotedLikeExecution": False,
                    },
                    {
                        "file": "arbitration.latest.json",
                        "role": "pre-trade-consensus-gate",
                        "authority": "block-or-reduce-only",
                        "promotedLikeExecution": False,
                    },
                    {
                        "file": "master-signal.latest.json",
                        "role": "execution-candidate",
                        "authority": "requires-daily-plan-and-firewalls",
                        "promotedLikeExecution": False,
                    },
                ],
            },
            storage={"totalSize": "19.3GB", "archiveCandidateSize": "13.0GB", "movesFiles": False, "deletesFiles": False},
            clearance_evidence={"status": "PASS", "allCommandsPassed": True, "failedCommandIds": []},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={
                "decision": "source-hygiene-plan-research-only-execution-locked",
                "researchOnly": True,
                "sourceHygieneCleared": False,
                "automaticCleanupAllowed": False,
                "safeToStageAutomatically": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "dirtyStatusCount": 11,
                "reviewBacklogCount": 10,
                "bundleSummary": [
                    {
                        "id": "validated-research-scaffold",
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    }
                ],
                "bundles": [{"id": "validated-research-scaffold", "count": 2}],
                "nextReductionOrder": [{"rank": 1, "bundleId": "validated-research-scaffold"}],
                "nextReviewPackets": [
                    {
                        "id": "packet-01-control-research-scaffold",
                        "bundleId": "validated-research-scaffold",
                        "pathCount": 2,
                        "paths": ["scripts/a.py"],
                        "pathFootprint": [{"path": "scripts/a.py", "status": "??", "exists": True, "addedLines": 1, "deletedLines": 0, "trackedDiff": False}],
                        "diffSummary": {"pathCount": 1, "existingPathCount": 1, "trackedDiffPathCount": 0, "addedLines": 1, "deletedLines": 0, "statusCounts": {"??": 1}},
                        "commands": ["npm run --silent bill:source-hygiene-plan"],
                        "decision": "manual-review-only",
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "operatorApprovalRequired": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                    {
                        "id": "packet-02-execution-firewall-quarantine",
                        "bundleId": "execution-live-quarantine",
                        "pathCount": 1,
                        "paths": ["scripts/master_bridge.py"],
                        "pathFootprint": [{"path": "scripts/master_bridge.py", "status": "M", "exists": True, "addedLines": 2, "deletedLines": 1, "trackedDiff": True}],
                        "diffSummary": {"pathCount": 1, "existingPathCount": 1, "trackedDiffPathCount": 1, "addedLines": 2, "deletedLines": 1, "statusCounts": {"M": 1}},
                        "commands": ["npm run --silent bill:verify-master-bridge-firewall"],
                        "decision": "quarantine-locked",
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "operatorApprovalRequired": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                    {
                        "id": "packet-03-data-provenance-refresh",
                        "bundleId": "data-research-refresh",
                        "pathCount": 1,
                        "paths": ["data/free/NQ-1m-5d.csv"],
                        "pathFootprint": [{"path": "data/free/NQ-1m-5d.csv", "status": "M", "exists": True, "addedLines": 10, "deletedLines": 9, "trackedDiff": True}],
                        "diffSummary": {"pathCount": 1, "existingPathCount": 1, "trackedDiffPathCount": 1, "addedLines": 10, "deletedLines": 9, "statusCounts": {"M": 1}},
                        "commands": ["npm run --silent bill:data-intake-manifest"],
                        "decision": "research-data-only",
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "operatorApprovalRequired": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                    {
                        "id": "packet-04-strategy-backlog-sample",
                        "bundleId": "strategy-research-review",
                        "pathCount": 1,
                        "paths": ["bill-core/src/gold_strategies.rs"],
                        "pathFootprint": [{"path": "bill-core/src/gold_strategies.rs", "status": "M", "exists": True, "addedLines": 3, "deletedLines": 0, "trackedDiff": True}],
                        "diffSummary": {"pathCount": 1, "existingPathCount": 1, "trackedDiffPathCount": 1, "addedLines": 3, "deletedLines": 0, "statusCounts": {"M": 1}},
                        "commands": ["npm run --silent bill:alpha-frontier-queue"],
                        "decision": "split-before-review",
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "operatorApprovalRequired": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                    {
                        "id": "packet-05-futures-strategy-lane",
                        "bundleId": "strategy-research-review",
                        "pathCount": 2,
                        "paths": ["scripts/futures_nq_research_cycle.py", "scripts/cot_signal.py"],
                        "pathFootprint": [
                            {"path": "scripts/futures_nq_research_cycle.py", "status": "??", "exists": True, "addedLines": 1, "deletedLines": 0, "trackedDiff": False},
                            {"path": "scripts/cot_signal.py", "status": "M", "exists": True, "addedLines": 2, "deletedLines": 1, "trackedDiff": True},
                        ],
                        "diffSummary": {"pathCount": 2, "existingPathCount": 2, "trackedDiffPathCount": 1, "addedLines": 3, "deletedLines": 1, "statusCounts": {"??": 1, "M": 1}},
                        "commands": [
                            "npm run --silent bill:futures-evidence-triage || true",
                            "npm run --silent bill:futures-broker-parity-plan",
                        ],
                        "decision": "lane-review-only",
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "operatorApprovalRequired": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                    {
                        "id": "packet-06-prediction-market-lane",
                        "bundleId": "strategy-research-review",
                        "pathCount": 2,
                        "paths": ["scripts/prediction_event_lag_replay.py", "scripts/polymarket_clob_recorder.mjs"],
                        "pathFootprint": [
                            {"path": "scripts/prediction_event_lag_replay.py", "status": "??", "exists": True, "addedLines": 1, "deletedLines": 0, "trackedDiff": False},
                            {"path": "scripts/polymarket_clob_recorder.mjs", "status": "??", "exists": True, "addedLines": 1, "deletedLines": 0, "trackedDiff": False},
                        ],
                        "diffSummary": {"pathCount": 2, "existingPathCount": 2, "trackedDiffPathCount": 0, "addedLines": 2, "deletedLines": 0, "statusCounts": {"??": 2}},
                        "commands": [
                            "npm run --silent bill:prediction-evidence-triage",
                            "npm run --silent bill:verify-prediction-funding-firewall",
                        ],
                        "decision": "lane-review-only",
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "operatorApprovalRequired": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                ],
            },
            open_session_data_proof={
                "command": "bill-open-session-data-proof",
                "mode": "run-data-only",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": True,
                "brokerTouchMode": "read-only-market-data",
                "movesFunds": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "brokerReadOnlyStepIncluded": True,
                "preferredDataPath": "topstepx_projectx",
                "includeDatabentoOptionalProof": True,
                "allCommandsPassed": True,
                "executionGradeDataProofPassed": False,
                "failedStepIds": [],
                "plannedStepIds": [
                    "topstep-realtime-proof",
                    "topstep-realtime-bridge-write",
                    "databento-open-session-smoke",
                    "topstep-readonly-bar-archive",
                    "databento-open-session-bridge-write",
                ],
                "plannedSteps": [
                    {
                        "id": "topstep-realtime-proof",
                        "command": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false RH_TOPSTEP_READ_ONLY=true npm run --silent bill:topstep-realtime-proof",
                        "env": {
                            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                            "RH_TOPSTEP_READ_ONLY": "true",
                            "RH_LIVE_EXECUTION_ENABLED": "false",
                        },
                        "writesOrders": False,
                        "touchesBroker": True,
                        "brokerTouchMode": "read-only-market-data",
                        "movesFunds": False,
                    },
                    {
                        "id": "topstep-realtime-bridge-write",
                        "command": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false RH_TOPSTEP_READ_ONLY=true npm run --silent bill:topstep-realtime-bridge",
                        "env": {
                            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                            "RH_TOPSTEP_READ_ONLY": "true",
                            "RH_LIVE_EXECUTION_ENABLED": "false",
                        },
                        "writesOrders": False,
                        "touchesBroker": True,
                        "brokerTouchMode": "read-only-market-data",
                        "movesFunds": False,
                    },
                    {
                        "id": "databento-open-session-smoke",
                        "command": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false RH_TOPSTEP_READ_ONLY=true npm run --silent bill:databento-realtime-smoke -- --timeout-sec 20.0",
                        "env": {
                            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                            "RH_TOPSTEP_READ_ONLY": "true",
                            "RH_LIVE_EXECUTION_ENABLED": "false",
                        },
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                    {
                        "id": "topstep-readonly-bar-archive",
                        "command": "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false RH_TOPSTEP_READ_ONLY=true npm run --silent bill:topstep-readonly-bar-archive",
                        "env": {
                            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                            "RH_TOPSTEP_READ_ONLY": "true",
                            "RH_LIVE_EXECUTION_ENABLED": "false",
                        },
                        "writesOrders": False,
                        "touchesBroker": True,
                        "brokerTouchMode": "read-only-market-data",
                        "movesFunds": False,
                    },
                    {
                        "id": "databento-open-session-bridge-write",
                        "argv": [".venv/bin/python", "scripts/realtime_data_bridge.py", "--quiet", "--databento-only"],
                        "command": "BILL_DATABENTO_REALTIME_ENABLED=true BILL_ENABLE_FUTURES_DEMO_EXECUTION=false RH_LIVE_EXECUTION_ENABLED=false RH_TOPSTEP_READ_ONLY=true .venv/bin/python scripts/realtime_data_bridge.py --quiet --databento-only",
                        "env": {
                            "BILL_DATABENTO_REALTIME_ENABLED": "true",
                            "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                            "RH_TOPSTEP_READ_ONLY": "true",
                            "RH_LIVE_EXECUTION_ENABLED": "false",
                        },
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                ],
            },
            source_packet_review={
                "decision": "source-packet-review-visible-execution-locked",
                "researchOnly": True,
                "sourceHygieneCleared": False,
                "packetReviewCleared": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "safeToStageAutomatically": False,
                "automaticCleanupAllowed": False,
                "operatorApprovalRequired": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "missingPackets": [],
                "reviewedPacketCount": 3,
                "classificationCounts": {"keep-research": 2, "shadow-only": 1},
                "manualClearanceProposal": {
                    "decision": "manual-clearance-proposal-only",
                    "researchOnly": True,
                    "safeToStageAutomatically": False,
                    "writesOrders": False,
                    "touchesBroker": False,
                    "movesFunds": False,
                    "nextCommands": [
                        "npm run --silent bill:source-packet-review",
                        "npm run --silent bill:clearance-evidence",
                    ],
                    "hardBlockers": ["operator approval required before staging"],
                    "laneProposals": [
                        {
                            "lane": "control-research",
                            "reviewFirst": [],
                            "keepResearchCandidates": ["scripts/bill_source_hygiene_plan.py"],
                            "shadowOnly": [],
                            "quarantineReview": [],
                            "safeToStageAutomatically": False,
                            "writesOrders": False,
                            "touchesBroker": False,
                            "movesFunds": False,
                        },
                        {
                            "lane": "futures",
                            "reviewFirst": ["scripts/cot_signal.py"],
                            "keepResearchCandidates": ["scripts/futures_data_requirements.py"],
                            "shadowOnly": ["scripts/dom_proxy_ohlcv.py"],
                            "quarantineReview": [],
                            "safeToStageAutomatically": False,
                            "writesOrders": False,
                            "touchesBroker": False,
                            "movesFunds": False,
                        },
                        {
                            "lane": "prediction-markets",
                            "reviewFirst": ["src/prediction/matcher.ts"],
                            "keepResearchCandidates": ["scripts/kalshi_fillability_snapshot.py"],
                            "shadowOnly": [],
                            "quarantineReview": [],
                            "safeToStageAutomatically": False,
                            "writesOrders": False,
                            "touchesBroker": False,
                            "movesFunds": False,
                        },
                    ],
                },
                "packets": [
                    {
                        "id": "packet-01-control-research-scaffold",
                        "lane": "control-research",
                        "decision": "manual-review-only",
                        "packetDecision": "manual-review-only",
                        "pathCount": 1,
                        "classificationCounts": {"keep-research": 1},
                        "firstCommand": "npm run --silent bill:source-hygiene-plan",
                        "researchOnly": True,
                        "rows": [{"path": "scripts/bill_source_hygiene_plan.py", "classification": "keep-research"}],
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "operatorApprovalRequired": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                        "readyForExecution": False,
                    },
                    {
                        "id": "packet-05-futures-strategy-lane",
                        "lane": "futures",
                        "decision": "manual-review-only",
                        "packetDecision": "lane-review-only",
                        "pathCount": 1,
                        "classificationCounts": {"shadow-only": 1},
                        "firstCommand": "npm run --silent bill:futures-evidence-triage || true",
                        "researchOnly": True,
                        "rows": [{"path": "scripts/dom_proxy_ohlcv.py", "classification": "shadow-only"}],
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "operatorApprovalRequired": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                        "readyForExecution": False,
                    },
                    {
                        "id": "packet-06-prediction-market-lane",
                        "lane": "prediction-markets",
                        "decision": "manual-review-only",
                        "packetDecision": "lane-review-only",
                        "pathCount": 1,
                        "classificationCounts": {"keep-research": 1},
                        "firstCommand": "npm run --silent bill:prediction-evidence-triage",
                        "researchOnly": True,
                        "rows": [{"path": "scripts/prediction_event_lag_replay.py", "classification": "keep-research"}],
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "operatorApprovalRequired": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                        "readyForExecution": False,
                    },
                ],
            },
            sibling_worktree_intake={
                "decision": "sibling-worktree-intake-visible-quarantine",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "sourceHygieneCleared": False,
                "safeToMergeAutomatically": False,
                "dirtySiblingWorktreeCount": 1,
                "dirtyFileCount": 111,
                "executionLiveDirtyCount": 5,
                "classificationCounts": {
                    "execution-live-quarantine": 5,
                    "governance-risk-review": 26,
                    "strategy-research-review": 27,
                },
                "blockers": [
                    "dirty-sibling-worktree-requires-selective-intake",
                    "sibling-worktree-has-execution-live-dirty-files",
                ],
            },
            cron_validator={
                "summary": "2 issues flagged",
                "cron_trust": {
                    "activeDirtyExecutionLiveScriptReferenceCount": 2,
                    "activeDirtyExecutionLiveScriptReferences": [
                        {
                            "name": "60m-lucidflex-execution",
                            "script": "60m_exec_bridge.py",
                            "source": {
                                "relativePath": "scripts/60m_exec_bridge.py",
                                "classification": "firewall-covered-still-quarantined",
                                "firewallPassed": True,
                            },
                        },
                        {
                            "name": "agentic-fund-cycle",
                            "script": "agentic_fund.sh",
                            "source": {
                                "relativePath": "scripts/agentic_fund.sh",
                                "classification": "firewall-covered-still-quarantined",
                                "firewallPassed": True,
                            },
                        },
                    ],
                    "activeTradingAgentBackedCount": 0,
                    "noAgentMetadataMismatchCount": 0,
                    "executionIntakeManifest": "/tmp/bill-execution-intake-manifest.latest.json",
                },
                "issues": [
                    {
                        "type": "active_cron_references_dirty_execution_live_script",
                        "severity": "P1",
                        "job": "60m-lucidflex-execution",
                    },
                    {
                        "type": "active_cron_references_dirty_execution_live_script",
                        "severity": "P1",
                        "job": "agentic-fund-cycle",
                    },
                ],
            },
            codex_automation=safe_codex_automation_audit(),
            runtime_architecture=safe_runtime_architecture_audit(),
            resource_inventory_text="\n".join(
                [
                    "# Bill Resource Inventory",
                    "Full machine-readable manifest: Bill-Resource-Full-Manifest.jsonl",
                    "Display policy: highest-signal Bill/Hermes resources first; archived repo READMEs/examples are down-ranked, not removed.",
                    "- `execution-review`: execution/funding-adjacent code; review firewall evidence before use.",
                    "## Priority Outside Obsidian",
                ]
            ),
        )

        self.assertFalse(payload["goalComplete"])
        self.assertEqual(payload["decision"], "continue-research-only-locked")
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])
        self.assertIn("futures-demo-not-cleared", payload["blockedIds"])
        self.assertIn("prediction-paper-not-cleared", payload["blockedIds"])
        self.assertIn("execution-grade-data-not-cleared", payload["blockedIds"])
        self.assertIn("source-hygiene-not-cleared", payload["blockedIds"])
        self.assertIn("cron-control-trust-not-cleared", payload["blockedIds"])
        self.assertNotIn("codex-automation-control-visible", payload["blockedIds"])
        self.assertIn("promptToArtifactChecklist", payload)
        self.assertIn("source-hygiene-not-faked", payload["promptUncoveredIds"])
        self.assertIn("prediction-frontier-wired", payload["promptUncoveredIds"])
        prompt_checks = {item["id"]: item for item in payload["promptToArtifactChecklist"]}
        self.assertEqual(prompt_checks["execution-remains-locked"]["status"], "pass")
        self.assertEqual(prompt_checks["codex-automation-loops-controlled"]["status"], "pass")
        self.assertEqual(prompt_checks["runtime-architecture-and-ai-scientist-wired"]["status"], "pass")
        self.assertEqual(
            prompt_checks["codex-automation-loops-controlled"]["evidence"]["activeFuturesOpenSessionProofIds"],
            [
                "bill-futures-open-session-data-proof",
                "bill-open-session-data-proof",
            ],
        )
        self.assertEqual(
            prompt_checks["codex-automation-loops-controlled"]["evidence"]["activeFuturesOpenSessionProofConflictIds"],
            [],
        )
        self.assertIn(
            "/Users/brain/.codex/automations/bill-open-session-data-proof/automation.toml",
            prompt_checks["codex-automation-loops-controlled"]["artifacts"],
        )
        self.assertEqual(prompt_checks["source-hygiene-not-faked"]["status"], "blocked")
        self.assertIn(
            ".rumbling-hedge/state/bill-source-hygiene-plan.latest.json",
            prompt_checks["source-hygiene-not-faked"]["artifacts"],
        )
        self.assertIn(
            ".rumbling-hedge/state/bill-sibling-worktree-intake.latest.json",
            prompt_checks["source-hygiene-not-faked"]["artifacts"],
        )
        self.assertEqual(
            prompt_checks["source-hygiene-not-faked"]["evidence"]["siblingWorktreeIntake"]["executionLiveDirtyCount"],
            5,
        )
        self.assertFalse(
            prompt_checks["source-hygiene-not-faked"]["evidence"]["siblingWorktreeIntake"]["safeToMergeAutomatically"],
        )
        self.assertEqual(prompt_checks["source-hygiene-not-faked"]["evidence"]["reviewBacklogCount"], 8)
        self.assertEqual(prompt_checks["source-hygiene-not-faked"]["evidence"]["hygienePlanReviewBacklogCount"], 10)
        self.assertIn(
            "explicit paper-promotion gate remains blocked",
            prompt_checks["prediction-frontier-wired"]["uncovered"],
        )
        self.assertIn(
            ".rumbling-hedge/state/prediction-event-paper-promotion-gate.latest.json",
            prompt_checks["prediction-frontier-wired"]["artifacts"],
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventLagSensitivity"]["bestRepricedWindowCount"],
            2,
        )
        self.assertFalse(prompt_checks["prediction-frontier-wired"]["evidence"]["eventLagSensitivity"]["readyForPaper"])
        self.assertTrue(prompt_checks["prediction-frontier-wired"]["evidence"]["eventLagResearchWatchReady"])
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventLagWatchReview"]["repricedWatchWindowCount"],
            2,
        )
        self.assertFalse(prompt_checks["prediction-frontier-wired"]["evidence"]["eventLagWatchReview"]["readyForPaper"])
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventLagManualReview"]["reviewedWindowCount"],
            2,
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventLagManualReview"]["decisionCounts"]["reject-paper"],
            1,
        )
        self.assertFalse(prompt_checks["prediction-frontier-wired"]["evidence"]["eventLagManualReview"]["readyForPaper"])
        self.assertIn(
            "forward-public-clob-capture-still-required",
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventLagManualReview"]["blockers"],
        )
        self.assertIn(
            ".rumbling-hedge/state/prediction-event-mapping-refinement.latest.json",
            prompt_checks["prediction-frontier-wired"]["artifacts"],
        )
        self.assertIn(
            ".rumbling-hedge/state/prediction-event-market-mapping-plan.latest.json",
            prompt_checks["prediction-frontier-wired"]["artifacts"],
        )
        self.assertIn(
            "ambiguous-headline-event-family-fanout",
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMarketMapping"]["blockers"],
        )
        self.assertIn(
            "ambiguous-headline-counterparty-fanout",
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMarketMapping"]["blockers"],
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMarketMapping"]["headlineFamilyFanoutCount"],
            2,
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMarketMapping"]["ambiguousHeadlineFamilyFanoutCount"],
            1,
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMarketMapping"]["ambiguousHeadlineCounterpartyFanoutCount"],
            1,
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingRefinement"]["mappingCandidateCount"],
            20,
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingRefinement"]["mappingRepairTargetCount"],
            1,
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingRefinement"]["mappingRepairTargetSample"][0]["candidateCount"],
            15,
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingRefinement"]["publicCaptureReviewLeadCount"],
            1,
        )
        self.assertIn(
            "not a mapping override",
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingRefinement"]["publicCaptureReviewLeadSample"][0]["reviewUseOnly"],
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingRefinement"]["deadlineLadderCaptureCandidateCount"],
            1,
        )
        self.assertIn(
            "deadline-ladder-forward-capture-only",
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingRefinement"]["deadlineLadderCaptureCandidateSample"][0]["reviewUseOnly"],
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingExclusions"]["tokenSpecificCandidateCount"],
            5,
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingExclusions"]["excludedMappingCandidateCount"],
            15,
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingExclusions"]["excludedMappingReasonCounts"]["market-counterparty-not-explicit-in-headline"],
            15,
        )
        self.assertIn(
            "ambiguous-headline-to-market-fanout",
            prompt_checks["prediction-frontier-wired"]["evidence"]["eventMappingRefinement"]["blockers"],
        )
        self.assertEqual(
            prompt_checks["prediction-frontier-wired"]["evidence"]["paperPromotionGate"]["decision"],
            "research-only-paper-promotion-blocked",
        )
        self.assertIn(
            "post-spread-clob-edge",
            prompt_checks["prediction-frontier-wired"]["evidence"]["paperPromotionGate"]["blockedIds"],
        )
        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(
            checks["prediction-paper-not-cleared"]["evidence"]["eventLagSensitivity"]["watchScenarioCount"],
            2,
        )
        self.assertFalse(checks["prediction-paper-not-cleared"]["evidence"]["eventLagSensitivity"]["readyForPaper"])
        self.assertTrue(checks["prediction-paper-not-cleared"]["evidence"]["eventLagResearchWatchReady"])
        self.assertTrue(checks["prediction-paper-not-cleared"]["evidence"]["eventLagWatchReview"]["watchReady"])
        self.assertEqual(
            checks["prediction-paper-not-cleared"]["evidence"]["eventLagManualReview"]["decision"],
            "research-only-manual-review-no-paper",
        )
        self.assertIn(
            "explicit paper-promotion gate remains blocked",
            checks["prediction-paper-not-cleared"]["blocker"],
        )
        self.assertTrue(checks["prediction-paper-not-cleared"]["evidence"]["captureCycleEvidencePassed"])
        self.assertFalse(checks["prediction-paper-not-cleared"]["evidence"]["paperPromotionEvidencePassed"])
        self.assertEqual(
            checks["prediction-paper-not-cleared"]["evidence"]["executedRecorder"]["tokenIds"],
            ["selected-review-token"],
        )
        self.assertIn(
            "paper-review-requires-positive-fillability-and-spread-adjusted-replay",
            checks["prediction-paper-not-cleared"]["evidence"]["paperPromotionBlockers"],
        )
        self.assertEqual(checks["prediction-paper-not-cleared"]["evidence"]["eventMarketMapping"]["ambiguousHeadlineCount"], 1)
        self.assertEqual(checks["prediction-paper-not-cleared"]["evidence"]["eventMarketMapping"]["ambiguousCounterpartyHeadlineCount"], 1)
        self.assertEqual(checks["prediction-paper-not-cleared"]["evidence"]["eventMarketMapping"]["ambiguousHeadlineFamilyFanoutCount"], 1)
        self.assertEqual(checks["prediction-paper-not-cleared"]["evidence"]["eventMarketMapping"]["ambiguousHeadlineCounterpartyFanoutCount"], 1)
        self.assertEqual(checks["prediction-paper-not-cleared"]["evidence"]["eventMappingExclusions"]["excludedMappingCandidateCount"], 15)
        self.assertIn(
            "ambiguous-headline-counterparty-fanout",
            checks["prediction-paper-not-cleared"]["evidence"]["eventMappingExclusions"]["mappingBlockers"],
        )
        self.assertFalse(checks["prediction-paper-not-cleared"]["evidence"]["eventMappingRefinement"]["readyForPaper"])
        self.assertEqual(checks["prediction-paper-not-cleared"]["evidence"]["eventMappingRefinement"]["mappingRepairTargetCount"], 1)
        self.assertEqual(checks["prediction-paper-not-cleared"]["evidence"]["eventMappingRefinement"]["publicCaptureReviewLeadCount"], 1)
        self.assertEqual(checks["source-hygiene-not-cleared"]["evidence"]["siblingWorktreeIntake"]["dirtyFileCount"], 111)
        self.assertEqual(checks["source-intake-visible"]["status"], "pass")
        self.assertIn("validationCommandSets", checks["source-intake-visible"]["evidence"])
        self.assertEqual(checks["futures-loop-focused"]["status"], "pass")
        self.assertFalse(checks["futures-loop-focused"]["evidence"]["readyForExecution"])
        self.assertFalse(checks["futures-loop-focused"]["evidence"]["readyForDemoExpansion"])
        self.assertFalse(checks["futures-loop-focused"]["evidence"]["historicalCurrentParitySummary"]["cleared"])
        self.assertIn(
            "research/OOS only",
            checks["futures-loop-focused"]["evidence"]["historicalCurrentParitySummary"]["operatorRead"],
        )
        self.assertEqual(checks["futures-broker-parity-visible"]["status"], "pass")
        self.assertIn("validationCommandSets", checks["futures-broker-parity-visible"]["evidence"])
        self.assertIn(
            "current-session depth",
            checks["futures-demo-not-cleared"]["blocker"],
        )
        self.assertIn(
            "Topstep broker/local parity",
            checks["futures-demo-not-cleared"]["blocker"],
        )
        self.assertNotIn(
            "current/broker parity",
            checks["futures-demo-not-cleared"]["blocker"],
        )
        self.assertEqual(checks["paper-source-frontier-wired"]["status"], "pass")
        self.assertIn("requires-one-variable-oos-before-promotion", checks["paper-source-frontier-wired"]["evidence"]["promotionBlockers"])
        self.assertEqual(checks["data-intake-visible"]["status"], "pass")
        self.assertIn("validationCommandSets", checks["data-intake-visible"]["evidence"])
        self.assertEqual(checks["execution-intake-visible"]["status"], "pass")
        self.assertIn("validationCommandSets", checks["execution-intake-visible"]["evidence"])
        self.assertEqual(checks["signal-quality-visible"]["status"], "pass")
        self.assertEqual(checks["signal-quality-visible"]["evidence"]["overallRating"], 7.1)
        self.assertEqual(
            checks["signal-quality-visible"]["evidence"]["sourceTruthRoles"]["alpha-lab.latest.json"]["authority"],
            "never-route",
        )
        self.assertEqual(checks["cron-control-trust-not-cleared"]["status"], "blocked")
        self.assertEqual(checks["codex-automation-control-visible"]["status"], "pass")
        self.assertEqual(
            checks["codex-automation-control-visible"]["evidence"]["activeFuturesOpenSessionProofCount"],
            2,
        )
        self.assertEqual(
            checks["codex-automation-control-visible"]["evidence"]["activeFuturesOpenSessionProofConflictIds"],
            [],
        )
        self.assertEqual(
            checks["cron-control-trust-not-cleared"]["evidence"]["activeDirtyExecutionLiveScriptReferenceCount"],
            2,
        )
        self.assertEqual(
            checks["cron-control-trust-not-cleared"]["evidence"]["blockingIssues"][0]["type"],
            "active_cron_references_dirty_execution_live_script",
        )
        self.assertEqual(checks["source-hygiene-plan-visible"]["status"], "pass")
        self.assertEqual(checks["source-hygiene-plan-visible"]["evidence"]["dirtyStatusCount"], 11)
        self.assertEqual(checks["source-hygiene-plan-visible"]["evidence"]["reviewBacklogCount"], 8)
        self.assertEqual(checks["source-hygiene-plan-visible"]["evidence"]["hygienePlanReviewBacklogCount"], 10)
        self.assertEqual(len(checks["source-hygiene-plan-visible"]["evidence"]["nextReviewPackets"]), 6)
        self.assertEqual(
            checks["source-hygiene-plan-visible"]["evidence"]["nextReviewPackets"][0]["diffSummary"]["pathCount"],
            1,
        )
        self.assertEqual(checks["futures-prediction-lane-packets-visible"]["status"], "pass")
        self.assertIn(
            "scripts/futures_nq_research_cycle.py",
            checks["futures-prediction-lane-packets-visible"]["evidence"]["futuresPacket"]["paths"],
        )
        self.assertIn(
            "scripts/prediction_event_lag_replay.py",
            checks["futures-prediction-lane-packets-visible"]["evidence"]["predictionPacket"]["paths"],
        )
        self.assertEqual(checks["source-packet-review-visible"]["status"], "pass")
        self.assertEqual(checks["source-packet-review-visible"]["evidence"]["reviewedPacketCount"], 3)
        self.assertEqual(
            checks["source-packet-review-visible"]["evidence"]["manualClearanceProposal"]["decision"],
            "manual-clearance-proposal-only",
        )
        self.assertEqual(
            checks["source-packet-review-visible"]["evidence"]["manualClearanceProposal"]["laneProposals"][0]["reviewFirst"],
            [],
        )
        self.assertEqual(
            checks["source-packet-review-visible"]["evidence"]["manualClearanceProposal"]["laneProposals"][1]["reviewFirst"],
            ["scripts/cot_signal.py"],
        )
        self.assertEqual(
            checks["source-packet-review-visible"]["evidence"]["packets"][0]["firstCommand"],
            "npm run --silent bill:source-hygiene-plan",
        )
        self.assertEqual(
            checks["source-packet-review-visible"]["evidence"]["packets"][1]["firstCommand"],
            "npm run --silent bill:futures-evidence-triage || true",
        )
        self.assertTrue(checks["source-packet-review-visible"]["evidence"]["packets"][0]["researchOnly"])
        self.assertEqual(checks["obsidian-resource-inventory-visible"]["status"], "pass")
        self.assertTrue(checks["obsidian-resource-inventory-visible"]["evidence"]["hasPriorityOutsideObsidian"])
        self.assertTrue(checks["obsidian-resource-inventory-visible"]["evidence"]["hasExecutionReviewLabel"])
        self.assertEqual(checks["open-session-data-proof-visible"]["status"], "pass")
        self.assertEqual(checks["control-plane-queue"]["status"], "pass")
        self.assertGreater(payload["passCount"], 0)

    def test_control_plane_queue_passes_when_topstep_session_safety_pauses_broker_proofs(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True, "blockers": []},
            next_actions={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "actions": [
                    {
                        "id": "control-plane-clearance-before-demo",
                        "commands": [
                            "npm run --silent bill:realtime-data-preflight || true",
                            "npm run --silent bill:databento-realtime-smoke",
                            "npm run --silent bill:data-freshness-gate || true",
                            "npm run --silent bill:futures-broker-parity-plan",
                            "npm run --silent bill:live-readiness-gate || true",
                            "npm run --silent bill:source-intake-manifest",
                            "npm run --silent bill:source-hygiene-plan",
                            "npm run --silent bill:data-intake-manifest",
                            "npm run --silent bill:verify-execution-quarantine",
                            "npm run --silent bill:execution-intake-manifest",
                            "npm run --silent bill:clearance-handoff",
                            "npm run --silent bill:goal-completion-audit",
                            "npm run --silent bill:obsidian-sync",
                        ],
                        "dataOnlyProof": {
                            "pausedByTopstepSessionSafety": True,
                            "topstepSessionSafety": {
                                "pauseBrokerTouchingProofs": True,
                                "safeUntil": "operator-confirms-topstep-session-warning-cleared",
                            },
                            "writesOrders": False,
                            "touchesBroker": True,
                            "brokerTouchMode": "read-only-market-data",
                            "movesFunds": False,
                        },
                    }
                ],
            },
            futures_cycle={"researchOnly": True, "readyForExecution": False, "readyForDemoExpansion": False, "blockers": []},
            futures_requirements={"researchOnly": True, "readyForDemoExpansion": False},
            prediction_capture={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False},
            realtime_preflight={"readyForExecutionData": False},
            databento_smoke={"readyForExecutionDataProof": False},
            worktree={},
            storage={},
            clearance_evidence={},
            daily_text="No new Bill/Hermes orders approved\nBILL_ROUTE_APPROVAL: BLOCKED\n",
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["control-plane-queue"]["status"], "pass")
        self.assertNotIn("blocker", checks["control-plane-queue"])
        commands = checks["control-plane-queue"]["evidence"]["commands"]
        self.assertIn("npm run --silent bill:futures-broker-parity-plan", commands)
        self.assertFalse(any("bill:open-session-data-proof" in command for command in commands))
        self.assertFalse(any("bill:clearance-evidence" in command for command in commands))

    def test_open_session_data_proof_visibility_passes_when_topstep_session_safety_pauses_refresh(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True, "blockers": []},
            next_actions={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "actions": [
                    {
                        "id": "control-plane-clearance-before-demo",
                        "commands": [
                            "npm run --silent bill:realtime-data-preflight || true",
                            "npm run --silent bill:databento-realtime-smoke",
                            "npm run --silent bill:futures-broker-parity-plan",
                            "npm run --silent bill:live-readiness-gate || true",
                            "npm run --silent bill:source-intake-manifest",
                            "npm run --silent bill:source-hygiene-plan",
                            "npm run --silent bill:data-intake-manifest",
                            "npm run --silent bill:verify-execution-quarantine",
                            "npm run --silent bill:execution-intake-manifest",
                            "npm run --silent bill:clearance-handoff",
                            "npm run --silent bill:goal-completion-audit",
                            "npm run --silent bill:obsidian-sync",
                        ],
                        "dataOnlyProof": {
                            "pausedByTopstepSessionSafety": True,
                            "topstepSessionSafety": {
                                "pauseBrokerTouchingProofs": True,
                                "safeUntil": "operator-confirms-topstep-session-warning-cleared",
                            },
                            "writesOrders": False,
                            "touchesBroker": True,
                            "brokerTouchMode": "read-only-market-data",
                            "movesFunds": False,
                        },
                    }
                ],
            },
            futures_cycle={"researchOnly": True, "readyForExecution": False, "readyForDemoExpansion": False, "blockers": []},
            futures_requirements={"researchOnly": True, "readyForDemoExpansion": False},
            prediction_capture={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False},
            realtime_preflight={"readyForExecutionData": False},
            databento_smoke={"readyForExecutionDataProof": False},
            worktree={},
            storage={},
            clearance_evidence={},
            daily_text="No new Bill/Hermes orders approved\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            open_session_data_proof={
                "command": "bill-open-session-data-proof",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "brokerTouchMode": None,
                "movesFunds": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "brokerReadOnlyStepIncluded": False,
                "brokerTouchingProofsPaused": True,
                "skippedBrokerTouchingStepIds": [
                    "topstep-realtime-proof",
                    "topstep-realtime-bridge-write",
                    "topstep-readonly-bar-archive",
                ],
                "plannedStepIds": [
                    "refresh-broker-parity-plan-before",
                    "refresh-realtime-preflight",
                    "refresh-data-freshness",
                    "sync-obsidian",
                ],
                "plannedSteps": [
                    {
                        "id": "refresh-realtime-preflight",
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    }
                ],
            },
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["open-session-data-proof-visible"]["status"], "pass")
        self.assertTrue(checks["open-session-data-proof-visible"]["evidence"]["pausedByTopstepSessionSafety"])

    def test_cron_control_trust_passes_when_no_blocking_refs_or_p1_issues(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
            cron_validator={
                "summary": "ok",
                "cron_trust": {
                    "activeDirtyExecutionLiveScriptReferenceCount": 0,
                    "activeDirtyExecutionLiveScriptReferences": [],
                    "activeTradingAgentBackedCount": 0,
                    "noAgentMetadataMismatchCount": 0,
                },
                "issues": [{"type": "shadow_state_stale", "severity": "P2"}],
            },
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["cron-control-trust-not-cleared"]["status"], "pass")
        self.assertNotIn("cron-control-trust-not-cleared", payload["blockedIds"])

    def test_codex_automation_audit_blocks_when_capture_loops_are_duplicated(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            codex_automation={
                **safe_codex_automation_audit(),
                "status": "BLOCKED",
                "activePredictionCaptureIds": [
                    "bill-prediction-forward-clob-capture",
                    "bill-prediction-event-clob-capture",
                ],
                "pausedPredictionCaptureIds": [],
                "blockers": ["multiple-active-prediction-clob-captures"],
            },
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        prompt_checks = {item["id"]: item for item in payload["promptToArtifactChecklist"]}

        self.assertEqual(checks["codex-automation-control-visible"]["status"], "blocked")
        self.assertIn("codex-automation-control-visible", payload["blockedIds"])
        self.assertEqual(prompt_checks["codex-automation-loops-controlled"]["status"], "blocked")
        self.assertIn("codex-automation-loops-controlled", payload["promptUncoveredIds"])

    def test_futures_open_session_proof_conflict_blocks_codex_automation_control(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            futures_broker_parity={},
            prediction_capture={},
            prediction_market_mapping={},
            prediction_mapping_refinement={},
            realtime_preflight={},
            databento_smoke={},
            source_intake={},
            source_hygiene={},
            source_packet_review={},
            sibling_worktree_intake={},
            worktree={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            codex_automation={
                **safe_codex_automation_audit(),
                "status": "BLOCKED",
                "activeFuturesOpenSessionProofConflictIds": [
                    "bill-futures-open-session-data-proof",
                    "bill-open-session-data-proof",
                ],
                "blockers": ["multiple-active-futures-open-session-proofs-same-window"],
            },
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        prompt_checks = {item["id"]: item for item in payload["promptToArtifactChecklist"]}

        self.assertEqual(checks["codex-automation-control-visible"]["status"], "blocked")
        self.assertIn("codex-automation-control-visible", payload["blockedIds"])
        self.assertIn(
            "bill-open-session-data-proof",
            checks["codex-automation-control-visible"]["evidence"]["activeFuturesOpenSessionProofConflictIds"],
        )
        self.assertEqual(prompt_checks["codex-automation-loops-controlled"]["status"], "blocked")
        self.assertIn("codex-automation-loops-controlled", payload["promptUncoveredIds"])

    def test_missing_public_recorder_command_blocks_prediction_loop_check(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "actions": [
                    {"id": "control-plane-clearance-before-demo", "commands": []},
                    {"id": "futures-paid-nq-1m-session-structure-oos", "commands": []},
                    {"id": "prediction-news-first-event-lag-study", "commands": ["npm run --silent bill:prediction-event-capture-cycle"]},
                ],
            },
            futures_cycle={},
            futures_requirements={},
            prediction_capture={"decision": "research-only-capture-cycle-dry-run-ready"},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["prediction-loop-focused"]["status"], "blocked")
        self.assertEqual(payload["decision"], "continue-research-only-locked")

    def test_prediction_loop_requires_safe_research_only_capture_artifact(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "actions": [
                    {
                        "id": "prediction-news-first-event-lag-study",
                        "commands": [
                            "npm run --silent bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 15",
                        ],
                    }
                ],
            },
            futures_cycle={},
            futures_requirements={},
            prediction_capture={
                "decision": "research-only-capture-cycle-ran",
                "mode": "run-recorder",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "readyForPaper": True,
                "paperPromotionEvidencePassed": True,
                "latestRecorder": {
                    "writesOrders": False,
                    "liveQualityDiagnostics": {"readyForPaperEvidence": True},
                },
            },
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["prediction-loop-focused"]["status"], "blocked")
        self.assertIn("safe research-only recorder artifact", checks["prediction-loop-focused"]["blocker"])

    def test_futures_loop_requires_safe_research_only_cycle_artifact(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "actions": [
                    {
                        "id": "futures-paid-nq-1m-session-structure-oos",
                        "commands": [
                            "npm run --silent bill:futures-nq-historical-session-replay",
                            "npm run --silent bill:futures-nq-current-data-parity",
                            "npm run --silent bill:futures-data-requirements",
                            "npm run --silent bill:futures-broker-parity-plan",
                            "npm run --silent bill:futures-nq-research-cycle",
                        ],
                    }
                ],
            },
            futures_cycle={
                "decision": "research-only-futures-cycle-ran",
                "mode": "run-local-research",
                "researchOnly": True,
                "readyForExecution": True,
                "readyForDemoExpansion": True,
                "blockers": [],
            },
            futures_requirements={
                "decision": "data-requirements-cleared",
                "researchOnly": True,
                "readyForDemoExpansion": True,
            },
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["futures-loop-focused"]["status"], "blocked")
        self.assertIn("safe research-only", checks["futures-loop-focused"]["blocker"])

    def test_missing_futures_broker_parity_plan_blocks_broker_parity_check(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            futures_broker_parity={
                "decision": "research-only-futures-broker-parity-not-cleared",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "missingProofs": ["open-session-execution-grade-realtime-proof"],
                "safeEnv": {
                    "BILL_ENABLE_FUTURES_DEMO_EXECUTION": "false",
                    "RH_TOPSTEP_READ_ONLY": "true",
                    "RH_LIVE_EXECUTION_ENABLED": "false",
                },
                "nextOpenSessionProofWindow": {"commandsAreDataOnly": True},
                "proofSequence": [],
                "validationCommandSets": {},
            },
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["futures-broker-parity-visible"]["status"], "blocked")
        self.assertIn("open-session/read-only validation commands", checks["futures-broker-parity-visible"]["blocker"])

    def test_missing_source_validation_command_sets_blocks_source_intake_check(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={
                "decision": "source-intake-visible-execution-locked",
                "sourceClean": False,
                "sourceIntakeVisible": True,
                "executionLiveDirtyCount": 1,
                "writesOrders": False,
                "touchesBroker": False,
                "readyForExecution": False,
            },
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["source-intake-visible"]["status"], "blocked")
        self.assertIn("validation command sets", checks["source-intake-visible"]["blocker"])

    def test_missing_data_validation_command_sets_blocks_data_intake_check(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={
                "decision": "data-intake-visible-execution-locked",
                "dirtyDataFileCount": 1,
                "csvFileCount": 1,
                "executionGradeData": False,
                "readyForExecutionData": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["data-intake-visible"]["status"], "blocked")
        self.assertIn("validation command sets", checks["data-intake-visible"]["blocker"])

    def test_missing_source_hygiene_review_packets_blocks_source_hygiene_check(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={
                "decision": "source-hygiene-plan-research-only-execution-locked",
                "researchOnly": True,
                "sourceHygieneCleared": False,
                "automaticCleanupAllowed": False,
                "safeToStageAutomatically": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "dirtyStatusCount": 1,
                "reviewBacklogCount": 1,
                "bundleSummary": [
                    {
                        "id": "validated-research-scaffold",
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    }
                ],
                "nextReviewPackets": [],
            },
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["source-hygiene-plan-visible"]["status"], "blocked")
        self.assertIn("review packets", checks["source-hygiene-plan-visible"]["blocker"])

    def test_open_session_data_proof_requires_locked_env_on_data_steps(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={
                "command": "bill-open-session-data-proof",
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "brokerReadOnlyStepIncluded": False,
                "executionGradeDataProofPassed": False,
                "plannedStepIds": ["databento-open-session-smoke", "databento-open-session-bridge-write"],
                "plannedSteps": [
                    {
                        "id": "databento-open-session-smoke",
                        "command": "npm run --silent bill:databento-realtime-smoke -- --timeout-sec 20.0",
                        "env": {},
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                    {
                        "id": "databento-open-session-bridge-write",
                        "command": "BILL_DATABENTO_REALTIME_ENABLED=true .venv/bin/python scripts/realtime_data_bridge.py --quiet --databento-only",
                        "env": {"BILL_DATABENTO_REALTIME_ENABLED": "true"},
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    },
                ],
            },
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["open-session-data-proof-visible"]["status"], "blocked")
        self.assertIn("open-session data proof runner", checks["open-session-data-proof-visible"]["blocker"])

    def test_missing_source_packet_manual_clearance_blocks_packet_review_check(self):
        packet = {
            "id": "packet-05-futures-strategy-lane",
            "lane": "futures",
            "decision": "manual-review-only",
            "pathCount": 1,
            "classificationCounts": {"keep-research": 1},
            "rows": [{"path": "scripts/futures_data_requirements.py", "classification": "keep-research"}],
            "safeToStageAutomatically": False,
            "automaticCleanupAllowed": False,
            "operatorApprovalRequired": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "readyForExecution": False,
        }
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
            source_packet_review={
                "decision": "source-packet-review-visible-execution-locked",
                "researchOnly": True,
                "sourceHygieneCleared": False,
                "packetReviewCleared": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "safeToStageAutomatically": False,
                "automaticCleanupAllowed": False,
                "operatorApprovalRequired": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "missingPackets": [],
                "classificationCounts": {"keep-research": 2},
                "packets": [
                    packet,
                    {**packet, "id": "packet-06-prediction-market-lane", "lane": "prediction-markets"},
                ],
            },
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["source-packet-review-visible"]["status"], "blocked")
        self.assertIn("manual clearance proposal", checks["source-packet-review-visible"]["blocker"])

    def test_source_hygiene_review_packet_without_diff_summary_blocks(self):
        packet = {
            "id": "packet-01-control-research-scaffold",
            "bundleId": "validated-research-scaffold",
            "pathCount": 1,
            "paths": ["scripts/a.py"],
            "commands": ["npm run --silent bill:source-hygiene-plan"],
            "decision": "manual-review-only",
            "safeToStageAutomatically": False,
            "automaticCleanupAllowed": False,
            "operatorApprovalRequired": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
        }
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={
                "decision": "source-hygiene-plan-research-only-execution-locked",
                "researchOnly": True,
                "sourceHygieneCleared": False,
                "automaticCleanupAllowed": False,
                "safeToStageAutomatically": False,
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "dirtyStatusCount": 1,
                "reviewBacklogCount": 1,
                "bundleSummary": [
                    {
                        "id": "validated-research-scaffold",
                        "safeToStageAutomatically": False,
                        "automaticCleanupAllowed": False,
                        "writesOrders": False,
                        "touchesBroker": False,
                        "movesFunds": False,
                    }
                ],
                "nextReviewPackets": [
                    packet,
                    {**packet, "id": "packet-02-execution-firewall-quarantine"},
                    {**packet, "id": "packet-03-data-provenance-refresh"},
                    {**packet, "id": "packet-04-strategy-backlog-sample"},
                ],
            },
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["source-hygiene-plan-visible"]["status"], "blocked")
        self.assertIn("review packets", checks["source-hygiene-plan-visible"]["blocker"])

    def test_missing_execution_validation_or_uncovered_paths_blocks_execution_intake_check(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={
                "decision": "execution-intake-visible-execution-locked",
                "dirtyExecutionFileCount": 1,
                "allFirewallCommandsPassed": True,
                "uncoveredExecutionPaths": ["scripts/pm_arb_scanner.py"],
                "executionLocked": True,
                "writesOrders": False,
                "touchesBroker": False,
                "movesFunds": False,
                "readyForExecution": False,
            },
            signal_quality={},
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["execution-intake-visible"]["status"], "blocked")
        self.assertIn("uncovered execution paths", checks["execution-intake-visible"]["blocker"])

    def test_signal_quality_blocks_when_shadow_signal_is_promoted(self):
        payload = build_audit(
            handoff={
                "decision": "KEEP_EXECUTION_LOCKED",
                "readyForExecution": False,
                "readyForDemoExpansion": False,
                "readyForLive": False,
                "writesOrders": False,
                "touchesBroker": False,
            },
            tooling={"status": "PASS", "readyForResearchLoop": True},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False, "readyForExecution": False, "actions": []},
            futures_cycle={},
            futures_requirements={},
            prediction_capture={},
            realtime_preflight={},
            databento_smoke={},
            worktree={},
            source_intake={},
            data_intake={},
            execution_intake={},
            signal_quality={
                "command": "signal-quality-advisor",
                "researchOnly": True,
                "writesOrders": False,
                "readyForExecution": False,
                "overallRating": 5.0,
                "blockers": [],
                "shadowSignalRows": [
                    {"name": "dom_proxy", "promotedForExecution": True, "tradableSignal": False}
                ],
            },
            storage={"movesFiles": False, "deletesFiles": False},
            clearance_evidence={"allCommandsPassed": True},
            daily_text="No new Bill/Hermes orders approved.\nBILL_ROUTE_APPROVAL: BLOCKED\n",
            source_hygiene={},
            open_session_data_proof={},
        )

        checks = {item["id"]: item for item in payload["checklist"]}
        self.assertEqual(checks["signal-quality-visible"]["status"], "blocked")
        self.assertIn("promoted/tradable shadow/research signals", checks["signal-quality-visible"]["blocker"])


if __name__ == "__main__":
    unittest.main()
