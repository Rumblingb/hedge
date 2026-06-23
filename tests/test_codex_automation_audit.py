import tempfile
import unittest
import json
from pathlib import Path

from scripts.codex_automation_audit import build_audit, render_markdown


def write_automation(root: Path, automation_id: str, *, status: str, prompt: str, rrule: str = "FREQ=HOURLY;INTERVAL=1") -> None:
    directory = root / automation_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "automation.toml").write_text(
        "\n".join([
            'version = 1',
            f'id = "{automation_id}"',
            'kind = "cron"',
            f'name = "{automation_id}"',
            f'prompt = "{prompt}"',
            f'status = "{status}"',
            f'rrule = "{rrule}"',
            'model = "gpt-5.4-mini"',
            'reasoning_effort = "low"',
            'execution_environment = "local"',
            'cwds = ["/Users/brain/hedge"]',
            "",
        ])
    )


SAFE_PROMPT = (
    "Run Bill/Hermes prediction-event-capture-cycle using public Polymarket CLOB capture only. "
    "Keep BILL_ENABLE_FUTURES_DEMO_EXECUTION=false, RH_TOPSTEP_READ_ONLY=true, and RH_LIVE_EXECUTION_ENABLED=false. "
    "Run bill:prediction-event-capture-cycle -- --run-recorder --duration-sec 900 --max-assets 20 --max-output-mb 128 --min-free-gb 20. "
    "Do not submit orders, do not fund accounts, do not enable demo/live execution, and do not mark the goal complete."
)


