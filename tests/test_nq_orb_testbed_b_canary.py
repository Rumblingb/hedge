from datetime import datetime, timezone

from scripts.nq_orb_testbed_b_canary import canary_window_open, signal_blockers


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
