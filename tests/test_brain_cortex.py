import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts import brain_cortex
from scripts.brain_cortex import ROOT, execute_decisions


class BrainCortexTests(unittest.TestCase):
    def test_default_root_is_canonical_repo_state(self):
        self.assertEqual(ROOT, Path.home() / "hedge" / ".rumbling-hedge")

    def test_advisory_only_skips_motor_outputs(self):
        awareness = {
            "decisions": [
                {"action": "urgent_execution", "priority": "high"},
                {"action": "process_signals", "priority": "medium"},
            ]
        }

        result = execute_decisions(awareness, memory=object(), advisory_only=True)

        self.assertEqual(result["executed"], 0)
        self.assertEqual([item["status"] for item in result["results"]], [
            "advisory_only_skipped",
            "advisory_only_skipped",
        ])
        self.assertEqual([item["target"] for item in result["results"]], ["none", "none"])

    def test_advisory_cycle_writes_no_order_brain_state_without_motor_outputs(self):
        sensory = {
            "ts": "2026-05-31T04:00:00+00:00",
            "active_count": 2,
            "total_count": 3,
            "fused_direction": 0.75,
            "top_signals": ["vol_regime_gate"],
            "signal_attribution": {"vol_regime_gate": 1.0},
        }
        awareness = {
            "ts": sensory["ts"],
            "regime": {"regime": "test", "day_of_week": "Sunday", "is_market_open": False},
            "signals": {
                "active": 2,
                "fused_direction": 0.75,
                "direction_breakdown": {"vol_regime_gate": 0},
                "top_signals": ["vol_regime_gate"],
                "signal_attribution": {"vol_regime_gate": 1.0},
            },
            "memory": {"novelty_score": 0.9},
            "pathway_weights": {},
            "proprioception": {"has_positions": False},
            "attention": ["test attention"],
            "decisions": [
                {"action": "urgent_execution", "priority": "high"},
                {"action": "collect_research", "priority": "medium"},
            ],
            "warnings": [],
        }

        class FakeMemory:
            def recall_similar(self, _sensory):
                return []

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brain_dir = root / "brain"
            with patch.object(brain_cortex, "ROOT", root), \
                 patch.object(brain_cortex, "BRAIN_DIR", brain_dir), \
                 patch.object(brain_cortex, "STATE_DIR", root / "state"), \
                 patch.object(brain_cortex, "ingest_all_signals", return_value=sensory), \
                 patch.object(brain_cortex, "Hippocampus", return_value=FakeMemory()), \
                 patch.object(brain_cortex, "load_position_state", return_value={"has_positions": False}), \
                 patch.object(brain_cortex, "build_awareness", return_value=awareness):
                brain_cortex.run_cycle(advisory_only=True)

            state = json.loads((brain_dir / "brain-state.latest.json").read_text())
            self.assertTrue(state["researchOnly"])
            self.assertTrue(state["advisoryOnly"])
            self.assertFalse(state["writesOrders"])
            self.assertFalse(state["touchesBroker"])
            self.assertFalse(state["tradable_signal"])
            self.assertFalse(state["promoted_for_execution"])
            self.assertFalse(state["readyForExecution"])
            self.assertEqual(state["execution_role"], "diagnostic_only")
            self.assertFalse((brain_dir / "motor-output.latest.json").exists())
            self.assertFalse((brain_dir / "urgent-execution.json").exists())
            self.assertFalse((brain_dir / "research-hunger.json").exists())


if __name__ == "__main__":
    unittest.main()
