#!/usr/bin/env python3
"""
Combined meta-strategy backtest:
  ES  → short-term-reversal (v3): 30-bar lookback, rev >1.5x ATR, high-vol gate
  NQ  → ret-30-momentum:          30-bar lookback, momentum >0.5x ATR, volume conf

Both run simultaneously on the same data with independent position tracking.
Combined P&L = sum(ES P&L, NQ P&L).
Max 2 trades/day/symbol.
"""
import csv
import argparse
import os
from datetime import datetime

DEFAULT_DATA = "data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized.csv"
FALLBACK_DATA_ROOTS = [
    os.environ.get("BILL_DATA_FREE_FALLBACK_DIR", ""),
    os.environ.get("BILL_FUTURES_COLD_DATA_ROOT", ""),
    "/Users/brain/mnt/agentpay-hdd/datasets/rumbling-hedge/data/free/free",
    "/Volumes/Seagate Expansion Drive/rumbling-hedge/data/free/free",
]

def resolve_data_path(path):
    if os.path.isfile(path):
        return path
    repo_path = os.path.abspath(path)
    if os.path.isfile(repo_path):
        return repo_path
    basename = os.path.basename(path)
    for root in FALLBACK_DATA_ROOTS:
        if not root:
            continue
        candidate = os.path.join(root, basename)
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(f"CSV not found: {path}")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def is_active_session(ts):
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    h, m = dt.hour, dt.minute
    total = h * 60 + m
    morning = (12*60+30) <= total <= (15*60+30)
    afternoon = (17*60) <= total <= (19*60+30)
    return morning or afternoon

def atr14(highs, lows, closes, i):
    trs = []
    for j in range(max(1, i-14), i):
        tr = max(highs[j] - lows[j], abs(highs[j] - closes[j-1]), abs(lows[j] - closes[j-1]))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0

# ---------------------------------------------------------------------------
# Strategy 1: Short-term-reversal (v3) — applied to ES
# ---------------------------------------------------------------------------
def backtest_v3(bars, symbol):
    closes = [float(b["close"]) for b in bars]
    highs  = [float(b["high"]) for b in bars]
    lows   = [float(b["low"]) for b in bars]
    ts_list = [b["ts"] for b in bars]
    vols   = [float(b.get("volume", 0) or 0) for b in bars]

    trades = []
    in_trade = False
    trade_entry_i = -1
    trade_entry_price = 0
    trade_stop = 0
    trade_target = 0
    trade_side = ""

    SL_ATR = 1.0

    for i in range(30, len(closes)):
        ts = ts_list[i]

        # --- Exit handling ---
        if in_trade:
            if trade_side == "long":
                if lows[i] <= trade_stop:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i],
                                   "side": trade_side, "entry": trade_entry_price, "exit": trade_stop,
                                   "result": "SL", "pnl": trade_stop - trade_entry_price})
                    in_trade = False; continue
                if highs[i] >= trade_target:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i],
                                   "side": trade_side, "entry": trade_entry_price, "exit": trade_target,
                                   "result": "TP", "pnl": trade_target - trade_entry_price})
                    in_trade = False; continue
                if i - trade_entry_i >= 60:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i],
                                   "side": trade_side, "entry": trade_entry_price, "exit": closes[i],
                                   "result": "MTM", "pnl": closes[i] - trade_entry_price})
                    in_trade = False; continue
                continue
            else:  # short
                if highs[i] >= trade_stop:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i],
                                   "side": trade_side, "entry": trade_entry_price, "exit": trade_stop,
                                   "result": "SL", "pnl": trade_entry_price - trade_stop})
                    in_trade = False; continue
                if lows[i] <= trade_target:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i],
                                   "side": trade_side, "entry": trade_entry_price, "exit": trade_target,
                                   "result": "TP", "pnl": trade_entry_price - trade_target})
                    in_trade = False; continue
                if i - trade_entry_i >= 60:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i],
                                   "side": trade_side, "entry": trade_entry_price, "exit": closes[i],
                                   "result": "MTM", "pnl": trade_entry_price - closes[i]})
                    in_trade = False; continue
                continue

        # --- Entry signal ---
        if not is_active_session(ts):
            continue

        lookback = closes[i] - closes[i-30]
        abs_ret = abs(lookback)
        atr = atr14(highs, lows, closes, i)
        if atr <= 0 or abs_ret < 1.5 * atr:
            continue

        avg_vol = sum(vols[i-30:i]) / 30
        if vols[i] < 1.5 * avg_vol:
            continue

        today = ts[:10]
        day_trades = [t for t in trades if t["ts"][:10] == today]
        if len(day_trades) >= 2:
            continue

        side = "long" if lookback < 0 else "short"   # reversal: fade the move
        entry = closes[i]

        sum_cv = sum(closes[j] * vols[j] for j in range(i-30, i))
        sum_v  = sum(vols[j] for j in range(i-30, i))
        vwap = sum_cv / sum_v if sum_v > 0 else entry

        if side == "long":
            stop = entry - atr * SL_ATR
            target = entry + (vwap - entry) * 0.5
            if target <= entry or stop >= entry:
                continue
        else:
            stop = entry + atr * SL_ATR
            target = entry - (entry - vwap) * 0.5
            if target >= entry or stop <= entry:
                continue

        in_trade = True
        trade_entry_i = i
        trade_entry_price = entry
        trade_stop = stop
        trade_target = target
        trade_side = side

    return compute_stats(trades, symbol, "v3-reversal")

