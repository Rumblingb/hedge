import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import (
    fibonacci_agent,
    heiken_ashi_agent,
    manipulation_4h_detector,
    new_arsenal_runner,
    noise_stepforward_analysis,
    vwap_agent,
)


class NewArsenalRunnerStateDirTest(unittest.TestCase):
    def test_defaults_to_canonical_state_dir(self):
        canonical = Path.home() / "hedge/.rumbling-hedge/state"
        self.assertEqual(
            new_arsenal_runner.STATE_DIR,
            canonical,
        )
        self.assertNotEqual(
            new_arsenal_runner.STATE_DIR,
            Path.home() / ".rumbling-hedge/state",
        )
        self.assertEqual(noise_stepforward_analysis.STATE_DIR, canonical)
        self.assertEqual(vwap_agent.STATE_DIR, canonical)
        self.assertEqual(heiken_ashi_agent.STATE_DIR, canonical)
        self.assertEqual(fibonacci_agent.STATE_DIR, canonical)
        self.assertEqual(manipulation_4h_detector.STATE_DIR, canonical)

    def test_child_generators_receive_canonical_state_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            script_dir = Path(tmp) / "scripts"
            script_dir.mkdir()
            original_state = new_arsenal_runner.STATE_DIR
            original_scripts = new_arsenal_runner.SCRIPTS_DIR
            try:
                new_arsenal_runner.STATE_DIR = state_dir
                new_arsenal_runner.SCRIPTS_DIR = script_dir
                captured = {}

                def fake_run(cmd, capture_output, text, timeout, env):
                    captured["cmd"] = cmd
                    captured["env"] = env
                    return SimpleNamespace(returncode=0, stdout="", stderr="")

                with patch.object(new_arsenal_runner.subprocess, "run", side_effect=fake_run):
                    result = new_arsenal_runner.run_script("pead_earnings_scanner.py")

                self.assertEqual(result, {"status": "completed"})
                self.assertEqual(captured["env"]["BILL_STATE_DIR"], str(state_dir))
                self.assertEqual(captured["cmd"][1], str(script_dir / "pead_earnings_scanner.py"))
            finally:
                new_arsenal_runner.STATE_DIR = original_state
                new_arsenal_runner.SCRIPTS_DIR = original_scripts


if __name__ == "__main__":
    unittest.main()
