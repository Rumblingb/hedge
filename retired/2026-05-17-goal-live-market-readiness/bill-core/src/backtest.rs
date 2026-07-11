use crate::types::{BacktestResult, BacktestTrade, Bar, Signal};

/// Run a deterministic bar-by-bar backtest.
/// Signals are generated externally (by strategy functions).
/// This engine ONLY simulates execution — no network, no disk, pure math.
pub fn run_backtest(
    signals: &[(usize, Signal)], // (bar_index, signal) pairs
    bars: &[Bar],
    max_hold_bars: usize,
) -> BacktestResult {
    let mut trades: Vec<BacktestTrade> = Vec::new();
    let mut active: Option<ActivePosition> = None;
    let mut trade_counter: u32 = 0;

    for (bar_idx, bar) in bars.iter().enumerate() {
        // Check for signals at this bar
        let new_signals: Vec<&Signal> = signals
            .iter()
            .filter(|(idx, _)| *idx == bar_idx)
            .map(|(_, s)| s)
            .collect();

        // Only enter if no active position
        if active.is_none() {
            for signal in &new_signals {
                if signal.symbol == bar.symbol {
                    active = Some(ActivePosition {
                        signal: (*signal).clone(),
                        entry_bar: bar_idx,
                        entry_price: bar.open, // Enter at open of signal bar
                    });
                    break; // One position at a time
                }
            }
        }

        // Check active position
        if let Some(ref pos) = active {
            let held_bars = bar_idx - pos.entry_bar;
            let mut exit_reason: Option<&str> = None;
            let mut exit_price = bar.close;

            // Check stop loss
            if pos.signal.side == "long" {
                if bar.low <= pos.signal.stop {
                    exit_price = pos.signal.stop;
                    exit_reason = Some("stop");
                } else if bar.high >= pos.signal.target {
                    exit_price = pos.signal.target;
                    exit_reason = Some("target");
                }
            } else {
                if bar.high >= pos.signal.stop {
                    exit_price = pos.signal.stop;
                    exit_reason = Some("stop");
                } else if bar.low <= pos.signal.target {
                    exit_price = pos.signal.target;
                    exit_reason = Some("target");
                }
            }

            // Timeout
            if exit_reason.is_none() && held_bars >= max_hold_bars {
                exit_reason = Some("timeout");
            }

            if let Some(reason) = exit_reason {
                trade_counter += 1;
                let pnl_points = if pos.signal.side == "long" {
                    exit_price - pos.signal.entry
                } else {
                    pos.signal.entry - exit_price
                };
                let gross_r = pnl_points / (pos.signal.entry - pos.signal.stop).abs().max(0.0001);
                // Apply transaction costs: 0.5R per round trip
                let cost_r = 0.5;
                let net_r = gross_r - cost_r;

                trades.push(BacktestTrade {
                    id: format!("trade-{}", trade_counter),
                    symbol: pos.signal.symbol.clone(),
                    strategy_id: pos.signal.strategy_id.clone(),
                    side: pos.signal.side.clone(),
                    entry_ts: bars[pos.entry_bar].ts.clone(),
                    exit_ts: bar.ts.clone(),
                    entry_price: pos.entry_price,
                    exit_price,
                    exit_reason: reason.to_string(),
                    pnl_points,
                    gross_r,
                    net_r,
                    status: "closed".to_string(),
                });
                active = None;
            }
        }
    }

    // Close any remaining position at last bar
    if let Some(pos) = active {
        let last = bars.last().unwrap();
        trade_counter += 1;
        let exit_price = last.close;
        let pnl_points = if pos.signal.side == "long" {
            exit_price - pos.signal.entry
        } else {
            pos.signal.entry - exit_price
        };
        let gross_r =
            pnl_points / (pos.signal.entry - pos.signal.stop).abs().max(0.0001);
        let net_r = gross_r - 0.5;

        trades.push(BacktestTrade {
            id: format!("trade-{}", trade_counter),
            symbol: pos.signal.symbol.clone(),
            strategy_id: pos.signal.strategy_id.clone(),
            side: pos.signal.side.clone(),
            entry_ts: bars[pos.entry_bar].ts.clone(),
            exit_ts: last.ts.clone(),
            entry_price: pos.entry_price,
            exit_price,
            exit_reason: "flat_cutoff".to_string(),
            pnl_points,
            gross_r,
            net_r,
            status: "closed".to_string(),
        });
    }

    // Compute summary stats
    let total_trades = trades.len() as u32;
    let wins = trades.iter().filter(|t| t.net_r > 0.0).count() as u32;
    let losses = total_trades - wins;
    let win_rate = if total_trades > 0 {
        wins as f64 / total_trades as f64
    } else {
        0.0
    };
    let total_r: f64 = trades.iter().map(|t| t.net_r).sum();
    let average_r = if total_trades > 0 {
        total_r / total_trades as f64
    } else {
        0.0
    };

    // Max drawdown (running peak-to-trough)
    let mut max_dd = 0.0;
    let mut peak = 0.0;
    let mut running = 0.0;
    for t in &trades {
        running += t.net_r;
        if running > peak {
            peak = running;
        }
        let dd = peak - running;
        if dd > max_dd {
            max_dd = dd;
        }
    }

    let gross_profit: f64 = trades.iter().filter(|t| t.net_r > 0.0).map(|t| t.net_r).sum();
    let gross_loss: f64 = trades
        .iter()
        .filter(|t| t.net_r <= 0.0)
        .map(|t| t.net_r.abs())
        .sum();
    let profit_factor = if gross_loss > 0.0 {
        gross_profit / gross_loss
    } else if gross_profit > 0.0 {
        f64::INFINITY
    } else {
        0.0
    };

    BacktestResult {
        trades,
        total_trades,
        wins,
        losses,
        win_rate,
        total_r,
        average_r,
        max_drawdown_r: max_dd,
        profit_factor,
    }
}

struct ActivePosition {
    signal: Signal,
    entry_bar: usize,
    entry_price: f64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::Bar;

    fn make_bars(n: usize) -> Vec<Bar> {
        (0..n)
            .map(|i| Bar {
                ts: format!("2026-01-{:02}T00:00:00Z", i + 1),
                symbol: "ES".to_string(),
                open: 100.0 + i as f64,
                high: 101.0 + i as f64,
                low: 99.0 + i as f64,
                close: 100.5 + i as f64,
                volume: 1000.0,
            })
            .collect()
    }

    #[test]
    fn test_deterministic() {
        let bars = make_bars(100);
        let signal = Signal {
            symbol: "ES".to_string(),
            strategy_id: "test".to_string(),
            side: "long".to_string(),
            entry: 105.0,
            stop: 100.0,
            target: 115.0,
            rr: 2.0,
            confidence: 0.6,
            contracts: 1,
            max_hold_minutes: 30,
        };
        let result1 = run_backtest(&[(10, signal.clone())], &bars, 50);
        let result2 = run_backtest(&[(10, signal)], &bars, 50);
        // Same input → same output (deterministic)
        assert_eq!(result1.total_trades, result2.total_trades);
        assert_eq!(result1.total_r, result2.total_r);
    }
}
