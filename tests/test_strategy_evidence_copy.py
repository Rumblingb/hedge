import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STRATEGY_FILES = [
    ROOT / "src/strategies/orbBreakout.ts",
    ROOT / "src/strategies/orbBreakout60m.ts",
    ROOT / "src/strategies/wqTrendMom60m.ts",
    ROOT / "src/strategies/wqVolRegime60m.ts",
]


class StrategyEvidenceCopyTest(unittest.TestCase):
    def test_15m_60m_strategy_copy_does_not_claim_deployable_edge(self):
        banned = [
            "edge confirmed",
            "only strategy with consistent positive edge",
            "60% wr on nq",
            "64% wr on nq",
            "57% wr on nq",
        ]

        for path in STRATEGY_FILES:
            text = path.read_text().lower()
            with self.subTest(path=path.name):
                for phrase in banned:
                    self.assertNotIn(phrase, text)
                self.assertIn("research-only", text)


if __name__ == "__main__":
    unittest.main()
