import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.bill_runtime_architecture_audit import (
    ai_scientist_template_summary,
    build_audit,
    cron_validator_review,
    kanban_blocked_task_triage,
    latest_ai_scientist_final_info,
    n8n_db_summary,
    n8n_export_mismatches,
)


class BillRuntimeArchitectureAuditTests(unittest.TestCase):
    def test_n8n_summary_counts_live_bill_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "database.sqlite"
            con = sqlite3.connect(db)
            con.execute("create table workflow_entity (id text, name text, active integer, updatedAt text, nodes text)")
            con.execute(
                "insert into workflow_entity values (?, ?, ?, ?, ?)",
                ("bill-1", "Bill Research Monitor", 1, "2026-05-31", "[]"),
            )
            con.execute(
                "insert into workflow_entity values (?, ?, ?, ?, ?)",
                ("social-1", "LinkedIn", 1, "2026-05-31", "[]"),
            )
            con.commit()
            con.close()

            summary = n8n_db_summary(db)

        self.assertEqual(summary["workflowCount"], 2)
        self.assertEqual(summary["activeCount"], 2)
        self.assertEqual(summary["billWorkflowCount"], 1)
        self.assertEqual(summary["activeBillWorkflowCount"], 1)

    def test_n8n_export_mismatch_detects_stale_active_flag(self):
        db_summary = {
            "workflows": [
                {"id": "bill-pre", "name": "Bill Trading Day Premarket Brief", "active": False}
            ]
        }
        exported = [
            {
                "id": "bill-pre",
                "name": "Bill Trading Day Premarket Brief",
                "active": True,
                "path": "ops/n8n/bill.workflow.json",
            }
        ]

        mismatches = n8n_export_mismatches(db_summary, exported)

        self.assertEqual(mismatches[0]["issue"], "export-active-state-disagrees-with-live-db")
        self.assertTrue(mismatches[0]["exportActive"])
        self.assertFalse(mismatches[0]["liveActive"])

    def test_n8n_export_mismatch_is_empty_when_live_and_export_match(self):
        db_summary = {
            "workflows": [
                {"id": "bill-pre", "name": "Bill Trading Day Premarket Brief", "active": False}
            ]
        }
        exported = [
            {
                "id": "bill-pre",
                "name": "Bill Trading Day Premarket Brief",
                "active": False,
                "path": "ops/n8n/bill.workflow.json",
            }
        ]

        self.assertEqual(n8n_export_mismatches(db_summary, exported), [])

    def test_ai_scientist_template_requires_explicit_research_only_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "experiment.py").write_text("print('research only')\n")
            (root / "prompt.json").write_text("{}")
            (root / "ideas.json").write_text("[]")
            run = root / "test_run"
            run.mkdir()
            (run / "final_info.json").write_text(json.dumps({
                "AlphaStrategyTemplate": {
                    "means": {"ready_for_execution": False},
                    "safety": {
                        "research_only": True,
                        "writes_orders": False,
                        "touches_broker": False,
                        "moves_funds": False,
                    },
                    "experiment": {
                        "decision": "research-only-template-blocked",
                        "promotion_blockers": ["template-output-is-not-paper-demo-or-execution-promotion"],
                    },
                }
            }))

            summary = ai_scientist_template_summary(root)

        self.assertTrue(summary["hardSafetyOk"])
        self.assertFalse(summary["readyForExecution"])

    def test_ai_scientist_template_uses_newest_valid_final_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "experiment.py").write_text("print('research only')\n")
            (root / "prompt.json").write_text("{}")
            (root / "ideas.json").write_text("[]")
            old_run = root / "test_run"
            old_run.mkdir()
            (old_run / "final_info.json").write_text(json.dumps({
                "AlphaStrategyTemplate": {
                    "means": {"ready_for_execution": False},
                    "safety": {
                        "research_only": True,
                        "writes_orders": False,
                        "touches_broker": False,
                        "moves_funds": False,
                    },
                    "experiment": {
                        "decision": "old-result",
                        "promotion_blockers": ["template-output-is-not-paper-demo-or-execution-promotion"],
                    },
                }
            }))
            newest = root / "test_run_known_baselines_2026_06_04"
            newest.mkdir()
            latest_path = newest / "final_info.json"
            latest_path.write_text(json.dumps({
                "AlphaStrategyTemplate": {
                    "means": {"ready_for_execution": False},
                    "safety": {
                        "research_only": True,
                        "writes_orders": False,
                        "touches_broker": False,
                        "moves_funds": False,
                    },
                    "experiment": {
                        "decision": "newest-result",
                        "promotion_blockers": ["template-output-is-not-paper-demo-or-execution-promotion"],
                    },
                }
            }))
            os.utime(old_run / "final_info.json", (1_700_000_000, 1_700_000_000))
            os.utime(latest_path, (1_800_000_000, 1_800_000_000))

            summary = ai_scientist_template_summary(root)
            selected = latest_ai_scientist_final_info(root)

        self.assertEqual(latest_path, selected)
        self.assertEqual(str(latest_path), summary["finalInfoPath"])
        self.assertEqual("newest-result", summary["decision"])

    def test_cron_validator_review_clears_execution_like_names_when_firewalls_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cron-state-validator.latest.json"
            path.write_text(json.dumps({
                "summary": "cron trust clear; 1 diagnostic issues flagged",
                "issues": [{"severity": "P2", "type": "diagnostic"}],
                "cron_trust": {
                    "activeDirtyExecutionLiveScriptReferenceCount": 0,
                    "quarantinedScriptReferenceCount": 0,
                    "activeTradingAgentBackedCount": 0,
                    "noAgentMetadataMismatchCount": 0,
                    "activeShadowCronScriptGuardrailDriftCount": 0,
                },
            }))

            review = cron_validator_review(path)

        self.assertTrue(review["cleared"])
        self.assertEqual(review["blockingIssueCount"], 0)
        self.assertEqual(review["diagnosticIssueCount"], 1)

    def test_kanban_blocked_task_triage_parks_research_tooling_and_prediction_backlog(self):
        triage = kanban_blocked_task_triage({
            "blockedRelevantTasks": [
                {
                    "id": "firecrawl",
                    "status": "blocked",
                    "title": "n8n: build SearXNG+Firecrawl research pipeline",
                },
                {
                    "id": "prediction",
                    "status": "blocked",
                    "title": "edge: prediction-markets — cross-platform arbitrage & systematic edges",
                },
                {
                    "id": "n8n-activate",
                    "status": "blocked",
                    "title": "n8n: activate 7 paused Bill workflows",
                },
                {
                    "id": "topstep-proof",
                    "status": "blocked",
                    "title": "fix: refresh TopstepX realtime proof and promote canonical quote state",
                },
            ]
        })

        self.assertTrue(triage["allBlockedRelevantTasksTriaged"])
        self.assertEqual(triage["untriagedCount"], 0)
        self.assertEqual(
            [row["classification"] for row in triage["rows"]],
            [
                "parked-optional-research-tooling",
                "parked-alpha-research-backlog",
                "parked-obsolete-n8n-activation",
                "fulfilled-readonly-topstep-quote-refresh",
            ],
        )
        self.assertTrue(all(row["writesOrders"] is False for row in triage["rows"]))

    def test_build_audit_keeps_execution_locked_even_with_clean_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            n8n = root / "n8n.sqlite"
            con = sqlite3.connect(n8n)
            con.execute("create table workflow_entity (id text, name text, active integer, updatedAt text, nodes text)")
            con.commit()
            con.close()
            kanban = root / "kanban.sqlite"
            con = sqlite3.connect(kanban)
            con.execute(
                "create table tasks (id text, title text, body text, status text, priority integer, worker_pid integer, current_step_key text, consecutive_failures integer, created_at integer)"
            )
            con.execute(
                "insert into tasks values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "firecrawl",
                    "n8n: build SearXNG+Firecrawl research pipeline",
                    "research-only scraping",
                    "blocked",
                    2,
                    None,
                    None,
                    0,
                    1,
                ),
            )
            con.commit()
            con.close()
            cron = root / "jobs.json"
            cron.write_text(json.dumps({"jobs": []}))
            cron_validator = root / "cron-state-validator.latest.json"
            cron_validator.write_text(json.dumps({
                "summary": "cron trust clear",
                "issues": [],
                "cron_trust": {
                    "activeDirtyExecutionLiveScriptReferenceCount": 0,
                    "quarantinedScriptReferenceCount": 0,
                    "activeTradingAgentBackedCount": 0,
                    "noAgentMetadataMismatchCount": 0,
                    "activeShadowCronScriptGuardrailDriftCount": 0,
                },
            }))
            template = root / "template"
            template.mkdir()
            (template / "experiment.py").write_text("print('research only')\n")
            (template / "prompt.json").write_text("{}")
            (template / "ideas.json").write_text("[]")
            (template / "test_run").mkdir()
            (template / "test_run" / "final_info.json").write_text(json.dumps({
                "AlphaStrategyTemplate": {
                    "means": {"ready_for_execution": False},
                    "safety": {
                        "research_only": True,
                        "writes_orders": False,
                        "touches_broker": False,
                        "moves_funds": False,
                    },
                    "experiment": {
                        "promotion_blockers": ["template-output-is-not-paper-demo-or-execution-promotion"],
                    },
                }
            }))

            audit = build_audit(
                n8n_db=n8n,
                n8n_env=root / "missing-n8n.env",
                n8n_export_roots=[root / "exports"],
                kanban_db=kanban,
                cron_path=cron,
                cron_validator_path=cron_validator,
                ai_template=template,
                generated_at="2026-05-31T00:00:00+00:00",
            )

        self.assertEqual(audit["decision"], "runtime-architecture-visible-execution-locked")
        self.assertTrue(audit["researchOnly"])
        self.assertFalse(audit["readyForExecution"])
        self.assertFalse(audit["writesOrders"])
        self.assertEqual(audit["blockers"], [])
        self.assertTrue(audit["hermesKanban"]["blockedTaskTriage"]["allBlockedRelevantTasksTriaged"])
        self.assertEqual(audit["warnings"], [])
        self.assertEqual(audit["operatorActions"], [])

    def test_build_audit_does_not_warn_on_execution_like_cron_when_validator_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            n8n = root / "n8n.sqlite"
            con = sqlite3.connect(n8n)
            con.execute("create table workflow_entity (id text, name text, active integer, updatedAt text, nodes text)")
            con.commit()
            con.close()
            kanban = root / "kanban.sqlite"
            con = sqlite3.connect(kanban)
            con.execute(
                "create table tasks (id text, title text, body text, status text, priority integer, worker_pid integer, current_step_key text, consecutive_failures integer, created_at integer)"
            )
            con.commit()
            con.close()
            cron = root / "jobs.json"
            cron.write_text(json.dumps({
                "jobs": [
                    {
                        "id": "topstep-watchdog",
                        "name": "topstep-demo-watchdog",
                        "enabled": True,
                        "prompt": "monitor only; trading requires guarded bridge and approval",
                    }
                ]
            }))
            cron_validator = root / "cron-state-validator.latest.json"
            cron_validator.write_text(json.dumps({
                "summary": "cron trust clear",
                "issues": [],
                "cron_trust": {
                    "activeDirtyExecutionLiveScriptReferenceCount": 0,
                    "quarantinedScriptReferenceCount": 0,
                    "activeTradingAgentBackedCount": 0,
                    "noAgentMetadataMismatchCount": 0,
                    "activeShadowCronScriptGuardrailDriftCount": 0,
                },
            }))
            template = root / "template"
            template.mkdir()
            (template / "experiment.py").write_text("print('research only')\n")
            (template / "prompt.json").write_text("{}")
            (template / "ideas.json").write_text("[]")
            (template / "test_run").mkdir()
            (template / "test_run" / "final_info.json").write_text(json.dumps({
                "AlphaStrategyTemplate": {
                    "means": {"ready_for_execution": False},
                    "safety": {
                        "research_only": True,
                        "writes_orders": False,
                        "touches_broker": False,
                        "moves_funds": False,
                    },
                    "experiment": {
                        "promotion_blockers": ["template-output-is-not-paper-demo-or-execution-promotion"],
                    },
                }
            }))

            audit = build_audit(
                n8n_db=n8n,
                n8n_env=root / "missing-n8n.env",
                n8n_export_roots=[root / "exports"],
                kanban_db=kanban,
                cron_path=cron,
                cron_validator_path=cron_validator,
                ai_template=template,
                generated_at="2026-05-31T00:00:00+00:00",
            )

        self.assertEqual(audit["hermesCron"]["activeExecutionLikeCount"], 1)
        self.assertTrue(audit["hermesCron"]["validatorReview"]["cleared"])
        self.assertNotIn("active-execution-like-cron-names-require-review", audit["warnings"])
        self.assertEqual(audit["operatorActions"], [])


if __name__ == "__main__":
    unittest.main()
