#!/usr/bin/env python3
"""Signal Decay Monitor — tracks rolling strategy performance and flags decay.
Reads futures-demo-samples.jsonl, computes rolling metrics per strategy,
flags when performance degrades. Writes to signal-decay.latest.json"""

import json, os, sys
from datetime import datetime, timezone, timedelta

JOURNAL = os.path.expanduser("~/.rumbling-hedge/logs/futures-demo-samples.jsonl")
# Fallback paths
ALT_JOURNAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".rumbling-hedge/logs/futures-demo-samples.jsonl")
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".rumbling-hedge/state")

ROLLING_WINDOW = 20
MIN_TRADES = 5
WIN_RATE_THRESHOLD = 0.40
EXPECTANCY_THRESHOLD = -0.3
DORMANT_DAYS = 30

def load_trades(journal_path):
    trades = []
    for path in [JOURNAL, ALT_JOURNAL]:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                trades.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
            except Exception:
                pass
    return trades

def extract_strategy_trades(trades):
    by_strategy = {}
    for entry in trades:
        execution = entry.get("execution", {})
        lanes = execution.get("lanes", [])
        for lane in lanes:
            sid = lane.get("primaryStrategy", "unknown")
            signal = lane.get("signal")
            if signal is None:
                continue
            trade = {
                "strategyId": sid,
                "symbol": lane.get("focusSymbol", signal.get("symbol", "?")),
                "side": signal.get("side", "?"),
                "rr": signal.get("rr", 0),
                "ts": entry.get("ts", ""),
            }
            if sid not in by_strategy:
                by_strategy[sid] = []
            by_strategy[sid].append(trade)
    return by_strategy

def analyze_strategy(sid, trades):
    if not trades:
        return {
            "strategyId": sid, "totalTrades": 0, "flags": ["INSUFFICIENT_DATA"],
            "rollingWinRate": None, "rollingExpectancy": None
        }

    total = len(trades)
    if total < MIN_TRADES:
        return {
            "strategyId": sid, "totalTrades": total, "flags": ["INSUFFICIENT_DATA"],
            "rollingWinRate": None, "rollingExpectancy": None
        }

    # Compute rolling metrics on last N trades
    recent = trades[-ROLLING_WINDOW:]
    wins = sum(1 for t in recent if t["rr"] > 0)
    win_rate = wins / len(recent) if recent else 0
    total_r = sum(t["rr"] for t in recent)
    expectancy = total_r / len(recent) if recent else 0

    flags = []
    if win_rate < WIN_RATE_THRESHOLD:
        flags.append("WIN_RATE_DECAY")
    if expectancy < EXPECTANCY_THRESHOLD:
        flags.append("EXPECTANCY_DECAY")

    # Check dormancy
    if trades:
        last_ts = trades[-1]["ts"]
        try:
            last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - last_dt).days
            if days_since > DORMANT_DAYS:
                flags.append("DORMANT")
        except (ValueError, TypeError):
            pass

    if not flags:
        flags.append("HEALTHY")

    return {
        "strategyId": sid,
        "totalTrades": total,
        "rollingWinRate": round(win_rate, 3),
        "rollingExpectancy": round(expectancy, 3),
        "rollingWindow": ROLLING_WINDOW,
        "flags": flags,
    }

def main():
    trades = load_trades(JOURNAL)
    by_strategy = extract_strategy_trades(trades)

    results = []
    for sid in sorted(by_strategy.keys()):
        results.append(analyze_strategy(sid, by_strategy[sid]))

    # Also add strategies with zero trades
    all_ids = set()
    for entry in trades:
        for lane in entry.get("execution", {}).get("lanes", []):
            all_ids.add(lane.get("primaryStrategy") or "unknown")
    for sid in sorted(all_ids):
        if sid not in by_strategy:
            results.append(analyze_strategy(sid, []))

    # Sort: flagged first, then by alpha
    results.sort(key=lambda r: (0 if any(f != "HEALTHY" and f != "INSUFFICIENT_DATA" for f in r["flags"]) else 1, r["strategyId"]))

    # Print summary
    print(f"{'Strategy':30s} {'Trades':>6} {'WinRate':>8} {'Expect':>8} {'Flags'}")
    print("-" * 80)
    for r in results:
        wr = f"{r['rollingWinRate']:.2f}" if r['rollingWinRate'] is not None else "N/A"
        ex = f"{r['rollingExpectancy']:.2f}" if r['rollingExpectancy'] is not None else "N/A"
        flags = ",".join(r["flags"])
        print(f"{r['strategyId']:30s} {r['totalTrades']:>6} {wr:>8} {ex:>8}  {flags}")

    # Write output
    os.makedirs(STATE_DIR, exist_ok=True)
    output_path = os.path.join(STATE_DIR, "signal-decay.latest.json")
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "strategies": results,
        "summary": {
            "total": len(results),
            "healthy": sum(1 for r in results if "HEALTHY" in r["flags"]),
            "decayed": sum(1 for r in results if "WIN_RATE_DECAY" in r["flags"] or "EXPECTANCY_DECAY" in r["flags"]),
            "dormant": sum(1 for r in results if "DORMANT" in r["flags"]),
            "insufficient": sum(1 for r in results if "INSUFFICIENT_DATA" in r["flags"]),
        }
    }
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote: {output_path}")

if __name__ == "__main__":
    main()