# ---------------------------------------------------------------------------
# Strategy 2: ret-30-momentum — applied to NQ
# ---------------------------------------------------------------------------
def backtest_ret30(bars, symbol):
    closes = [float(b["close"]) for b in bars]
    highs  = [float(b["high"]) for b in bars]
    lows   = [float(b["low"]) for b in bars]
    ts_list = [b["ts"] for b in bars]
    vols   = [float(b.get("volume", 0) or 0) for b in bars]

    trades = []
    in_trade = None

    for i in range(30, len(closes)):
        ts = ts_list[i]

        # --- Exit handling ---
        if in_trade:
            if in_trade["side"] == "long":
                if lows[i] <= in_trade["stop"]:
                    pnl = in_trade["stop"] - in_trade["entry"]
                    trades.append({**in_trade, "exit_i": i, "exit_px": in_trade["stop"], "pnl": round(pnl, 2), "result": "SL"})
                    in_trade = None; continue
                if highs[i] >= in_trade["target"]:
                    pnl = in_trade["target"] - in_trade["entry"]
                    trades.append({**in_trade, "exit_i": i, "exit_px": in_trade["target"], "pnl": round(pnl, 2), "result": "TP"})
                    in_trade = None; continue
                if i - in_trade["entry_i"] >= 30:
                    pnl = closes[i] - in_trade["entry"]
                    trades.append({**in_trade, "exit_i": i, "exit_px": closes[i], "pnl": round(pnl, 2), "result": "MTM"})
                    in_trade = None; continue
                continue
            else:  # short
                if highs[i] >= in_trade["stop"]:
                    pnl = in_trade["entry"] - in_trade["stop"]
                    trades.append({**in_trade, "exit_i": i, "exit_px": in_trade["stop"], "pnl": round(pnl, 2), "result": "SL"})
                    in_trade = None; continue
                if lows[i] <= in_trade["target"]:
                    pnl = in_trade["entry"] - in_trade["target"]
                    trades.append({**in_trade, "exit_i": i, "exit_px": in_trade["target"], "pnl": round(pnl, 2), "result": "TP"})
                    in_trade = None; continue
                if i - in_trade["entry_i"] >= 30:
                    pnl = in_trade["entry"] - closes[i]
                    trades.append({**in_trade, "exit_i": i, "exit_px": closes[i], "pnl": round(pnl, 2), "result": "MTM"})
                    in_trade = None; continue
                continue

        # --- Entry signal ---
        if not is_active_session(ts):
            continue

        ret_30 = closes[i] - closes[i-30]
        atr = atr14(highs, lows, closes, i)
        if atr <= 0 or abs(ret_30) < 0.5 * atr:
            continue

        avg_vol = sum(vols[i-30:i]) / 30
        if vols[i] < 1.2 * avg_vol:
            continue

        today = ts[:10]
        day_trades = [t for t in trades if t.get("ts", "")[:10] == today]
        if len(day_trades) >= 2:
            continue

        side = "long" if ret_30 > 0 else "short"   # momentum: go with the move
        entry = closes[i]

        lowest = min(lows[i-29:i+1]) if side == "long" else None
        highest = max(highs[i-29:i+1]) if side == "short" else None

        if side == "long":
            stop = max(lowest - atr, lowest)
            target = entry + max(abs(ret_30) * 0.5, atr * 1.5)
            if stop >= entry or target <= entry:
                continue
        else:
            stop = min(highest + atr, highest)
            target = entry - max(abs(ret_30) * 0.5, atr * 1.5)
            if stop <= entry or target >= entry:
                continue

        in_trade = {"entry_i": i, "ts": ts, "entry": entry, "stop": stop, "target": target, "side": side}

    return compute_stats(trades, symbol, "ret30-momentum")

