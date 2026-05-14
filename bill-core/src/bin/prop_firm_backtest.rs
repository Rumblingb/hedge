//! prop_firm_backtest.rs — Strategy backtest with Topstep + Lucid Trading prop firm compliance
//!
//! Extends full_strategy_pipeline with:
//! - Per-day P&L aggregation (EOD settlement)
//! - Trailing drawdown from peak equity (EOD)
//! - Best day % of total profit (consistency rule)
//! - Days to pass $50K combine
//!
//! SIMULATES:
//! - Topstep $50K ($3,000 target, $2,000 DD, 50% consistency, 2-day min)
//! - LucidFlex $50K ($3,000 target, $2,000 MLL, 50% eval consistency, 0% funded, no min days)
//! - LucidPro $50K ($3,000 target, $2,000 MLL, 40% eval consistency, soft DLL $1,000, no min days)
//!
//! USAGE: cargo run --bin prop_firm_backtest -- <csv_path> --symbol NQ

use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::collections::HashMap;

#[derive(Debug, Clone)]
struct Bar { ts: String, symbol: String, open: f64, high: f64, low: f64, close: f64, volume: u64, }

#[derive(Debug, Clone)]
struct Trade { entry: f64, exit: f64, r_multiple: f64, side: String, entry_ts: String, }

/// Prop firm config — same $50K account size, different rules
struct PropFirmConfig {
    name: &'static str,
    profit_target: f64,       // $3,000 for $50K
    max_drawdown: f64,        // $2,000 MLL
    max_best_day_pct: f64,    // 50% Topstep/Flex, 40% LucidPro
    min_trading_days: usize,  // 2 for Topstep, 0 for Lucid
    daily_loss_limit: f64,    // 0 = none, $1,000 for LucidPro (soft breach)
}

const PROP_FIRMS: &[PropFirmConfig] = &[
    PropFirmConfig {
        name: "Topstep $50K",
        profit_target: 3000.0,
        max_drawdown: 2000.0,
        max_best_day_pct: 0.50,
        min_trading_days: 2,
        daily_loss_limit: 0.0,
    },
    PropFirmConfig {
        name: "LucidFlex $50K",
        profit_target: 3000.0,
        max_drawdown: 2000.0,
        max_best_day_pct: 0.50,
        min_trading_days: 0,
        daily_loss_limit: 0.0,
    },
    PropFirmConfig {
        name: "LucidPro $50K",
        profit_target: 3000.0,
        max_drawdown: 2000.0,
        max_best_day_pct: 0.40,
        min_trading_days: 0,
        daily_loss_limit: 1000.0,
    },
];

const POINT_VALUE_NQ: f64 = 20.0;
const COMMISSION_PER_TRADE: f64 = 5.0;

fn parse_date(ts: &str) -> String {
    ts.chars().take(10).collect()
}

fn run_orb_breakout(bars: &[Bar], range_window: usize, vol_threshold: f64, exit_offset: usize) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    let min_bars = std::cmp::max(range_window + exit_offset + 14, 30);
    if n < min_bars { return trades; }

    for i in range_window.max(14)..n - exit_offset {
        let range_high = bars[0..range_window].iter().map(|b| b.high).fold(0.0_f64, f64::max);
        let range_low = bars[0..range_window].iter().map(|b| b.low).fold(f64::MAX, f64::min);
        let range = range_high - range_low;
        if range <= 0.0 { continue; }

        let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
        if avg_vol <= 0.0 { continue; }
        if (bars[i].volume as f64) < avg_vol * vol_threshold { continue; }

        if bars[i].close > range_high {
            let exit = bars[i + exit_offset].close;
            let rr = (exit - bars[i].close) / (bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0);
            trades.push(Trade { entry: bars[i].close, exit, r_multiple: rr, side: "long".into(), entry_ts: bars[i].ts.clone() });
        } else if bars[i].close < range_low {
            let exit = bars[i + exit_offset].close;
            let rr = (bars[i].close - exit) / (bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0);
            trades.push(Trade { entry: bars[i].close, exit, r_multiple: rr, side: "short".into(), entry_ts: bars[i].ts.clone() });
        }
    }
    trades
}

