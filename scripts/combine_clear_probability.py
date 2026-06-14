#!/usr/bin/env python3
"""Monte Carlo: probability of clearing the Topstep $50K combine and reaching
consistent funded payouts, driven by the verified nq-orb-3m-vt16 edge.

RESEARCH-ONLY. Touches no broker, writes no orders, moves no funds. Output is a
probability study to inform sizing — not a route, signal, or execution approval.

Edge calibration (authoritative OOS, ai-scientist run_n4_vt1.6_postfix/final_info.json):
  win_rate = 0.717, profit_factor = 3.245, avg net = 24.3 pts/trade, 145 OOS trades,
  time-based exit (hold 6x3m bars, NO hard stop) -> fat loss tail is the real DD risk.

Derived per-trade point geometry (solve PF & avg-net with WR):
  avg_win ~= 49.0 pts, avg_loss ~= 38.2 pts.
We model wins and losses as lognormal around those means and sweep the loss-tail
CV to stress the no-hard-stop tail that threatens the $2,000 trailing drawdown.
"""
from __future__ import annotations
import json, math, argparse
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".rumbling-hedge" / "state"
OUT = STATE / "combine-clear-probability.latest.json"

# --- Topstep $50K combine rules (system-conservative encoding) ---
PROFIT_TARGET = 3000.0
TRAILING_DD = 2000.0          # EOD trailing, freezes once +$2,000 locked
DD_LOCK = 52000.0             # trailing floor stops trailing at start+target
DAILY_LOSS_LOCK = 1000.0      # system guardrail: stop day if <= -$1000
MAX_TRADES_PER_DAY = 3
MAX_CONSEC_LOSSES = 2
CONSISTENCY_CAP = 0.40        # best day <= 40% of total at the moment target is hit
START = 50000.0

# --- edge calibration ---
WR = 0.717
AVG_WIN_PTS = 49.0
AVG_LOSS_PTS = 38.2
TRADES_PER_DAY_LAMBDA = 0.65  # ~80 trades / 125 RTH days from OOS windows
POINT_VALUE = {"NQ": 20.0, "MNQ": 2.0}


def lognormal_params(mean: float, cv: float) -> tuple[float, float]:
    """Return (mu, sigma) of underlying normal for a lognormal with given mean & CV."""
    sigma2 = math.log(1.0 + cv * cv)
    sigma = math.sqrt(sigma2)
    mu = math.log(mean) - 0.5 * sigma2
    return mu, sigma


def make_rng(seed: int):
    # deterministic LCG-backed normal via Box-Muller (no Math.random/numpy dep on global state)
    import random
    return random.Random(seed)


def sample_trade_pts(rng, win_cv: float, loss_cv: float) -> float:
    if rng.random() < WR:
        mu, sig = lognormal_params(AVG_WIN_PTS, win_cv)
        return math.exp(rng.gauss(mu, sig))
    mu, sig = lognormal_params(AVG_LOSS_PTS, loss_cv)
    return -math.exp(rng.gauss(mu, sig))