class CodexAutomationAuditTest(unittest.TestCase):
    def test_passes_with_consolidated_hermes_capture_and_codex_duplicates_paused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_automation(root, "bill-prediction-forward-clob-capture", status="PAUSED", prompt=SAFE_PROMPT)
            write_automation(root, "bill-prediction-event-clob-capture", status="PAUSED", prompt=SAFE_PROMPT)
            jobs_path = root / "jobs.json"
            recorder_script = root / "polymarket_clob_recorder.sh"
            jobs_path.write_text(json.dumps({"jobs": [
                {
                    "id": "recorder",
                    "name": "prediction-clob-recorder",
                    "enabled": True,
                    "no_agent": True,
                    "script": "polymarket_clob_recorder.sh",
                    "last_status": "ok",
                    "last_error": None,
                    "prompt": "Research-only public capture; never place orders, fund accounts, or touch broker state.",
                },
                {
                    "id": "analysis",
                    "name": "prediction-snapshot-refresh",
                    "enabled": True,
                    "no_agent": True,
                    "script": "bill_prediction_snapshot_refresh.sh",
                    "last_status": "ok",
                    "last_error": None,
                    "prompt": "Research-only analysis; no orders, funds, broker state, or promotion.",
                },
            ]}))
            recorder_script.write_text("--duration-sec 90 --max-output-mb 64 --min-free-gb 20 Seagate Expansion Drive")

            payload = build_audit(
                root,
                hermes_jobs_path=jobs_path,
                hermes_recorder_script_path=recorder_script,
            )

        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["predictionCaptureAuthority"], "hermes")
        self.assertTrue(payload["hermesPredictionLoopConsolidated"])
        self.assertEqual(payload["activePredictionCaptureIds"], [])
        self.assertEqual(payload["activeHermesPredictionCaptureIds"], ["recorder"])
        self.assertEqual(payload["blockers"], [])

    def test_passes_with_one_active_storage_bounded_prediction_capture_and_one_paused_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_automation(root, "bill-prediction-forward-clob-capture", status="ACTIVE", prompt=SAFE_PROMPT)
            write_automation(root, "bill-prediction-event-clob-capture", status="PAUSED", prompt=SAFE_PROMPT)

            payload = build_audit(root)

        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["activePredictionCaptureCount"], 1)
        self.assertEqual(payload["pausedPredictionCaptureCount"], 1)
        self.assertEqual(payload["activePredictionCaptureIds"], ["bill-prediction-forward-clob-capture"])
        self.assertEqual(payload["pausedPredictionCaptureIds"], ["bill-prediction-event-clob-capture"])
        self.assertEqual(payload["blockers"], [])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForExecution"])

    def test_blocks_multiple_active_prediction_capture_loops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_automation(root, "bill-prediction-forward-clob-capture", status="ACTIVE", prompt=SAFE_PROMPT)
            write_automation(root, "bill-prediction-event-clob-capture", status="ACTIVE", prompt=SAFE_PROMPT)

            payload = build_audit(root)

        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("multiple-active-prediction-clob-captures", payload["blockers"])

    def test_blocks_multiple_active_futures_open_session_proofs(self):
        prompt = (
            "Run Bill futures open-session data proof. Keep "
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false, RH_TOPSTEP_READ_ONLY=true, "
            "and RH_LIVE_EXECUTION_ENABLED=false. Do not submit orders, do not "
            "enable demo/live execution, and do not mark the goal complete."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_automation(root, "bill-futures-open-session-data-proof", status="ACTIVE", prompt=prompt)
            write_automation(root, "bill-open-session-data-proof", status="ACTIVE", prompt=prompt)

            payload = build_audit(root)

        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["activeFuturesOpenSessionProofCount"], 2)
        self.assertIn("multiple-active-futures-open-session-proofs", payload["blockers"])
        self.assertEqual(
            payload["activeFuturesOpenSessionProofConflictIds"],
            ["bill-futures-open-session-data-proof", "bill-open-session-data-proof"],
        )
        self.assertEqual(
            payload["activeFuturesOpenSessionProofIds"],
            ["bill-futures-open-session-data-proof", "bill-open-session-data-proof"],
        )

    def test_allows_future_recurring_futures_proof_after_one_time_window(self):
        prompt = (
            "Run Bill futures open-session data proof. Keep "
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false, RH_TOPSTEP_READ_ONLY=true, "
            "and RH_LIVE_EXECUTION_ENABLED=false. Do not submit orders, do not "
            "enable demo/live execution, and do not mark the goal complete."
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_automation(
                root,
                "bill-futures-open-session-data-proof",
                status="ACTIVE",
                prompt=prompt,
                rrule="DTSTART:20260531T230500\\nRRULE:FREQ=DAILY;COUNT=1",
            )
            write_automation(
                root,
                "bill-open-session-data-proof",
                status="ACTIVE",
                prompt=prompt,
                rrule="DTSTART:20260607T230500\\nRRULE:FREQ=WEEKLY;BYDAY=SU;BYHOUR=23;BYMINUTE=5;BYSECOND=0",
            )

            payload = build_audit(root)

        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["activeFuturesOpenSessionProofCount"], 2)
        self.assertEqual(payload["activeFuturesOpenSessionProofConflictIds"], [])
        self.assertNotIn("multiple-active-futures-open-session-proofs", payload["blockers"])

    def test_blocks_active_capture_without_storage_bounds_or_locks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_automation(
                root,
                "bill-prediction-forward-clob-capture",
                status="ACTIVE",
                prompt="Run Bill prediction-event-capture-cycle with Polymarket CLOB capture.",
            )

            payload = build_audit(root)

        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("active-prediction-capture-missing-storage-bounds", payload["blockers"])
        self.assertIn("active-bill-automation-missing-safe-lock-flags", payload["blockers"])

    def test_markdown_surfaces_active_and_paused_capture_ids(self):
        markdown = render_markdown({
            "status": "PASS",
            "generatedAt": "2026-05-31T09:00:00+00:00",
            "decision": "codex-automations-visible-research-locked",
            "activeBillAutomationCount": 1,
            "activePredictionCaptureIds": ["active-capture"],
            "pausedPredictionCaptureIds": ["paused-capture"],
            "blockers": [],
            "readyForExecution": False,
            "automations": [
                {
                    "id": "active-capture",
                    "status": "ACTIVE",
                    "kind": "cron",
                    "storageBounded": True,
                    "hasSafeLocks": True,
                    "forbidsExecution": True,
                }
            ],
            "hardRules": ["read-only"],
        })

        self.assertIn("active-capture", markdown)
        self.assertIn("paused-capture", markdown)
        self.assertIn("Active futures open-session proofs", markdown)
        self.assertIn("Ready for execution: `False`", markdown)
        self.assertIn("# Codex Automation Audit - 2026-05-31", markdown.splitlines()[0])
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