# ---------------------------------------------------------------------------
# Shared stats computation
# ---------------------------------------------------------------------------
def compute_stats(trades, symbol, strategy_name):
    total = len(trades)
    if total == 0:
        return {"symbol": symbol, "strategy": strategy_name, "total_trades": 0, "total_pnl": 0}

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = sum(abs(t["pnl"]) for t in losses)
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else "inf"

    days = sorted(set(t["ts"][:10] for t in trades))
    day_pnl = {}
    for d in days:
        day_trades = [t for t in trades if t["ts"][:10] == d]
        day_pnl[d] = round(sum(t["pnl"] for t in day_trades), 2)

    cum = 0; peak = 0; dd = 0
    for t in trades:
        cum += t["pnl"]
        if cum > peak:
            peak = cum
        dd = min(dd, cum - peak)

    sl  = [t for t in trades if t["result"] == "SL"]
    tp  = [t for t in trades if t["result"] == "TP"]
    mtm = [t for t in trades if t["result"] == "MTM"]

    return {
        "symbol": symbol,
        "strategy": strategy_name,
        "total_trades": total,
        "win_rate_pct": round(len(wins) / total * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total, 2),
        "avg_win": round(gross_win / len(wins), 2) if wins else 0,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else 0,
        "profit_factor": pf,
        "max_drawdown": round(dd, 2),
        "sl_trades": len(sl),
        "tp_trades": len(tp),
        "mtm_trades": len(mtm),
        "daily_trades": round(total / len(days), 1) if days else 0,
        "day_pnl": day_pnl,
        "trades": trades,
    }

# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------
def print_strategy(r):
    if r["total_trades"] == 0:
        print(f"  {r['symbol']} ({r['strategy']}): 0 trades\n")
        return

    symbol_s = r['symbol']
    strat_s  = r['strategy']
    print(f"=== {symbol_s} — {strat_s} ({r['total_trades']} trades, {r['daily_trades']}/day) ===")
    print(f"  P&L:       ${r['total_pnl']:>8.2f}  | WR: {r['win_rate_pct']}%  | PF: {r['profit_factor']}")
    print(f"  Avg win:   ${r['avg_win']:>8.2f}  | Avg loss: ${r['avg_loss']:>8.2f}")
    print(f"  Max DD:    ${r['max_drawdown']:>8.2f}  | SL/TP/MTM: {r['sl_trades']}/{r['tp_trades']}/{r['mtm_trades']}")
    if r["day_pnl"]:
        print(f"  Day P&L:   {', '.join(f'{d}=${p}' for d, p in r['day_pnl'].items())}")
    print(f"  Trades:")
    for t in r["trades"]:
        ts_s = t["ts"][11:19]
        pnl_s = f"+${t['pnl']:.2f}" if t["pnl"] > 0 else f"-${abs(t['pnl']):.2f}"
        print(f"    {ts_s} | {t['side']:5s} | entry={t['entry']:.1f} | {pnl_s} | {t['result']}")
    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Research-only ES/NQ meta-strategy backtest.")
