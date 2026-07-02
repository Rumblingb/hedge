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


def load_master_bridge():
    spec = importlib.util.spec_from_file_location("master_bridge", ROOT / "scripts/master_bridge.py")
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
        self.assertEqual(decision["instrument"], "MNQ")
        self.assertEqual(decision["point_value"], 2.0)
        self.assertEqual(decision["sl_pts"], 36.0)
        self.assertEqual(decision["risk_dollars"], 72.0)
        self.assertTrue(decision["research_only"])
        self.assertFalse(decision["writes_orders"])
        self.assertFalse(decision["touches_broker"])

    def test_pre_trade_nq_override_uses_full_nq_point_value(self):
        os.environ["BILL_PRE_TRADE_INSTRUMENT"] = "NQ"
        scores = {
            "bullish": 10,
            "bearish": 1,
            "session_ok": True,
            "session": "NY",
            "fft": "bullish",
            "atr_15m": 20.0,
        }

        decision = pre_trade_check.decide(scores, is_fresh=True, force=False, has_force_flag=False)

        self.assertEqual(decision["instrument"], "NQ")
        self.assertEqual(decision["point_value"], 20.0)
        self.assertEqual(decision["contracts"], 1)
        self.assertEqual(decision["risk_dollars"], 720.0)

    def test_60m_bridge_defaults_to_one_contract_even_when_kelly_wants_more(self):
        bridge = load_sixty_min_bridge()
        signal = {"entry": 100.0, "stop": 99.0, "target": 104.0, "rr": 4.0}

        self.assertEqual(bridge.calc_position(signal, account_balance=50000), 1)

    def test_master_bridge_defaults_to_one_contract_even_when_kelly_wants_more(self):
        bridge = load_master_bridge()
        signal = {"strategy": "orb-breakout", "entry": 100.0, "stop": 99.0, "target": 104.0, "rr": 4.0}

        self.assertEqual(bridge.calc_position(signal, account_balance=50000), 1)

    def test_60m_bridge_uses_mnq_two_dollar_point_value_for_webhook_dollars(self):
        source = (ROOT / "scripts/60m_exec_bridge.py").read_text()

        self.assertIn("price_per_point = 2", source)
        self.assertNotIn("price_per_point = 5", source)

    def test_master_bridge_uses_mnq_two_dollar_point_value_and_no_forced_minimum(self):
        source = (ROOT / "scripts/master_bridge.py").read_text()

        self.assertIn('risk_per_contract = stop_dist * point_value(signal.get("symbol", "MNQ"))', source)
        self.assertNotIn("risk_per_contract = stop_dist * 5", source)
        self.assertNotIn("return max(3", source)
        self.assertNotIn("contracts = max(3", source)

        bridge = load_master_bridge()
        self.assertEqual(bridge.point_value("MNQ"), 2.0)
        self.assertEqual(bridge.DEFAULT_INSTRUMENT, "MNQ")


if __name__ == "__main__":
    unittest.main()
