from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import nq_orb_testbed_b_canary as canary
from scripts.nq_orb_testbed_b_canary import build_challenge_order, canary_window_open, signal_blockers


def test_canary_window_is_bounded_to_post_open_orb_period():
    assert canary_window_open(datetime(2026, 6, 24, 13, 48, tzinfo=timezone.utc))
    assert not canary_window_open(datetime(2026, 6, 24, 13, 47, tzinfo=timezone.utc))
    assert not canary_window_open(datetime(2026, 6, 24, 15, 31, tzinfo=timezone.utc))


def test_signal_guard_accepts_fresh_one_mnq_geometry():
    now = datetime(2026, 6, 24, 13, 50, tzinfo=timezone.utc)
    signal = {
        "ts": now.isoformat(),
        "tradable_signal": True,
        "promoted_for_execution": True,
        "side": "long",
        "entry": 30000,
        "stop": 29975,
        "target": 30050,
        "price_now": 30003,
        "rr": 2.0,
    }
    assert signal_blockers(signal, now, now) == []


def test_signal_guard_rejects_stale_or_chased_breakout():
    started = datetime(2026, 6, 24, 13, 50, tzinfo=timezone.utc)
    signal = {
        "ts": datetime(2026, 6, 24, 13, 49, tzinfo=timezone.utc).isoformat(),
        "tradable_signal": True,
        "promoted_for_execution": True,
        "side": "long",
        "entry": 30000,
        "stop": 29975,
        "target": 30050,
        "price_now": 30010,
        "rr": 2.0,
    }
    blockers = signal_blockers(signal, started, started)
    assert "ORB signal was not generated fresh by this canary run" in blockers
    assert any("moved too far" in blocker for blocker in blockers)


def test_challenge_overlay_sizes_below_1000_and_preserves_exact_1_5r():
    order, blockers = build_challenge_order({
        "side": "long",
        "entry": 30000.0,
        "stop": 29980.0,
    })
    assert blockers == []
    assert order["contracts"] == 25
    assert order["risk_usd"] == 1000.0
    assert order["target_usd"] == 1500.0
    assert order["rr"] == 1.5
    assert order["stop"] == 29980.0
    assert order["target"] == 30030.0


def test_challenge_overlay_blocks_when_50_micro_cap_cannot_use_90pct_budget():
    order, blockers = build_challenge_order({
        "side": "short",
        "entry": 30000.0,
        "stop": 30004.0,
    })
    assert order["contracts"] == 50
    assert order["risk_usd"] == 400.0
    assert any("required band" in blocker for blocker in blockers)


def test_news_gate_blocks_high_impact_window_and_allows_low_impact():
    now = datetime(2026, 6, 24, 14, 0, tzinfo=timezone.utc)
    with TemporaryDirectory() as raw:
        root = Path(raw)
        calendar_path = root / "calendar.json"
        fomc_path = root / "fomc.json"
        calendar_path.write_text(json.dumps({
            "status": "PASS",
            "generatedAt": now.isoformat(),
            "todayEvents": [
                {"ts": now.isoformat(), "headline": "CPI", "impact": "high"},
                {"ts": now.isoformat(), "headline": "Housing", "impact": "low"},
            ],
        }))
        fomc_path.write_text(json.dumps({"timestamp": now.isoformat(), "verdict": "PASS"}))
        old_calendar, old_fomc = canary.RED_FOLDER_STATUS, canary.FOMC_STATUS
        try:
            canary.RED_FOLDER_STATUS = calendar_path
            canary.FOMC_STATUS = fomc_path
            blockers = canary.news_blockers(now)
            assert any("CPI" in blocker for blocker in blockers)
            assert not any("Housing" in blocker for blocker in blockers)
        finally:
            canary.RED_FOLDER_STATUS, canary.FOMC_STATUS = old_calendar, old_fomc
