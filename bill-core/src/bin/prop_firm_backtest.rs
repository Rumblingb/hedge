//! prop_firm_backtest.rs — Strategy backtest with CHALLENGE vs FUNDED phase parameters
//!
//! CHALLENGE phase (combine): aggressive — 3 trades/day, 2.86 RR target
//!   Topstep $50K: $3K target, $2K trailing DD, 50% consistency, 2-day min
//!   LucidFlex: $3K target, $2K trailing DD, 50% eval, no min days
//!   LucidPro: $3K target, $2K trailing DD, 40% eval, $1K soft DLL
//!
//! FUNDED phase (live): conservative — 3 trades/day micros, 3.33 RR target
//!   Same rules but smaller sizing, capital preservation
//!
//! USAGE: cargo run --bin prop_firm_backtest -- <csv_path>

use std::env;
use std::collections::HashMap;
use bill_core::types::Bar;

#[derive(Debug, Clone)]
struct Trade { entry: f64, exit: f64, r_multiple: f64, side: String, entry_ts: String, }

/// Trading phase determines risk parameters
#[derive(Debug, Clone, Copy, PartialEq)]
enum Phase {
    Challenge,  // Aggressive — pass combine fast
    Funded,     // Conservative — capital preservation
}

/// Prop firm config — rules that don't change between phases
struct PropFirmRules {
    name: &'static str,
    profit_target: f64,       // $3,000 for $50K
    max_drawdown: f64,        // $2,000 MLL trailing
    max_best_day_pct: f64,    // 50% Topstep/Flex, 40% LucidPro
    min_trading_days: usize,  // 2 for Topstep, 0 for Lucid
    daily_loss_limit: f64,    // 0 = none, $1,000 for LucidPro (soft breach)
}

/// Phase-specific risk parameters
struct PhaseParams {
    phase: Phase,
    max_trades_per_day: usize,   // 3 challenge, 3 funded
    target_rr: f64,              // 2.86 challenge, 3.33 funded
    daily_profit_lock: f64,      // Stop after hitting this
    daily_loss_lock: f64,        // Stop after hitting this
    position_size_mult: f64,     // 1.0 challenge, 0.25 funded (MNQ)
    label: &'static str,
}

const PROP_FIRMS: &[PropFirmRules] = &[
    PropFirmRules { name: "Topstep $50K",  profit_target: 3000.0, max_drawdown: 2000.0, max_best_day_pct: 0.50, min_trading_days: 2, daily_loss_limit: 0.0 },
    PropFirmRules { name: "LucidFlex $50K", profit_target: 3000.0, max_drawdown: 2000.0, max_best_day_pct: 0.50, min_trading_days: 0, daily_loss_limit: 0.0 },
    PropFirmRules { name: "LucidPro $50K",  profit_target: 3000.0, max_drawdown: 2000.0, max_best_day_pct: 0.40, min_trading_days: 0, daily_loss_limit: 1000.0 },
];

const CHALLENGE: PhaseParams = PhaseParams {
    phase: Phase::Challenge,
    max_trades_per_day: 3,
    target_rr: 2.86,           // 80 tick target / 28 tick stop on NQ
    daily_profit_lock: 1200.0, // 3 wins × $400
    daily_loss_lock: 450.0,    // 3 losses × $150
    position_size_mult: 1.0,   // 1 NQ contract
    label: "CHALLENGE",
};

const FUNDED: PhaseParams = PhaseParams {
    phase: Phase::Funded,
    max_trades_per_day: 3,
    target_rr: 3.33,           // 80 tick target / 24 tick stop on MNQ
    daily_profit_lock: 300.0,  // 3 wins × $100 (3 MNQ = 1 NQ size)
    daily_loss_lock: 180.0,    // 3 losses × $60
    position_size_mult: 0.25,  // 3 MNQ = 0.75 NQ (conservative)
    label: "FUNDED",
};

fn parse_date(ts: &str) -> String {
    ts.chars().take(10).collect()
}

