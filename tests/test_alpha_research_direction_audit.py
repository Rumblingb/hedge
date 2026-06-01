import unittest

from scripts.alpha_research_direction_audit import build_audit


class AlphaResearchDirectionAuditTests(unittest.TestCase):
    def test_direction_audit_keeps_research_lanes_and_retirements_separate(self):
        payload = build_audit(
            seed_triage={
                "summary": {
                    "queuedYouTubeSeeds": 3,
                    "duplicateSourceIds": 13,
                    "nextBuildQueueCount": 0,
                },
                "nextBuildQueue": [],
            },
            alpha_frontier={"frontier": [{"id": "frontier-a"}]},
            next_actions={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "actions": [
                    {
                        "id": "futures-paid-nq-1m-session-structure-oos",
                        "oneVariable": "data source",
                        "firstCommand": "npm run --silent bill:external-alpha-data-audit",
                        "commands": ["npm run --silent bill:futures-nq-historical-session-replay"],
                        "dataPaths": ["/Volumes/Seagate Expansion Drive/hedge-data/features/nq_futures/nq_15_minute.parquet"],
                        "writesOrders": False,
                        "touchesBroker": False,
                    },
                    {
                        "id": "prediction-news-first-event-lag-study",
                        "oneVariable": "news-to-market lag feature",
                        "firstCommand": "npm run --silent bill:finnhub-news",
                        "commands": ["npm run --silent bill:prediction-event-capture-cycle -- --run-recorder"],
                        "writesOrders": False,
                        "touchesBroker": False,
                    },
                    {
                        "id": "futures-options-regime-risk-overlay",
                        "oneVariable": "options regime overlay",
                        "firstCommand": "npm run --silent bill:alpha-frontier-queue",
                        "commands": ["npm run --silent bill:alpha-frontier-queue"],
                        "writesOrders": False,
                        "touchesBroker": False,
                    },
                ],
            },
            futures_no_edge={
                "noEdgeCount": 4,
                "promotableCount": 0,
                "entries": [{"id": "wq-vol-regime-60m-current-form", "verdict": "no-edge"}],
            },
            prediction_no_edge={
                "noEdgeCount": 10,
                "promotableCount": 0,
                "entries": [{"id": "polymarket-clob-drift-persistence-current-thresholds", "verdict": "no-edge"}],
            },
            futures_cycle={
                "blockers": ["execution-grade-realtime-not-cleared"],
            },
            prediction_gate={
                "decision": "research-only-paper-promotion-blocked",
                "blockedIds": ["post-spread-clob-edge"],
            },
            source_intake={
                "sourceClean": False,
                "dirtyStatusCount": 341,
                "reviewBacklogCount": 195,
                "executionLiveDirtyCount": 27,
            },
        )

        self.assertEqual(payload["decision"], "research-direction-clear-execution-locked")
        self.assertTrue(payload["queueSafe"])
        self.assertTrue(payload["readyForResearchLoop"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["writesOrders"])
        self.assertEqual([item["id"] for item in payload["continueLanes"]], [
            "futures-paid-nq-session-structure",
            "prediction-news-event-lag-forward-clob",
            "futures-options-regime-risk-overlay",
        ])
        self.assertIn("current-fixed-prediction-clob-forms", [item["id"] for item in payload["retireOrQuarantineLanes"]])
        self.assertEqual(payload["nextOneVariableTest"]["oneVariable"], "data source/cadence only")
        self.assertEqual(payload["nextOneVariableTest"]["parallelWatch"]["blockedBy"], ["post-spread-clob-edge"])

    def test_direction_audit_flags_unsafe_queue_command(self):
        payload = build_audit(
            seed_triage={},
            alpha_frontier={},
            next_actions={
                "researchOnly": True,
                "writesOrders": False,
                "touchesBroker": False,
                "actions": [
                    {
                        "id": "bad",
                        "commands": ["node scripts/fund-and-trade.ts"],
                        "writesOrders": False,
                        "touchesBroker": False,
                    }
                ],
            },
            futures_no_edge={},
            prediction_no_edge={},
            futures_cycle={},
            prediction_gate={},
            source_intake={},
        )

        self.assertEqual(payload["decision"], "research-direction-needs-command-review")
        self.assertFalse(payload["queueSafe"])
        self.assertFalse(payload["readyForResearchLoop"])


if __name__ == "__main__":
    unittest.main()
