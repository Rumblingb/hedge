//! prop_firm_backtest.rs — Strategy backtest with Topstep prop firm compliance metrics
//!
//! Extends full_strategy_pipeline with:
//! - Per-day P&L aggregation (EOD settlement)
//! - Trailing drawdown from peak equity
//! - Best day % of total profit (consistency rule)
//! - Days to pass $50K combine ($3,000 target, $2,000 max DD)
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

// Topstep $50K combine constants
const PROFIT_TARGET: f64 = 3000.0;
const MAX_DRAWDOWN: f64 = 2000.0;
const MAX_BEST_DAY_PCT: f64 = 0.50;
const POINT_VALUE_NQ: f64 = 20.0;
const COMMISSION_PER_TRADE: f64 = 5.0;

fn parse_date(ts: &str) -> String {
    // CSV format: "YYYY-MM-DD HH:MM:SS+00" or similar
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

fn run_wq_trend_mom(bars: &[Bar], exit_offset: usize) -> Vec<Trade> {
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
        let exit = bars[i + exit_offset].close;
        
        if bars[i].close > sma20 && sma20 > sma50 {
            let rr = (exit - bars[i].close) / atr_val;
            trades.push(Trade { entry: bars[i].close, exit, r_multiple: rr, side: "long".into(), entry_ts: bars[i].ts.clone() });
        } else if bars[i].close < sma20 && sma20 < sma50 {
            let rr = (bars[i].close - exit) / atr_val;
            trades.push(Trade { entry: bars[i].close, exit, r_multiple: rr, side: "short".into(), entry_ts: bars[i].ts.clone() });
        }
    }
    trades
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
    println!("Target: NQ (${}/pt), CSV: {}, Bars: {}", point_value, csv_path, all_bars.len());
    println!("Combine: $50K ($3,000 target, $2,000 DD, best day ≤{}%)", MAX_BEST_DAY_PCT * 100.0);
    println!();
    
    let strategies: Vec<(&str, Vec<Trade>)> = vec![
        ("orb-breakout (w12_v1.3_e5)", run_orb_breakout(&all_bars, 12, 1.3, 5)),
        ("orb-breakout (w16_v1.3_e8)", run_orb_breakout(&all_bars, 16, 1.3, 8)),
        ("orb-breakout (w12_v1.3_e8)", run_orb_breakout(&all_bars, 12, 1.3, 8)),
        ("wq-trend-mom (e5)", run_wq_trend_mom(&all_bars, 5)),
        ("wq-trend-mom (e8)", run_wq_trend_mom(&all_bars, 8)),
    ];
    
    for (name, trades) in &strategies {
        if trades.is_empty() { println!("{}: 0 trades — skipping", name); continue; }
        
        // Basic stats
        let total = trades.len();
        let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
        let losses = trades.iter().filter(|t| t.r_multiple <= 0.0).count();
        let wr = wins as f64 / total as f64 * 100.0;
        let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
        let avg_r = total_r / total as f64;
        
        // Dollar P&L (1 MNQ micro = $2/point, but let's use full NQ $20)
        let gross_pnl: f64 = trades.iter().map(|t| {
            let pts = (t.entry - t.exit).abs();
            let side_mult = if t.r_multiple > 0.0 { 1.0 } else { -1.0 };
            pts * point_value * side_mult
        }).sum();
        let net_pnl = gross_pnl - total as f64 * COMMISSION_PER_TRADE;
        
        // Per-day aggregation (Topstep EOD settlement)
        let mut daily_pnl: HashMap<String, f64> = HashMap::new();
        let mut daily_trades: HashMap<String, usize> = HashMap::new();
        for t in trades {
            let day = parse_date(&t.entry_ts);
            let pts = (t.entry - t.exit).abs();
            let side_mult = if t.r_multiple > 0.0 { 1.0 } else { -1.0 };
            *daily_pnl.entry(day.clone()).or_insert(0.0) += pts * point_value * side_mult;
            *daily_trades.entry(day.clone()).or_insert(0) += 1;
        }
        
        // Sort days by date
        let mut days: Vec<&String> = daily_pnl.keys().collect();
        days.sort();
        
        // Trailing drawdown from peak equity
        let mut peak_equity = 0.0_f64;
        let mut current_equity = 0.0_f64;
        let mut max_dd = 0.0_f64;
        let mut max_dd_pct = 0.0_f64;
        
        for day in &days {
            let pnl = daily_pnl.get(*day).unwrap_or(&0.0);
            current_equity += pnl;
            if current_equity > peak_equity {
                peak_equity = current_equity;
            }
            let dd = peak_equity - current_equity;
            if dd > max_dd { max_dd = dd; }
            if peak_equity > 0.0 {
                let dd_pct = dd / peak_equity;
                if dd_pct > max_dd_pct { max_dd_pct = dd_pct; }
            }
        }
        
        // Best day % of total profit
        let total_profit: f64 = daily_pnl.values().filter(|&&v| v > 0.0).sum();
        let best_day_profit = daily_pnl.values().fold(0.0_f64, |a, &b| a.max(b));
        let consistency_ratio = if total_profit > 0.0 { best_day_profit / total_profit } else { 0.0 };
        let consistency_pass = consistency_ratio <= MAX_BEST_DAY_PCT;
        
        // Combine simulation: how many days to pass $50K combine?
        let mut sim_equity = 0.0_f64;
        let mut sim_peak = 0.0_f64;
        let mut days_to_target = 0;
        let mut passed = false;
        let mut failed_dd = false;
        
        for day in days.iter() {
            let pnl = daily_pnl.get(*day).unwrap_or(&0.0);
            sim_equity += pnl;
            if sim_equity > sim_peak { sim_peak = sim_equity; }
            let dd = sim_peak - sim_equity;
            if dd > MAX_DRAWDOWN { failed_dd = true; break; }
            days_to_target += 1;
            if sim_equity >= PROFIT_TARGET {
                passed = true;
                break;
            }
        }
        
        println!("── {} ──", name);
        println!("  Trades: {}, WR: {:.1}%", total, wr);
        println!("  Total R: {:.2}, Avg R: {:.2}", total_r, avg_r);
        println!("  Net PnL: ${:.0} (${:.0} gross, {} trades × ${} comm)", net_pnl, gross_pnl, total, COMMISSION_PER_TRADE as i32);
        println!("  Trading days: {}", days.len());
        println!("  Max EOD drawdown: ${:.0} ({:.1}% from peak)", max_dd, max_dd_pct * 100.0);
        println!("  Best day: ${:.0} / ${:.0} total profit ({:.1}%)", best_day_profit, total_profit, consistency_ratio * 100.0);
        println!("  Consistency rule: {} (≤50%: {})", 
            if consistency_pass { "✅ PASS" } else { "❌ FAIL" },
            if consistency_pass { "met" } else { "violated" }
        );
        
        if passed {
            println!("  🏆 COMBINE PASS: ${:.0} in {} trading days", sim_equity, days_to_target);
            println!("  ️ Best day: {:.1}% of total — within 50% rule", consistency_ratio * 100.0);
        } else if failed_dd {
            println!("  💀 COMBINE FAILED: trailing DD exceeded $2,000 in {} days", days_to_target);
        } else {
            println!("  ⏳ INCOMPLETE: ${:.0} in {} days (needs $3,000 target)", sim_equity, days_to_target);
        }
        println!("  ️ Days simulated: {}/{}", days_to_target, days.len());
        println!();
    }
    
    Ok(())
}
