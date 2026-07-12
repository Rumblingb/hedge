import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.bill_fund_os_completion_audit import (
    Check,
    ROOT,
    audit_shadow_signal,
    build_fund_expansion_ladder,
    clearance_evidence_safe,
    clearance_handoff_safe,
    closed_market_bar_ok,
    cron_prompts_shadow_aligned,
    cron_validator_cleared,
    databento_smoke_safe,
    funding_helper_guarded,
    hermes_storage_audit_safe,
    research_data_fresh_enough,
)


class BillFundOsCompletionAuditTest(unittest.TestCase):
    def test_closed_market_bar_is_ok_after_friday_futures_close(self):
        now = datetime(2026, 5, 29, 23, 50, tzinfo=timezone.utc)

        self.assertTrue(closed_market_bar_ok("2026-05-29T20:45:00.000Z", 15, now))
        self.assertTrue(closed_market_bar_ok("2026-05-29T20:00:00.000Z", 60, now))

    def test_old_market_hour_bar_is_not_fresh(self):
        now = datetime(2026, 5, 29, 18, 0, tzinfo=timezone.utc)

        self.assertFalse(closed_market_bar_ok("2026-05-29T14:00:00.000Z", 60, now))

    def test_research_data_fresh_enough_reports_closed_market_evidence(self):
        now = datetime(2026, 5, 29, 23, 50, tzinfo=timezone.utc)
        ok, evidence = research_data_fresh_enough("2026-05-29T20:45:00.000Z", 180, 15, now)

        self.assertTrue(ok)
        self.assertIn("closed_market_bar_ok=True", evidence)

    def test_databento_smoke_safe_requires_research_only_no_state_write(self):
        payload = {
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "writesRealtimeQuoteState": False,
            "readyForExecutionDataProof": False,
            "status": "NO_QUOTES_MARKET_CLOSED",
            "session": {
                "market": "CME Globex equity-index futures",
                "reason": "Saturday Globex closure",
            },
        }

        self.assertTrue(databento_smoke_safe(payload))

        payload["writesRealtimeQuoteState"] = True
        self.assertFalse(databento_smoke_safe(payload))

    def test_hermes_storage_audit_safe_requires_manifest_only(self):
        payload = {
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFiles": False,
            "deletesFiles": False,
            "entries": [],
            "topCandidates": [],
        }

        self.assertTrue(hermes_storage_audit_safe(payload))

        payload["deletesFiles"] = True
        self.assertFalse(hermes_storage_audit_safe(payload))

    def test_clearance_handoff_safe_requires_locked_research_only_state(self):
        payload = {
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "readyForExecution": False,
            "decision": "KEEP_EXECUTION_LOCKED",
            "gates": {},
            "lanes": {},
            "nextActions": [],
        }

        self.assertTrue(clearance_handoff_safe(payload))

        payload["readyForExecution"] = True
        self.assertFalse(clearance_handoff_safe(payload))

    def test_clearance_evidence_safe_requires_non_executing_report(self):
        payload = {
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "movesFunds": False,
            "readyForExecution": False,
            "status": "PASS",
            "results": [],
        }

        self.assertTrue(clearance_evidence_safe(payload))

        payload["touchesBroker"] = True
        self.assertFalse(clearance_evidence_safe(payload))

    def test_funding_helper_guarded_accepts_retired_quarantined_helper(self):
        self.assertTrue(
            funding_helper_guarded(
                active_path=Path("/tmp/nonexistent-deposit-clob.ts"),
                retired_path=ROOT / ".retired" / "deposit-clob.ts",
            )
        )

    def test_funding_helper_guarded_blocks_missing_required_active_helper(self):
        self.assertFalse(
            funding_helper_guarded(
                active_path=Path("/tmp/nonexistent-required-funding-helper.ts"),
                active_required=True,
            )
        )

    def test_audit_shadow_signal_appends_non_executing_check(self):
        checks: list[Check] = []

        audit_shadow_signal(checks, "dom-proxy-signal.latest.json", "proxy_shadow_only")

        self.assertTrue(any("dom-proxy-signal.latest.json" in item.requirement for item in checks))
        self.assertIn(checks[-1].status, {"PASS", "BLOCKED"})
        self.assertIn("promoted=", checks[-1].evidence)

    def test_cron_validator_can_clear_execution_like_prompt_names(self):
        cron = {
            "enabledExecutionAdjacent": [
                {"name": "bill-demo-eod-execution", "prompt": "run local cycle"},
            ],
        }
        validator = {
            "cronTrustCleared": True,
            "blockingIssueCount": 0,
            "activeDirtyExecutionLiveScriptReferenceCount": 0,
            "quarantinedScriptReferenceCount": 0,
            "activeTradingAgentBackedCount": 0,
            "noAgentMetadataMismatchCount": 0,
        }

        self.assertTrue(cron_validator_cleared(validator))
        ok, evidence = cron_prompts_shadow_aligned(cron, validator)
        self.assertTrue(ok)
        self.assertIn("validatorCleared=True", evidence)

    def test_cron_prompt_fallback_still_blocks_stale_unvalidated_prompts(self):
        cron = {
            "enabledExecutionAdjacent": [
                {"name": "bill-demo-eod-execution", "prompt": "run local cycle"},
            ],
        }

        ok, evidence = cron_prompts_shadow_aligned(cron, {"cleared": False})

        self.assertFalse(ok)
        self.assertIn("validatorCleared=False", evidence)
        self.assertIn("shadow", evidence)

    def test_fund_expansion_ladder_blocks_later_stages_until_evidence_clears(self):
        payload = build_fund_expansion_ladder(
            source_hygiene={"sourceHygieneCleared": False},
            realtime_preflight={"readyForExecutionData": False},
            futures_requirements={"readyForDemoExpansion": False},
            futures_broker_parity={"readyForDemoExpansion": False},
            live_readiness={"readyForDemoExpansion": False},
            prediction_paper_gate={
                "decision": "research-only-paper-promotion-blocked",
                "readyForPaper": False,
                "blockedIds": ["post-spread-clob-edge"],
            },
            prediction_capture={
                "readyForPaper": False,
                "paperPromotionEvidencePassed": False,
            },
            runtime_architecture={
                "researchOnly": True,
                "readyForExecution": False,
                "warnings": [],
            },
            next_actions={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
            },
        )

        self.assertEqual(payload["decision"], "fund-promotion-contract-research-only-execution-locked")
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertEqual(payload["currentStage"], "research-only-control-plane")
        self.assertEqual(payload["nextStage"], "clear-futures-demo-gates")
        by_id = {item["id"]: item for item in payload["ladder"]}
        self.assertEqual(by_id["l0-research-only-control-plane"]["status"], "pass")
        self.assertEqual(by_id["l1-futures-topstep-demo"]["status"], "blocked")
        self.assertIn("source-hygiene", by_id["l1-futures-topstep-demo"]["blockedBy"])
        self.assertEqual(by_id["l2-prediction-paper"]["status"], "blocked")
        self.assertTrue(payload["portfolioIntent"]["compoundRule"].startswith("Compound only after gates pass"))

    def test_fund_expansion_ladder_allows_demo_stage_only_when_all_futures_gates_clear(self):
        payload = build_fund_expansion_ladder(
            source_hygiene={"sourceHygieneCleared": True},
            realtime_preflight={"readyForExecutionData": True},
            futures_requirements={"readyForDemoExpansion": True},
            futures_broker_parity={"readyForDemoExpansion": True},
            live_readiness={"readyForDemoExpansion": True},
            prediction_paper_gate={"readyForPaper": False},
            prediction_capture={"readyForPaper": False, "paperPromotionEvidencePassed": False},
            runtime_architecture={"researchOnly": True, "readyForExecution": False, "warnings": []},
            next_actions={"researchOnly": True, "writesOrders": False, "touchesBroker": False},
        )

        self.assertTrue(payload["readyForDemoExpansion"])
        by_id = {item["id"]: item for item in payload["ladder"]}
        self.assertEqual(by_id["l1-futures-topstep-demo"]["status"], "pass")
        self.assertEqual(by_id["l4-copy-trading-and-brokerage"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
