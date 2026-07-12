from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import trading_day_cycle


def test_replace_managed_block_is_idempotent():
    first = trading_day_cycle.replace_managed_block("# Plan\n", f"{trading_day_cycle.MANAGED_START}\none\n{trading_day_cycle.MANAGED_END}")
    second = trading_day_cycle.replace_managed_block(first, f"{trading_day_cycle.MANAGED_START}\ntwo\n{trading_day_cycle.MANAGED_END}")
    assert second.count(trading_day_cycle.MANAGED_START) == 1
    assert "two" in second
    assert "one" not in second


def test_remove_legacy_canary_block_preserves_following_sections():
    text = "# Plan\n\n## Founder-Approved ProjectX Demo Canary\nold $100 rule\n\n## Gate State\ncurrent\n"
    result = trading_day_cycle.remove_legacy_canary_block(text)
    assert "old $100 rule" not in result
    assert "## Gate State\ncurrent" in result


def test_daily_controls_label_sub_48k_testbed_as_practice_only():
    with TemporaryDirectory() as raw:
        old_hermes = trading_day_cycle.HERMES
        try:
            trading_day_cycle.HERMES = Path(raw)
            path = trading_day_cycle.write_daily_controls([], {"lane": {"balance": 47482.94}})
            text = path.read_text()
            assert "PRACTICE_ONLY_OR_RESET_REQUIRED" in text
            assert "BILL_CHALLENGE_PROFILE: APPROVED" in text
            assert "BILL_ROUTE_APPROVAL: APPROVED" in text
        finally:
            trading_day_cycle.HERMES = old_hermes
