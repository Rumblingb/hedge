#!/usr/bin/env python3
"""
v3 short-term-reversal backtest v2 — proper position tracking, no overlapping trades.
Reads ES/NQ 1m data, applies v3 strategy logic, tracks cumulative P&L.
"""
import csv
from datetime import datetime

DATA = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv"
SL_ATR = 1.0

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

def backtest(bars, symbol):
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    ts_list = [b["ts"] for b in bars]
    vols = [float(b.get("volume", 0) or 0) for b in bars]

    trades = []
    in_trade = False
    trade_entry_i = -1
    trade_entry_price = 0
    trade_stop = 0
    trade_target = 0
    trade_side = ""
    trade_day = ""

    for i in range(30, len(closes)):
        ts = ts_list[i]
        
        # If in a trade, check for exit
        if in_trade:
            if trade_side == "long":
                if lows[i] <= trade_stop:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i], "side": trade_side,
                                   "entry": trade_entry_price, "exit": trade_stop, "result": "SL",
                                   "pnl": trade_stop - trade_entry_price})
                    in_trade = False
                    continue
                if highs[i] >= trade_target:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i], "side": trade_side,
                                   "entry": trade_entry_price, "exit": trade_target, "result": "TP",
                                   "pnl": trade_target - trade_entry_price})
                    in_trade = False
                    continue
                # Time stop: max 60 bars
                if i - trade_entry_i >= 60:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i], "side": trade_side,
                                   "entry": trade_entry_price, "exit": closes[i], "result": "MTM",
                                   "pnl": closes[i] - trade_entry_price})
                    in_trade = False
                    continue
                continue  # trade still open, don't check for new signals
            
            if trade_side == "short":
                if highs[i] >= trade_stop:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i], "side": trade_side,
                                   "entry": trade_entry_price, "exit": trade_stop, "result": "SL",
                                   "pnl": trade_entry_price - trade_stop})
                    in_trade = False
                    continue
                if lows[i] <= trade_target:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i], "side": trade_side,
                                   "entry": trade_entry_price, "exit": trade_target, "result": "TP",
                                   "pnl": trade_entry_price - trade_target})
                    in_trade = False
                    continue
                if i - trade_entry_i >= 60:
                    trades.append({"entry_i": trade_entry_i, "exit_i": i, "ts": ts_list[trade_entry_i], "side": trade_side,
                                   "entry": trade_entry_price, "exit": closes[i], "result": "MTM",
                                   "pnl": trade_entry_price - closes[i]})
                    in_trade = False
                    continue
                continue  # trade still open
        
        # Not in a trade — check for entry signal
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

        # Max 2 trades/day/symbol
        today = ts[:10]
        day_trades = [t for t in trades if t["ts"][:10] == today]
        if len(day_trades) >= 2:
            continue

        side = "long" if lookback < 0 else "short"
        entry = closes[i]
        
        sum_cv = sum(closes[j] * vols[j] for j in range(i-30, i))
        sum_v = sum(vols[j] for j in range(i-30, i))
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
        trade_day = today

    total = len(trades)
    if total == 0:
        return {"symbol": symbol, "total_trades": 0}

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = sum(abs(t["pnl"]) for t in losses)
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else "inf"
    
    # Per-day P&L
    days = sorted(set(t["ts"][:10] for t in trades))
    day_pnl = {}
    for d in days:
        day_trades = [t for t in trades if t["ts"][:10] == d]
        day_pnl[d] = round(sum(t["pnl"] for t in day_trades), 2)
    
    # Max drawdown
    cum = 0
    peak = 0
    dd = 0
    for t in trades:
        cum += t["pnl"]
        if cum > peak:
            peak = cum
        dd = min(dd, cum - peak)
    
    sl = [t for t in trades if t["result"] == "SL"]
    tp = [t for t in trades if t["result"] == "TP"]
    mtm = [t for t in trades if t["result"] == "MTM"]
    
    # R:R
    avg_rr = 0
    for t in trades:
        side = t["side"]
        if side == "long":
            risk = t["entry"] - trade_stop  # approximate
        else:
            risk = trade_stop - t["entry"]
    
    return {
        "symbol": symbol, "total_trades": total,
        "win_rate_pct": round(len(wins) / total * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total, 2),
        "avg_win": round(round(gross_win / len(wins), 2), 2) if wins else 0,
        "avg_loss": round(round(gross_loss / len(losses), 2), 2) if losses else 0,
        "profit_factor": pf, "max_drawdown": round(dd, 2),
        "sl_trades": len(sl), "tp_trades": len(tp), "mtm_trades": len(mtm),
        "daily_trades": round(total / len(days), 1) if days else 0,
        "day_pnl": day_pnl,
        "trades": trades,
    }

# Load
with open(DATA) as f:
    rows = list(csv.DictReader(f))
by_sym = {}
for r in rows:
    by_sym.setdefault(r["symbol"], []).append(r)

print(f"=== Short-Term Reversal v3 Backtest (position-tracked) ===\n")
print(f"Data: 5 trading days, {len(rows)} 1m bars\n")

all_results = []
for sym in ["ES", "NQ"]:
    r = backtest(by_sym[sym], sym)
    if r["total_trades"] == 0:
        print(f"{sym}: 0 trades")
        continue

    print(f"=== {sym} ({r['total_trades']} trades, {r['daily_trades']}/day) ===")
    print(f"  P&L:       ${r['total_pnl']:>8.2f}  | WR: {r['win_rate_pct']}%  | PF: {r['profit_factor']}")
    print(f"  Avg win:   ${r['avg_win']:>8.2f}  | Avg loss: ${r['avg_loss']:>8.2f}")
    print(f"  Max DD:    ${r['max_drawdown']:>8.2f}  | SL/TP/MTM: {r['sl_trades']}/{r['tp_trades']}/{r['mtm_trades']}")
    print(f"  Day P&L:   {', '.join(f'{d}=${p}' for d, p in r['day_pnl'].items())}")
    print(f"  Trades:")
    raw_trades = r["trades"]
    for t in raw_trades:
        ts_s = t["ts"][11:19]
        pnl_s = f"+${t['pnl']:.2f}" if t["pnl"] > 0 else f"-${abs(t['pnl']):.2f}"
        print(f"    {ts_s} | {t['side']:5s} | entry={t['entry']:.1f} | {pnl_s} | {t['result']}")
    print()
    all_results.append(r)

# Combined
total_t = sum(r["total_trades"] for r in all_results)
if total_t > 0:
    comb_pnl = round(sum(r["total_pnl"] for r in all_results), 2)
    comb_wr = round(sum(r["total_trades"] * r["win_rate_pct"] for r in all_results) / total_t, 1)
    print("=" * 50)
    print(f"COMBINED: {total_t} trades | ${comb_pnl:.2f} | {comb_wr}% WR")
    for r in all_results:
        pf = r["profit_factor"]
        print(f"  {r['symbol']}: {r['total_trades']}t ${r['total_pnl']:.2f} {r['win_rate_pct']}% PF={pf}")
    
    if total_t < 20:
        print(f"\nVERDICT: INCONCLUSIVE — only {total_t} trades on 5 days of data")
    elif comb_pnl > 0:
        print(f"\nVERDICT: PROMISING (+${comb_pnl:.0f}) — needs OOS validation on more data")
    else:
        print(f"\nVERDICT: WEAK (${comb_pnl:.0f}) — strategy not ready")