fn run_wq_trend_mom(bars: &[Bar], exit_offset: usize, stop_atr: f64, target_atr: f64) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    if n < 60 { return trades; }

    for i in 40..n - exit_offset {
        let sma20: f64 = bars[i-20..i].iter().map(|b| b.close).sum::<f64>() / 20.0;
        let sma50: f64 = if i >= 50 { bars[i-50..i].iter().map(|b| b.close).sum::<f64>() / 50.0 } else { continue; };
        let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
        if avg_vol <= 0.0 { continue; }
        let vol_ratio = bars[i].volume as f64 / avg_vol;
        if vol_ratio < 1.3 { continue; }

        let atr_val = bars[i-14..i].iter().map(|b| b.high - b.low).sum::<f64>() / 14.0;
        if atr_val <= 0.0 { continue; }

        let entry = bars[i].close;
        let mut exit = bars[i + exit_offset].close;

        if bars[i].close > sma20 && sma20 > sma50 {
            // LONG
            if stop_atr > 0.0 {
                let stop = entry - stop_atr * atr_val;
                let target = entry + target_atr * atr_val;
                exit = exit.min(stop);
                let exit_high = bars[i + exit_offset].high;
                if exit_high >= target { exit = target; }
            }
            let rr = (exit - entry) / atr_val;
            trades.push(Trade { entry, exit, r_multiple: rr, side: "long".into(), entry_ts: bars[i].ts.clone() });
        } else if bars[i].close < sma20 && sma20 < sma50 {
            // SHORT
            if stop_atr > 0.0 {
                let stop = entry + stop_atr * atr_val;
                let target = entry - target_atr * atr_val;
                exit = exit.max(stop);
                let exit_low = bars[i + exit_offset].low;
                if exit_low <= target { exit = target; }
            }
            let rr = (entry - exit) / atr_val;
            trades.push(Trade { entry, exit, r_multiple: rr, side: "short".into(), entry_ts: bars[i].ts.clone() });
        }
    }
    trades
}