def simulate_combine(symbol: str, contracts: int, win_cv: float, loss_cv: float,
                     paths: int, horizon_days: int, seed: int) -> dict:
    pv = POINT_VALUE[symbol] * contracts
    cleared = blown = timeout = 0
    days_to_clear = []
    fail_days = []   # wall-clock consumed on non-clearing attempts (bust/timeout)
    best_day_ratios = []
    for p in range(paths):
        rng = make_rng(seed + p)
        balance = START
        peak = START
        dd_floor = START - TRAILING_DD
        total = 0.0
        day_pnls = []
        outcome = None
        for d in range(horizon_days):
            n_trades = min(MAX_TRADES_PER_DAY, rng_poisson(rng, TRADES_PER_DAY_LAMBDA))
            day_pnl = 0.0
            consec_loss = 0
            for _ in range(n_trades):
                pts = sample_trade_pts(rng, win_cv, loss_cv)
                pnl = pts * pv
                balance += pnl
                day_pnl += pnl
                total += pnl
                # intraday trailing peak until lock
                if balance > peak:
                    peak = balance
                    if peak < DD_LOCK:
                        dd_floor = peak - TRAILING_DD
                    else:
                        dd_floor = DD_LOCK - TRAILING_DD  # = 50000 once locked
                if balance <= dd_floor:
                    outcome = "blown"
                    break
                consec_loss = consec_loss + 1 if pnl < 0 else 0
                if consec_loss >= MAX_CONSEC_LOSSES:
                    break
                if day_pnl <= -DAILY_LOSS_LOCK:
                    break
            day_pnls.append(day_pnl)
            if outcome == "blown":
                break
            if total >= PROFIT_TARGET:
                best = max(day_pnls)
                ratio = best / total if total > 0 else 1.0
                best_day_ratios.append(ratio)
                # consistency: if best day > cap, must keep trading to dilute; approximate
                # as pass if ratio <= cap, else needs more days (counted as cleared-but-capped)
                outcome = "cleared" if ratio <= CONSISTENCY_CAP else "cleared_consistency_pending"
                days_to_clear.append(d + 1)
                break
        if outcome is None:
            timeout += 1
            fail_days.append(horizon_days)
        elif outcome == "blown":
            blown += 1
            fail_days.append(d + 1)
        else:
            cleared += 1
    n = float(paths)
    med_days = sorted(days_to_clear)[len(days_to_clear) // 2] if days_to_clear else None
    mean_clear_days = (sum(days_to_clear) / len(days_to_clear)) if days_to_clear else horizon_days
    mean_fail_days = (sum(fail_days) / len(fail_days)) if fail_days else 0.0
    p_clear = cleared / n
    # Expected wall-clock to a PASS, accounting for free restarts on the demo combine:
    # E[total] = (expected #failed attempts) * mean_fail_days + mean_clear_days
    exp_days_to_pass = (((1 - p_clear) / p_clear) * mean_fail_days + mean_clear_days) if p_clear > 0 else None
    consistency_pass = (sum(1 for r in best_day_ratios if r <= CONSISTENCY_CAP) /
                        len(best_day_ratios)) if best_day_ratios else None
    return {
        "symbol": symbol, "contracts": contracts,
        "lossCV": loss_cv, "winCV": win_cv,
        "pClear": round(cleared / n, 4),
        "pBlowTrailingDD": round(blown / n, 4),
        "pTimeout": round(timeout / n, 4),
        "medianDaysToClear": med_days,
        "expDaysToPassWithRestarts": round(exp_days_to_pass, 1) if exp_days_to_pass else None,
        "dollarsPerPoint": pv,
        "evPerTradeUSD": round((WR * AVG_WIN_PTS - (1 - WR) * AVG_LOSS_PTS) * pv, 2),
        "consistencyPassRateAtClear": round(consistency_pass, 4) if consistency_pass is not None else None,
    }


def rng_poisson(rng, lam: float) -> int:
    # Knuth
    L = math.exp(-lam)
    k = 0
    pr = 1.0
    while True:
        k += 1
        pr *= rng.random()
        if pr <= L:
            return k - 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=20000)
    ap.add_argument("--horizon-days", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20260614)
    a = ap.parse_args()

    configs = []
    # Fine micro ladder (1 NQ == 10 MNQ; micros give granular DD control).
    ladder = [("MNQ", n) for n in range(2, 11)] + [("NQ", 2)]
    # loss-tail sensitivity: base CV 0.8, stressed 1.2 (fat tail from no hard stop)
    for sym, ct in ladder:
        for loss_cv in (0.8, 1.2):
            configs.append(simulate_combine(sym, ct, 0.7, loss_cv,
                                            a.paths, a.horizon_days, a.seed))

    # --- Recommendation: use the STRESSED tail (CV 1.2) as the honest case. ---
    # The demo combine bust is a FREE restart, so the true objective for "don't waste
    # time" is minimizing EXPECTED wall-clock to a pass INCLUDING restarts. We still cap
    # bust risk (a bust forfeits in-progress days and risks demoralizing resets).
    BUST_CAP = 0.12
    stressed = [r for r in configs if r["lossCV"] == 1.2 and r["expDaysToPassWithRestarts"]]
    eligible = [r for r in stressed if r["pBlowTrailingDD"] <= BUST_CAP]
    rec = min(eligible or stressed, key=lambda r: r["expDaysToPassWithRestarts"])
    # also report the max-pClear point (the "safe / fewest-resets" pick)
    safest = max(stressed, key=lambda r: r["pClear"])

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True, "writesOrders": False, "touchesBroker": False, "movesFunds": False,
        "edge": "nq-orb-3m-vt16",
        "calibration": {"winRate": WR, "profitFactor": 3.245, "avgNetPtsPerTrade": 24.3,
                        "avgWinPts": AVG_WIN_PTS, "avgLossPts": AVG_LOSS_PTS,
                        "tradesPerDayLambda": TRADES_PER_DAY_LAMBDA, "exit": "time-based 6x3m bars, no hard stop"},
        "rules": {"profitTarget": PROFIT_TARGET, "trailingDD": TRAILING_DD,
                  "dailyLossLock": DAILY_LOSS_LOCK, "maxTradesPerDay": MAX_TRADES_PER_DAY,
                  "consistencyCap": CONSISTENCY_CAP},
        "paths": a.paths, "horizonDays": a.horizon_days,
        "recommendation": {
            "bustRiskCap": BUST_CAP,
            "method": "stressed-tail (CV1.2); maximize pClear/sqrt(medianDays) s.t. pBlowDD<=cap",
            "objective": "minimize expDaysToPassWithRestarts s.t. pBlowDD<=cap",
            "idealCombineSize": {"symbol": rec["symbol"], "contracts": rec["contracts"],
                                  "pClear": rec["pClear"], "pBlowDD": rec["pBlowTrailingDD"],
                                  "medianDays": rec["medianDaysToClear"],
                                  "expDaysToPassWithRestarts": rec["expDaysToPassWithRestarts"],
                                  "evPerTradeUSD": rec["evPerTradeUSD"]},
            "maxPClearSize": {"symbol": safest["symbol"], "contracts": safest["contracts"],
                               "pClear": safest["pClear"], "pBlowDD": safest["pBlowTrailingDD"],
                               "medianDays": safest["medianDaysToClear"]},
            "fundedPayoutSize": {"symbol": "MNQ", "contracts": 1,
                                  "note": "drop to 1-2 MNQ on funding: consistency rule (best-day<=40%) gates payouts, not size"},
        },
        "results": configs,
        "interpretation": "pClear = reached $3k net within horizon without breaching $2k trailing DD. "
                          "loss-tail CV swept 0.8 (base) -> 1.2 (fat, stresses no-hard-stop tail).",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    # compact stdout table
    print(f"{'sym':4} {'ct':>2} {'lossCV':>6} {'$/pt':>5} {'pClear':>7} {'pBlowDD':>7} {'medDays':>7} {'E[days+restart]':>15} {'consist%':>8}")
    for r in configs:
        print(f"{r['symbol']:4} {r['contracts']:>2} {r['lossCV']:>6} {r['dollarsPerPoint']:>5.0f} "
              f"{r['pClear']:>7.3f} {r['pBlowTrailingDD']:>7.3f} {str(r['medianDaysToClear']):>7} "
              f"{str(r['expDaysToPassWithRestarts']):>15} "
              f"{('' if r['consistencyPassRateAtClear'] is None else format(r['consistencyPassRateAtClear'],'.3f')):>8}")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
