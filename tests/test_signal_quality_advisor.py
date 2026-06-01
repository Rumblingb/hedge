import unittest
import os
import tempfile
from pathlib import Path

from scripts import signal_quality_advisor as advisor
from scripts.signal_quality_advisor import (
    direction_value,
    extract_signals,
    microstructure_health_score,
    payload_timestamp_age_seconds,
    shadow_data_age_seconds,
    shadow_signal_integrity,
    sizing_score,
    source_summary,
)


class SignalQualityAdvisorTests(unittest.TestCase):
    def test_shadow_no_data_is_blocker(self):
        score, blockers, warnings, rows = shadow_signal_integrity({
            "whale_flow": {
                "method": "fallback_no_data",
                "evidence_level": "no_live_data_shadow_only",
                "execution_role": "diagnostic_only",
                "promoted_for_execution": False,
                "tradable_signal": False,
                "direction": "neutral",
                "confidence": 0,
                "components": {
                    "options_unusual": {"status": "no_data"},
                },
            }
        })

        self.assertLess(score, 10)
        self.assertIn("shadow no-data/fallback input: whale_flow", blockers)
        self.assertFalse(warnings)
        self.assertTrue(rows[0]["noData"])
        self.assertTrue(rows[0]["shadowOnly"])

    def test_promoted_shadow_input_is_blocker(self):
        _, blockers, _, _ = shadow_signal_integrity({
            "dom_proxy": {
                "method": "OHLCV_DOM_proxy",
                "evidence_level": "proxy_shadow_only",
                "execution_role": "diagnostic_only",
                "promoted_for_execution": True,
                "tradable_signal": False,
                "direction": "neutral",
                "confidence": 0,
            }
        })

        self.assertIn("shadow input promoted for execution: dom_proxy", blockers)

    def test_directional_shadow_input_is_warning_not_confirmation(self):
        _, blockers, warnings, _ = shadow_signal_integrity({
            "kalman_pairs": {
                "method": "kalman",
                "evidence_level": "research_shadow_only",
                "execution_role": "diagnostic_only",
                "promoted_for_execution": False,
                "tradable_signal": False,
                "direction": "long",
                "confidence": 0.8,
            }
        })

        self.assertFalse(blockers)
        self.assertIn("directional shadow input is research-only: kalman_pairs", warnings)

    def test_proxy_shadow_input_is_warned_even_when_neutral(self):
        _, blockers, warnings, rows = shadow_signal_integrity({
            "dom_proxy": {
                "method": "OHLCV_DOM_proxy",
                "evidence_level": "proxy_shadow_only",
                "execution_role": "diagnostic_only",
                "promoted_for_execution": False,
                "tradable_signal": False,
                "direction": "neutral",
                "confidence": 0,
            }
        })

        self.assertFalse(blockers)
        self.assertIn("proxy shadow input cannot confirm execution: dom_proxy", warnings)
        self.assertTrue(rows[0]["proxyOnly"])

    def test_fresh_shadow_payload_with_stale_underlying_bar_is_warned(self):
        now = advisor.datetime(2026, 5, 31, 2, 0, tzinfo=advisor.timezone.utc).timestamp()
        payload = {
            "timestamp": "2026-05-31T01:59:00+00:00",
            "last_bar_time": "2026-05-29 20:45:00+00:00",
            "method": "OHLCV_DOM_proxy",
            "evidence_level": "proxy_shadow_only",
            "execution_role": "diagnostic_only",
            "promoted_for_execution": False,
            "tradable_signal": False,
            "direction": "neutral",
            "confidence": 0,
        }

        self.assertGreater(shadow_data_age_seconds(payload, now=now), advisor.MAX_FRESH_AGE_S)

        original_time = advisor.time.time
        try:
            advisor.time.time = lambda: now
            _, blockers, warnings, rows = shadow_signal_integrity({"dom_proxy": payload})
        finally:
            advisor.time.time = original_time

        self.assertFalse(blockers)
        self.assertIn("shadow input refreshed from stale source data: dom_proxy", warnings)
        self.assertTrue(rows[0]["refreshedFromStaleSourceData"])
        self.assertEqual(rows[0]["payloadAgeSeconds"], 60)
        self.assertEqual(rows[0]["dataTimestamp"], "2026-05-29T20:45:00+00:00")

    def test_explicit_source_data_stale_flag_is_warned_without_timestamp(self):
        payload = {
            "timestamp": "2026-05-31T01:59:00+00:00",
            "method": "performance_scores",
            "evidence_level": "research_shadow_only",
            "execution_role": "diagnostic_only",
            "promoted_for_execution": False,
            "tradable_signal": False,
            "direction": "neutral",
            "confidence": 0,
            "source_data_stale": True,
            "stale_threshold_seconds": 7200,
        }

        _, blockers, warnings, rows = shadow_signal_integrity({"rolling_window": payload})

        self.assertFalse(blockers)
        self.assertIn("shadow input refreshed from stale source data: rolling_window", warnings)
        self.assertTrue(rows[0]["sourceDataStale"])
        self.assertTrue(rows[0]["refreshedFromStaleSourceData"])
        self.assertEqual(rows[0]["staleThresholdSeconds"], 7200)

    def test_disconnected_shadow_components_are_warned(self):
        _, blockers, warnings, rows = shadow_signal_integrity({
            "whale_flow": {
                "method": "cftc_tff_cot_weekly",
                "evidence_level": "weekly_cot_shadow_only",
                "execution_role": "diagnostic_only",
                "promoted_for_execution": False,
                "tradable_signal": False,
                "direction": "bearish",
                "confidence": 0.2,
                "components": {
                    "cftc_tff_cot": {"status": "ok"},
                    "options_unusual": {"status": "not_connected"},
                    "institutional_13f": {"status": "not_connected"},
                },
            }
        })

        self.assertFalse(blockers)
        self.assertIn("shadow input has disconnected components: whale_flow (options_unusual, institutional_13f)", warnings)
        self.assertEqual(rows[0]["disconnectedComponents"], ["options_unusual", "institutional_13f"])

    def test_brain_state_prefers_repo_brain_before_home_brain(self):
        original_repo_brain = advisor.REPO_BRAIN
        original_home_brain = advisor.HOME_BRAIN
        original_repo_state = advisor.REPO_STATE
        original_home_state = advisor.HOME_STATE
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                advisor.REPO_BRAIN = root / "repo-brain"
                advisor.HOME_BRAIN = root / "home-brain"
                advisor.REPO_STATE = root / "repo-state"
                advisor.HOME_STATE = root / "home-state"
                advisor.REPO_BRAIN.mkdir()
                advisor.HOME_BRAIN.mkdir()
                (advisor.REPO_BRAIN / "brain-state.latest.json").write_text('{"source":"repo"}')
                (advisor.HOME_BRAIN / "brain-state.latest.json").write_text('{"source":"home"}')

                data, path, _ = advisor.read_json("brain-state.latest.json")

            self.assertEqual(data["source"], "repo")
            self.assertIn("repo-brain", str(path))
        finally:
            advisor.REPO_BRAIN = original_repo_brain
            advisor.HOME_BRAIN = original_home_brain
            advisor.REPO_STATE = original_repo_state
            advisor.HOME_STATE = original_home_state

    def test_read_json_uses_fresh_home_fallback_when_repo_state_is_stale(self):
        original_repo_state = advisor.REPO_STATE
        original_home_state = advisor.HOME_STATE
        original_max_age = advisor.MAX_FRESH_AGE_S
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                advisor.REPO_STATE = root / "repo-state"
                advisor.HOME_STATE = root / "home-state"
                advisor.MAX_FRESH_AGE_S = 10
                advisor.REPO_STATE.mkdir()
                advisor.HOME_STATE.mkdir()
                (advisor.REPO_STATE / "arbitration.latest.json").write_text('{"source":"repo-stale"}')
                (advisor.HOME_STATE / "arbitration.latest.json").write_text('{"source":"home-fresh"}')
                stale_time = advisor.time.time() - 100
                os.utime(advisor.REPO_STATE / "arbitration.latest.json", (stale_time, stale_time))

                data, path, age = advisor.read_json("arbitration.latest.json")

            self.assertEqual(data["source"], "home-fresh")
            self.assertIn("home-state", str(path))
            self.assertIsInstance(age, int)
        finally:
            advisor.REPO_STATE = original_repo_state
            advisor.HOME_STATE = original_home_state
            advisor.MAX_FRESH_AGE_S = original_max_age

    def test_source_summary_prefers_payload_timestamp_over_file_mtime(self):
        now = advisor.datetime(2026, 5, 31, 2, 0, tzinfo=advisor.timezone.utc).timestamp()
        payload = {"timestamp": "2026-05-29T19:59:00+00:00"}

        self.assertEqual(payload_timestamp_age_seconds(payload, now=now), 108060)

        original_max_age = advisor.MAX_FRESH_AGE_S
        try:
            advisor.MAX_FRESH_AGE_S = 7200
            summary = source_summary(payload, Path("/tmp/microstructure-filter.latest.json"), 5)
        finally:
            advisor.MAX_FRESH_AGE_S = original_max_age

        self.assertEqual(summary["fileAgeSeconds"], 5)
        self.assertIsNotNone(summary["payloadAgeSeconds"])
        self.assertEqual(summary["ageSeconds"], summary["payloadAgeSeconds"])
        self.assertFalse(summary["fresh"])

    def test_microstructure_stale_bar_during_weekend_closure_is_advisory_fresh(self):
        now = advisor.datetime(2026, 5, 31, 2, 0, tzinfo=advisor.timezone.utc).timestamp()
        payload = {"timestamp": "2026-05-29T19:59:00+00:00"}

        original_max_age = advisor.MAX_FRESH_AGE_S
        try:
            advisor.MAX_FRESH_AGE_S = 7200
            with self.subTest("generic source remains stale"):
                generic = source_summary(payload, Path("/tmp/generic.latest.json"), 5)
            with self.subTest("microstructure source is expected-market-closed"):
                micro = source_summary(payload, Path("/tmp/microstructure-filter.latest.json"), 5, label="microstructure")
        finally:
            advisor.MAX_FRESH_AGE_S = original_max_age

        self.assertFalse(generic["fresh"])
        self.assertTrue(micro["fresh"])
        self.assertFalse(micro["payloadFresh"])
        self.assertEqual(micro["staleReason"], "market-closed-no-new-regular-session")
        self.assertEqual(micro["sessionContext"]["currentSessionDay"], "2026-05-29")
        self.assertEqual(micro["sessionContext"]["nextRegularOpen"], "2026-06-01T13:30:00+00:00")

    def test_extract_signals_reads_nested_details_and_numeric_direction(self):
        rows = {row["name"]: row for row in extract_signals({
            "multitf_confirmation": {
                "direction": 1,
                "confidence": 0.42,
                "details": {"confirmation": "bullish"},
            },
            "microstructure": {
                "confidence": 0.95,
                "details": {"filter_verdict": "TIGHT"},
            },
            "vol_regime_gate": {
                "details": {"regime": "LOW", "confidence_multiplier": 0.67},
            },
        })}

        self.assertEqual(direction_value(1), 1.0)
        self.assertEqual(direction_value("-1"), -1.0)
        self.assertEqual(rows["multitf_confirmation"]["direction"], 1.0)
        self.assertEqual(rows["multitf_confirmation"]["raw"], "bullish")
        self.assertEqual(rows["microstructure"]["raw"], "tight")
        self.assertEqual(rows["microstructure"]["confidence"], 0.95)
        self.assertEqual(rows["vol_regime_gate"]["raw"], "LOW")
        self.assertEqual(rows["vol_regime_gate"]["confidence"], 0.67)
        self.assertEqual(microstructure_health_score(list(rows.values())), 8.0)

    def test_sizing_score_reads_nested_recommended_contracts(self):
        score, notes = sizing_score({"details": {"recommended_contracts": 2.25}})

        self.assertEqual(score, 2.0)
        self.assertIn("recommended size 2.25 exceeds 1-contract research/demo envelope", notes)

    def test_report_carries_hard_safety_metadata(self):
        report = advisor.build_report()

        self.assertTrue(report["researchOnly"])
        self.assertFalse(report["writesOrders"])
        self.assertFalse(report["touchesBroker"])
        self.assertFalse(report["movesFunds"])
        self.assertFalse(report["readyForExecution"])
        self.assertIn("staleShadowSourceRows", report)


if __name__ == "__main__":
    unittest.main()
