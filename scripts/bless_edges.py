#!/usr/bin/env python3
"""
bless_edges.py — Scans AI Scientist run_*/final_info.json, identifies edges
that meet qualification criteria, and writes blessed-edges-candidates.json.

Does NOT auto-promote anything. Use promote_edge.py to approve a candidate
after manual review. This is intentional: live money requires operator sign-off.

Usage:
  python3 scripts/bless_edges.py
  python3 scripts/bless_edges.py --json        # JSON output only
"""
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "ai-scientist-templates" / "financial_strategy"
STATE = ROOT / ".rumbling-hedge" / "state"
OUTPUT = STATE / "blessed-edges-candidates.json"

PF_MIN = 1.5
WF_SHARE_MIN = 0.60
MIN_OOS_TRADES = 30
WIN_RATE_MIN = 0.40


def scan_runs():
    candidates, rejected = [], []

    for final_info in sorted(RUNS_DIR.glob("run_*/final_info.json")):
        run_id = final_info.parent.name
        try:
            data = json.loads(final_info.read_text())
        except Exception as e:
            rejected.append({"run_id": run_id, "reason": f"parse error: {e}"})
            continue

        t = data.get("AlphaStrategyTemplate", {})
        means = t.get("means", {})
        safety = t.get("safety", {})
        exp = t.get("experiment", {})

        strategy = exp.get("strategy", "")
        if strategy == "known_baselines":
            continue  # meta-run, not an edge

        pf = float(means.get("oos_profit_factor") or 0.0)
        wf = float(means.get("walkforward_positive_fold_share") or 0.0)
        trades = int(means.get("oos_trade_count") or 0)
        wr = float(means.get("oos_win_rate") or 0.0)
        net_pts = float(means.get("oos_total_net_points") or 0.0)

        blockers = []
        if pf < PF_MIN:
            blockers.append(f"oos_pf={pf:.3f} < {PF_MIN}")
        if wf < WF_SHARE_MIN:
            blockers.append(f"wf_share={wf:.2f} < {WF_SHARE_MIN}")
        if trades < MIN_OOS_TRADES:
            blockers.append(f"oos_trades={trades} < {MIN_OOS_TRADES}")
        if wr < WIN_RATE_MIN:
            blockers.append(f"oos_wr={wr:.2f} < {WIN_RATE_MIN}")

        entry = {
            "run_id": run_id,
            "strategy": strategy,
            "symbol": exp.get("symbol", "?"),
            "timeframe": exp.get("timeframe", "?"),
            "oos_profit_factor": round(pf, 4),
            "walkforward_positive_fold_share": round(wf, 3),
            "oos_trade_count": trades,
            "oos_win_rate": round(wr, 4),
            "oos_net_points": round(net_pts, 2),
            "params": exp.get("params", {}),
        }

        if blockers:
            entry["blockers"] = blockers
            rejected.append(entry)
        else:
            entry["status"] = "candidate"
            entry["promote_cmd"] = (
                f"python3 scripts/promote_edge.py --signal <signal-name> --run {run_id}"
            )
            candidates.append(entry)

    return candidates, rejected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print JSON output only")
    args = parser.parse_args()

    candidates, rejected = scan_runs()

    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "criteria": {
            "oos_profit_factor_min": PF_MIN,
            "walkforward_positive_fold_share_min": WF_SHARE_MIN,
            "min_oos_trades": MIN_OOS_TRADES,
            "oos_win_rate_min": WIN_RATE_MIN,
        },
        "candidateCount": len(candidates),
        "rejectedCount": len(rejected),
        "candidates": candidates,
        "rejected": rejected,
        "operatorNote": (
            "Candidates require manual review + explicit promotion. "
            "Use: python3 scripts/promote_edge.py --signal <signal> --run <run-id>"
        ),
    }

    STATE.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, default=str))

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return result

    print(f"Blessed edges: {len(candidates)} candidates / {len(rejected)} rejected")
    if candidates:
        for c in candidates:
            print(f"  CANDIDATE  {c['run_id']:<30s}  "
                  f"{c['strategy']} {c['symbol']} {c['timeframe']}  "
                  f"PF={c['oos_profit_factor']}  WF={c['walkforward_positive_fold_share']}  "
                  f"trades={c['oos_trade_count']}")
    else:
        print("  No candidates meet criteria yet.")
    print(f"\nOutput: {OUTPUT}")
    return result


if __name__ == "__main__":
    main()