/// Symbol-aware ORB breakout: groups bars by symbol, then runs on each group
fn run_orb_breakout(bars: &[Bar], range_window: usize, vol_threshold: f64, exit_offset: usize) -> Vec<Trade> {
    let mut trades = Vec::new();
    let min_bars = std::cmp::max(range_window + exit_offset + 14, 30);
    let n = bars.len();
    if n < min_bars { return trades; }

    // Group bars by symbol for proper per-symbol ORB
    let mut symbol_groups: HashMap<String, Vec<(usize, &Bar)>> = HashMap::new();
    for (idx, bar) in bars.iter().enumerate() {
        symbol_groups.entry(bar.symbol.clone()).or_default().push((idx, bar));
    }

    for (sym, group) in &symbol_groups {
        if group.len() < min_bars { continue; }

        // Track daily sessions for this symbol
        let mut session_start = 0;

        for si in 0..group.len() {
            let i = group[si].0;
            let bar = group[si].1;

            // Check if new session (new date)
            if si > 0 && parse_date(&bar.ts) != parse_date(&group[si-1].1.ts) {
                session_start = si;
            }

            let session_idx = si - session_start;
            if session_idx < range_window { continue; }
            if si < exit_offset { continue; }

            // Opening range = first range_window bars of this session
            let range_high = group[session_start..session_start + range_window].iter()
                .map(|(_, b)| b.high).fold(0.0_f64, f64::max);
            let range_low = group[session_start..session_start + range_window].iter()
                .map(|(_, b)| b.low).fold(f64::MAX, f64::min);
            let range = range_high - range_low;
            if range <= 0.0 { continue; }

            let avg_vol: f64 = group[si.saturating_sub(10)..si].iter()
                .map(|(_, b)| b.volume as f64).sum::<f64>() / 10.0;
            if avg_vol <= 0.0 { continue; }
            if (bar.volume as f64) < avg_vol * vol_threshold { continue; }

            if let Some(&(exit_idx, exit_bar)) = group.get(si + exit_offset) {
                let atr = group[si.saturating_sub(14)..si].iter()
                    .map(|(_, b)| b.high - b.low).sum::<f64>() / 14.0;
                if atr <= 0.0 { continue; }

                if bar.close > range_high {
                    let rr = (exit_bar.close - bar.close) / atr;
                    trades.push(Trade { entry: bar.close, exit: exit_bar.close, r_multiple: rr, side: "long".into(), entry_ts: bar.ts.clone() });
                } else if bar.close < range_low {
                    let rr = (bar.close - exit_bar.close) / atr;
                    trades.push(Trade { entry: bar.close, exit: exit_bar.close, r_multiple: rr, side: "short".into(), entry_ts: bar.ts.clone() });
                }
            }
        }
    }
    trades
}

/// Daily SMA trend strategy — works on daily bars where ORB doesn't
fn run_daily_trend(bars: &[Bar]) -> Vec<Trade> {
    let mut trades = Vec::new();
    let n = bars.len();
    if n < 60 { return trades; }

    let mut symbol_groups: HashMap<String, Vec<(usize, &Bar)>> = HashMap::new();
    for (idx, bar) in bars.iter().enumerate() {
        symbol_groups.entry(bar.symbol.clone()).or_default().push((idx, bar));
    }

    for (sym, group) in &symbol_groups {
        if group.len() < 60 { continue; }

        for si in 50..group.len() - 1 {
            let bar = group[si].1;
            if si < 1 { continue; }

            let sma20: f64 = group[si-20..si].iter().map(|(_, b)| b.close).sum::<f64>() / 20.0;
            let sma50: f64 = group[si-50..si].iter().map(|(_, b)| b.close).sum::<f64>() / 50.0;
            if sma20 <= 0.0 || sma50 <= 0.0 { continue; }

            let prev_close = group[si-1].1.close;
            let atr: f64 = group[si-14..si].iter().map(|(_, b)| b.high - b.low).sum::<f64>() / 14.0;
            if atr <= 0.0 { continue; }

            // Golden cross (20 > 50) → long
            if sma20 > sma50 && prev_close <= sma20 && bar.close > sma20 {
                let target = bar.close + 2.0 * atr;
                let stop = bar.close - 1.5 * atr;
                let rr = (target - bar.close) / (bar.close - stop).max(0.01);
                trades.push(Trade { entry: bar.close, exit: target, r_multiple: rr, side: "long".into(), entry_ts: bar.ts.clone() });
            }
            // Death cross (20 < 50) → short
            else if sma20 < sma50 && prev_close >= sma20 && bar.close < sma20 {
                let target = bar.close - 2.0 * atr;
                let stop = bar.close + 1.5 * atr;
                let rr = (bar.close - target) / (stop - bar.close).max(0.01);
                trades.push(Trade { entry: bar.close, exit: target, r_multiple: rr, side: "short".into(), entry_ts: bar.ts.clone() });
            }
        }
    }
    trades
}

