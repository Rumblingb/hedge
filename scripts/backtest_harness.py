#!/usr/bin/env python3
"""
Automated Walkforward Validation Harness
========================================
Reads walkforward-matrix and oos-rolling state files, cross-references
against the confirmed edge portfolio, and produces a unified health report.

Can optionally trigger fresh CLI runs per symbol/tf combo when state is stale.

USAGE:
  # Read existing state files and compare:
  python scripts/backtest_harness.py --read-only

  # Run fresh walkforward-matrix on NQ-60m (single combo):
  python scripts/backtest_harness.py --run NQ 60m

  # Run all confirmed edge combos (BATCH — takes 15-30 min):
  python scripts/backtest_harness.py --run-all

CRON (runs after data pipeline refreshes data):
  30 2 * * 1-5 cd ~/hedge && python scripts/backtest_harness.py --read-only >> logs/harness.log 2>&1
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── CONFIG ────────────────────────────────────────────────────────────────

HEDGE_ROOT = Path(os.environ.get("BILL_ROOT", Path(__file__).resolve().parent.parent))
STATE_DIR = HEDGE_ROOT / ".rumbling-hedge" / "state"
VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT", "/Users/brain/Documents/memorybrain"))
DAILY_DIR = VAULT_ROOT / "Agent-Hermes" / "daily"

WF_MATRIX_STATE = STATE_DIR / "walkforward-matrix.latest.json"
OOS_ROLLING_STATE = STATE_DIR / "rolling-oos.latest.json"

CONFIRMED_EDGES = {
    ("NQ", "60m", "wq-vol-regime"):    {"wr": 71.1, "totalR": 210.64, "avgR": 1.85, "notes": "Rust param_sweep optimal — SLK=10, LLK=20, ST=1.6, LT=0.8"},
    ("NQ", "30m", "wq-trend-mom"):     {"wr": 61.0, "totalR": 252.69, "avgR": 1.35, "notes": "Champion"},
    ("NQ", "15m", "orb-breakout"):     {"wr": 60.6, "totalR": 385.21, "avgR": 0.79, "notes": "Range window 8/10/12"},
    ("NQ", "30m", "orb-breakout"):     {"wr": 59.6, "totalR": 280.94, "avgR": 1.00, "notes": "RW=8, VT=1.3"},
    ("ES", "60m", "wq-vol-regime"):    {"wr": 57.5, "totalR": 126.00, "avgR": 0.60, "notes": ""},
    ("ES", "60m", "orb-breakout"):     {"wr": 59.1, "totalR": 68.00,  "avgR": 0.62, "notes": ""},
    ("ES", "60m", "wq-trend-mom"):     {"wr": 58.0, "totalR": 114.00, "avgR": 0.39, "notes": ""},
    ("ES", "30m", "wq-trend-mom"):     {"wr": 56.8, "totalR": 214.00, "avgR": 0.46, "notes": ""},
}

# Strategy → CSV timeframe mapping (which TF data to feed walkforward on)
EDGE_TO_TF = {
    ("NQ", "60m"): "60m",
    ("NQ", "30m"): "30m",
    ("NQ", "15m"): "15m",
    ("ES", "60m"): "60m",
    ("ES", "30m"): "30m",
}


# ─── HELPERS ───────────────────────────────────────────────────────────────

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def date_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_json(path: Path) -> Optional[dict]:
    """Load a JSON file, returning None if missing or corrupt."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def resolve_csv(symbol: str, tf: str) -> Optional[Path]:
    """Find the best available CSV for symbol+tf combo."""
    candidates = [
        HEDGE_ROOT / "data" / "free" / f"ALL-6MARKETS-{tf}-60d.csv",
        HEDGE_ROOT / "data" / "free" / f"ALL-6MARKETS-{tf}-60d-normalized.csv",
        HEDGE_ROOT / "data" / "free" / f"{symbol}-{tf}-60d.csv",
        HEDGE_ROOT / "data" / "free" / f"ALL-2MARKETS-NQ-ES-{tf}-60d-fresh.csv",
        HEDGE_ROOT / "data" / "free" / f"ALL-6MARKETS-{tf}-30d.csv",
        HEDGE_ROOT / "data" / "free" / f"ALL-6MARKETS-{tf}-30d-normalized.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def run_matrix_cli(symbol: str, tf: str, timeout: int = 600) -> Optional[dict]:
    """Run the TS walkforward-matrix CLI and return parsed JSON."""
    csv = resolve_csv(symbol, tf)
    if not csv:
        return {"error": f"no CSV for {symbol}-{tf}"}
    
    start = time.time()
    env = os.environ.copy()
    env.setdefault("NODE_OPTIONS", "--max-old-space-size=4096")
    try:
        result = subprocess.run(
            ["npx", "tsx", "src/cli.ts", "walkforward-matrix", str(csv)],
            cwd=HEDGE_ROOT, capture_output=True, text=True, timeout=timeout, env=env
        )
        elapsed = round(time.time() - start, 1)
        if result.returncode != 0:
            return {"error": f"CLI exit {result.returncode}", "stderr": result.stderr[-500:], "elapsed_s": elapsed}
        data = json.loads(result.stdout)
        data["_meta"] = {"symbol": symbol, "tf": tf, "csv": str(csv), "elapsed_s": elapsed, "source": "fresh-run"}
        return data
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def run_oos_cli(symbol: str, tf: str, timeout: int = 600) -> Optional[dict]:
    """Run the TS oos-rolling CLI."""
    csv = resolve_csv(symbol, tf)
    if not csv:
        return {"error": f"no CSV for {symbol}-{tf}"}
    
    start = time.time()
    env = os.environ.copy()
    env.setdefault("NODE_OPTIONS", "--max-old-space-size=4096")
    try:
        result = subprocess.run(
            ["npx", "tsx", "src/cli.ts", "oos-rolling", str(csv), "4", "20", "5", "1"],
            cwd=HEDGE_ROOT, capture_output=True, text=True, timeout=timeout, env=env
        )
        elapsed = round(time.time() - start, 1)
        if result.returncode != 0:
            return {"error": f"CLI exit {result.returncode}", "stderr": result.stderr[-500:], "elapsed_s": elapsed}
        data = json.loads(result.stdout)
        data["_meta"] = {"symbol": symbol, "tf": tf, "csv": str(csv), "elapsed_s": elapsed, "source": "fresh-run"}
        return data
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


# ─── CROSS-REFERENCE ───────────────────────────────────────────────────────

def classify_matrix(config: dict, status: str) -> str:
    """Classify a single walkforward-matrix config."""
    oos = config.get("stitchedOos", {})
    wfe = oos.get("wfe", 0)
    netR = oos.get("netTotalR", 0)
    pf = oos.get("profitFactor", 0)
    trades = oos.get("totalTrades", 0)

    if wfe >= 0.6 and netR > 0 and pf >= 1.4 and trades >= 20:
        return "✅ GREEN"
    elif wfe >= 0.5 and netR > 0:
        return "🟡 AMBER — WFE borderline"
    elif netR > 0 and wfe >= 0.3:
        return "🔶 RESEARCH-ONLY"
    else:
        return "🔴 REJECT"


def cross_reference_edge(edge_key: Tuple[str, str, str], matrix_data: dict) -> dict:
    """Compare walkforward result against confirmed baseline."""
    sym, tf, strategy = edge_key
    baseline = CONFIRMED_EDGES.get(edge_key, {})
    
    if not matrix_data or "error" in matrix_data:
        return {
            "edge_key": f"{sym}/{tf}/{strategy}",
            "status": "❌ CLI FAILED",
            "error": matrix_data.get("error") if matrix_data else "no data",
            "baseline_wr": baseline.get("wr"),
            "baseline_totalR": baseline.get("totalR"),
            "baseline_avgR": baseline.get("avgR"),
        }

    configs = matrix_data.get("configs", [])
    status = matrix_data.get("status", "reject")

    # Find best config (no failure modes, highest netR)
    best = None
    for c in configs:
        oos = c.get("stitchedOos", {})
        if not c.get("failureModes"):
            if best is None or oos.get("netTotalR", -999) > best.get("stitchedOos", {}).get("netTotalR", -999):
                best = c
    
    if not best and configs:
        best = configs[0]  # fallback to first config even with failures

    if not best:
        return {
            "edge_key": f"{sym}/{tf}/{strategy}",
            "status": "NO CONFIGS",
            "baseline_wr": baseline.get("wr"),
            "baseline_totalR": baseline.get("totalR"),
        }

    oos = best.get("stitchedOos", {})
    classification = classify_matrix(best, status)

    return {
        "edge_key": f"{sym}/{tf}/{strategy}",
        "status": classification,
        "matrix_status": status,
        "config_id": best.get("configId"),
        "config_mode": best.get("mode"),
        "train_days": best.get("trainDays"),
        "test_days": best.get("testDays"),
        "windows_evaluated": best.get("windowsEvaluated"),
        "wfe": oos.get("wfe"),
        "oos_netR": oos.get("netTotalR"),
        "oos_pf": oos.get("profitFactor"),
        "oos_sharpe": oos.get("sharpePerTrade"),
        "oos_maxDD": oos.get("maxDrawdownR"),
        "oos_trades": oos.get("totalTrades"),
        "deployable_windows": oos.get("deployableWindows"),
        "failure_modes": best.get("failureModes", []),
        "baseline_wr": baseline.get("wr"),
        "baseline_totalR": baseline.get("totalR"),
        "baseline_avgR": baseline.get("avgR"),
        "baseline_notes": baseline.get("notes", ""),
    }


def read_matrix_for_edge(edge_key: Tuple[str, str, str]) -> Optional[dict]:
    """Read the walkforward-matrix state file — it runs against the whole CSV
    including all symbols. Extracting symbol-specific would require re-running
    per-symbol. For now, we read the multi-symbol CSV results and note the
    selectedProfileId to attribute results, but the matrix tests profiles
    not individual strategies. 

    Instead, we return the full matrix and cross-reference assigns the
    same matrix to all edges on the same (symbol, tf) pair.
    """
    return load_json(WF_MATRIX_STATE)


def read_oos_for_edge(edge_key: Tuple[str, str, str]) -> Optional[dict]:
    """Read oos-rolling state file."""
    return load_json(OOS_ROLLING_STATE)


# ─── REPORT ────────────────────────────────────────────────────────────────

def build_matrix_map(matrix_data: dict) -> Dict[str, dict]:
    """Given a matrix run on a multi-symbol CSV, map it to all edges covered.
    For the walkforward matrix, it tests RESEARCH_PROFILES (which are strategy
    combos). The best profile selected per window is recorded.
    
    We build a simple map: if the matrix CSV covers the symbols we care about,
    apply its results to all (symbol, tf) edges sharing that CSV.
    """
    return {}  # matrix runs on mixed CSV — we'll map per-run results instead


def build_report(edge_results: Dict[str, dict]) -> dict:
    """Merge all edge results into a unified harness report."""
    comparisons = sorted(edge_results.values(), key=lambda x: x.get("edge_key", ""))
    green = sum(1 for c in comparisons if "GREEN" in c.get("status", ""))
    amber = sum(1 for c in comparisons if "AMBER" in c.get("status", ""))
    red = sum(1 for c in comparisons if "REJECT" in c.get("status", "") or "FAILED" in c.get("status", ""))
    research = len(comparisons) - green - amber - red

    good_wfes = [c.get("wfe", 0) for c in comparisons if c.get("wfe") is not None and c["wfe"] >= 0.5]
    total_trades = sum(c.get("oos_trades", 0) for c in comparisons if c.get("oos_trades"))

    return {
        "command": "backtest-harness",
        "generated_at": iso_now(),
        "hedge_root": str(HEDGE_ROOT),
        "vault_daily_dir": str(DAILY_DIR),
        "data_sources": {
            "walkforward_matrix": str(WF_MATRIX_STATE),
            "oos_rolling": str(OOS_ROLLING_STATE),
        },
        "summary": {
            "edges_tested": len(comparisons),
            "green": green,
            "amber": amber,
            "research_only": research,
            "red": red,
            "robust_config_count": len(good_wfes),
            "mean_robust_wfe": round(sum(good_wfes) / len(good_wfes), 4) if good_wfes else 0,
            "total_oos_trades": total_trades,
            "promotable": green > 0,
        },
        "comparisons": comparisons,
        "confirmed_baseline": {
            f"{sym}/{tf}/{s}": {"wr": v["wr"], "totalR": v["totalR"], "avgR": v["avgR"]}
            for (sym, tf, s), v in CONFIRMED_EDGES.items()
        },
    }


def write_markdown(report: dict) -> Path:
    """Write a human-readable markdown to the vault daily dir."""
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    md_path = DAILY_DIR / f"{date_key()}-backtest-harness.md"

    s = report["summary"]
    lines = [
        f"# Walkforward Harness — {date_key()}",
        "",
        f"**Generated:** {report['generated_at']}",
        f"**Hedge root:** `{report['hedge_root']}`",
        "",
        "## Summary",
        f"| Metric | Value |",
        f"|:-------|:-----:|",
        f"| Edges tested | {s['edges_tested']} |",
        f"| ✅ Green (promotable) | {s['green']} |",
        f"| 🟡 Amber | {s['amber']} |",
        f"| 🔶 Research-only | {s['research_only']} |",
        f"| 🔴 Red | {s['red']} |",
        f"| Robust configs (WFE≥0.5) | {s['robust_config_count']} |",
        f"| Mean robust WFE | {s['mean_robust_wfe']} |",
        f"| Total OOS trades | {s['total_oos_trades']} |",
        f"| Promotable? | {'✅ YES' if s['promotable'] else '🔴 NO'} |",
        "",
        "## Edge Comparison",
        "| Edge | Status | WFE | OOS NetR | OOS PF | OOS DD | Trades | Baseline WR | Baseline R |",
        "|:-----|:------:|:---:|:--------:|:------:|:------:|:------:|:-----------:|:----------:|",
    ]

    for c in report["comparisons"]:
        lines.append(
            f"| `{c.get('edge_key','?')}` | {c.get('status','?')} | "
            f"{c.get('wfe','?')} | {c.get('oos_netR','?')} | "
            f"{c.get('oos_pf','?')} | {c.get('oos_maxDD','?')} | "
            f"{c.get('oos_trades','?')} | {c.get('baseline_wr','?')}% | {c.get('baseline_totalR','?')} |"
        )

    lines += [
        "",
        "## Robust Config Details",
    ]

    for c in report["comparisons"]:
        if "GREEN" in c.get("status", ""):
            lines.append(f"### {c['edge_key']}")
            lines.append(f"- Config: `{c.get('config_id','?')}` ({c.get('config_mode','?')})")
            lines.append(f"- Train/Test days: {c.get('train_days')}/{c.get('test_days')}")
            lines.append(f"- Deployable windows: {c.get('deployable_windows')}")
            lines.append(f"- Baseline: WR={c.get('baseline_wr')}% TotalR={c.get('baseline_totalR')} AvgR={c.get('baseline_avgR')}")
            lines.append("")

    lines += [
        "## Failure Modes",
    ]
    failures_seen = set()
    for c in report["comparisons"]:
        for fm in c.get("failure_modes", []):
            if fm not in failures_seen:
                failures_seen.add(fm)
                lines.append(f"- `{fm}`")
    if not failures_seen:
        lines.append("- None — all configs pass")

    lines += [
        "",
        "## Action Items",
    ]
    if s["green"] > 0:
        lines.append("- [ ] Promote green strategies to live-readiness gate (`npm run live-readiness`)")
    if s["amber"] > 0:
        lines.append("- [ ] Review amber strategies — borderline metrics need parameter tuning")
    if s["red"] > 0:
        lines.append("- [ ] Red strategies need rework or burial — negative/stale OOS performance")

    lines.append("")
    lines.append("## Baselines (Confirmed Edge Portfolio)")
    for key, v in report["confirmed_baseline"].items():
        lines.append(f"- `{key}` → WR={v['wr']}% TotalR={v['totalR']} AvgR={v['avgR']}")
    lines.append("")

    text = "\n".join(lines)
    md_path.write_text(text)
    print(f"[harness] Markdown written: {md_path}")
    return md_path


def write_json(report: dict) -> Path:
    """Write full JSON report to state dir."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    json_path = STATE_DIR / "backtest-harness.latest.json"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"[harness] JSON written: {json_path}")
    return json_path


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Automated walkforward validation harness.")
    parser.add_argument("--read-only", action="store_true",
                        help="Read existing state files and produce report (no CLI runs)")
    parser.add_argument("--run", nargs=2, metavar=("SYMBOL", "TF"),
                        help="Run fresh walkforward-matrix on a single symbol+tf combo")
    parser.add_argument("--run-all", action="store_true",
                        help="Run fresh walkforward-matrix on all unique (symbol,tf) combos from confirmed edges")
    parser.add_argument("--write-vault", action="store_true", default=True,
                        help="Write markdown to obsidian vault (default: true)")
    parser.add_argument("--no-vault", action="store_false", dest="write_vault",
                        help="Skip writing to vault")
    args = parser.parse_args()

    print("=" * 72)
    print(f"  BACKTEST HARNESS — {iso_now()}")
    print(f"  Mode: {'read-only' if args.read_only else 'run' if args.run else 'run-all' if args.run_all else 'read-only'}")
    print("=" * 72)

    edge_results: Dict[str, dict] = {}

    if args.run:
        sym, tf = args.run
        slug = f"{sym}-{tf}"
        print(f"\n[{slug}] Running walkforward-matrix CLI…")
        result = run_matrix_cli(sym, tf)
        if result and "error" not in result:
            # Map result to all edges sharing this (symbol, tf)
            for (esym, etf, estr), base in CONFIRMED_EDGES.items():
                if esym == sym and etf == tf:
                    ek = f"{esym}-{etf}-{estr}"
                    edge_results[ek] = cross_reference_edge((esym, etf, estr), result)
                    print(f"  {ek}: {edge_results[ek]['status']}")
        else:
            print(f"  Failed: {result.get('error','?') if result else 'null'}")

    elif args.run_all:
        # Run unique (symbol, tf) combos
        unique_combos = sorted(set((sym, tf) for sym, tf, _ in CONFIRMED_EDGES.keys()))
        for sym, tf in unique_combos:
            slug = f"{sym}-{tf}"
            csv = resolve_csv(sym, tf)
            if not csv:
                print(f"\n[{slug}] SKIP — no CSV")
                continue

            print(f"\n{'─'*60}")
            print(f"[{slug}] Running walkforward-matrix CLI…")
            print(f"  CSV: {csv}")

            result = run_matrix_cli(sym, tf)
            if result and "error" not in result:
                for (esym, etf, estr), base in CONFIRMED_EDGES.items():
                    if esym == sym and etf == tf:
                        ek = f"{esym}-{etf}-{estr}"
                        edge_results[ek] = cross_reference_edge((esym, etf, estr), result)
                        print(f"  {ek}: {edge_results[ek]['status']}")
            else:
                err = result.get("error", "null") if result else "null"
                print(f"  Failed: {err}")
                for (esym, etf, estr), base in CONFIRMED_EDGES.items():
                    if esym == sym and etf == tf:
                        ek = f"{esym}-{etf}-{estr}"
                        edge_results[ek] = {
                            "edge_key": f"{esym}/{etf}/{estr}",
                            "status": "❌ CLI FAILED",
                            "error": err,
                            "baseline_wr": base["wr"],
                            "baseline_totalR": base["totalR"],
                        }

    else:
        # Read-only: read existing state file and cross-reference
        state = load_json(WF_MATRIX_STATE)
        if not state:
            print(f"\n[ERROR] No state file at {WF_MATRIX_STATE}")
            print("Run with --run SYMBOL TF or --run-all to generate fresh data.")
            sys.exit(1)

        print(f"\n[read] State file: {WF_MATRIX_STATE}")
        print(f"  Generated: {state.get('generatedAt', '?')}")
        print(f"  CSV: {state.get('csvPath', '?')}")
        print(f"  Status: {state.get('status', '?')}")

        # The state file covers all symbols in the CSV. Apply to all edges.
        for (sym, tf, strat), base in CONFIRMED_EDGES.items():
            ek = f"{sym}-{tf}-{strat}"
            edge_results[ek] = cross_reference_edge((sym, tf, strat), state)

    # ─── Build and write report ───
    if not edge_results:
        print("\nNo results to report.")
        sys.exit(1)

    report = build_report(edge_results)
    json_path = write_json(report)
    
    if args.write_vault:
        md_path = write_markdown(report)
    else:
        md_path = None

    s = report["summary"]
    print(f"\n{'='*72}")
    print(f"  HARNESS COMPLETE")
    print(f"  Edges tested: {s['edges_tested']}")
    print(f"  Green: {s['green']} | Amber: {s['amber']} | Research: {s['research_only']} | Red: {s['red']}")
    print(f"  Robust configs: {s['robust_config_count']} | Mean WFE: {s['mean_robust_wfe']}")
    print(f"  Promotable: {'✅ YES' if s['promotable'] else '🔴 NO'}")
    print(f"  JSON:   {json_path}")
    if md_path:
        print(f"  Vault:  {md_path}")
    print(f"{'='*72}")

    return 0 if s["green"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
