#!/usr/bin/env python3
"""
promote_edge.py — Operator tool. Promotes a blessed edge candidate to live execution.

Reads blessed-edges-candidates.json to verify the run qualifies.
Writes to signal-promotion-registry.json (persists across cron restarts).
Updates the current signal file immediately.

signal_arbitration.py checks the registry BEFORE the signal file, so the
registry is authoritative even if a cron overwrites promoted_for_execution.

Usage:
  python3 scripts/promote_edge.py --list
  python3 scripts/promote_edge.py --signal orb-signal --run run_it_orb_es15m
  python3 scripts/promote_edge.py --demote orb-signal
"""
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
CANDIDATES_FILE = STATE / "blessed-edges-candidates.json"
REGISTRY_FILE = STATE / "signal-promotion-registry.json"
AUDIT_FILE = STATE / "blessed-edges-audit.jsonl"

VALID_SIGNALS = {
    "pead-signal", "sr-proximity-signal", "donchian-signal", "ichimoku-signal",
    "insider-signal", "noise-analysis", "cot-signal", "vwap-signal",
    "heiken-ashi-signal", "fibonacci-signal", "kalman-pairs-signal",
    "whale-flow-signal", "orb-signal",
    "london-orb-signal", "asia-session-signal",
    "nq-quant-signal",
    "es-orb-signal",
    # NOTE: gc-volregime, gc-orbretest, nq-vwaptrend, gc-pjireversal are excluded.
    # They are HEURISTIC_STUB signal generators with false PF claims.
    # Only add them here after proper AI Scientist replication.
}

# Blessed-edges pipeline sources (read by bless_edges.py + promote_edge.py)
BLESSED_EDGE_SOURCES = [
    "ai-scientist-templates/financial_strategy/run_n4_vt1.6_postfix",
    "ai-scientist-templates/financial_strategy/run_p3b_pji",
    "ai-scientist-templates/financial_strategy/run_p3b_vol",
    "ai-scientist-templates/financial_strategy/run_gc_volregime_postfix",
    "ai-scientist-templates/financial_strategy/run_it_orb_es15m",
]


def load_registry():
    try:
        return json.loads(REGISTRY_FILE.read_text())
    except Exception:
        return {"promotions": [], "lastUpdated": None}


def save_registry(reg):
    reg["lastUpdated"] = datetime.now(timezone.utc).isoformat()
    REGISTRY_FILE.write_text(json.dumps(reg, indent=2, default=str))


def append_audit(entry):
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_FILE, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def update_signal_file(signal_name: str, promote: bool):
    """Update promoted_for_execution in the current signal file. Non-fatal."""
    state_dirs = [STATE, Path.home() / ".rumbling-hedge" / "state"]
    for state_dir in state_dirs:
        path = state_dir / f"{signal_name}.latest.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                data["promoted_for_execution"] = promote
                data["tradable_signal"] = promote
                data["promotedAt"] = datetime.now(timezone.utc).isoformat() if promote else None
                path.write_text(json.dumps(data, indent=2, default=str))
                print(f"  Updated: {path}")
            except Exception as e:
                print(f"  Warning: could not update {path}: {e}", file=sys.stderr)


def cmd_list(_args):
    reg = load_registry()
    promos = reg.get("promotions", [])
    active = [p for p in promos if p.get("active")]
    inactive = [p for p in promos if not p.get("active")]
    if not promos:
        print("No promotions in registry.")
        return
    if active:
        print(f"Active promotions ({len(active)}):")
        for p in active:
            print(f"  ACTIVE  {p['signal']:<25s} <- {p.get('run_id','?')}  "
                  f"PF={p.get('oos_profit_factor','?')}  "
                  f"promoted {p.get('promotedAt','?')[:10]}")
    if inactive:
        print(f"Inactive promotions ({len(inactive)}):")
        for p in inactive:
            print(f"  INACTIVE {p['signal']:<24s} <- {p.get('run_id','?')}  "
                  f"demoted {p.get('demotedAt','?')[:10]}")


