import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scripts.research_seed_target_refresh_plan import build_plan, render_markdown


class ResearchSeedTargetRefreshPlanTest(unittest.TestCase):
    def test_zero_yield_same_targets_are_not_rerunnable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            triage = tmp_path / "triage.json"
            targets = tmp_path / "targets.json"
            triage.write_text(json.dumps({
                "queuedYouTubeResearcherTargets": [
                    {"id": "youtube-queue-a", "videos": ["https://youtu.be/a"]},
                    {"id": "youtube-queue-b", "videos": ["https://youtu.be/b"]},
                ],
                "queuedYouTubeLatestRun": {
                    "present": True,
                    "runId": "run-zero",
                    "status": "degraded",
                    "chunksCollected": 0,
                    "strategyHypothesesCount": 0,
                    "blockers": ["no novel chunks"],
                    "targetResults": [
                        {"targetId": "youtube-queue-a", "videosProcessed": 1, "collected": 0, "kept": 0},
                        {"targetId": "youtube-queue-b", "videosProcessed": 1, "collected": 0, "kept": 0},
                    ],
                },
                "items": [
                    {"sourceId": "youtube-queue-a", "title": "Futures source A", "decision": "research-only-unmapped-seed"},
                    {"sourceId": "youtube-queue-b", "title": "Prediction source B", "decision": "research-only-unmapped-seed"},
                ],
            }))
            targets.write_text(json.dumps({
                "targets": [
                    {"id": "youtube-queue-a", "videos": ["https://youtu.be/a"]},
                    {"id": "youtube-queue-b", "videos": ["https://youtu.be/b"]},
                ]
            }))

            plan = build_plan(argparse.Namespace(
                triage=str(triage),
                targets=str(targets),
            ))

        self.assertEqual(plan["decision"], "refresh-required-current-targets-exhausted")
        self.assertTrue(plan["researchOnly"])
        self.assertFalse(plan["writesOrders"])
        self.assertFalse(plan["touchesBroker"])
        self.assertFalse(plan["readyForExecution"])
        self.assertEqual(plan["summary"]["retireOrManualConvertCount"], 2)
        self.assertEqual(plan["summary"]["rerunnableTargetCount"], 0)
        self.assertTrue(plan["summary"]["zeroYieldSameTargets"])
        self.assertTrue(all(item["action"] == "retire-or-manual-convert" for item in plan["targetDecisions"]))
        self.assertTrue(all(item["rerunAllowed"] is False for item in plan["targetDecisions"]))
        self.assertIn("one changed variable", " ".join(plan["newTargetRequirements"]))
        self.assertIn("npm run --silent bill:next-research-actions", plan["nextCommands"])

    def test_missing_latest_run_allows_one_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            triage = tmp_path / "triage.json"
            targets = tmp_path / "targets.json"
            triage.write_text(json.dumps({
                "queuedYouTubeResearcherTargets": [
                    {"id": "youtube-queue-a", "videos": ["https://youtu.be/a"]},
                ],
                "items": [
                    {"sourceId": "youtube-queue-a", "title": "Futures source A"},
                ],
            }))
            targets.write_text(json.dumps({"targets": []}))

            plan = build_plan(argparse.Namespace(
                triage=str(triage),
                targets=str(targets),
            ))

        self.assertEqual(plan["decision"], "review-targets-before-extraction")
        self.assertEqual(plan["summary"]["rerunnableTargetCount"], 1)
        self.assertEqual(plan["targetDecisions"][0]["action"], "extract-transcript-once")
        self.assertTrue(plan["targetDecisions"][0]["rerunAllowed"])

    def test_markdown_surfaces_target_decision_and_hard_rules(self):
        plan = {
            "decision": "refresh-required-current-targets-exhausted",
            "researchOnly": True,
            "writesOrders": False,
            "touchesBroker": False,
            "summary": {
                "queuedTargetCount": 1,
                "retireOrManualConvertCount": 1,
                "rerunnableTargetCount": 0,
            },
            "latestQueuedRun": {
                "runId": "run-zero",
                "status": "degraded",
                "chunksCollected": 0,
                "strategyHypothesesCount": 0,
            },
            "targetDecisions": [
                {
                    "targetId": "youtube-queue-a",
                    "action": "retire-or-manual-convert",
                    "rerunAllowed": False,
                    "title": "Futures source A",
                    "videos": ["https://youtu.be/a"],
                    "reason": "same queued target already produced zero chunks",
                }
            ],
            "newTargetRequirements": ["futures or prediction-market source only"],
            "nextCommands": ["npm run --silent bill:research-seed-target-refresh-plan"],
            "hardRules": ["Do not rerun a zero-yield queued target."],
        }

        markdown = render_markdown(plan)

        self.assertIn("refresh-required-current-targets-exhausted", markdown)
        self.assertIn("youtube-queue-a", markdown)
        self.assertIn("retire-or-manual-convert", markdown)
        self.assertIn("Do not rerun", markdown)


if __name__ == "__main__":
    unittest.main()