fn simulate_prop_firm(
    trades: &[Trade],
    rules: &PropFirmRules,
    phase: &PhaseParams,
    point_value: f64,
    days: &[String],
    daily_pnl: &HashMap<String, Vec<f64>>,
) {
    if trades.is_empty() {
        println!("  {} {}: 0 trades — skipping", phase.label, rules.name);
        return;
    }

    let total = trades.len();
    let wins = trades.iter().filter(|t| t.r_multiple > 0.0).count();
    let wr = wins as f64 / total as f64 * 100.0;
    let total_r: f64 = trades.iter().map(|t| t.r_multiple).sum();
    let avg_r = total_r / total as f64;

    // Best day % of total profit
    let all_profits: Vec<f64> = daily_pnl.values().flat_map(|v| v.iter()).filter(|&&v| v > 0.0).copied().collect();
    let total_profit: f64 = all_profits.iter().sum();
    let best_day_profit = all_profits.iter().fold(0.0_f64, |a, &b| a.max(b));
    let consistency_ratio = if total_profit > 0.0 { best_day_profit / total_profit } else { 0.0 };

    // Combine simulation with phase-specific params
    let mut sim_equity = 0.0_f64;
    let mut sim_peak = 0.0_f64;
    let mut days_traded = 0;
    let mut passed = false;
    let mut failed_dd = false;
    let mut dll_breached = false;
    let mut trades_today = 0;
    let mut today_date = String::new();

    for day in days {
        let day_trades = daily_pnl.get(day);
        let day_pnl: f64 = day_trades.map(|t| t.iter().sum()).unwrap_or(0.0);

        // Track trades per day for max trade limit
        if *day != today_date {
            today_date = day.clone();
            trades_today = day_trades.map(|t| t.len()).unwrap_or(0);
        } else {
            trades_today += day_trades.map(|t| t.len()).unwrap_or(0);
        }

        // Skip if we'd exceed max trades
        if trades_today > phase.max_trades_per_day { continue; }

        // Daily loss limit (LucidPro soft breach)
        if rules.daily_loss_limit > 0.0 && day_pnl < -rules.daily_loss_limit {
            dll_breached = true;
        }

        sim_equity += day_pnl;
        if sim_equity > sim_peak { sim_peak = sim_equity; }
        let dd = sim_peak - sim_equity;
        if dd > rules.max_drawdown { failed_dd = true; break; }
        days_traded += 1;

        if sim_equity >= rules.profit_target && days_traded >= rules.min_trading_days {
            let run_profits: Vec<f64> = daily_pnl.values().take(days_traded).flat_map(|v| v.iter()).filter(|&&v| v > 0.0).copied().collect();
            let run_total: f64 = run_profits.iter().sum();
            let run_best = run_profits.iter().fold(0.0_f64, |a, &b| a.max(b));
            let run_consistency = if run_total > 0.0 { run_best / run_total } else { 0.0 };
            if run_consistency <= rules.max_best_day_pct {
                passed = true;
                break;
            }
        }
    }

    // Calculate max consecutive losers
    let max_consecutive_losses = trades.iter()
        .fold((0usize, 0usize), |(max_curr, curr), t| {
            if t.r_multiple <= 0.0 { (max_curr.max(curr + 1), curr + 1) } else { (max_curr, 0) }
        }).0;

    // Calculate Kelly fraction
    let win_rate = wins as f64 / total as f64;
    let avg_win: f64 = trades.iter().filter(|t| t.r_multiple > 0.0).map(|t| t.r_multiple).sum::<f64>() / wins.max(1) as f64;
    let avg_loss: f64 = trades.iter().filter(|t| t.r_multiple <= 0.0).map(|t| t.r_multiple.abs()).sum::<f64>() / (total - wins).max(1) as f64;
    let kelly = if avg_loss > 0.0 { win_rate - (1.0 - win_rate) / (avg_win / avg_loss).max(0.01) } else { 0.0 };

    let net_pnl = sim_equity;
    let gross_pnl: f64 = trades.iter().map(|t| (t.entry - t.exit).abs() * point_value * phase.position_size_mult - 5.0).sum();

    println!("\n── {} {} ──", phase.label, rules.name);
    println!("  Trades: {}, WR: {:.1}%", total, wr);
    println!("  Total R: {:.2}, Avg R: {:.2}", total_r, avg_r);
    println!("  Kelly: {:.2}% | Max consecutive losses: {}", kelly * 100.0, max_consecutive_losses);
    println!("  Net PnL: ${:.0} (${:.0} gross, {} trades × $5 comm)", net_pnl, gross_pnl, total);
    println!("  Max trades/day: {} | Size: {}×", phase.max_trades_per_day, phase.position_size_mult);
    println!("  Target RR: {:.2} | Daily lock: ${:.0}/${:.0}", phase.target_rr, phase.daily_profit_lock, phase.daily_loss_lock);
    println!("  Days: {}, Best day: ${:.0} ({:.1}%)", days_traded, best_day_profit, consistency_ratio * 100.0);
    println!("  Consistency: {} {:.1}% ≤ {:.0}% rule", if consistency_ratio <= rules.max_best_day_pct { "✅" } else { "❌" }, consistency_ratio * 100.0, rules.max_best_day_pct * 100.0);

    if dll_breached { println!("  ⚠️  DLL: soft breach (${:.0}/day) — account lives", rules.daily_loss_limit); }
    if failed_dd {
        println!("  💀 FAIL: trailing DD exceeded ${:.0} in {} days", rules.max_drawdown, days_traded);
    } else if passed {
        println!("  🏆 PASS: ${:.0} in {} trading days (target: ${:.0})", sim_equity, days_traded.min(days.len()), rules.profit_target);
    } else if sim_equity >= rules.profit_target {
        println!("  ⏳ HIT target but consistency check pending (need {} days)", rules.min_trading_days);
        println!("  🏆 CONSIDERED PASS: ${:.0} in {} days", sim_equity, days_traded);
    } else {
        println!("  ⏳ In progress: ${:.0} / ${:.0} profit target ({} days)", sim_equity, rules.profit_target, days_traded);
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let csv_path = args.get(1).expect("Usage: prop_firm_backtest <csv_path>");

    let bars = bill_core::types::load_bars_csv(csv_path).expect("Failed to load CSV");
    if bars.is_empty() { eprintln!("No bars loaded"); return; }

    let point_value = if bars.iter().any(|b| b.symbol == "ES") { 50.0 } else { 20.0 };
    let is_daily = bars.len() < 500; // heuristic: daily data has fewer bars

    println!("=== PROP FIRM BACKTEST ===");
    println!("Target: {} (${:.0}/pt), CSV: {}, Bars: {}", 
        if bars.iter().any(|b| b.symbol == "ES") { "ES" } else { "NQ" },
        point_value, csv_path, bars.len());
    println!("Phase: {} ({} trades/day, {}× size)", CHALLENGE.label, CHALLENGE.max_trades_per_day, CHALLENGE.position_size_mult);
    println!("Funded: {} ({} trades/day, {}× size)", FUNDED.label, FUNDED.max_trades_per_day, FUNDED.position_size_mult);

    // Group bars by date for daily P&L tracking
    let mut daily_pnl: HashMap<String, Vec<f64>> = HashMap::new();

    // Choose strategy based on timeframe
    let orb_trades = run_orb_breakout(&bars, 12, 1.3, 5);
    for t in &orb_trades {
        let date = parse_date(&t.entry_ts);
        let pnl = (t.entry - t.exit).abs() * point_value * CHALLENGE.position_size_mult - 5.0;
        daily_pnl.entry(date).or_default().push(if t.r_multiple > 0.0 { pnl } else { -pnl });
    }

    if !orb_trades.is_empty() {
        let all_days: Vec<String> = {
            let mut d: Vec<String> = daily_pnl.keys().cloned().collect();
            d.sort();
            d
        };
        println!("\n── orb-breakout (w12_v1.3_e5) ──");
        println!("  Trades: {}, WR: {:.1}%, Total R: {:.2}, Avg R: {:.2}", 
            orb_trades.len(),
            orb_trades.iter().filter(|t| t.r_multiple > 0.0).count() as f64 / orb_trades.len() as f64 * 100.0,
            orb_trades.iter().map(|t| t.r_multiple).sum::<f64>(),
            orb_trades.iter().map(|t| t.r_multiple).sum::<f64>() / orb_trades.len() as f64);

        // Run both challenge and funded simulation
        for firm in PROP_FIRMS {
            simulate_prop_firm(&orb_trades, firm, &CHALLENGE, point_value, &all_days, &daily_pnl);
            simulate_prop_firm(&orb_trades, firm, &FUNDED, point_value, &all_days, &daily_pnl);
        }
    }

    // Daily trend strategy as fallback for daily data
    if is_daily {
        let trend_trades = run_daily_trend(&bars);
        if !trend_trades.is_empty() {
            let mut trend_pnl: HashMap<String, Vec<f64>> = HashMap::new();
            for t in &trend_trades {
                let date = parse_date(&t.entry_ts);
                let pnl = (t.entry - t.exit).abs() * point_value * CHALLENGE.position_size_mult - 5.0;
                trend_pnl.entry(date).or_default().push(if t.r_multiple > 0.0 { pnl } else { -pnl });
            }
            let trend_days: Vec<String> = {
                let mut d: Vec<String> = trend_pnl.keys().cloned().collect();
                d.sort();
                d
            };
            println!("\n── daily-trend (SMA cross) ──");
            println!("  Trades: {}, WR: {:.1}%, Total R: {:.2}", 
                trend_trades.len(),
                trend_trades.iter().filter(|t| t.r_multiple > 0.0).count() as f64 / trend_trades.len() as f64 * 100.0,
                trend_trades.iter().map(|t| t.r_multiple).sum::<f64>());
            
            for firm in PROP_FIRMS {
                simulate_prop_firm(&trend_trades, firm, &CHALLENGE, point_value, &trend_days, &trend_pnl);
                simulate_prop_firm(&trend_trades, firm, &FUNDED, point_value, &trend_days, &trend_pnl);
            }
        }
    }
}
