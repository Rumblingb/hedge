#!/usr/bin/env python3
"""Config-parity gate — execution must match evidence, or be a bounded experiment.

The systemic failure mode this closes (three instances found 2026-06-11): the
executed configuration drifting from the verified one (sessions traded without
evidence, exit geometry never backtested). Verdicts:

  verified    — strategy + session inside its blessed evidence map
  experiment  — outside evidence, but an active experiment budget covers it
                and its cumulative realized loss since started_ts is within budget
  exhausted   — covering experiment breached its loss budget
  unverified  — outside evidence, no covering experiment

Advisory by default: callers route regardless and the verdict is recorded.
Enforce with BILL_CONFIG_PARITY_ENFORCE=true → exhausted/unverified block.
Designed fail-open: any internal error yields verdict "gate-error" (never blocks).

State: .rumbling-hedge/state/config-parity.latest.json
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "hedge"
EVIDENCE_MAP = ROOT / "config/strategy-evidence-map.json"
BUDGETS = ROOT / "config/experiment-budgets.json"
JOURNAL = ROOT / ".rumbling-hedge/state/trade-journal.jsonl"
STATE_OUT = ROOT / ".rumbling-hedge/state/config-parity.latest.json"


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _norm_session(s):
    return str(s or "").strip().lower().replace("-", "_")


def _experiment_consumed_usd(exp):
    """Cumulative realized PnL for an experiment from the trade journal."""
    if not JOURNAL.exists():
        return 0.0
    started = str(exp.get("started_ts", ""))
    sessions = {_norm_session(x) for x in exp.get("sessions", [])}
    strategy = exp.get("strategy")
    total = 0.0
    for line in JOURNAL.read_text().splitlines():
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            continue
        if strategy and t.get("signal_source") not in (strategy, "unattributed"):
            continue
        if _norm_session(t.get("session")) not in sessions:
            continue
        if str(t.get("entry_ts", "")) < started:
            continue
        acct = exp.get("account_id")
        if acct and t.get("account_id") and t["account_id"] != acct:
            continue
        try:
            total += float(t.get("pnl_dollars", 0) or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def evaluate(strategy, session, exit_mode=None, write_state=True):
    """Return the parity verdict for routing `strategy` in `session` now.

    exit_mode (optional): "bracket" or "time" — how the caller will actually
    exit. Verified requires BOTH session and exit mode inside evidence.
    """
    enforce = os.environ.get("BILL_CONFIG_PARITY_ENFORCE", "").lower() == "true"
    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "strategy": strategy,
        "session": session,
        "exit_mode": exit_mode,
        "enforce_mode": enforce,
        "verdict": "unverified",
        "blocked": False,
        "reason": "",
    }
    try:
        smap = _read_json(EVIDENCE_MAP).get("strategies", {})
        entry = smap.get(strategy)
        sess = _norm_session(session)
        if entry is None:
            result["reason"] = f"no evidence map entry for '{strategy}'"
        else:
            session_ok = sess in {_norm_session(x) for x in entry.get("verified_sessions", [])}
            exit_ok = exit_mode is None or exit_mode == entry.get("exit_mode")
            if session_ok and exit_ok:
                result["verdict"] = "verified"
                result["edge_id"] = entry.get("edge_id")
                result["reason"] = f"session '{sess}' + exit inside blessed evidence ({entry.get('edge_id')})"
            elif not session_ok:
                result["reason"] = (f"session '{sess}' outside verified sessions "
                                    f"{entry.get('verified_sessions')} for {entry.get('edge_id')}")
            else:
                result["reason"] = (f"exit mode '{exit_mode}' does not match verified "
                                    f"exit mode '{entry.get('exit_mode')}' for {entry.get('edge_id')}")
        if result["verdict"] != "verified":
            for exp in _read_json(BUDGETS).get("experiments", []):
                if exp.get("status") != "active" or exp.get("strategy") != strategy:
                    continue
                if sess not in {_norm_session(x) for x in exp.get("sessions", [])}:
                    continue
                consumed = _experiment_consumed_usd(exp)
                budget = float(exp.get("budget_usd", 0) or 0)
                remaining = round(budget + min(consumed, 0.0), 2)
                result["experiment"] = {
                    "id": exp.get("id"),
                    "budget_usd": budget,
                    "consumed_usd": consumed,
                    "remaining_usd": remaining,
                }
                if remaining > 0:
                    result["verdict"] = "experiment"
                    result["reason"] += (f"; covered by experiment '{exp.get('id')}' "
                                         f"(${remaining:,.2f} of ${budget:,.2f} budget remaining)")
                else:
                    result["verdict"] = "exhausted"
                    result["reason"] += (f"; experiment '{exp.get('id')}' EXHAUSTED "
                                         f"(consumed ${consumed:,.2f} vs ${budget:,.2f} budget)")
                break
        result["blocked"] = enforce and result["verdict"] in ("unverified", "exhausted")
    except Exception as e:  # fail-open: a gate bug must never block routing
        result["verdict"] = "gate-error"
        result["blocked"] = False
        result["reason"] = f"gate error (fail-open): {e}"
    if write_state:
        try:
            STATE_OUT.write_text(json.dumps(result, indent=2) + "\n")
        except OSError:
            pass
    return result


if __name__ == "__main__":
    import sys
    strat = sys.argv[1] if len(sys.argv) > 1 else "orb-breakout"
    sess = sys.argv[2] if len(sys.argv) > 2 else "ny"
    emode = sys.argv[3] if len(sys.argv) > 3 else None
    print(json.dumps(evaluate(strat, sess, exit_mode=emode), indent=2))
