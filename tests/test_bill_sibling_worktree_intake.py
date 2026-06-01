import unittest

from scripts.bill_sibling_worktree_intake import build_intake, classify_path, parse_git_status


class BillSiblingWorktreeIntakeTests(unittest.TestCase):
    def test_parse_git_status_handles_renames_and_untracked(self):
        rows = parse_git_status(" M src/cli.ts\n?? data/free/NQ.csv\nR  old.py -> scripts/new.py\n")

        self.assertEqual(rows[0], {"status": "M", "path": "src/cli.ts"})
        self.assertEqual(rows[1], {"status": "??", "path": "data/free/NQ.csv"})
        self.assertEqual(rows[2], {"status": "R", "path": "scripts/new.py"})

    def test_classifies_sibling_paths_conservatively(self):
        self.assertEqual(classify_path("src/live/demoExecution.ts"), "execution-live-quarantine")
        self.assertEqual(classify_path("src/prediction/adapters/polymarket.ts"), "execution-live-quarantine")
        self.assertEqual(classify_path("package.json"), "dependency-review")
        self.assertEqual(classify_path("data/free/NQ.csv"), "data-research-review")
        self.assertEqual(classify_path("src/engine/riskPolicyGuard.ts"), "governance-risk-review")
        self.assertEqual(classify_path("ops/mac-mini/README.md"), "ops-docs-review")
        self.assertEqual(classify_path("tests/backtest.test.ts"), "strategy-research-review")

    def test_build_intake_keeps_dirty_sibling_quarantined(self):
        payload = build_intake(
            {
                "dirtySiblingWorktrees": {
                    "worktrees": [
                        {
                            "path": "/tmp/sibling",
                            "branch": "codex/test",
                            "head": "abc",
                            "dirtyFiles": 4,
                        }
                    ]
                }
            },
            status_text_by_path={
                "/tmp/sibling": "\n".join(
                    [
                        " M src/live/demoExecution.ts",
                        " M package.json",
                        "?? src/engine/riskPolicyGuard.ts",
                        "?? tests/riskPolicyGuard.test.ts",
                    ]
                )
            },
        )

        self.assertEqual(payload["decision"], "sibling-worktree-intake-visible-quarantine")
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertFalse(payload["safeToMergeAutomatically"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertEqual(payload["dirtySiblingWorktreeCount"], 1)
        self.assertEqual(payload["dirtyFileCount"], 4)
        self.assertEqual(payload["executionLiveDirtyCount"], 1)
        self.assertIn("sibling-worktree-has-execution-live-dirty-files", payload["blockers"])
        self.assertIn("src/live/demoExecution.ts", payload["worktrees"][0]["topReviewFirst"])

    def test_build_intake_clear_when_no_dirty_sibling(self):
        payload = build_intake({"dirtySiblingWorktrees": {"worktrees": []}})

        self.assertEqual(payload["decision"], "sibling-worktree-intake-clear")
        self.assertEqual(payload["dirtySiblingWorktreeCount"], 0)
        self.assertEqual(payload["blockers"], [])


if __name__ == "__main__":
    unittest.main()
