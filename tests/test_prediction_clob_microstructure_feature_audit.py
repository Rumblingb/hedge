import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from scripts.prediction_clob_microstructure_feature_audit import build_report


class PredictionClobMicrostructureFeatureAuditTests(unittest.TestCase):
    def test_audit_is_research_only_and_identifies_ready_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "clob.jsonl"
            rows = []
            for idx in range(260):
                rows.append({
                    "eventType": "best_bid_ask",
                    "assetId": "asset-a",
                    "localTs": f"2026-05-30T00:00:{idx % 60:02d}.000Z",
                    "bestBid": 0.49,
                    "bestAsk": 0.51,
                })
            for idx in range(260):
                rows.append({
                    "eventType": "price_change",
                    "assetId": "asset-a",
                    "localTs": f"2026-05-30T00:01:{idx % 60:02d}.000Z",
                    "priceChanges": [{"asset_id": "asset-a", "best_bid": "0.49", "best_ask": "0.51"}],
                })
            for idx in range(30):
                rows.append({
                    "eventType": "book",
                    "assetId": "asset-a",
                    "bids": [{"price": "0.49", "size": "10"}],
                    "asks": [{"price": "0.51", "size": "12"}],
                })
            jsonl.write_text("\n".join(__import__("json").dumps(row) for row in rows) + "\n")
            persistence = root / "persistence.json"
            persistence.write_text('{"quoteObservations":120,"assetsEligible":1,"decision":"research-data-ready-for-offline-feature-test"}')
            edge_gate = root / "edge.json"
            edge_gate.write_text('{"status":"REJECT_NO_EDGE","watchResearchGroups":0,"thresholds":{"minNetDrift":0.0025}}')
            no_edge_ledger = root / "no-edge.json"
            no_edge_ledger.write_text('{"entries":[]}')
            repo = root / "repo"
            measures = repo / "polydata" / "measures"
            measures.mkdir(parents=True)
            (measures / "depth.py").write_text("# depth")
            (measures / "spread.py").write_text("# spread")
            (measures / "latency.py").write_text("# latency")

            payload = build_report(Namespace(
                input=str(jsonl),
                persistence=str(persistence),
                edge_gate=str(edge_gate),
                no_edge_ledger=str(no_edge_ledger),
                repo=str(repo),
                max_rows=1000,
            ))

        self.assertTrue(payload["researchOnly"])
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["touchesBroker"])
        self.assertFalse(payload["readyForPaper"])
        self.assertEqual(payload["rejectedBaseline"]["status"], "REJECT_NO_EDGE")
        self.assertGreaterEqual(payload["readyFeatureCount"], 3)
        self.assertGreaterEqual(payload["rawDataReadyFeatureCount"], 3)
        self.assertEqual(payload["rejectedFixedFeatureCount"], 0)
        ids = {item["id"] for item in payload["featureCandidates"] if item["readyForOfflineResearch"]}
        self.assertIn("clob-depth-imbalance-persistence", ids)
        self.assertIn("clob-spread-compression-before-move", ids)

    def test_no_edge_ledger_removes_rejected_fixed_forms_from_ready_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "clob.jsonl"
            rows = []
            for idx in range(260):
                rows.append({
                    "eventType": "best_bid_ask",
                    "assetId": "asset-a",
                    "localTs": f"2026-05-30T00:00:{idx % 60:02d}.000Z",
                    "bestBid": 0.49,
                    "bestAsk": 0.51,
                })
                rows.append({
                    "eventType": "price_change",
                    "assetId": "asset-a",
                    "localTs": f"2026-05-30T00:01:{idx % 60:02d}.000Z",
                    "priceChanges": [{"asset_id": "asset-a", "best_bid": "0.49", "best_ask": "0.51"}],
                })
            for idx in range(30):
                rows.append({
                    "eventType": "book",
                    "assetId": "asset-a",
                    "bids": [{"price": "0.49", "size": "10"}],
                    "asks": [{"price": "0.51", "size": "12"}],
                })
            jsonl.write_text("\n".join(__import__("json").dumps(row) for row in rows) + "\n")
            persistence = root / "persistence.json"
            persistence.write_text('{"quoteObservations":120,"assetsEligible":1,"decision":"research-data-ready-for-offline-feature-test"}')
            edge_gate = root / "edge.json"
            edge_gate.write_text('{"status":"REJECT_NO_EDGE","watchResearchGroups":0,"thresholds":{"minNetDrift":0.0025}}')
            no_edge_ledger = root / "no-edge.json"
            no_edge_ledger.write_text(__import__("json").dumps({
                "count": 3,
                "noEdgeCount": 3,
                "promotableCount": 0,
                "entries": [
                    {"id": "polymarket-clob-depth-imbalance-current-form", "verdict": "no-edge", "currentFormRejected": True, "nextAction": "do not rerun depth"},
                    {"id": "polymarket-clob-quote-intensity-current-form", "verdict": "no-edge", "currentFormRejected": True, "nextAction": "do not rerun quote"},
                    {"id": "polymarket-clob-spread-compression-current-form", "verdict": "no-edge", "currentFormRejected": True, "nextAction": "do not rerun spread"},
                    {"id": "polymarket-clob-latency-staleness-current-form", "verdict": "no-edge", "currentFormRejected": True, "nextAction": "do not rerun latency"},
                ],
            }))
            repo = root / "repo"
            measures = repo / "polydata" / "measures"
            measures.mkdir(parents=True)
            (measures / "depth.py").write_text("# depth")
            (measures / "spread.py").write_text("# spread")
            (measures / "latency.py").write_text("# latency")

            payload = build_report(Namespace(
                input=str(jsonl),
                persistence=str(persistence),
                edge_gate=str(edge_gate),
                no_edge_ledger=str(no_edge_ledger),
                repo=str(repo),
                max_rows=1000,
            ))

        # 6 candidates now: 5 original + clob-resolved-label-resting-convergence. The test capture
        # (120 quote obs, no last-trade events) only makes the new offline familys raw-ready. The
        # test ledger rejects the 4 original forms it lists; the new family is a genuinely new
        # candidate (offline-tested vs resolved corpus), so it surfaces as ready for offline research
        # and the audit decision reflects a new-feature-audit rather than exhaustion.
        self.assertEqual(payload["rawDataReadyFeatureCount"], 5)
        self.assertEqual(payload["readyFeatureCount"], 1)
        self.assertEqual(payload["rejectedFixedFeatureCount"], 4)
        self.assertEqual(payload["decision"], "research-only-new-feature-audit")
        new_family = next(c for c in payload["featureCandidates"] if c["id"] == "clob-resolved-label-resting-convergence")
        self.assertTrue(new_family["readyForOfflineResearch"])
        self.assertFalse(new_family["currentFixedFormRejected"])
        for item in payload["featureCandidates"]:
            if item["id"] == "clob-resolved-label-resting-convergence":
                # Intentionally exempt: this is a genuinely NEW family (offline-tested vs resolved
                # corpus), not one of the 5 rejected fixed forms. It is raw-ready AND ready.
                continue
            if item["rawDataReady"]:
                self.assertFalse(item["readyForOfflineResearch"])
                self.assertTrue(item["currentFixedFormRejected"])


if __name__ == "__main__":
    unittest.main()
