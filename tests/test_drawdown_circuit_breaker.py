import tempfile
import unittest
from pathlib import Path

from scripts.drawdown_circuit_breaker import (
    DEFAULT_STATE_DIR,
    TIER_BLACK,
    compute_breaker,
)


class DrawdownCircuitBreakerTests(unittest.TestCase):
    def test_default_state_dir_is_canonical_hedge_state(self):
        self.assertEqual(DEFAULT_STATE_DIR, Path.home() / "hedge/.rumbling-hedge/state")
        self.assertNotEqual(DEFAULT_STATE_DIR, Path.home() / ".rumbling-hedge/state")

    def test_emergency_stop_uses_passed_state_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp)
            (state_dir / "EMERGENCY_STOP").write_text("stop\n")

            result = compute_breaker(state_dir, balance_override=100000)

        self.assertEqual(result["tier"], TIER_BLACK)
        self.assertEqual(result["sizing_multiplier"], 0.0)
        self.assertIn("EMERGENCY_STOP", result["reason"])


if __name__ == "__main__":
    unittest.main()