def cmd_promote(args):
    signal = args.signal
    run_id = args.run

    if signal not in VALID_SIGNALS:
        print(f"ERROR: '{signal}' not a recognized signal name.")
        print("Valid signals: " + ", ".join(sorted(VALID_SIGNALS)))
        sys.exit(1)

    # Verify the run is a qualified candidate
    try:
        raw = json.loads(CANDIDATES_FILE.read_text())
    except FileNotFoundError:
        print("ERROR: blessed-edges-candidates.json not found. Run bless_edges.py first.")
        sys.exit(1)

    candidates = {c["run_id"]: c for c in raw.get("candidates", [])}

    if run_id not in candidates:
        rejected_map = {r["run_id"]: r for r in raw.get("rejected", [])}
        if run_id in rejected_map:
            r = rejected_map[run_id]
            print(f"ERROR: {run_id} was rejected by bless_edges.py.")
            print(f"  Blockers: {r.get('blockers', '?')}")
            print("  Fix the edge metrics and re-run bless_edges.py before promoting.")
        else:
            print(f"ERROR: {run_id} not found. Run bless_edges.py first.")
        sys.exit(1)

    candidate = candidates[run_id]

    print("\n=== PROMOTION REVIEW ===")
    print(f"  Signal:    {signal}")
    print(f"  Run:       {run_id}")
    print(f"  Strategy:  {candidate['strategy']} / {candidate['symbol']} / {candidate['timeframe']}")
    print(f"  OOS PF:    {candidate['oos_profit_factor']}")
    print(f"  WF share:  {candidate['walkforward_positive_fold_share']}")
    print(f"  OOS trades:{candidate['oos_trade_count']}")
    print(f"  OOS WR:    {candidate['oos_win_rate']}")
    print()
    print("This will set promoted_for_execution=True in signal_arbitration.py registry.")
    print("The signal will contribute weight to TRADE decisions immediately after this.")
    print()

    confirm = input("Type 'promote' to confirm, anything else to abort: ").strip()
    if confirm != "promote":
        print("Aborted.")
        sys.exit(0)

    reg = load_registry()
    promos = reg.get("promotions", [])

    # Remove any existing entry for this signal
    promos = [p for p in promos if p["signal"] != signal]

    entry = {
        "signal": signal,
        "run_id": run_id,
        "strategy": candidate["strategy"],
        "symbol": candidate["symbol"],
        "timeframe": candidate["timeframe"],
        "oos_profit_factor": candidate["oos_profit_factor"],
        "walkforward_positive_fold_share": candidate["walkforward_positive_fold_share"],
        "oos_trade_count": candidate["oos_trade_count"],
        "active": True,
        "promotedAt": datetime.now(timezone.utc).isoformat(),
        "promotedBy": "operator",
    }
    promos.append(entry)
    reg["promotions"] = promos
    save_registry(reg)

    update_signal_file(signal, promote=True)
    append_audit({**entry, "action": "promote", "ts": datetime.now(timezone.utc).isoformat()})

    print(f"\nDone. {signal} promoted from {run_id}.")
    print("Registry: " + str(REGISTRY_FILE))
    print("Note: arbitration reads registry before signal file — promotion persists across cron restarts.")


def cmd_demote(args):
    signal = args.demote
    reg = load_registry()
    promos = reg.get("promotions", [])
    entry = next((p for p in promos if p["signal"] == signal), None)
    if not entry:
        print(f"'{signal}' not found in registry.")
        return
    entry["active"] = False
    entry["demotedAt"] = datetime.now(timezone.utc).isoformat()
    reg["promotions"] = promos
    save_registry(reg)
    update_signal_file(signal, promote=False)
    append_audit({"signal": signal, "action": "demote", "ts": datetime.now(timezone.utc).isoformat()})
    print(f"Demoted: {signal}")


def main():
    parser = argparse.ArgumentParser(
        description="Promote or demote signals for live execution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--signal", help="Signal name to promote")
    parser.add_argument("--run", help="AI Scientist run ID backing the promotion")
    parser.add_argument("--list", action="store_true", help="List registry")
    parser.add_argument("--demote", metavar="SIGNAL", help="Deactivate a promoted signal")
    args = parser.parse_args()

    if args.list:
        cmd_list(args)
    elif args.demote:
        cmd_demote(args)
    elif args.signal and args.run:
        cmd_promote(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