fn simulate_prop_firm(
    trades: &[Trade],
    cfg: &PropFirmConfig,
    point_value: f64,
    days: &[&String],
    daily_pnl: &HashMap<String, f64>,
) {
    if trades.is_empty() {
        println!("  {}: 0 trades — skipping", cfg.name);
        return;
    }

    let total = trades.len();
    let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
    let wr = wins as f64 / total as f64 * 100.0;
    let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
    let avg_r = total_r / total as f64;

    // Best day % of total profit
    let total_profit: f64 = daily_pnl.values().filter(|&&v| v > 0.0).sum();
    let best_day_profit = daily_pnl.values().fold(0.0_f64, |a, &b| a.max(b));
    let consistency_ratio = if total_profit > 0.0 { best_day_profit / total_profit } else { 0.0 };
    let consistency_pass = consistency_ratio <= cfg.max_best_day_pct;

    // Combine simulation
    let mut sim_equity = 0.0_f64;
    let mut sim_peak = 0.0_f64;
    let mut days_to_target = 0;
    let mut passed = false;
    let mut failed_dd = false;
    let mut dll_breached = false;

    for day in days.iter() {
        let pnl = daily_pnl.get(*day).unwrap_or(&0.0);

        // Daily loss limit (LucidPro soft breach)
        if cfg.daily_loss_limit > 0.0 && *pnl < -cfg.daily_loss_limit {
            dll_breached = true;
            // Soft breach: skip rest of day, account lives
        }

        sim_equity += pnl;
        if sim_equity > sim_peak { sim_peak = sim_equity; }
        let dd = sim_peak - sim_equity;
        if dd > cfg.max_drawdown { failed_dd = true; break; }
        days_to_target += 1;
        if sim_equity >= cfg.profit_target && days_to_target >= cfg.min_trading_days {
            // Also check consistency at pass time
            let run_total_profit: f64 = daily_pnl.values().take(days.len()).filter(|&&v| v > 0.0).sum();
            let run_best_day = daily_pnl.values().take(days.len()).fold(0.0_f64, |a, &b| a.max(b));
            let run_consistency = if run_total_profit > 0.0 { run_best_day / run_total_profit } else { 0.0 };
            if run_consistency <= cfg.max_best_day_pct {
                passed = true;
                break;
            }
            // If consistency fails, keep going
        }
    }

    println!("── {} ──", cfg.name);
    println!("  Trades: {}, WR: {:.1}%", total, wr);
    println!("  Total R: {:.2}, Avg R: {:.2}", total_r, avg_r);
    let gross_pnl: f64 = trades.iter().map(|t| {
        let pts = (t.entry - t.exit).abs();
        let side_mult = if t.r_multiple > 0.0 { 1.0 } else { -1.0 };
        pts * point_value * side_mult
    }).sum();
    let net_pnl = gross_pnl - total as f64 * COMMISSION_PER_TRADE;
    println!("  Net PnL: ${:.0} (${:.0} gross, {} trades × ${} comm)", net_pnl, gross_pnl, total, COMMISSION_PER_TRADE as i32);
    println!("  Trading days: {}", days.len());
    println!("  Best day: ${:.0} / ${:.0} total profit ({:.1}%)", best_day_profit, total_profit, consistency_ratio * 100.0);

    if dll_breached {
        println!("  ⚠️  DLL: soft breach (LucidPro $1K/day) — account lives");
    }

    let gross_pnl_abs = gross_pnl.abs();
    let max_dd_val = (0..days.len()).scan(0.0_f64, |peak, i| {
        let eq: f64 = days[..=i].iter().map(|d| daily_pnl.get(*d).unwrap_or(&0.0)).sum();
        if eq > *peak { *peak = eq; }
        Some(*peak - eq)
    }).fold(0.0_f64, f64::max);
    let peak_val = days.iter().scan(0.0_f64, |peak, d| {
        let eq: f64 = days[..1].iter().map(|x| daily_pnl.get(*x).unwrap_or(&0.0)).sum();
        if eq > *peak { *peak = eq; }
        Some(*peak)
    }).last().unwrap_or(0.0);
    let max_dd_pct = if peak_val > 0.0 { max_dd_val / peak_val * 100.0 } else { 0.0 };
    println!("  Max EOD drawdown: ${:.0}", max_dd_val);

    if consistency_pass {
        println!("  Consistency: ✅ {:.1}% ≤ {}% rule", consistency_ratio * 100.0, cfg.max_best_day_pct * 100.0);
    } else {
        println!("  Consistency: ❌ {:.1}% > {}% rule", consistency_ratio * 100.0, cfg.max_best_day_pct * 100.0);
    }

    if passed {
        println!("  🏆 PASS: ${:.0} in {} trading days (target: ${:.0})", sim_equity, days_to_target, cfg.profit_target);
        println!("  ️ Days needed: {}/{}", days_to_target, days.len());
    } else if failed_dd {
        println!("  💀 FAIL: trailing DD exceeded ${:.0} in {} days", cfg.max_drawdown, days_to_target);
    } else if days_to_target >= days.len() {
        println!("  ⏳ INCOMPLETE: ${:.0} in {} days (needs ${:.0})", sim_equity, days_to_target, cfg.profit_target);
    } else {
        println!("  ⏳ INCOMPLETE: ${:.0} in {} days — hit consistency cap", sim_equity, days_to_target);
    }
    println!("  ️ Days simulated: {}/{}", days_to_target, days.len());
    println!();
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    let csv_path = args.get(1).map(|s| s.as_str()).unwrap_or("data/free/ALL-2MARKETS-NQ-ES-1m-21d-normalized-15m.csv");
    let target_symbol = args.iter().position(|a| a == "--symbol").and_then(|i| args.get(i+1)).map(|s| s.as_str()).unwrap_or("NQ");

    let file = File::open(csv_path)?;
    let reader = BufReader::new(file);
    let mut all_bars: Vec<Bar> = Vec::new();

    for line in reader.lines().skip(1) {
        let line = line?;
        let parts: Vec<&str> = line.split(',').collect();
        if parts.len() >= 7 {
            let symbol = parts[1].trim().to_uppercase();
            if symbol == target_symbol {
                all_bars.push(Bar {
                    ts: parts[0].trim().to_string(), symbol,
                    open: parts[2].parse::<f64>().unwrap_or(0.0),
                    high: parts[3].parse::<f64>().unwrap_or(0.0),
                    low: parts[4].parse::<f64>().unwrap_or(0.0),
                    close: parts[5].parse::<f64>().unwrap_or(0.0),
                    volume: parts[6].parse::<u64>().unwrap_or(0),
                });
            }
        }
    }

    let point_value = if target_symbol == "NQ" { 20.0 } else if target_symbol == "ES" { 50.0 } else { 10.0 };

    println!("=== PROP FIRM BACKTEST ===");
    println!("Target: {} (${}/pt), CSV: {}, Bars: {}", target_symbol, point_value, csv_path, all_bars.len());
    println!("Prop firms simulated: {}", PROP_FIRMS.len());
    for cfg in PROP_FIRMS {
        println!("  {} — target=${}, max_dd=${}, consistency≤{}%, min_days={}, DLL=${}",
            cfg.name, cfg.profit_target as i32, cfg.max_drawdown as i32,
            (cfg.max_best_day_pct * 100.0) as i32, cfg.min_trading_days,
            cfg.daily_loss_limit as i32);
    }
    println!();

    let strategies: Vec<(&str, Vec<Trade>)> = vec![
        ("orb-breakout (w12_v1.3_e5)", run_orb_breakout(&all_bars, 12, 1.3, 5)),
        ("orb-breakout (w16_v1.3_e8)", run_orb_breakout(&all_bars, 16, 1.3, 8)),
        ("orb-breakout (w12_v1.3_e8)", run_orb_breakout(&all_bars, 12, 1.3, 8)),
        ("wq-trend-mom (e5, noSL)", run_wq_trend_mom(&all_bars, 5, 0.0, 0.0)),
        ("wq-trend-mom (e8, noSL)", run_wq_trend_mom(&all_bars, 8, 0.0, 0.0)),
        ("wq-trend-mom (e5, SL1.5, TP3.0)", run_wq_trend_mom(&all_bars, 5, 1.5, 3.0)),
        ("wq-trend-mom (e8, SL1.5, TP3.0)", run_wq_trend_mom(&all_bars, 8, 1.5, 3.0)),
        ("wq-trend-mom (e5, SL2.0, TP4.0)", run_wq_trend_mom(&all_bars, 5, 2.0, 4.0)),
        ("wq-trend-mom (e8, SL2.0, TP4.0)", run_wq_trend_mom(&all_bars, 8, 2.0, 4.0)),
    ];

    for (name, trades) in &strategies {
        if trades.is_empty() { println!("── {} ──\n  0 trades for any prop firm — no signal\n", name); continue; }

        // Per-day aggregation
        let mut daily_pnl: HashMap<String, f64> = HashMap::new();
        for t in trades {
            let day = parse_date(&t.entry_ts);
            let pts = (t.entry - t.exit).abs();
            let side_mult = if t.r_multiple > 0.0 { 1.0 } else { -1.0 };
            *daily_pnl.entry(day.clone()).or_insert(0.0) += pts * point_value * side_mult;
        }

        let mut days: Vec<&String> = daily_pnl.keys().collect();
        days.sort();

        // Aggregate stats (shared across all prop firms — same trades)
        let total = trades.len();
        let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
        let wr = wins as f64 / total as f64 * 100.0;
        let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
        let avg_r = total_r / total as f64;

        println!("── {} ──", name);
        println!("  Trades: {}, WR: {:.1}%, Total R: {:.2}, Avg R: {:.2}, Trading days: {}",
            total, wr, total_r, avg_r, days.len());
        println!();

        // Simulate each prop firm
        for cfg in PROP_FIRMS {
            simulate_prop_firm(trades, cfg, point_value, &days, &daily_pnl);
        }
    }

    Ok(())
}
