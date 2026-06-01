import unittest

from scripts.current_alpha_watch import build_watch, default_markdown_path, render_markdown


class CurrentAlphaWatchTest(unittest.TestCase):
    def test_build_watch_keeps_execution_locked_and_surfaces_main_lanes(self):
        payload = build_watch(
            alpha_direction={
                "readyForResearchLoop": True,
                "continueLanes": [
                    {
                        "id": "futures-paid-nq-session-structure",
                        "reason": "change data source before parameters",
                        "oneVariable": "data source",
                        "firstCommand": "npm run --silent bill:external-alpha-data-audit",
                    }
                ],
                "retireOrQuarantineLanes": [{"id": "generic-yt-gold-strategy-reruns", "reason": "needs rules"}],
                "nextOneVariableTest": {
                    "id": "futures-paid-nq-session-structure-oos",
                    "lane": "futures",
                    "oneVariable": "data source/cadence only",
                    "command": "npm run --silent bill:external-alpha-data-audit",
                    "successCriteria": ["OOS positive"],
                    "rejectionCriteria": ["full-sample only"],
                },
            },
            alpha_tooling={
                "status": "PASS",
                "readyForResearchLoop": True,
                "blockers": [],
                "warnings": [],
                "commands": {"required": [{"command": "python3", "ok": True}]},
                "pythonModules": [{"package": "backtrader", "ok": True}],
            },
            next_actions={
                "actions": [
                    {
                        "id": "futures-paid-nq-1m-session-structure-oos",
                        "lane": "futures",
                        "priority": 20,
                        "oneVariable": "data source",
                        "firstCommand": "npm run --silent bill:external-alpha-data-audit",
                        "promotionBlockers": ["execution remains locked"],
                        "researchOnly": True,
                        "writesOrders": False,
                        "touchesBroker": False,
                    },
                    {
                        "id": "prediction-event-lag-watch-window-review",
                        "lane": "prediction-markets",
                        "priority": 40,
                        "oneVariable": "capture duration/window only",
                        "firstCommand": "npm run --silent bill:prediction-event-capture-cycle",
                        "promotionBlockers": ["paper gate blocked"],
                    },
                ]
            },
            paper_cards={
                "cards": [
                    {
                        "id": "paper-a",
                        "lane": "futures",
                        "decision": "candidate",
                        "tradableVariable": "volatility regime overlay",
                        "oneVariableTest": "Add exactly one overlay.",
                    },
                    {
                        "id": "not-alpha",
                        "lane": "exclude",
                        "decision": "not-bill-alpha",
                    },
                ]
            },
            seed_triage={
                "decision": "research-only; no seed is executable",
                "totalSeeds": 35,
                "queuedYT": 3,
                "candidateRetest": 0,
                "executable": 0,
            },
            futures_cycle={"decision": "research-only-futures-cycle-ran-still-blocked", "blockers": ["broker-parity-not-checked"]},
            prediction_capture={
                "decision": "research-only-capture-cycle-ran-still-blocked",
                "blockers": ["recorder-live-quality-not-fillable"],
                "liveQualityDiagnostics": {"fillableLiveBookCount": 0},
            },
            prediction_gate={
                "decision": "research-only-paper-promotion-blocked",
                "blockedIds": ["forward-public-clob-capture"],
            },
            automation_audit={
                "decision": "codex-automations-visible-research-locked",
                "status": "PASS",
                "activePredictionCaptureIds": ["bill-prediction-forward-clob-capture"],
                "activeFuturesOpenSessionProofIds": ["bill-open-session-data-proof"],
            },
            goal_audit={
                "decision": "continue-research-only-locked",
                "blockedIds": ["futures-demo-not-cleared"],
            },
        )

        self.assertEqual(payload["decision"], "research-only-alpha-watch-execution-locked")
        self.assertTrue(payload["readyForResearchLoop"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertEqual(payload["goalBlockedIds"], ["futures-demo-not-cleared"])
        self.assertEqual(payload["tooling"]["status"], "PASS")
        self.assertTrue(payload["tooling"]["readyForResearchLoop"])
        self.assertEqual(payload["tooling"]["requiredCommandsMissing"], [])
        self.assertEqual(payload["futures"]["paperSeeds"][0]["id"], "paper-a")
        self.assertEqual(payload["predictionMarkets"]["fillableLiveBookCount"], 0)
        self.assertEqual(payload["seedTriage"]["queuedYT"], 3)

    def test_markdown_uses_generated_date_and_hard_rules(self):
        markdown = render_markdown({
            "generatedAt": "2026-05-31T10:00:00+00:00",
            "decision": "research-only-alpha-watch-execution-locked",
            "goalDecision": "continue-research-only-locked",
            "goalBlockedIds": ["source-hygiene-not-cleared"],
            "readyForResearchLoop": True,
            "readyForExecution": False,
            "readyForDemoExpansion": False,
            "readyForLive": False,
            "tooling": {
                "status": "PASS",
                "readyForResearchLoop": True,
                "blockers": [],
                "warnings": [],
                "requiredCommandsMissing": [],
                "requiredModulesMissing": [],
            },
            "continueLanes": [],
            "retireOrQuarantineLanes": [],
            "nextOneVariableTest": {},
            "futures": {"topActions": [], "paperSeeds": []},
            "predictionMarkets": {"topActions": []},
            "seedTriage": {},
            "automations": {},
            "hardRules": ["This watchlist is not execution evidence."],
        })

        self.assertIn("# Current Alpha Watch - 2026-05-31", markdown.splitlines()[0])
        self.assertNotIn("2026-05-30", markdown.splitlines()[0])
        self.assertIn("Ready for research loop: `True`", markdown)
        self.assertIn("## Tooling", markdown)
        self.assertIn("Status: `PASS`", markdown)
        self.assertIn("This watchlist is not execution evidence.", markdown)

    def test_fillable_live_book_count_reads_latest_recorder_zero(self):
        payload = build_watch(
            alpha_direction={},
            alpha_tooling={
                "commands": {"required": [{"command": "yt-dlp", "ok": False}]},
                "pythonModules": [{"package": "databento", "ok": False}],
            },
            next_actions={},
            paper_cards={},
            seed_triage={},
            futures_cycle={},
            prediction_capture={
                "latestRecorder": {
                    "liveQualityDiagnostics": {
                        "fillableLiveBookCount": 0,
                    }
                }
            },
            prediction_gate={},
            automation_audit={},
            goal_audit={},
        )

        self.assertEqual(payload["predictionMarkets"]["fillableLiveBookCount"], 0)
        self.assertEqual(payload["tooling"]["requiredCommandsMissing"], ["yt-dlp"])
        self.assertEqual(payload["tooling"]["requiredModulesMissing"], ["databento"])

    def test_default_markdown_path_uses_current_date(self):
        path = default_markdown_path()

        self.assertRegex(path.name, r"^current-alpha-watch-\d{4}-\d{2}-\d{2}\.md$")
        self.assertNotEqual(path.name, "current-alpha-watch-2026-05-30.md")


if __name__ == "__main__":
    unittest.main()
