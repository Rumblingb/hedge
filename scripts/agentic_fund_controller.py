#!/usr/bin/env python3
"""agentic_fund_controller.py — READ-ONLY agentic fund brain for the command center.

Turns the command center from observer into operator-advisor. Each run it:
  1. Classifies every blessed-edge CANDIDATE by real promotion-readiness:
     PROMOTABLE / DATA-BLOCKED / FAILS-OOS / NEEDS-VERIFICATION
     (a sweep PF is NOT a promotion; current-data OOS + data parity decide.)
  2. Computes a live VOL-REGIME POSTURE from recent NQ bars (ATR percentile) →
     recommended aggression (stand-down / normal / lean-in) for the ORB edge,
     since the edge concentrates on vol expansion.
  3. Emits the single NEXT ACTION that most advances consistent-payout compounding.

Routes NOTHING. Touches no broker. Writes one artifact the command center reads.
Promotion to live ALWAYS stays operator-confirmed; this only proposes.
"""
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
REPO = HOME / "hedge"
STATE = REPO / ".rumbling-hedge" / "state"
DATA = REPO / "data" / "free"
OUT = STATE / "agentic-fund-controller.latest.json"

# Promotion gate (mirrors blessed-edges.promotion_criteria)
CRIT = {"pf": 1.5, "wf": 0.6, "n": 30, "wr": 0.4}
# Instruments we currently have CURRENT-PARITY data for (verifiable today).
# GC/CL added 2026-06-16: data/free has GC-5m/15m/60m-60d + GC-1h-2000-2026 (deep) and
# CL-5m-60d. (SI/silver has only daily/forecast CSVs — no intraday bars yet.)
HAVE_CURRENT_DATA = {"NQ", "ES", "GC", "CL"}