parser.add_argument("csv_path", nargs="?", default=DEFAULT_DATA)
args = parser.parse_args()
DATA = resolve_data_path(args.csv_path)

print("=" * 60)
print("  COMBINED META-STRATEGY BACKTEST")
print("  ES:  v3 short-term-reversal (fade the move)")
print("  NQ:  ret-30-momentum (go with the move)")
print("  MODE: research-only; ignores commissions/slippage unless added externally")
print("=" * 60)

with open(DATA) as f:
    rows = list(csv.DictReader(f))

by_sym = {}
for r in rows:
    by_sym.setdefault(r["symbol"], []).append(r)
missing = [symbol for symbol in ("ES", "NQ") if symbol not in by_sym]
if missing:
    raise SystemExit(f"Missing required symbols in CSV: {', '.join(missing)}")

print(f"\nData: {DATA}, {len(rows)} 1m bars\n")

# Run ES with v3 strategy
res_es = backtest_v3(by_sym["ES"], "ES")
print_strategy(res_es)

# Run NQ with ret30 strategy
res_nq = backtest_ret30(by_sym["NQ"], "NQ")
print_strategy(res_nq)

# ---------------------------------------------------------------------------
# Combined summary
# ---------------------------------------------------------------------------
results = [r for r in (res_es, res_nq) if r["total_trades"] > 0]
total_t = sum(r["total_trades"] for r in results)
total_pnl = round(sum(r["total_pnl"] for r in results), 2)

print("=" * 60)
print("COMBINED META-STRATEGY RESULTS")
print("=" * 60)

if total_t == 0:
    print("  0 total trades across both strategies.")
else:
    # Weighted win rate
    comb_wr = round(sum(r["total_trades"] * r["win_rate_pct"] for r in results) / total_t, 1)

    # Combined max drawdown (replay merged trade timeline)
    all_merged = []
    for r in results:
        for t in r["trades"]:
            all_merged.append((t["ts"], t["pnl"]))
    all_merged.sort(key=lambda x: x[0])

    cum = 0; peak = 0; comb_dd = 0
    for _, pnl in all_merged:
        cum += pnl
        if cum > peak: peak = cum
        comb_dd = min(comb_dd, cum - peak)

    # Combined day P&L
    all_days = sorted(set(t["ts"][:10] for r_ in results for t in r_["trades"]))
    comb_day_pnl = {}
    for d in all_days:
        dp = 0
        for r_ in results:
            dp += r_["day_pnl"].get(d, 0)
        comb_day_pnl[d] = round(dp, 2)

    # Avg trade
    avg_pnl = round(total_pnl / total_t, 2)

    print(f"  Total trades:   {total_t}")
    print(f"  Total P&L:      ${total_pnl:>8.2f}")
    print(f"  Avg trade:      ${avg_pnl:>8.2f}")
    print(f"  Win rate:       {comb_wr}%")
    print(f"  Max drawdown:   ${comb_dd:>8.2f}")
    print(f"  Combined day P&L: {', '.join(f'{d}=${p}' for d, p in comb_day_pnl.items())}")
    print()

    # Per-strategy breakdown
    print("Per-strategy:")
    for r in results:
        pf = r["profit_factor"]
        print(f"  {r['symbol']} ({r['strategy']}): {r['total_trades']}t  ${r['total_pnl']:>7.2f}  "
              f"WR={r['win_rate_pct']}%  PF={pf}")

    print()
    # Verdict
    if total_t < 20:
        print(f"VERDICT: INCONCLUSIVE — only {total_t} trades on 21d of data")
    elif total_pnl > 0:
        print(f"VERDICT: PROMISING (+${total_pnl:.0f}) — positive combined P&L over {total_t} trades")
    else:
        print(f"VERDICT: WEAK (${total_pnl:.0f}) — negative combined P&L")
