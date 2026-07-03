import argparse
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import topstep_readonly_bar_archive as archive


class TopstepReadonlyBarArchiveTests(unittest.TestCase):
    def test_append_symbol_archive_dedupes_and_counts_rth_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_dir = Path(tmp)
            bars = [
                {"t": "2026-06-02T13:31:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 10},
                {"t": "2026-06-02T13:31:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 10},
                {"t": "2026-06-03T13:31:00Z", "o": 101, "h": 102, "l": 100, "c": 101.5, "v": 11},
            ]

            first = archive.append_symbol_archive(
                archive_dir=archive_dir,
                symbol="NQ",
                contract_id="CON.F.US.ENQ.M26",
                bars=bars,
            )
            second = archive.append_symbol_archive(
                archive_dir=archive_dir,
                symbol="NQ",
                contract_id="CON.F.US.ENQ.M26",
                bars=bars,
            )

            self.assertEqual(first["rowCount"], 2)
            self.assertEqual(first["addedRows"], 2)
            self.assertEqual(first["rthSessionCount"], 2)
            self.assertEqual(second["rowCount"], 2)
            self.assertEqual(second["addedRows"], 0)
            with (archive_dir / "NQ-1m-topstep-readonly.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)

    def test_build_report_is_read_only_and_never_execution_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                search_text="NQ",
                lookback_minutes=240,
                limit=500,
                archive_dir=tmp,
                min_sessions=2,
                preferred_sessions=60,
                live=False,
                dry_run=False,
            )
            contracts = [
                {"id": "CON.F.US.ENQ.M26", "symbolId": "F.US.ENQ", "activeContract": True, "name": "NQM6"},
                {"id": "CON.F.US.MNQ.M26", "symbolId": "F.US.MNQ", "activeContract": True, "name": "MNQM6"},
            ]
            bars = [
                {"t": "2026-06-02T13:31:00Z", "o": 100, "h": 101, "l": 99, "c": 100.5, "v": 10},
                {"t": "2026-06-03T13:31:00Z", "o": 101, "h": 102, "l": 100, "c": 101.5, "v": 11},
            ]

            with patch.object(archive.topstep_md, "safety_blockers", return_value=[]), \
                patch.object(archive.topstep_md, "login", return_value="token"), \
                patch.object(archive.topstep_md, "search_contracts", return_value=contracts), \
                patch.object(archive.topstep_md, "retrieve_bars", return_value=bars):
                payload = archive.build_report(args)

        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["researchOnly"])
        self.assertTrue(payload["touchesBroker"])
        self.assertEqual(payload["brokerTouchMode"], "read-only-market-data")
        self.assertFalse(payload["writesOrders"])
        self.assertFalse(payload["placesOrders"])
        self.assertFalse(payload["modifiesOrders"])
        self.assertFalse(payload["cancelsOrders"])
        self.assertFalse(payload["readyForExecution"])
        self.assertFalse(payload["readyForDemoExpansion"])
        self.assertTrue(payload["brokerBarArchiveReadyForResearchDepth"])
        self.assertEqual(payload["nqArchiveRthSessionCount"], 2)

    def test_safety_blockers_prevent_broker_touch(self):
        args = argparse.Namespace(
            search_text="NQ",
            lookback_minutes=240,
            limit=500,
            archive_dir="/tmp/unused",
            min_sessions=20,
            preferred_sessions=60,
            live=False,
            dry_run=False,
        )
        with patch.object(archive.topstep_md, "safety_blockers", return_value=["read-only lock missing"]), \
            patch.object(archive.topstep_md, "login") as login:
            payload = archive.build_report(args)

        self.assertEqual(payload["status"], "BLOCKED_BY_SAFETY_ENV")
        self.assertFalse(payload["brokerBarArchiveReadyForResearchDepth"])
        login.assert_not_called()

    def _args(self):
        return argparse.Namespace(
            search_text="NQ",
            lookback_minutes=240,
            limit=500,
            archive_dir="/tmp/unused",
            min_sessions=20,
            preferred_sessions=60,
            live=False,
            dry_run=False,
        )

    def test_armed_demo_env_blockers_do_not_bypass_other_safety_blockers(self):
        blockers = [
            "RH_TOPSTEP_READ_ONLY must be true for market-data smoke",
            "kill switch is enabled; do not touch broker/API until operator reviews",
        ]
        with patch.object(archive.topstep_md, "safety_blockers", return_value=blockers), \
                patch.object(archive, "armed_demo_readonly_allowed", return_value=True), \
                patch.object(archive.topstep_md, "login") as login:
            payload = archive.build_report(self._args())

        self.assertEqual(payload["status"], "BLOCKED_BY_SAFETY_ENV")
        self.assertFalse(payload["armedDemoReadonlyOverride"])
        login.assert_not_called()

    def test_armed_demo_override_requires_daily_plan_tokens(self):
        env_blockers = [
            "RH_TOPSTEP_READ_ONLY must be true for market-data smoke",
            "BILL_ENABLE_FUTURES_DEMO_EXECUTION must be false",
        ]
        with patch.object(archive.topstep_md, "safety_blockers", return_value=env_blockers), \
                patch.object(archive, "armed_demo_readonly_allowed", return_value=False), \
                patch.object(archive.topstep_md, "login") as login:
            payload = archive.build_report(self._args())

        self.assertEqual(payload["status"], "BLOCKED_BY_SAFETY_ENV")
        self.assertFalse(payload["armedDemoReadonlyOverride"])
        login.assert_not_called()

    def test_armed_demo_readonly_allowed_fails_closed(self):
        # Live execution enabled -> never allowed, regardless of plan tokens.
        with patch.object(archive.topstep_md, "read_secure", return_value="true"):
            self.assertFalse(archive.armed_demo_readonly_allowed())

        # Session safety paused -> never allowed.
        with patch.object(archive.topstep_md, "read_secure", return_value=None), \
                patch.object(archive.topstep_md, "topstep_session_safety_paused", return_value=True):
            self.assertFalse(archive.armed_demo_readonly_allowed())

        # Missing daily plan -> never allowed.
        with patch.object(archive.topstep_md, "read_secure", return_value=None), \
                patch.object(archive.topstep_md, "topstep_session_safety_paused", return_value=False), \
                patch.object(archive, "DAILY_PLAN_DIR", Path("/tmp/does-not-exist-bill")):
            self.assertFalse(archive.armed_demo_readonly_allowed())

    def test_armed_demo_readonly_allowed_with_full_token_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp)
            import datetime as dt
            from zoneinfo import ZoneInfo
            stamp = dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo("Europe/London")).date().isoformat()
            (plan_dir / f"{stamp}-bill-trading-plan.md").write_text(
                "BILL_ROUTE_APPROVAL: APPROVED\n"
                "BROKER_RECONCILIATION: GREEN\n"
                "BILL_TOPSTEP_SINGLE_API_SESSION: APPROVED\n"
            )
            with patch.object(archive.topstep_md, "read_secure", return_value=None), \
                    patch.object(archive.topstep_md, "topstep_session_safety_paused", return_value=False), \
                    patch.object(archive, "DAILY_PLAN_DIR", plan_dir):
                self.assertTrue(archive.armed_demo_readonly_allowed())


if __name__ == "__main__":
    unittest.main()
