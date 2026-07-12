import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import scripts.realtime_data_preflight as preflight


class RealtimeDataPreflightTests(unittest.TestCase):
    def test_realtime_cron_topstep_broker_touch_is_opt_in_and_locked(self):
        repo = Path(__file__).resolve().parents[1]
        wrapper = repo / "scripts" / "realtime_cron.sh"
        text = wrapper.read_text()
        template = repo / "ops" / "mac-mini" / "launchd" / "com.agentpay.bill.realtime-bridge.plist.template"
        template_text = template.read_text()

        self.assertIn("BILL_TOPSTEP_REALTIME_CRON_ENABLED", text)
        self.assertIn('TOPSTEP_REALTIME_CRON_ENABLED="${BILL_TOPSTEP_REALTIME_CRON_ENABLED:-false}"', text)
        self.assertIn('if [ "$TOPSTEP_REALTIME_CRON_ENABLED" = "true" ]; then', text)
        self.assertIn("mkdir \"$TOPSTEP_LOCK_FILE\"", text)
        self.assertIn("TopstepX realtime refresh skipped", text)
        self.assertIn("<key>BILL_TOPSTEP_REALTIME_CRON_ENABLED</key>", template_text)
        self.assertIn("<string>false</string>", template_text)

    def test_parse_env_file_handles_export_and_quotes_without_printing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bill.env"
            path.write_text(
                "\n".join([
                    "export DATABENTO_API_KEY='secret-value'",
                    'TV_SESSION="session-value"',
                    "# ignored",
                ])
            )

            parsed = preflight.parse_env_file(path)
            with patch.dict(preflight.os.environ, {}, clear=True):
                presence = preflight.safe_env_presence(parsed, "DATABENTO_API_KEY")

            self.assertEqual(parsed["DATABENTO_API_KEY"], "secret-value")
            self.assertEqual(presence, {
                "key": "DATABENTO_API_KEY",
                "present": True,
                "source": "bill.env",
            })
            self.assertNotIn("secret-value", json.dumps(presence))

    def test_build_report_blocks_delayed_fallback_even_with_databento_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".rumbling-hedge" / "state"
            state_dir.mkdir(parents=True)
            env_file = root / "bill.env"
            env_file.write_text("DATABENTO_API_KEY=secret-value\n")
            wrapper = root / "scripts" / "realtime_cron.sh"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                "\n".join([
                    'PYTHON_BIN="${PYTHON_BIN:-$HOME_DIR/hedge/.venv/bin/python}"',
                    "export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false",
                    "export RH_TOPSTEP_READ_ONLY=true",
                    "export RH_LIVE_EXECUTION_ENABLED=false",
                ])
            )
            now = datetime(2026, 5, 30, 3, 0, tzinfo=timezone.utc)
            (state_dir / "realtime-quote.latest.json").write_text(json.dumps({
                "timestamp": now.isoformat(),
                "source": "yahoo_fallback",
                "execution_grade": False,
                "execution_block_reason": "fallback quote is delayed/research-only, not execution-grade realtime data",
                "price_nq": 1,
                "price_es": 1,
            }))
            (state_dir / "data-freshness-gate.latest.json").write_text(json.dumps({
                "verdict": "STALE",
                "action": "block_all_trades",
                "checks": [],
            }))
            (state_dir / "databento-realtime-smoke.latest.json").write_text(json.dumps({
                "status": "NO_QUOTES_MARKET_CLOSED",
                "readyForExecutionDataProof": False,
                "quoteSummary": {
                    "reason": "market likely closed: Saturday Globex closure",
                    "status": "NO_QUOTES_MARKET_CLOSED",
                },
                "session": {
                    "likelyOpen": False,
                    "reason": "Saturday Globex closure",
                },
                "writesOrders": False,
                "touchesBroker": False,
                "writesRealtimeQuoteState": False,
            }))
            (state_dir / "topstep-realtime-proof.latest.json").write_text(json.dumps({
                "generatedAt": now.isoformat(),
                "status": "PASS",
                "readyForExecutionDataProof": True,
                "writesOrders": False,
                "touchesBroker": True,
                "writesRealtimeQuoteState": False,
                "symbols": {"NQ": {"quotes": 2}, "MNQ": {"quotes": 2}},
            }))

            with patch.dict(preflight.os.environ, {}, clear=True), \
                patch.object(preflight, "BILL_ENV", env_file), \
                patch.object(preflight, "STATE_DIR", state_dir), \
                patch.object(preflight, "REALTIME_STATE", state_dir / "realtime-quote.latest.json"), \
                patch.object(preflight, "DATA_FRESHNESS_STATE", state_dir / "data-freshness-gate.latest.json"), \
                patch.object(preflight, "DATABENTO_SMOKE_STATE", state_dir / "databento-realtime-smoke.latest.json"), \
                patch.object(preflight, "TOPSTEP_REALTIME_PROOF_STATE", state_dir / "topstep-realtime-proof.latest.json"), \
                patch.object(preflight, "CRON_WRAPPER", wrapper), \
                patch.object(preflight, "module_available", return_value={"module": "databento", "available": True, "origin": "test"}):
                report = preflight.build_report(now=now)

            self.assertFalse(report["readyForExecutionData"])
            self.assertEqual(report["decision"], "block-execution-data")
            self.assertIn(
                "data freshness gate is STALE (expected until open-session proof; Databento smoke reports market closed)",
                report["blockers"],
            )
            self.assertTrue(report["proofTiming"]["marketClosed"])
            self.assertEqual(report["proofTiming"]["safeEnv"]["RH_TOPSTEP_READ_ONLY"], "true")
            self.assertEqual(
                report["dataSources"]["databentoRealtimeSmoke"]["status"],
                "NO_QUOTES_MARKET_CLOSED",
            )
            self.assertEqual(
                report["dataSources"]["databentoLive"]["status"],
                "disabled-until-explicit-opt-in",
            )
            self.assertEqual(
                report["dataSources"]["preferredExecutionDataPath"],
                "topstepx_projectx_signalr",
            )
            self.assertTrue(report["dataSources"]["topstepRealtimeProof"]["readyForExecutionDataProof"])
            self.assertIn(
                "TopstepX realtime proof is visible, but canonical realtime quote state/freshness is not yet promoted",
                report["blockers"],
            )
            self.assertFalse(report["dataSources"]["databentoLive"]["canAttemptLiveFetch"])
            self.assertIn("BILL_ENABLE_FUTURES_DEMO_EXECUTION=false", report["dataSources"]["databentoLive"]["safeDataOnlyCommand"])
            self.assertIn("--databento-only", report["dataSources"]["databentoLive"]["safeDataOnlyCommand"])
            self.assertIn("secret-value", preflight.parse_env_file(env_file)["DATABENTO_API_KEY"])
            self.assertNotIn("secret-value", json.dumps(report))

    def test_databento_live_summary_marks_explicit_data_only_attempt_ready(self):
        env_values = {
            "DATABENTO_API_KEY": "secret-value",
            "BILL_DATABENTO_REALTIME_ENABLED": "true",
        }
        summary = preflight.databento_live_summary(env_values, {"available": True})

        self.assertEqual(summary["status"], "ready-to-attempt-live-data")
        self.assertTrue(summary["canAttemptLiveFetch"])
        self.assertTrue(summary["explicitlyEnabled"])
        self.assertTrue(summary["dataset"]["usesDefault"])
        self.assertEqual(summary["dataset"]["value"], "GLBX.MDP3")
        self.assertNotIn("secret-value", json.dumps(summary))

    def test_databento_module_absent_does_not_block_when_optional_path_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_dir = root / ".rumbling-hedge" / "state"
            state_dir.mkdir(parents=True)
            env_file = root / "bill.env"
            env_file.write_text("")
            wrapper = root / "scripts" / "realtime_cron.sh"
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text(
                "\n".join([
                    'PYTHON_BIN="${PYTHON_BIN:-$HOME_DIR/hedge/.venv/bin/python}"',
                    "export BILL_ENABLE_FUTURES_DEMO_EXECUTION=false",
                    "export RH_TOPSTEP_READ_ONLY=true",
                    "export RH_LIVE_EXECUTION_ENABLED=false",
                ])
            )

            now = datetime(2026, 5, 30, 3, 0, tzinfo=timezone.utc)
            (state_dir / "realtime-quote.latest.json").write_text(json.dumps({
                "timestamp": now.isoformat(),
                "source": "topstep_realtime",
                "execution_grade": True,
                "price_nq": 1,
                "price_es": 1,
            }))
            (state_dir / "data-freshness-gate.latest.json").write_text(json.dumps({
                "verdict": "PASS",
                "action": "allow_trades",
                "checks": [],
            }))
            (state_dir / "databento-realtime-smoke.latest.json").write_text(json.dumps({}))
            (state_dir / "topstep-realtime-proof.latest.json").write_text(json.dumps({
                "generatedAt": now.isoformat(),
                "status": "PASS",
                "readyForExecutionDataProof": True,
            }))

            with patch.dict(preflight.os.environ, {
                "RH_TOPSTEP_API_KEY": "topstep-key",
                "RH_TOPSTEP_USERNAME": "topstep-user",
            }, clear=True), \
                patch.object(preflight, "BILL_ENV", env_file), \
                patch.object(preflight, "STATE_DIR", state_dir), \
                patch.object(preflight, "REALTIME_STATE", state_dir / "realtime-quote.latest.json"), \
                patch.object(preflight, "DATA_FRESHNESS_STATE", state_dir / "data-freshness-gate.latest.json"), \
                patch.object(preflight, "DATABENTO_SMOKE_STATE", state_dir / "databento-realtime-smoke.latest.json"), \
                patch.object(preflight, "TOPSTEP_REALTIME_PROOF_STATE", state_dir / "topstep-realtime-proof.latest.json"), \
                patch.object(preflight, "CRON_WRAPPER", wrapper), \
                patch.object(preflight, "module_available", return_value={"module": "databento", "available": False, "origin": None}):
                report = preflight.build_report(now=now)

            self.assertTrue(report["readyForExecutionData"])
            self.assertNotIn("databento python module is not importable from the bridge runtime", report["blockers"])
            self.assertEqual(report["dataSources"]["databentoRole"], "optional-secondary-depth-research")
            self.assertFalse(report["dataSources"]["alpacaSandbox"]["executionAuthority"])


if __name__ == "__main__":
    unittest.main()
