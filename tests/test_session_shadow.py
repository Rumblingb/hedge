import importlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


class SessionShadowTest(unittest.TestCase):
    def load_modules(self, tmp_path: Path):
        premarket = importlib.import_module("scripts.session_shadow_premarket")
        logger = importlib.import_module("scripts.session_shadow_trade_logger")
        postmarket = importlib.import_module("scripts.session_shadow_postmarket")

        state = tmp_path / "state"
        shadow_dir = state / "session-shadows"
        shadow_dir.mkdir(parents=True)

        for module in (premarket, logger, postmarket):
            module.STATE = state
            module.SHADOW_DIR = shadow_dir
        logger.JOURNAL_PATH = state / "trade-journal.latest.json"
        postmarket.OBSIDIAN_HERMES = tmp_path / "vault" / "Agent-Hermes"
        postmarket.OBSIDIAN_HERMES.mkdir(parents=True)
        (postmarket.OBSIDIAN_HERMES / "daily").mkdir(parents=True)
        return premarket, logger, postmarket

    def test_microprice_imbalance_requires_size_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            premarket, _, _ = self.load_modules(Path(tmp))

            no_size = {
                "nq": {"bid": 100.0, "ask": 100.25, "price": 100.1},
                "source": "test",
            }
            with_size = {
                "nq": {"bid": 100.0, "ask": 100.25, "price": 100.1, "bid_size": 9, "ask_size": 3},
                "source": "test",
            }

            self.assertIsNone(premarket.estimate_microprice_imbalance(no_size))
            self.assertEqual(premarket.estimate_microprice_imbalance(with_size), 0.5)

    def test_premarket_shadow_is_research_only_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            premarket, _, _ = self.load_modules(Path(tmp))
            now = datetime(2026, 6, 8, 13, 25, tzinfo=timezone.utc)

            shadow = premarket.build_premarket_shadow(now)

            self.assertTrue(shadow["researchOnly"])
            self.assertFalse(shadow["writesOrders"])
            self.assertFalse(shadow["touchesBroker"])
            self.assertFalse(shadow["readyForExecution"])
            self.assertEqual(shadow["plan"]["max_algo_contracts"], 0)
            self.assertTrue((Path(tmp) / "state/session-shadows/session-2026-06-08.json").exists())

    def test_trade_logger_records_observation_not_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            premarket, logger, _ = self.load_modules(Path(tmp))
            now = datetime(2026, 6, 8, 13, 25, tzinfo=timezone.utc)
            premarket.build_premarket_shadow(now)

            ok = logger.log_trade(
                {
                    "side": "long",
                    "entry": 30100.0,
                    "symbol": "MNQ",
                    "strategy_id": "manual-observation",
                    "intent_notes": "Testing NY ORB watch only.",
                    "mistake_tags": ["early-entry"],
                },
                now=now,
            )

            self.assertTrue(ok)
            journal = json.loads((Path(tmp) / "state/trade-journal.latest.json").read_text())
            self.assertEqual(journal[0]["mistake_tags"], ["early-entry"])
            self.assertFalse(journal[0]["writesOrders"])
            self.assertFalse(journal[0]["touchesBroker"])
            self.assertFalse(journal[0]["readyForExecution"])

    def test_postmarket_shadow_turns_trade_into_learning_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            premarket, logger, postmarket = self.load_modules(Path(tmp))
            now = datetime(2026, 6, 8, 13, 25, tzinfo=timezone.utc)
            premarket.build_premarket_shadow(now)
            trade = {
                "trade_number": 1,
                "timestamp": "2026-06-08T14:35:00+00:00",
                "entry_time": "2026-06-08T14:35:00+00:00",
                "side": "long",
                "entry": 30100.0,
                "exit": 30090.0,
                "points": -10.0,
                "outcome": "loss",
                "post_mortem": {"timing_early": True, "bars_premature": 2},
            }
            logger.write_json(Path(tmp) / "state/trade-journal.latest.json", [trade])

            shadow = postmarket.build_postmarket_shadow(datetime(2026, 6, 8, 20, 0, tzinfo=timezone.utc))

            self.assertTrue(shadow["researchOnly"])
            self.assertFalse(shadow["readyForExecution"])
            self.assertEqual(shadow["post_mortem"]["outcome"], "loss")
            self.assertIn("too early", shadow["post_mortem"]["lesson"])
            daily = Path(tmp) / "vault/Agent-Hermes/daily/2026-06-08.md"
            self.assertIn("Session Shadow", daily.read_text())


if __name__ == "__main__":
    unittest.main()
