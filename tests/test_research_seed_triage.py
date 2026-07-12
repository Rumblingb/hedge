import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scripts.research_seed_triage import (
    build_report,
    parse_youtube_source_cards,
    queued_youtube_latest_run_summary,
    queued_youtube_targets,
    render_markdown,
)


class ResearchSeedTriageTest(unittest.TestCase):
    def test_triage_keeps_youtube_gold_as_research_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            hypotheses = tmp_path / "hypotheses.json"
            strategy_feed = tmp_path / "feed.json"
            strategy_zoo = tmp_path / "zoo.json"
            futures_no_edge = tmp_path / "futures-no-edge.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            backtrader_research = tmp_path / "backtrader.json"
            youtube_source_cards = tmp_path / "youtube-source-cards.md"

            hypotheses.write_text(json.dumps({
                "hypotheses": [
                    {
                        "id": "fvg-1",
                        "title": "FVG Day Trading Strategy",
                        "market": "futures",
                        "symbols": ["ES", "NQ"],
                        "timeframes": ["5m"],
                        "entryRules": ["Long after FVG retest"],
                        "stopRules": ["Stop below FVG"],
                        "targetRules": ["2R target"],
                        "sourceVideoIds": ["abc"],
                        "sourceUrls": ["https://www.youtube.com/watch?v=abc"],
                        "evidence": ["Backtest 81% win rate over 16 trades"]
                    },
                    {
                        "id": "trend-1",
                        "title": "Trend momentum with session filter",
                        "market": "futures",
                        "symbols": ["NQ"],
                        "timeframes": ["30m"],
                        "entryRules": ["Trend up and momentum positive"],
                        "stopRules": ["ATR stop"],
                        "targetRules": ["Fixed target"],
                        "sourceUrls": ["https://example.test/paper"]
                    },
                    {
                        "id": "bb-1",
                        "title": "Mean Reversion with Bollinger Bands, RSI, and ADX",
                        "market": "futures",
                        "symbols": ["NQ"],
                        "timeframes": ["1h"],
                        "entryRules": ["Close below lower band"],
                        "stopRules": ["ATR stop"],
                        "targetRules": ["Upper band exit"],
                        "sourceVideoIds": ["def"]
                    },
                    {
                        "id": "vp-1",
                        "title": "Volume Profile Edge Strategy",
                        "market": "futures",
                        "symbols": ["NQ"],
                        "timeframes": ["1h"],
                        "entryRules": ["Fade high value area edge"],
                        "stopRules": ["Stop beyond value area"],
                        "targetRules": ["Mean reversion to POC"],
                        "sourceVideoIds": ["ghi"]
                    },
                    {
                        "id": "liq-1",
                        "title": "Research-seeded liquidity reversion stress test",
                        "market": "futures",
                        "symbols": ["NQ"],
                        "timeframes": ["5m"],
                        "entryRules": ["Fade liquidity extension"],
                        "stopRules": ["Stop beyond sweep"],
                        "targetRules": ["Range rebalance"],
                        "sourceUrls": ["https://example.test/paper"]
                    }
                ]
            }))
            strategy_feed.write_text(json.dumps({
                "blockedDirectives": [
                    {"strategyId": "ict-displacement"},
                    {"strategyId": "liquidity-reversion"}
                ]
            }))
            strategy_zoo.write_text(json.dumps({
                "items": [
                    {
                        "strategyId": "ict-displacement",
                        "classification": "QUARANTINED",
                        "phase": "quarantine",
                        "executable": False
                    },
                    {
                        "strategyId": "wq-trend-mom",
                        "classification": "BRONZE",
                        "phase": "candidate-retest",
                        "executable": False
                    },
                    {
                        "strategyId": "liquidity-reversion",
                        "classification": "QUARANTINED",
                        "phase": "quarantine",
                        "executable": False
                    }
                ]
            }))
            futures_no_edge.write_text(json.dumps({"entries": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            backtrader_research.write_text(json.dumps({"results": []}))
            youtube_source_cards.write_text("\n".join([
                "# YouTube Transcript Source Cards - 2026-05-30",
                "",
                "- Researcher run: `run-yt-cards`",
                "- Result: `3/3` queued YouTube targets succeeded, `3` raw transcript chunks kept, `0` strategy hypotheses promoted.",
                "",
                "| Source | Decision | Lane | Tradable Variable | One-Variable Test |",
                "|---|---|---|---|---|",
                "| [FaberVaale opening range improvement](https://youtu.be/wm6XQFw1GHI) | `candidate` | `futures` | ORB sizing | Freeze entry; change sizing only. |",
                "| [PEAD](https://youtu.be/EP4ptjamPYA) | `candidate-with-caution` | `futures-overlay/equities-research` | earnings breadth | Add PEAD flag on/off. |",
                "| [NeuroTrader](https://youtu.be/9Y79o6Wby0w) | `research-only` | `background` | none | Do not implement. |",
            ]))

            report = build_report(argparse.Namespace(
                hypotheses=str(hypotheses),
                strategy_feed=str(strategy_feed),
                strategy_zoo=str(strategy_zoo),
                futures_no_edge=str(futures_no_edge),
                prediction_no_edge=str(prediction_no_edge),
                backtrader_research=str(backtrader_research),
                youtube_source_cards=str(youtube_source_cards),
            ))

        by_id = {item["id"]: item for item in report["items"]}
        self.assertTrue(report["researchOnly"])
        self.assertFalse(report["writesOrders"])
        self.assertFalse(report["readyForExecution"])
        self.assertEqual(report["decision"], "research-only; no seed is executable without local OOS/promotion evidence")
        self.assertEqual(report["totalSeeds"], report["summary"]["totalSeeds"])
        self.assertEqual(report["queuedYT"], report["summary"]["queuedYouTubeSeeds"])
        self.assertEqual(report["candidateRetest"], report["summary"]["candidateRetestSeeds"])
        self.assertEqual(report["quarantinedNoEdge"], report["summary"]["quarantinedNoEdgeSeeds"])
        self.assertEqual(report["executable"], 0)
        self.assertEqual(report["summary"]["executableSeeds"], 0)
        self.assertTrue(report["queuedYouTubeSourceCards"]["present"])
        self.assertEqual(report["queuedYouTubeSourceCards"]["researcherRun"], "run-yt-cards")
        self.assertEqual(report["queuedYouTubeSourceCards"]["targetsSucceeded"], 3)
        self.assertEqual(report["queuedYouTubeSourceCards"]["strategyHypothesesPromoted"], 0)
        self.assertFalse(report["queuedYouTubeSourceCards"]["executionRelevant"])
        self.assertEqual(by_id["fvg-1"]["decision"], "quarantine-no-edge")
        self.assertEqual(by_id["trend-1"]["decision"], "candidate-retest-research-only")
        self.assertEqual(by_id["trend-1"]["localExecutable"], False)
        self.assertEqual(by_id["bb-1"]["decision"], "research-only-unmapped-seed")
        self.assertEqual(by_id["vp-1"]["inferredStrategyId"], "auction-profile-unmapped")
        self.assertEqual(by_id["liq-1"]["decision"], "quarantine-no-edge")
        self.assertEqual(by_id["liq-1"]["inferredStrategyId"], "liquidity-reversion")
        self.assertIn("external-backtest-claim", by_id["fvg-1"]["sourceKinds"])

    def test_duplicate_source_ids_get_stable_unique_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            hypotheses = tmp_path / "hypotheses.json"
            strategy_feed = tmp_path / "feed.json"
            strategy_zoo = tmp_path / "zoo.json"
            futures_no_edge = tmp_path / "futures-no-edge.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            backtrader_research = tmp_path / "backtrader.json"

            hypotheses.write_text(json.dumps({
                "hypotheses": [
                    {
                        "id": "yt-seed",
                        "title": "Trend momentum seed A",
                        "market": "futures",
                        "symbols": ["NQ"],
                        "timeframes": ["30m"],
                        "entryRules": ["Trend up"],
                        "stopRules": ["ATR stop"],
                        "targetRules": ["Fixed target"],
                    },
                    {
                        "id": "yt-seed",
                        "title": "Trend momentum seed B",
                        "market": "futures",
                        "symbols": ["NQ"],
                        "timeframes": ["30m"],
                        "entryRules": ["Trend up"],
                        "stopRules": ["ATR stop"],
                        "targetRules": ["Fixed target"],
                    },
                ]
            }))
            strategy_feed.write_text(json.dumps({"blockedDirectives": []}))
            strategy_zoo.write_text(json.dumps({
                "items": [
                    {
                        "strategyId": "wq-trend-mom",
                        "classification": "BRONZE",
                        "phase": "candidate-retest",
                        "executable": False,
                    }
                ]
            }))
            futures_no_edge.write_text(json.dumps({"entries": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            backtrader_research.write_text(json.dumps({"results": []}))

            report = build_report(argparse.Namespace(
                hypotheses=str(hypotheses),
                strategy_feed=str(strategy_feed),
                strategy_zoo=str(strategy_zoo),
                futures_no_edge=str(futures_no_edge),
                prediction_no_edge=str(prediction_no_edge),
                backtrader_research=str(backtrader_research),
            ))

        ids = [item["id"] for item in report["items"]]
        source_ids = [item["sourceId"] for item in report["items"]]
        self.assertEqual(ids, ["yt-seed", "yt-seed#2"])
        self.assertEqual(source_ids, ["yt-seed", "yt-seed"])
        self.assertEqual(report["summary"]["duplicateSourceIds"], 1)

    def test_local_backtrader_rejection_removes_candidate_from_next_build_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            hypotheses = tmp_path / "hypotheses.json"
            strategy_feed = tmp_path / "feed.json"
            strategy_zoo = tmp_path / "zoo.json"
            futures_no_edge = tmp_path / "futures-no-edge.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            backtrader_research = tmp_path / "backtrader.json"

            hypotheses.write_text(json.dumps({
                "hypotheses": [
                    {
                        "id": "trend-1",
                        "title": "Trend momentum with volatility filter",
                        "market": "futures",
                        "symbols": ["NQ"],
                        "timeframes": ["30m"],
                        "entryRules": ["Trend up and momentum positive"],
                        "stopRules": ["ATR stop"],
                        "targetRules": ["Fixed target"],
                    }
                ]
            }))
            strategy_feed.write_text(json.dumps({"blockedDirectives": []}))
            strategy_zoo.write_text(json.dumps({
                "items": [
                    {
                        "strategyId": "wq-trend-mom",
                        "classification": "BRONZE",
                        "phase": "candidate-retest",
                        "executable": False,
                    }
                ]
            }))
            futures_no_edge.write_text(json.dumps({"entries": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            backtrader_research.write_text(json.dumps({
                "results": [
                    {"strategy": "wq-trend-mom-30m", "totalR": -1.5, "avgR": -0.02},
                    {"strategy": "wq-trend-mom-30m", "totalR": -3.0, "avgR": -0.04},
                    {"strategy": "wq-vol-regime-60m", "totalR": 10.0, "avgR": 0.1},
                ]
            }))

            report = build_report(argparse.Namespace(
                hypotheses=str(hypotheses),
                strategy_feed=str(strategy_feed),
                strategy_zoo=str(strategy_zoo),
                futures_no_edge=str(futures_no_edge),
                prediction_no_edge=str(prediction_no_edge),
                backtrader_research=str(backtrader_research),
            ))

        by_id = {item["id"]: item for item in report["items"]}
        self.assertEqual(by_id["trend-1"]["decision"], "quarantine-no-edge")
        self.assertIn("local Backtrader replay rejected current form", by_id["trend-1"]["blockers"][0])
        self.assertEqual(report["nextBuildQueue"], [])
        self.assertEqual(report["summary"]["candidateRetestSeeds"], 0)
        self.assertEqual(report["summary"]["localBacktraderRejectedFamilies"], 1)
        self.assertEqual(report["localBacktraderRejections"]["wq-trend-mom"]["bestTotalR"], -1.5)

    def test_youtube_queue_is_added_as_research_only_unextracted_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            hypotheses = tmp_path / "hypotheses.json"
            strategy_feed = tmp_path / "feed.json"
            strategy_zoo = tmp_path / "zoo.json"
            futures_no_edge = tmp_path / "futures-no-edge.json"
            prediction_no_edge = tmp_path / "prediction-no-edge.json"
            backtrader_research = tmp_path / "backtrader.json"
            researcher_latest_run = tmp_path / "latest-run.json"
            youtube_queue = tmp_path / "youtube-queue.md"
            youtube_source_cards = tmp_path / "youtube-source-cards.md"

            hypotheses.write_text(json.dumps({"hypotheses": []}))
            strategy_feed.write_text(json.dumps({"blockedDirectives": []}))
            strategy_zoo.write_text(json.dumps({"items": []}))
            futures_no_edge.write_text(json.dumps({"entries": []}))
            prediction_no_edge.write_text(json.dumps({"entries": []}))
            backtrader_research.write_text(json.dumps({"results": []}))
            researcher_latest_run.write_text(json.dumps({
                "runId": "run-test",
                "status": "degraded",
                "strategyHypothesesCount": 0,
                "chunksCollected": 0,
                "transcriptArtifactsDeleted": 2,
                "blockers": ["Selected researcher targets yielded no novel chunks in the latest run."],
                "targetResults": [
                    {"targetId": "youtube-queue-pead", "videosProcessed": 1, "collected": 0, "kept": 0},
                    {"targetId": "youtube-queue-faber", "videosProcessed": 1, "collected": 0, "kept": 0},
                    {"targetId": "other-target", "videosProcessed": 1, "collected": 1, "kept": 1},
                ],
            }))
            youtube_queue.write_text("\n".join([
                "# YouTube Channel Queue",
                "",
                "## @matfinog - quant strategies",
                "- [The strategy that keeps MAKING BILLIONS to INSTITUTIONAL traders: PEAD.](https://youtu.be/EP4ptjamPYA) - 26.0min",
                "- [How to IMPROVE FaberVaale Strategy](https://youtu.be/wm6XQFw1GHI) - 20.0min",
            ]))
            youtube_source_cards.write_text("\n".join([
                "# YouTube Transcript Source Cards - 2026-05-30",
                "",
                "- Researcher run: `run-queued-source-cards`",
                "- Result: `2/2` queued YouTube targets succeeded, `2` raw transcript chunks kept, `0` strategy hypotheses promoted.",
                "",
                "| Source | Decision | Lane | Tradable Variable | One-Variable Test |",
                "|---|---|---|---|---|",
                "| [FaberVaale](https://youtu.be/wm6XQFw1GHI) | `candidate` | `futures` | ORB sizing | Change position sizing only. |",
                "| [PEAD](https://youtu.be/EP4ptjamPYA) | `candidate-with-caution` | `futures-overlay/equities-research` | PEAD breadth | Add PEAD flag only. |",
            ]))

            report = build_report(argparse.Namespace(
                hypotheses=str(hypotheses),
                strategy_feed=str(strategy_feed),
                strategy_zoo=str(strategy_zoo),
                futures_no_edge=str(futures_no_edge),
                prediction_no_edge=str(prediction_no_edge),
                backtrader_research=str(backtrader_research),
                youtube_queue=str(youtube_queue),
                researcher_latest_run=str(researcher_latest_run),
                youtube_source_cards=str(youtube_source_cards),
            ))

        self.assertEqual(report["summary"]["queuedYouTubeSeeds"], 2)
        self.assertEqual(report["summary"]["youtubeSeeds"], 2)
        self.assertEqual(report["summary"]["machineTestableSeeds"], 0)
        self.assertEqual(report["summary"]["executableSeeds"], 0)
        self.assertEqual(len(report["queuedYouTubeResearcherTargets"]), 2)
        self.assertEqual(report["queuedYouTubeResearcherTargets"][0]["kind"], "youtube-transcript")
        self.assertEqual(report["queuedYouTubeResearcherTargets"][0]["videos"], ["https://youtu.be/EP4ptjamPYA"])
        self.assertTrue(report["queuedYouTubeLatestRun"]["present"])
        self.assertEqual(report["queuedYouTubeLatestRun"]["runId"], "run-test")
        self.assertEqual(report["queuedYouTubeLatestRun"]["targetsAttempted"], 2)
        self.assertEqual(report["queuedYouTubeLatestRun"]["strategyHypothesesCount"], 0)
        self.assertTrue(report["queuedYouTubeSourceCards"]["present"])
        self.assertEqual(report["queuedYouTubeSourceCards"]["targetsAttempted"], 2)
        self.assertEqual(report["queuedYouTubeSourceCards"]["rawTranscriptChunksKept"], 2)
        self.assertEqual(len(report["queuedYouTubeSourceCards"]["cards"]), 2)
        self.assertFalse(report["readyForExecution"])
        self.assertTrue(all(item["sourceId"].startswith("youtube-queue-") for item in report["items"]))
        self.assertTrue(all(item["decision"] == "research-only-narrative-seed" for item in report["items"]))
        markdown = render_markdown(report)
        self.assertIn("# Research Seed Triage - ", markdown)
        self.assertNotIn("# Research Seed Triage - 2026-05-30", markdown)
        self.assertIn("Queued YouTube Seeds", markdown)
        self.assertIn("Queued YouTube Researcher Targets", markdown)
        self.assertIn("Queued YouTube Latest Researcher Run", markdown)
        self.assertIn("Queued YouTube Source Cards", markdown)
        self.assertIn("run-test", markdown)
        self.assertIn("run-queued-source-cards", markdown)
        self.assertIn("PEAD", markdown)
        self.assertIn("FaberVaale", markdown)

    def test_queued_youtube_targets_skip_items_without_urls(self):
        targets = queued_youtube_targets([
            {"id": "ok", "sourceOrigin": "youtube-queue", "title": "A", "sourceUrls": ["https://youtu.be/abc"]},
            {"id": "missing-url", "sourceOrigin": "youtube-queue", "title": "B", "sourceUrls": []},
            {"id": "other", "sourceOrigin": "manual", "title": "C", "sourceUrls": ["https://youtu.be/def"]},
        ])

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["id"], "ok")
        self.assertEqual(targets[0]["videos"], ["https://youtu.be/abc"])
        self.assertIn("youtube-queue", targets[0]["tags"])

    def test_queued_youtube_latest_run_summary_ignores_non_queue_runs(self):
        self.assertEqual(queued_youtube_latest_run_summary({}), {"present": False})
        self.assertEqual(
            queued_youtube_latest_run_summary({"targetResults": [{"targetId": "yt-quant-strategy"}]}),
            {"present": False},
        )

    def test_queued_youtube_latest_run_summary_surfaces_failures(self):
        summary = queued_youtube_latest_run_summary({
            "runId": "run-1",
            "status": "degraded",
            "strategyHypothesesCount": 0,
            "chunksCollected": 0,
            "transcriptArtifactsDeleted": 1,
            "blockers": ["no novel chunks"],
            "targetResults": [
                {"targetId": "youtube-queue-a", "videosProcessed": 1, "collected": 0, "kept": 0},
                {"targetId": "youtube-queue-b", "videosProcessed": 0, "collected": 0, "kept": 0, "error": "no transcript"},
            ],
        })

        self.assertTrue(summary["present"])
        self.assertEqual(summary["targetsAttempted"], 2)
        self.assertEqual(summary["targetsSucceeded"], 1)
        self.assertEqual(summary["failedTargetIds"], ["youtube-queue-b"])
        self.assertEqual(summary["strategyHypothesesCount"], 0)

    def test_parse_youtube_source_cards_absent_or_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            missing = parse_youtube_source_cards(tmp_path / "missing.md")
            self.assertFalse(missing["present"])

            cards = tmp_path / "cards.md"
            cards.write_text("\n".join([
                "# YouTube Transcript Source Cards - 2026-05-30",
                "- Researcher run: `run-card-test`",
                "- Result: `1/1` queued YouTube targets succeeded, `1` raw transcript chunks kept, `0` strategy hypotheses promoted.",
                "| Source | Decision | Lane | Tradable Variable | One-Variable Test |",
                "|---|---|---|---|---|",
                "| [A](https://youtu.be/a) | `candidate` | `futures` | NQ ORB | Change sizing only. |",
            ]))

            parsed = parse_youtube_source_cards(cards)

        self.assertTrue(parsed["present"])
        self.assertEqual(parsed["researcherRun"], "run-card-test")
        self.assertEqual(parsed["targetsSucceeded"], 1)
        self.assertEqual(parsed["strategyHypothesesPromoted"], 0)
        self.assertFalse(parsed["executionRelevant"])
        self.assertEqual(parsed["cards"][0]["title"], "A")


if __name__ == "__main__":
    unittest.main()
