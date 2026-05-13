//! param_sweep.rs — Parameter sweep for orb-breakout strategy
//! Tests different combinations of: range_window, vol_threshold, exit_offset
//! USAGE: cargo run --bin param_sweep -- <csv_path> --symbol NQ

use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::collections::HashMap;

#[derive(Debug, Clone)]
struct Bar { ts: String, symbol: String, open: f64, high: f64, low: f64, close: f64, volume: u64, }

#[derive(Debug, Clone)]
struct Trade { entry: f64, exit: f64, r_multiple: f64, }

fn run_orb_breakout(bars: &[Bar], range_window: usize, vol_threshold: f64, exit_offset: usize) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    if n < range_window + exit_offset + 14 { return trades; }
    
    for i in range_window..n - exit_offset {
        let range_high = bars[0..range_window].iter().map(|b| b.high).fold(0.0_f64, f64::max);
        let range_low = bars[0..range_window].iter().map(|b| b.low).fold(f64::MAX, f64::min);
        let range = range_high - range_low;
        if range <= 0.0 { continue; }
        
        // vol lookback: max(14, range_window)
        let vol_lookback = std::cmp::max(14, range_window);
        if i < vol_lookback + 2 { continue; }
        
        let avg_vol: f64 = bars[i-10..i].iter().map(|b| b.volume as f64).sum::<f64>() / 10.0;
        if avg_vol <= 0.0 { continue; }
        
        let atr_val = bars[i-vol_lookback..i].iter().map(|b| b.high - b.low).sum::<f64>() / vol_lookback as f64;
        if atr_val <= 0.0 { continue; }
        
        let exit = bars[i + exit_offset].close;
        
        if bars[i].close > range_high && bars[i].volume as f64 > avg_vol * vol_threshold {
            // LONG: price broke above range, expect continuation up
            let rr = (exit - bars[i].close) / atr_val;
            trades.push(Trade { entry: bars[i].close, exit, r_multiple: rr });
        } else if bars[i].close < range_low && bars[i].volume as f64 > avg_vol * vol_threshold {
            // SHORT: price broke below range, expect continuation down
            let rr = (bars[i].close - exit) / atr_val;
            trades.push(Trade { entry: bars[i].close, exit, r_multiple: rr });
        }
    }
    trades
}

fn report(trades: &[Trade], label: &str) {
    if trades.is_empty() { println!("  {}: 0 trades", label); return; }
    let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
    let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
    let losses = trades.iter().filter(|t| t.r_multiple <= 0.0).count();
    let total = trades.len();
    let wr = wins as f64 / total as f64 * 100.0;
    println!("  {}: {} trades, {}/{} W/L ({:.1}%), total R {:.2}", label, total, wins, losses, wr, total_r);
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
    
    println!("=== ORB-BREAKOUT PARAM SWEEP ===");
    println!("Symbol: {}, Bars: {}", target_symbol, all_bars.len());
    println!();
    
    // Default params
    let default_window = 12usize;
    let default_vol = 1.3_f64;
    let default_exit = 5usize;
    
    // Sweep range window
    println!("--- Sweep: range_window (vol={}, exit={}) ---", default_vol, default_exit);
    for w in &[6, 8, 10, 12, 14, 16, 20, 25] {
        let t = run_orb_breakout(&all_bars, *w, default_vol, default_exit);
        report(&t, &format!("window={}", w));
    }
    
    // Sweep vol threshold
    println!();
    println!("--- Sweep: vol_threshold (window={}, exit={}) ---", default_window, default_exit);
    for v in &[1.0, 1.1, 1.2, 1.3, 1.5, 1.8, 2.0, 2.5, 3.0] {
        let t = run_orb_breakout(&all_bars, default_window, *v, default_exit);
        report(&t, &format!("vol={:.1}", v));
    }
    
    // Sweep exit offset
    println!();
    println!("--- Sweep: exit_offset (window={}, vol={}) ---", default_window, default_vol);
    for e in &[1, 2, 3, 5, 8, 10, 15] {
        let t = run_orb_breakout(&all_bars, default_window, default_vol, *e);
        report(&t, &format!("exit={}", e));
    }
    
    // Best combo: test top 3 from each sweep
    println!();
    println!("--- BEST COMBOS ---");
    let best_windows = [12, 14, 16];
    let best_vols = [1.3, 1.5, 2.0];
    let best_exits = [3, 5, 8];
    
    let mut all_combos: Vec<(String, Vec<Trade>)> = Vec::new();
    for w in &best_windows {
        for v in &best_vols {
            for e in &best_exits {
                let t = run_orb_breakout(&all_bars, *w, *v, *e);
                all_combos.push((format!("w{}_v{}_e{}", w, v, e), t));
            }
        }
    }
    all_combos.sort_by(|a, b| {
        let ra: f64 = a.1.iter().map(|t| t.r_multiple).sum();
        let rb: f64 = b.1.iter().map(|t| t.r_multiple).sum();
        rb.partial_cmp(&ra).unwrap_or(std::cmp::Ordering::Equal)
    });
    
    for (label, trades) in &all_combos {
        report(trades, label);
    }
    
    // Print best
    if let Some((best_label, best_trades)) = all_combos.first() {
        let best_r: f64 = best_trades.iter().map(|t| t.r_multiple).sum();
        let best_wins = best_trades.iter().filter(|t| t.r_multiple > 0.0).count();
        let best_total = best_trades.len();
        let best_wr = best_wins as f64 / best_total as f64 * 100.0;
        println!();
        println!("=== BEST: {} ===", best_label);
        println!("Trades: {}, WR: {:.1}%, Total R: {:.2}", best_total, best_wr, best_r);
    }
    
    Ok(())
}
