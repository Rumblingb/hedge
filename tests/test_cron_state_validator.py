from datetime import datetime, timezone
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from scripts import cron_state_validator as validator


class CronStateValidatorTests(TestCase):
    def test_dom_proxy_last_bar_stale_is_allowed_during_weekend_closure(self):
        summary = {
            "exists": True,
            "status": "ok",
            "method": "OHLCV_DOM_proxy",
            "evidenceLevel": "proxy_shadow_only",
            "promotedForExecution": False,
            "tradableSignal": False,
            "timestampAgeSeconds": 120,
            "lastBarAgeSeconds": 4 * 3600,
            "finiteScores": True,
        }

        saturday_utc = datetime(2026, 5, 30, 0, 30, tzinfo=timezone.utc).timestamp()
        with patch.object(validator, "NOW", saturday_utc):
            issues = validator.shadow_state_issues(
                "dom_proxy",
                validator.SHADOW_STATE_SPECS["dom_proxy"],
                summary,
            )

        self.assertNotIn("stale_shadow_state_last_bar", {issue["type"] for issue in issues})

    def test_futures_shadow_bars_are_allowed_during_weekend_closure(self):
        summary = {
            "exists": True,
            "status": "ok",
            "method": "kalman_dynamic_hedge",
            "evidenceLevel": "research_shadow_only",
            "promotedForExecution": False,
            "tradableSignal": False,
            "timestampAgeSeconds": 120,
            "lastBarAgeSeconds": 28 * 3600,
            "finiteScores": True,
        }

        saturday_utc = datetime(2026, 5, 30, 0, 30, tzinfo=timezone.utc).timestamp()
        with patch.object(validator, "NOW", saturday_utc):
            issues = validator.shadow_state_issues(
                "kalman_pairs",
                validator.SHADOW_STATE_SPECS["kalman_pairs"],
                summary,
            )

        self.assertNotIn("stale_shadow_state_last_bar", {issue["type"] for issue in issues})

    def test_dom_proxy_last_bar_stale_is_flagged_during_weekday_session(self):
        summary = {
            "exists": True,
            "status": "ok",
            "method": "OHLCV_DOM_proxy",
            "evidenceLevel": "proxy_shadow_only",
            "promotedForExecution": False,
            "tradableSignal": False,
            "timestampAgeSeconds": 120,
            "lastBarAgeSeconds": 4 * 3600,
            "finiteScores": True,
        }

        monday_utc = datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc).timestamp()
        with patch.object(validator, "NOW", monday_utc):
            issues = validator.shadow_state_issues(
                "dom_proxy",
                validator.SHADOW_STATE_SPECS["dom_proxy"],
                summary,
            )

        self.assertIn("stale_shadow_state_last_bar", {issue["type"] for issue in issues})

    def test_shadow_state_summary_carries_explicit_source_stale_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / ".rumbling-hedge" / "state"
            state_root.mkdir(parents=True)
            state = state_root / "dom-proxy-signal.latest.json"
            state.write_text(
                "{"
                "\"timestamp\":\"2026-05-31T09:00:00+00:00\","
                "\"last_bar_time\":\"2026-05-29T20:45:00+00:00\","
                "\"method\":\"OHLCV_DOM_proxy\","
                "\"evidence_level\":\"proxy_shadow_only\","
                "\"execution_role\":\"diagnostic_only\","
                "\"tradable_signal\":false,"
                "\"promoted_for_execution\":false,"
                "\"source_data_stale\":true,"
                "\"stale_threshold_seconds\":7200"
                "}"
            )

            with patch.object(validator, "HEDGE", Path(tmp)), \
                 patch.object(validator, "NOW", datetime(2026, 5, 31, 9, 1, tzinfo=timezone.utc).timestamp()):
                summary = validator.audit_shadow_state("dom_proxy", validator.SHADOW_STATE_SPECS["dom_proxy"])

        self.assertTrue(summary["sourceDataStale"])
        self.assertEqual(summary["staleThresholdSeconds"], 7200)

    def test_shadow_state_summary_infers_source_stale_from_last_bar_when_field_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / ".rumbling-hedge" / "state"
            state_root.mkdir(parents=True)
            state = state_root / "dom-proxy-signal.latest.json"
            state.write_text(
                "{"
                "\"timestamp\":\"2026-05-31T09:00:00+00:00\","
                "\"last_bar_time\":\"2026-05-29T20:45:00+00:00\","
                "\"method\":\"OHLCV_DOM_proxy\","
                "\"evidence_level\":\"proxy_shadow_only\","
                "\"execution_role\":\"diagnostic_only\","
                "\"tradable_signal\":false,"
                "\"promoted_for_execution\":false"
                "}"
            )

            with patch.object(validator, "HEDGE", Path(tmp)), \
                 patch.object(validator, "NOW", datetime(2026, 5, 31, 9, 1, tzinfo=timezone.utc).timestamp()):
                summary = validator.audit_shadow_state("dom_proxy", validator.SHADOW_STATE_SPECS["dom_proxy"])

        self.assertTrue(summary["sourceDataStale"])
        self.assertEqual(summary["staleThresholdSeconds"], validator.SHADOW_STATE_SPECS["dom_proxy"]["ttl_s"])

    def test_split_brain_is_allowed_when_repo_brain_is_fresh_and_home_is_legacy(self):
        issues = validator.brain_path_issues({
            "brain_state": {"exists": True, "status": "ok", "stale": True},
            "hedge_brain_state": {"exists": True, "status": "ok", "stale": False},
        })

        self.assertEqual([], issues)

    def test_split_brain_is_flagged_when_both_brains_are_fresh(self):
        issues = validator.brain_path_issues({
            "brain_state": {"exists": True, "status": "ok", "stale": False},
            "hedge_brain_state": {"exists": True, "status": "ok", "stale": False},
        })

        self.assertIn("split_brain_paths", {issue["type"] for issue in issues})
        remediation = issues[0]["operatorRemediation"]
        self.assertFalse(remediation["safeAutomaticAction"])
        self.assertIn("diagnostic context only", remediation["requiredAction"])
        self.assertIn("npm run --silent bill:cron-state-validator", remediation["validationCommands"])

    def test_deterministic_ai_fallback_safe_wait_is_not_issue(self):
        ai_confidence = 0
        states = {
            "ai_debate": {
                "llm_available": False,
                "final_decision": "WAIT",
                "confidence": ai_confidence,
                "deterministic_fallback": True,
                "tradable_signal": False,
                "promoted_for_execution": False,
                "writesOrders": False,
            }
        }
        ai_safe_wait = (
            states["ai_debate"].get("final_decision") == "WAIT"
            and isinstance(ai_confidence, (int, float))
            and ai_confidence <= 0
        )
        ai_deterministic_safe = (
            ai_safe_wait
            and states["ai_debate"].get("deterministic_fallback") is True
            and states["ai_debate"].get("tradable_signal") is False
            and states["ai_debate"].get("promoted_for_execution") is False
            and states["ai_debate"].get("writesOrders") is False
        )

        self.assertTrue(ai_deterministic_safe)

    def test_execution_live_script_index_tracks_quarantined_script_by_basename(self):
        index = validator.execution_live_script_index({
            "items": [
                {
                    "relativePath": "scripts/60m_exec_bridge.py",
                    "classification": "firewall-covered-still-quarantined",
                    "gitStatus": "M",
                    "firewallId": "verify-60m-bridge-firewall",
                    "firewallPassed": True,
                    "readyForExecution": False,
                },
                {
                    "relativePath": "scripts/research_only.py",
                    "classification": "research-review",
                    "readyForExecution": True,
                },
            ]
        })

        self.assertIn("60m_exec_bridge.py", index)
        self.assertNotIn("research_only.py", index)

    def test_active_cron_referencing_dirty_execution_live_script_is_flagged(self):
        jobs = [
            {
                "id": "abc",
                "name": "60m-lucidflex-execution",
                "enabled": True,
                "state": "scheduled",
                "no_agent": True,
                "script": "60m_exec_bridge.py",
                "last_status": "ok",
            }
        ]
        execution_index = {
            "60m_exec_bridge.py": {
                "relativePath": "scripts/60m_exec_bridge.py",
                "classification": "firewall-covered-still-quarantined",
                "firewallId": "verify-60m-bridge-firewall",
                "firewallPassed": True,
                "readyForExecution": False,
            }
        }

        refs = validator.cron_execution_live_references(jobs, execution_index)
        self.assertEqual(1, len(refs))
        self.assertTrue(refs[0]["operatorRemediation"]["approvalRequired"])
        self.assertFalse(refs[0]["operatorRemediation"]["safeAutomaticAction"])
        self.assertIn(
            "npm run --silent bill:verify-60m-bridge-firewall",
            refs[0]["operatorRemediation"]["validationCommands"],
        )

        issues = validator.cron_trust_issues({
            "activeDirtyExecutionLiveScriptReferences": refs,
            "activeTradingAgentBacked": [],
            "noAgentMetadataMismatch": [],
            "quarantinedScripts": [],
        })
        self.assertIn(
            "active_cron_references_dirty_execution_live_script",
            {issue["type"] for issue in issues},
        )
        self.assertEqual("P1", issues[0]["severity"])

        handoff = validator.cron_trust_handoff_fields(
            {
                "activeDirtyExecutionLiveScriptReferenceCount": len(refs),
                "activeDirtyExecutionLiveScriptReferences": refs,
                "activeTradingAgentBackedCount": 0,
                "noAgentMetadataMismatchCount": 0,
                "quarantinedScriptReferenceCount": 0,
            },
            issues,
        )
        self.assertFalse(handoff["cronTrustCleared"])
        self.assertEqual(1, handoff["blockingIssueCount"])
        self.assertEqual(1, handoff["activeDirtyExecutionLiveScriptReferenceCount"])
        self.assertEqual(refs, handoff["activeDirtyExecutionLiveScriptReferences"])
        self.assertEqual(
            "active_cron_references_dirty_execution_live_script",
            handoff["blockingIssues"][0]["type"],
        )

    def test_active_shadow_cron_script_guardrails_scan_actual_hermes_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir = Path(tmp) / "scripts"
            scripts_dir.mkdir()
            script = scripts_dir / "dom_proxy_ohlcv.py"
            script.write_text(
                "source_data_stale = True\n"
                "stale_threshold_seconds = 7200\n"
                "print('NOT A TRADE SIGNAL: writesOrders=false, promoted_for_execution=false')\n"
            )
            jobs = [{
                "id": "dom",
                "name": "dom-proxy-ohlcv",
                "enabled": True,
                "state": "scheduled",
                "no_agent": True,
                "script": "dom_proxy_ohlcv.py",
            }]

            with patch.object(validator, "SCRIPT_DIR", scripts_dir):
                rows = validator.shadow_cron_script_guardrails(jobs)

        self.assertEqual(1, len(rows))
        self.assertTrue(rows[0]["guardrailPresent"])
        self.assertEqual([], rows[0]["missingTokens"])
        self.assertEqual([], validator.shadow_cron_script_guardrail_issues(rows))

    def test_active_shadow_cron_script_guardrail_drift_is_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir = Path(tmp) / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "rolling_window_optimizer.py").write_text("print('Selected window: macro')\n")
            jobs = [{
                "id": "rolling",
                "name": "rolling-window-optimizer",
                "enabled": True,
                "state": "scheduled",
                "no_agent": True,
                "script": "rolling_window_optimizer.py",
            }]

            with patch.object(validator, "SCRIPT_DIR", scripts_dir):
                rows = validator.shadow_cron_script_guardrails(jobs)
                issues = validator.shadow_cron_script_guardrail_issues(rows)

        self.assertFalse(rows[0]["guardrailPresent"])
        self.assertIn("NOT A TRADE SIGNAL", rows[0]["missingTokens"])
        self.assertEqual("active_shadow_cron_script_guardrail_drift", issues[0]["type"])
        self.assertEqual("P1", issues[0]["severity"])

    def test_active_shadow_cron_script_guardrail_scans_runpy_canonical_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir = Path(tmp) / "scripts"
            scripts_dir.mkdir()
            canonical = Path(tmp) / "canonical_whale.py"
            canonical.write_text(
                "evidence_level = 'weekly_cot_shadow_only'\n"
                "print('NOT A TRADE SIGNAL: writesOrders=false, promoted_for_execution=false')\n"
            )
            wrapper = scripts_dir / "whale_flow_signal.py"
            wrapper.write_text(
                "from pathlib import Path\n"
                f"CANONICAL = Path(\"{canonical}\")\n"
                "import runpy\n"
                "runpy.run_path(str(CANONICAL), run_name='__main__')\n"
            )
            jobs = [{
                "id": "whale",
                "name": "whale-flow-signal",
                "enabled": True,
                "state": "scheduled",
                "no_agent": True,
                "script": "whale_flow_signal.py",
            }]

            with patch.object(validator, "SCRIPT_DIR", scripts_dir):
                rows = validator.shadow_cron_script_guardrails(jobs)

        self.assertTrue(rows[0]["guardrailPresent"])

    def test_cron_trust_handoff_fields_clear_when_no_blocking_issues_or_dirty_refs(self):
        handoff = validator.cron_trust_handoff_fields(
            {
                "activeDirtyExecutionLiveScriptReferenceCount": 0,
                "activeDirtyExecutionLiveScriptReferences": [],
                "activeTradingAgentBackedCount": 0,
                "noAgentMetadataMismatchCount": 0,
                "quarantinedScriptReferenceCount": 0,
            },
            [{"severity": "P2", "type": "diagnostic-only"}],
        )

        self.assertTrue(handoff["cronTrustCleared"])
        self.assertEqual(0, handoff["blockingIssueCount"])
        self.assertEqual([], handoff["blockingIssues"])
        self.assertEqual(1, handoff["diagnosticIssueCount"])

    def test_validator_summary_distinguishes_clear_diagnostics_from_blockers(self):
        handoff = {
            "cronTrustCleared": True,
            "blockingIssueCount": 0,
            "diagnosticIssueCount": 2,
            "activeDirtyExecutionLiveScriptReferenceCount": 0,
        }

        summary = validator.validator_summary(handoff, {"P2": 2})

        self.assertEqual("cron trust clear; 2 diagnostic issues flagged", summary)

    def test_validator_summary_surfaces_blocking_and_diagnostic_counts(self):
        handoff = {
            "cronTrustCleared": False,
            "blockingIssueCount": 1,
            "diagnosticIssueCount": 2,
            "activeDirtyExecutionLiveScriptReferenceCount": 0,
        }

        summary = validator.validator_summary(handoff, {"P0": 1, "P2": 2})

        self.assertEqual("1 blocking and 2 diagnostic issues flagged", summary)

    def test_fixed_no_agent_script_path_error_is_downgraded_until_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts_dir = Path(tmp) / "scripts"
            scripts_dir.mkdir()
            script = scripts_dir / "check_expiry.sh"
            script.write_text("#!/usr/bin/env bash\necho ok\n")

            with patch.object(validator, "SCRIPT_DIR", scripts_dir):
                job = {
                    "id": "expiry",
                    "name": "expiry-checker",
                    "enabled": True,
                    "state": "scheduled",
                    "no_agent": True,
                    "script": "check_expiry.sh",
                }
                detail = "Blocked: script path resolves outside the scripts directory (/tmp/scripts): 'check_expiry.sh'"

                self.assertTrue(validator.stale_script_path_error_is_fixed(job, detail))
                issue = {
                    "severity": "P2",
                    "type": "stale_script_path_error_fixed_pending_next_run",
                    "job": "expiry-checker",
                    "operatorRemediation": {
                        "approvalRequired": False,
                        "safeAutomaticAction": False,
                        "requiredAction": "wait for the cron job to run again or manually inspect the latest job output; the script path now resolves inside ~/.hermes/scripts",
                        "validationCommands": [
                            "npm run --silent bill:cron-state-validator",
                            "ls -l /Users/brain/.hermes/scripts/check_expiry.sh",
                        ],
                    },
                }
                self.assertFalse(issue["operatorRemediation"]["approvalRequired"])
                self.assertIn(
                    "script path now resolves inside",
                    issue["operatorRemediation"]["requiredAction"],
                )
                handoff = validator.cron_trust_handoff_fields(
                    {
                        "activeDirtyExecutionLiveScriptReferenceCount": 0,
                        "activeDirtyExecutionLiveScriptReferences": [],
                        "activeTradingAgentBackedCount": 0,
                        "noAgentMetadataMismatchCount": 0,
                        "quarantinedScriptReferenceCount": 0,
                    },
                    [issue],
                )

        self.assertTrue(handoff["cronTrustCleared"])
        self.assertEqual(1, handoff["diagnosticIssueCount"])