def load(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def atr_percentile_posture():
    """Realized-vol posture from NQ 5m bars: where does the latest ATR sit in its
    own recent distribution? High percentile (vol expansion) = lean into ORB."""
    csv = DATA / "NQ-5m-5d.csv"
    if not csv.exists():
        return {"posture": "unknown", "reason": "no NQ 5m bars", "atr_pct": None}
    try:
        rows = [r.split(",") for r in csv.read_text().splitlines() if r][1:]
        highs = [float(r[2]) for r in rows]
        lows = [float(r[3]) for r in rows]
        closes = [float(r[4]) for r in rows]
        trs = []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            trs.append(tr)
        if len(trs) < 30:
            return {"posture": "unknown", "reason": "thin bar history", "atr_pct": None}
        win = 14
        atrs = [statistics.mean(trs[i - win:i]) for i in range(win, len(trs))]
        latest = atrs[-1]
        sorted_a = sorted(atrs)
        rank = sum(1 for a in sorted_a if a <= latest) / len(sorted_a)
        if rank >= 0.66:
            posture, reason = "lean-in", "vol expansion (high ATR percentile) — ORB follow-through favored"
        elif rank <= 0.33:
            posture, reason = "stand-down", "low vol / chop — ORB false-break risk; preserve capital"
        else:
            posture, reason = "normal", "mid-range vol"
        return {"posture": posture, "reason": reason, "atr_pct": round(rank, 2),
                "latest_atr": round(latest, 2)}
    except Exception as e:
        return {"posture": "unknown", "reason": f"calc error: {e}", "atr_pct": None}


def classify_candidates():
    cands = load(STATE / "blessed-edges-candidates.json", {}) or {}
    blessed = load(STATE / "blessed-edges.json", {}) or load(REPO / "blessed-edges.json", {}) or {}
    promoted_ids = {e.get("id") for e in (blessed.get("edges") or [])}
    # Best current-OOS verdict for the NQ vol-regime family (real, not sweep).
    nq_volregime = load(STATE / "vol-regime-oos-replay.latest.json", {}) or {}
    nq_vr_status = nq_volregime.get("status")

    def g(x, k, dv=0):
        v = x.get(k)
        return dv if v is None else v

    # Dedup candidates by (strategy, symbol, timeframe), keep best PF.
    best = {}
    for x in (cands.get("candidates") or []):
        key = (x.get("strategy"), x.get("symbol"), x.get("timeframe"))
        if key not in best or g(x, "oos_profit_factor") > g(best[key], "oos_profit_factor"):
            best[key] = x

    out = []
    for (strat, sym, tf), x in best.items():
        passes_screen = (g(x, "oos_profit_factor") >= CRIT["pf"] and
                         g(x, "walkforward_positive_fold_share") >= CRIT["wf"] and
                         g(x, "oos_trade_count") >= CRIT["n"] and
                         g(x, "oos_win_rate") >= CRIT["wr"])
        if not passes_screen:
            verdict, why = "FAILS-SCREEN", "below sweep promotion screen"
        elif sym not in HAVE_CURRENT_DATA:
            verdict, why = "DATA-BLOCKED", f"no current-parity {sym} data to verify; acquire before promote"
        elif strat == "wq_vol_regime" and sym == "NQ" and nq_vr_status == "reject-current-oos":
            verdict, why = "FAILS-OOS", "current-data OOS replay rejects (sweep PF was an artifact)"
        else:
            verdict, why = "NEEDS-VERIFICATION", "passes sweep screen + has data; run current-OOS + cost-stress to confirm"
        out.append({
            "strategy": strat, "symbol": sym, "timeframe": tf,
            "sweep_pf": round(g(x, "oos_profit_factor"), 2),
            "n": g(x, "oos_trade_count"), "wr": round(g(x, "oos_win_rate"), 2),
            "wf": x.get("walkforward_positive_fold_share"),
            "promoted_live": x.get("run_id") in promoted_ids,
            "verdict": verdict, "why": why,
        })
    out.sort(key=lambda r: (r["verdict"] != "NEEDS-VERIFICATION", -r["sweep_pf"]))
    return out


def shelf_audit():
    """Standing 'did we miss anything' check: machine-truth strategy zoo + the verified-
    but-unwired ledger. Surfaces the gap between the research shelf (Gold-Used cards) and
    what is actually promotable, so a shiny shelf can't masquerade as wired edges."""
    zoo = load(STATE / "strategy-zoo-audit.latest.json", {}) or {}
    counts = zoo.get("counts", {})
    # Verified-but-unwired ledger (hand-curated from the 2026-06-16 mining; update as we wire).
    unwired = [
        {"item": "ORB time-exit config (run_n4_vt1.6, PF 4.44)", "status": "verified, NOT wired",
         "note": "stronger than the live 2RR bracket (PF 3.245) on the SAME blessed 3m edge; "
                 "changes fills -> score + update config-parity evidence before wiring (Codex)."},
        {"item": "GC 1h ORB-retest conf=5 (claimed PF 2.398)", "status": "UNRELIABLE",
         "note": "never wired into experiment.py; standalone re-impl could not reproduce (PF ~0.8). "
                 "Re-implement faithfully + re-gate on current GC data before any trust."},
        {"item": "stop=1.0 ATR (e1 sweep)", "status": "verified, ALREADY in routed signal",
         "note": "orb3m_vt16/es_signal already use stop_atr 1.0; master_bridge coarse ORB (1.5) is not routed."},
    ]
    dead = ["all vol-regime (NQ/GC/CL/6E) — fails current OOS", "Misango noise-area — failed 200-shuffle permutation",
            "London/Asia session scalping — reduces edge, killed live", "GitHub extracts (QRS/HHT/VMACD/Alligator) — untested on our data"]
    return {
        "machine_truth": {"registered": counts.get("registered"),
                          "skeleton": counts.get("classification:SKELETON"),
                          "bronze": counts.get("classification:BRONZE"),
                          "quarantined": counts.get("classification:QUARANTINED"),
                          "promotable_gold": 0},
        "verified_unwired": unwired,
        "dead_do_not_revisit": dead,
        "verdict": "Shelf = research/evidence cards, NOT verified edges. Machine truth = 0 promotable gold. "
                   "Routed ORB-3m already uses blessed geometry. Only real upgrade = score the time-exit config.",
    }


def paper_research_queue():
    """Prioritized, executable research queue distilled from the linked papers
    (Research-Catalog Paper-Source-Cards + Oxford-Man). Every item is a ONE-VARIABLE
    test routed through experiment.py + the full purged-OOS/walkforward/cost gate.
    NOTHING here is live-wireable until it survives. Priority = alignment with our
    ONE verified edge (ORB-3m) + decorrelation value, lowest complexity first."""
    return [
        {"rank": 1, "test": "CTA vol-scaled trend overlay on ORB-3m",
         "papers": ["Lintner_Revisited", "Investing in Volatility (vol-regime overlay)"],
         "why": "Converges with verified 0.25-Kelly + time-exit findings; a SIZING/REGIME overlay "
                "on the edge we already trust — lowest risk, highest fit. Keep entries/stops fixed; "
                "vary only the vol-scaling. Risk-reducing, not a new entry signal.",
         "gate": "must add OOS Sharpe beyond fixed-size ORB after costs; purged WF + shuffle."},
        {"rank": 2, "test": "Tail-risk feature as a stand-down FILTER on ORB",
         "papers": ["ssrn-6702398 (tail-risk-aware gate)", "Slow-Mom+Fast-Reversion CPD gate (2105.13727)"],
         "why": "A filter can only REMOVE trades on extreme-tail days -> protects consistency without "
                "adding a fragile edge. Safer class than any new signal.",
         "gate": "must cut losing-day variance without killing net edge; WF + shuffle."},
        {"rank": 3, "test": "Network / lead-lag momentum on NQ+ES+GC+CL+6E+ZN",
         "papers": ["Network Momentum 2308.11294 (SR1.5)", "Lead-Lag 2305.06704"],
         "why": "Cross-instrument momentum spillover across the decorrelated set we have data for; "
                "directly serves compounding via decorrelation. Higher complexity -> later.",
         "gate": "SR1.5 was 2000-2022 pre-cost; reject if 2023-26 fails or costs erase it."},
        {"rank": 4, "test": "GC ORB-retest conf=5 faithful re-implementation",
         "papers": ["ai-scientist-p3 (SSRN 6745958)"],
         "why": "Best-looking shelved edge but my re-impl could not reproduce it; needs exact wiring "
                "into experiment.py + re-gate on current GC before trust.",
         "gate": "reproduce PF/WF/shuffle on current data or discard."},
    ]


def next_action(classified, posture):
    verifiable = [c for c in classified if c["verdict"] == "NEEDS-VERIFICATION" and not c["promoted_live"]]
    data_blocked = [c for c in classified if c["verdict"] == "DATA-BLOCKED"]
    if verifiable:
        c = verifiable[0]
        return (f"VERIFY {c['strategy']} {c['symbol']}/{c['timeframe']} (sweep PF {c['sweep_pf']}) "
                f"via current-OOS + cost-stress; promote to demo-shadow only if it survives.")
    if data_blocked:
        syms = sorted({c["symbol"] for c in data_blocked})
        return (f"ACQUIRE current-parity data for {','.join(syms)} — {len(data_blocked)} promising "
                f"candidates are stranded on missing data (e.g. GC vol-regime). Data is the unlock, not new sweeps.")
    return "No verifiable promotion candidate — ORB-3m remains the sole edge; focus on geometry/runner upgrade + combine clear."


def main():
    posture = atr_percentile_posture()
    classified = classify_candidates()
    record = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True, "writesOrders": False, "touchesBroker": False,
        "movesFunds": False, "readyForExecution": False,
        "readyForDemoExpansion": False, "readyForLive": False,
        "northStar": "consistent payouts -> compound; promote only verified edges (consistency > breadth)",
        "volRegimePosture": posture,
        "candidates": classified,
        "summary": {
            "needs_verification": sum(1 for c in classified if c["verdict"] == "NEEDS-VERIFICATION"),
            "data_blocked": sum(1 for c in classified if c["verdict"] == "DATA-BLOCKED"),
            "fails_oos": sum(1 for c in classified if c["verdict"] == "FAILS-OOS"),
            "fails_screen": sum(1 for c in classified if c["verdict"] == "FAILS-SCREEN"),
        },
        "nextAction": next_action(classified, posture),
        "shelfAudit": shelf_audit(),
        "paperResearchQueue": paper_research_queue(),
        "promotionPolicy": "Research evidence may become eligible for operator-reviewed demo only after every independent gate passes; this controller never auto-promotes demo or live risk.",
    }
    STATE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
