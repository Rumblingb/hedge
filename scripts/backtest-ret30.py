#!/usr/bin/env python3
"""ret-30-momentum backtest — position-tracked, bar-by-bar exit."""
import csv
from datetime import datetime

DATA = "/Users/brain/hedge/data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv"
SL_ATR = 1.0

def is_active_session(ts):
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    h, m = dt.hour, dt.minute
    total = h * 60 + m
    return ((12*60+30) <= total <= (15*60+30)) or ((17*60) <= total <= (19*60+30))

def atr14(highs, lows, closes, i):
    trs = []
    for j in range(max(1, i-14), i):
        tr = max(highs[j] - lows[j], abs(highs[j] - closes[j-1]), abs(lows[j] - closes[j-1]))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0

def backtest(bars, sym):
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    ts_list = [b["ts"] for b in bars]
    vols = [float(b.get("volume", 0) or 0) for b in bars]

    trades = []
    in_trade = None

    for i in range(30, len(closes)):
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
            else:
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

        if not is_active_session(ts_list[i]):
            continue
        
        ret_30 = closes[i] - closes[i-30]
        atr = atr14(highs, lows, closes, i)
        if atr <= 0 or abs(ret_30) < 0.5 * atr:
            continue
        
        avg_vol = sum(vols[i-30:i]) / 30
        if vols[i] < 1.2 * avg_vol:
            continue

        today = ts_list[i][:10]
        day_trades = [t for t in trades if t.get("ts", "")[:10] == today]
        if len(day_trades) >= 2:
            continue

        side = "long" if ret_30 > 0 else "short"
        entry = closes[i]
        
        # Find lowest/highest in lookback
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

        in_trade = {"entry_i": i, "ts": ts_list[i], "entry": entry, "stop": stop, "target": target, "side": side}

    total = len(trades)
    if total == 0:
        return {"symbol": sym, "total_trades": 0}

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = sum(abs(t["pnl"]) for t in losses)
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else "inf"
    
    cum, peak, dd = 0, 0, 0
    for t in trades:
        cum += t["pnl"]
        if cum > peak: peak = cum
        dd = min(dd, cum - peak)
    
    sl = [t for t in trades if t["result"] == "SL"]
    tp = [t for t in trades if t["result"] == "TP"]
    mtm = [t for t in trades if t["result"] == "MTM"]
    days = sorted(set(t["ts"][:10] for t in trades))
    day_pnl = {d: round(sum(t["pnl"] for t in trades if t["ts"][:10] == d), 2) for d in days}
    
    return {
        "symbol": sym, "total_trades": total,
        "win_rate_pct": round(len(wins) / total * 100, 1),
        "total_pnl": round(total_pnl, 2), "avg_pnl": round(total_pnl / total, 2),
        "avg_win": round(gross_win / len(wins), 2) if wins else 0,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else 0,
        "profit_factor": pf, "max_drawdown": round(dd, 2),
        "sl_trades": len(sl), "tp_trades": len(tp), "mtm_trades": len(mtm),
        "daily_trades": round(total / len(days), 1) if days else 0,
        "day_pnl": day_pnl, "trades": trades,
    }

with open(DATA) as f:
    rows = list(csv.DictReader(f))
by_sym = {}
for r in rows:
    by_sym.setdefault(r["symbol"], []).append(r)

print("=== ret-30-momentum Backtest ===\n")

results = []
for sym in ["ES", "NQ"]:
    r = backtest(by_sym[sym], sym)
    if r["total_trades"] == 0:
        print(f"{sym}: 0 trades\n"); continue
    print(f"=== {sym} ({r['total_trades']} trades, {r['daily_trades']}/day) ===")
    print(f"  P&L:       ${r['total_pnl']:>8.2f}  | WR: {r['win_rate_pct']}%  | PF: {r['profit_factor']}")
    print(f"  Avg win:   ${r['avg_win']:>8.2f}  | Avg loss: ${r['avg_loss']:>8.2f}")
    print(f"  Max DD:    ${r['max_drawdown']:>8.2f}  | SL/TP/MTM: {r['sl_trades']}/{r['tp_trades']}/{r['mtm_trades']}")
    if r["day_pnl"]:
        print(f"  Day P&L:   {', '.join(f'{d}=${p}' for d, p in r['day_pnl'].items())}")
    for t in r["trades"]:
        ts_s = t["ts"][11:19]
        pnl_s = f"+${t['pnl']:.2f}" if t["pnl"] > 0 else f"-${abs(t['pnl']):.2f}"
        print(f"    {ts_s} | {t['side']:5s} | entry={t['entry']:.1f} | {pnl_s} | {t['result']}")
    print()
    results.append(r)

total_t = sum(r["total_trades"] for r in results)
if total_t > 0:
    comb_pnl = round(sum(r["total_pnl"] for r in results), 2)
    comb_wr = round(sum(r["total_trades"] * r["win_rate_pct"] for r in results) / total_t, 1)
    print("=" * 50)
    print(f"COMBINED: {total_t} trades | ${comb_pnl:.2f} | {comb_wr}% WR")
    for r in results:
        print(f"  {r['symbol']}: {r['total_trades']}t ${r['total_pnl']:.2f} {r['win_rate_pct']}% PF={r['profit_factor']}")
    if total_t < 20:
        print(f"\nVERDICT: INCONCLUSIVE — only {total_t} trades")
    elif comb_pnl > 0:
        print(f"\nVERDICT: PROMISING (+${comb_pnl:.0f})")
    else:
        print(f"\nVERDICT: WEAK (${comb_pnl:.0f})")
