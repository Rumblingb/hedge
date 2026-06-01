import importlib.util
import os
import unittest
from pathlib import Path

from scripts import pre_trade_check


ROOT = Path(__file__).resolve().parents[1]


def load_sixty_min_bridge():
    spec = importlib.util.spec_from_file_location("sixty_min_exec_bridge", ROOT / "scripts/60m_exec_bridge.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DemoSizingCapsTest(unittest.TestCase):
    def setUp(self):
        self._old_env = {
            "BILL_PRE_TRADE_MAX_CONTRACTS": os.environ.get("BILL_PRE_TRADE_MAX_CONTRACTS"),
            "BILL_60M_MAX_CONTRACTS": os.environ.get("BILL_60M_MAX_CONTRACTS"),
            "BILL_FUTURES_DEMO_MAX_CONTRACTS": os.environ.get("BILL_FUTURES_DEMO_MAX_CONTRACTS"),
        }
        for key in self._old_env:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_pre_trade_defaults_to_one_contract_even_for_high_conviction(self):
        scores = {
            "bullish": 10,
            "bearish": 1,
            "session_ok": True,
            "session": "NY",
            "fft": "bullish",
            "atr_15m": 20.0,
        }

        decision = pre_trade_check.decide(scores, is_fresh=True, force=False, has_force_flag=False)

        self.assertEqual(decision["research_contracts"], 4)
        self.assertEqual(decision["contracts"], 1)
        self.assertEqual(decision["max_contracts"], 1)

    def test_60m_bridge_defaults_to_one_contract_even_when_kelly_wants_more(self):
        bridge = load_sixty_min_bridge()
        signal = {"entry": 100.0, "stop": 99.0, "target": 104.0, "rr": 4.0}

        self.assertEqual(bridge.calc_position(signal, account_balance=50000), 1)


if __name__ == "__main__":
    unittest.main()
