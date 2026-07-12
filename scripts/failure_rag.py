#!/usr/bin/env python3
"""
FAILURE RAG — Retrieval-Augmented Failure Detection
====================================================
Two modes:
  --log    Append a trade record to the failure log.
  --query  Find similar past scenarios and output a failure-risk signal.
  --demo   Seed 20 synthetic trade records for testing.

Trade log: ~/.rumbling-hedge/state/failure_rag_trades.json
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", str(HOME / "hedge" / ".rumbling-hedge" / "state")))
TRADE_LOG_PATH = STATE_DIR / "failure_rag_trades.json"

SESSIONS = ["ES", "NQ", "CL", "GC"]
REGIMES = ["normal", "high_noise", "low_noise", "trending", "mean_reverting"]
DIRECTIONS = ["LONG", "SHORT"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# ── helpers ──────────────────────────────────────────────────────────────

def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def configure_state_dir(path):
    global STATE_DIR, TRADE_LOG_PATH
    if path:
        STATE_DIR = Path(path).expanduser()
        TRADE_LOG_PATH = STATE_DIR / "failure_rag_trades.json"


def load_trades():
    """Load all logged trade records (returns list)."""
    if not TRADE_LOG_PATH.exists():
        return []
    try:
        with open(TRADE_LOG_PATH, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def save_trades(trades):
    """Persist the full trade list to disk."""
    ensure_state_dir()
    with open(TRADE_LOG_PATH, "w") as f:
        json.dump(trades, f, indent=2, default=str)


def load_state_file(filename):
    """Load a JSON state file from STATE_DIR."""
    path = STATE_DIR / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── --log mode ───────────────────────────────────────────────────────────

def cmd_log(args):
    record = {
        "timestamp": args.timestamp or now_iso(),
        "session": args.session.upper(),
        "regime": args.regime.lower(),
        "direction": args.direction.upper(),
        "entry_price": args.entry_price,
        "exit_price": args.exit_price,
        "pnl_pts": args.pnl_pts,
        "win_loss": args.win_loss.lower(),
        "atr_at_entry": args.atr_at_entry,
        "day_of_week": args.day_of_week,
        "reason": args.reason,
    }
    trades = load_trades()
    trades.append(record)
    save_trades(trades)
    print(json.dumps({"status": "logged", "total_records": len(trades)}, indent=2))


# ── --query mode ─────────────────────────────────────────────────────────

def cmd_query(args):
    # 1. Load arbitration → get current session (symbol)
    arb = load_state_file("arbitration.latest.json")
    if not arb:
        result = _query_error("arbitration.latest.json not found")
        write_signal(result)
        print(json.dumps(result, indent=2))
        return

    session = arb.get("symbol", "").upper()
    if not session:
        result = _query_error("arbitration.latest.json missing 'symbol'")
        write_signal(result)
        print(json.dumps(result, indent=2))
        return

    # 2. Load noise-analysis → get regime for current session
    noise = load_state_file("noise-analysis.latest.json")
    regime = "normal"  # default
    if noise:
        noise_key = f"{session.lower()}_noise"
        noise_details = noise.get("details", {}).get(noise_key, {})
        regime = noise_details.get("regime", "normal").lower()

    # 3. Get current day of week
    day_of_week = datetime.now(timezone.utc).strftime("%A")

    # 4. Load all trades and filter by session + day_of_week + regime
    trades = load_trades()
    similar = [
        t for t in trades
        if t.get("session", "").upper() == session
        and t.get("day_of_week", "") == day_of_week
        and t.get("regime", "").lower() == regime
    ]

    # If no exact session+day+regime match, relax to session+day
    if len(similar) < 2:
        similar = [
            t for t in trades
            if t.get("session", "").upper() == session
            and t.get("day_of_week", "") == day_of_week
        ]

    # If still not enough, relax to session+regime
    if len(similar) < 2:
        similar = [
            t for t in trades
            if t.get("session", "").upper() == session
            and t.get("regime", "").lower() == regime
        ]

    # Sort by recency, take up to 10
    similar.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
    similar = similar[:10]

    # 5. Calculate metrics
    total = len(similar)
    if total == 0:
        result = {
            "timestamp": now_iso(),
            "direction": 0,
            "confidence": 0.0,
            "signal_name": "failure_rag",
            "details": {
                "similar_win_rate": 0.0,
                "similar_trades_count": 0,
                "confidence_adjustment": 0.0,
            },
            "error": None,
        }
        result = with_advisory_contract(result)
        write_signal(result)
        print(json.dumps(result, indent=2))
        return

    wins = sum(1 for t in similar if t.get("win_loss", "").lower() == "win")
    win_rate = wins / total if total > 0 else 0.0

    # Scale confidence by sample size (caps at 10)
    size_factor = min(total / 10.0, 1.0)

    # confidence = how confident we are this setup leads to failure
    # (high win_rate means low failure confidence; low win_rate means high failure confidence)
    confidence = (1.0 - win_rate) * size_factor

    # confidence_adjustment: how much to adjust other signal confidences
    # positive = favorable setup (boost signals), negative = unfavorable (dampen signals)
    confidence_adjustment = (win_rate - 0.5) * size_factor

    result = with_advisory_contract({
        "timestamp": now_iso(),
        "direction": 0,
        "confidence": round(confidence, 4),
        "signal_name": "failure_rag",
        "details": {
            "similar_win_rate": round(win_rate, 4),
            "similar_trades_count": total,
            "confidence_adjustment": round(confidence_adjustment, 4),
        },
        "error": None,
    })
    write_signal(result)
    print(json.dumps(result, indent=2))


def _query_error(msg):
    return with_advisory_contract({
        "timestamp": now_iso(),
        "direction": 0,
        "confidence": 0.0,
        "signal_name": "failure_rag",
        "details": {
            "similar_win_rate": 0.0,
            "similar_trades_count": 0,
            "confidence_adjustment": 0.0,
        },
        "error": msg,
    })


def with_advisory_contract(signal):
    """Mark failure-memory lookups as advisory context only."""
    signal.update({
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "readyForExecution": False,
        "execution_role": "diagnostic_only",
        "limitations": [
            "Failure RAG is memory context only and cannot approve a trade",
            "Missing or sparse similar-trade history must not be treated as positive confirmation",
        ],
    })
    return signal


def write_signal(result):
    ensure_state_dir()
    (STATE_DIR / "failure-rag.latest.json").write_text(json.dumps(result, indent=2) + "\n")


# ── --demo mode ──────────────────────────────────────────────────────────

def cmd_demo(args):
    trades = load_trades()
    existing = len(trades)

    random.seed(42)
    synthetic = []
    base_ts = datetime(2026, 5, 1, tzinfo=timezone.utc)

    for i in range(20):
        session = random.choice(SESSIONS)
        regime = random.choice(REGIMES)
        direction = random.choice(DIRECTIONS)
        day = random.choice(DAYS)

        # Base price by session
        base_prices = {"ES": 5900, "NQ": 21000, "CL": 68, "GC": 3300}
        price = base_prices.get(session, 100)

        # Generate realistic PnL
        win = random.random() < 0.45  # 45% win rate, realistic for trading
        pnl_pts = round(random.uniform(5, 50), 2)
        if not win:
            pnl_pts = -pnl_pts

        entry = price + random.uniform(-20, 20)
        exit_p = entry + pnl_pts if session in ("ES", "NQ") else entry + pnl_pts * 0.1

        # Adjust for CL/GC which have different point values
        if session in ("CL",):
            entry = round(price + random.uniform(-1, 1), 2)
            exit_p = round(entry + pnl_pts * 0.01, 2)
            pnl_pts = round(exit_p - entry, 2)
            if not win and pnl_pts > 0:
                pnl_pts = -pnl_pts
        if session in ("GC",):
            entry = round(price + random.uniform(-30, 30), 2)
            exit_p = round(entry + pnl_pts * 0.1, 2)
            pnl_pts = round(exit_p - entry, 2)
            if not win and pnl_pts > 0:
                pnl_pts = -pnl_pts

        atr = round(random.uniform(5, 40), 2)

        reasons = [
            "stop loss hit on noise spike",
            "trend reversal at resistance",
            "failed breakout during low volume",
            "gap fill rejection",
            "momentum exhaustion after FOMC",
            "VWAP rejection with high delta divergence",
            "news catalyst invalidated setup",
            "whale absorption at level",
            "time stop — sideways consolidation",
            "liquidity sweep of range lows",
        ]
        reason = random.choice(reasons)

        ts = base_ts + timedelta(days=i, hours=random.randint(8, 20))

        record = {
            "timestamp": ts.isoformat(),
            "session": session,
            "regime": regime,
            "direction": direction,
            "entry_price": round(entry, 2),
            "exit_price": round(exit_p, 2),
            "pnl_pts": round(pnl_pts, 2),
            "win_loss": "win" if win else "loss",
            "atr_at_entry": atr,
            "day_of_week": day,
            "reason": reason,
        }
        synthetic.append(record)

    trades.extend(synthetic)
    save_trades(trades)
    print(json.dumps({
        "status": "demo_seeded",
        "existing_before": existing,
        "added": len(synthetic),
        "total_now": len(trades),
    }, indent=2))


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Failure RAG — log trades & query similar past failure scenarios"
    )
    parser.add_argument("--state-dir", default=None, help="State directory for failure-rag artifacts")
    sub = parser.add_subparsers(dest="mode", required=True)

    # --log
    p_log = sub.add_parser("log", help="Append a trade record to the failure log")
    p_log.add_argument("--timestamp", default=None, help="ISO timestamp (default: now)")
    p_log.add_argument("--session", required=True, choices=SESSIONS + [s.lower() for s in SESSIONS],
                       help="Trading session (ES, NQ, CL, GC)")
    p_log.add_argument("--regime", required=True, help="Market regime (e.g. normal, high_noise)")
    p_log.add_argument("--direction", required=True, choices=DIRECTIONS + [d.lower() for d in DIRECTIONS],
                       help="Trade direction (LONG/SHORT)")
    p_log.add_argument("--entry-price", required=True, type=float, help="Entry price")
    p_log.add_argument("--exit-price", required=True, type=float, help="Exit price")
    p_log.add_argument("--pnl-pts", required=True, type=float, help="PnL in points")
    p_log.add_argument("--win-loss", required=True, choices=["win", "loss", "WIN", "LOSS"],
                       help="Trade outcome")
    p_log.add_argument("--atr-at-entry", required=True, type=float, help="ATR at entry time")
    p_log.add_argument("--day-of-week", required=True, choices=DAYS,
                       help="Day of the week")
    p_log.add_argument("--reason", required=True, help="Reason for the trade / exit")

    # --query
    p_query = sub.add_parser("query", help="Query similar past scenarios for failure risk")
    # (no extra args needed — reads state files automatically)

    # --demo
    p_demo = sub.add_parser("demo", help="Seed 20 synthetic trade records for testing")

    args = parser.parse_args()
    configure_state_dir(args.state_dir)

    if args.mode == "log":
        cmd_log(args)
    elif args.mode == "query":
        cmd_query(args)
    elif args.mode == "demo":
        cmd_demo(args)


if __name__ == "__main__":
    main()
