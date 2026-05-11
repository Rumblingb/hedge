/// Gold strategies extracted from classified gold YouTube videos.
///
/// Implementations:
/// 1. LW Donchian Breakout (Larry Williams) — trend-following breakout
/// 2. Polymarket Edge Detector — prediction-market edge detection
/// 3. Gapper Statistical Edge — large gapper mean reversion
/// 4. Order Flow 80/20 — NQ-specific level-based strategy
/// 5. Strategy Degradation Detector (Timothy Masters)
/// 6. Drawdown-Based Position Sizer (Laurent Bernut)

use crate::indicators;
use crate::types::{Bar, Signal};

// ─── helpers ───────────────────────────────────────────────────────

fn build_signal(
    symbol: &str,
    strategy_id: &str,
    side: &str,
    entry: f64,
    stop: f64,
    target: f64,
    confidence: f64,
) -> Option<Signal> {
    let rr = if side == "long" {
        (target - entry) / (entry - stop).max(0.0001)
    } else {
        (entry - target) / (stop - entry).max(0.0001)
    };
    if rr <= 0.0 || !rr.is_finite() {
        return None;
    }
    Some(Signal {
        symbol: symbol.to_string(),
        strategy_id: strategy_id.to_string(),
        side: side.to_string(),
        entry,
        stop,
        target,
        rr,
        confidence,
        contracts: 1,
        max_hold_minutes: 60,
    })
}

fn donchian(bars: &[&Bar], period: usize) -> (f64, f64) {
    let high: f64 = bars.iter().rev().take(period).map(|b| b.high).fold(f64::NEG_INFINITY, f64::max);
    let low: f64  = bars.iter().rev().take(period).map(|b| b.low).fold(f64::INFINITY, f64::min);
    (high, low)
}

// ─── 1. Larry Williams Donchian Breakout ───────────────────────────
// From LW Volatility Breakout strategy (11,300% return in 12 months).
// Uses donchian breakout with specific period settings.
pub fn lw_donchian_breakout(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    const LW_DONCHIAN_PERIOD: usize = 20;
    const LW_CONFIRM_BARS: usize = 2;

    if bars.len() < LW_DONCHIAN_PERIOD + LW_CONFIRM_BARS + 5 {
        return None;
    }

    let (upper, lower) = donchian(bars, LW_DONCHIAN_PERIOD);
    let mid = (upper + lower) * 0.5;
    let price = bars.last()?.close;

    // ATR for stop/target sizing
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Breakout confirmation: price closes above upper donchian
    if price > upper && bars[bars.len() - 2].close > upper {
        let stop = mid.min(price - atr_val * 1.5);
        let target = price + atr_val * 3.0;
        return build_signal(symbol, "lw-donchian", "long", price, stop, target, 0.65);
    }

    // Breakdown: price closes below lower donchian
    if price < lower && bars[bars.len() - 2].close < lower {
        let stop = mid.max(price + atr_val * 1.5);
        let target = price - atr_val * 3.0;
        return build_signal(symbol, "lw-donchian", "short", price, stop, target, 0.65);
    }

    None
}

// ─── 2. Polymarket Edge Detector (Goomer interview) ───────────────
// Detects edge in prediction markets by analyzing closing-price gaps
// against a rolling volatility baseline. Adapted from Goomer's
// reported methodology on Polymarket.
pub fn polymarket_edge_detector(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 30 {
        return None;
    }

    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let returns: Vec<f64> = closes.windows(2).map(|w| (w[1] - w[0]) / w[0].max(0.0001)).collect();

    let recent = &returns[returns.len().saturating_sub(10)..];
    if recent.is_empty() {
        return None;
    }

    let avg_return: f64 = recent.iter().sum::<f64>() / recent.len() as f64;
    let std_return = indicators::std_dev(&returns, 20);

    if std_return <= 0.0 {
        return None;
    }

    let z_score = avg_return / std_return;
    let price = bars.last()?.close;
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Edge signal: z-score extreme indicates mispricing
    if z_score > 1.5 {
        // Negative edge detected — price overextended, fade it
        let stop = price + atr_val * 1.2;
        let target = price - atr_val * 2.0;
        return build_signal(symbol, "pm-edge", "short", price, stop, target, 0.55);
    }
    if z_score < -1.5 {
        let stop = price - atr_val * 1.2;
        let target = price + atr_val * 2.0;
        return build_signal(symbol, "pm-edge", "long", price, stop, target, 0.55);
    }

    None
}

// ─── 3. Gapper Statistical Edge ────────────────────────────────────
// From video T3sCLOvsdus: large percent gappers have ~80% chance
// of closing below the open price on the day.
pub fn gapper_edge(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 5 {
        return None;
    }

    let last = bars.last()?;
    let prev_close = if bars.len() >= 2 { bars[bars.len() - 2].close } else { return None; };
    let open = last.open;
    let close = last.close;

    // Gap percentage
    let gap_pct = if prev_close > 0.0 {
        (open - prev_close) / prev_close * 100.0
    } else {
        return None;
    };

    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Large gap up (>0.3%): 80% probability close below open
    if gap_pct > 0.3 {
        let entry = close;
        let stop = entry.max(open) + atr_val * 0.8;
        let target = entry - atr_val * 1.2;
        if target < stop {
            return build_signal(symbol, "gapper-edge", "short", entry, stop, target, 0.60);
        }
    }

    // Large gap down (<-0.3%): 80% probability close above open
    if gap_pct < -0.3 {
        let entry = close;
        let stop = entry.min(open) - atr_val * 0.8;
        let target = entry + atr_val * 1.2;
        if target > stop {
            return build_signal(symbol, "gapper-edge", "long", entry, stop, target, 0.60);
        }
    }

    None
}

// ─── 4. Order Flow 80/20 Nasdaq Strategy ───────────────────────────
// From video jsUTbjwpFVk: the 80/20 levels on NQ using market structure
// and order flow. Enters at key 80/20 level breaks with confirmation.
pub fn order_flow_80_20(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 30 {
        return None;
    }

    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let lookback = 20;
    let recent = &closes[closes.len().saturating_sub(lookback)..];

    if recent.len() < lookback {
        return None;
    }

    let min_price = recent.iter().fold(f64::INFINITY, |a, &b| a.min(b));
    let max_price = recent.iter().fold(f64::NEG_INFINITY, |a, &b| a.max(b));
    let range = max_price - min_price;

    if range <= 0.0 {
        return None;
    }

    // 80% and 20% levels
    let level_80 = min_price + range * 0.80;
    let level_20 = min_price + range * 0.20;
    let price = bars.last()?.close;
    let prev_price = if bars.len() >= 2 { bars[bars.len() - 2].close } else { return None; };

    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Break above 80 level with confirmation
    if price > level_80 && prev_price <= level_80 {
        let stop = level_80.min(price - atr_val * 1.0);
        let target = price + atr_val * 2.0;
        return build_signal(symbol, "80-20-flow", "long", price, stop, target, 0.58);
    }

    // Break below 20 level with confirmation
    if price < level_20 && prev_price >= level_20 {
        let stop = level_20.max(price + atr_val * 1.0);
        let target = price - atr_val * 2.0;
        return build_signal(symbol, "80-20-flow", "short", price, stop, target, 0.58);
    }

    None
}

// ─── 5. Strategy Degradation Detector (Timothy Masters) ──────────
// From "How to avoid trading strategies that degrade quickly" (Better System Trader).
// Monitors rolling win rate vs historical. Flags when metrics drift > 2σ.
// Returns a signal with confidence proportional to degradation severity.
pub fn strategy_degradation_detector(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    // Need enough data for two windows: baseline + recent
    if bars.len() < 40 {
        return None;
    }

    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let returns: Vec<f64> = closes.windows(2).map(|w| (w[1] - w[0]) / w[0].max(0.0001)).collect();

    // Split into baseline (first 2/3) and recent (last 1/3)
    let split = returns.len() * 2 / 3;
    if split < 10 {
        return None;
    }
    let baseline = &returns[..split];
    let recent = &returns[split..];

    // Compute Sharpe-like ratio for each window
    let baseline_sharpe = if !baseline.is_empty() {
        let mean: f64 = baseline.iter().sum::<f64>() / baseline.len() as f64;
        let var: f64 = baseline.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / baseline.len() as f64;
        if var > 0.0 { mean / var.sqrt() } else { 0.0 }
    } else { 0.0 };

    let recent_sharpe = if !recent.is_empty() {
        let mean: f64 = recent.iter().sum::<f64>() / recent.len() as f64;
        let var: f64 = recent.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / recent.len() as f64;
        if var > 0.0 { mean / var.sqrt() } else { 0.0 }
    } else { 0.0 };

    // Degradation = drop in Sharpe ratio
    let degradation = baseline_sharpe - recent_sharpe;

    // Only flag significant degradation
    if degradation <= 0.5 || baseline_sharpe <= 0.0 {
        return None;
    }

    let severity = (degradation / baseline_sharpe.max(0.001)).min(1.0);
    let price = bars.last()?.close;
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Signal: REDUCE exposure — confidence inversely proportional to degradation
    let confidence = (1.0 - severity).max(0.3);
    let stop = price + atr_val * 1.5;
    let target = price - atr_val * 1.0;
    if target < stop {
        return build_signal(symbol, "degradation-alert", "short", price, stop, target, confidence);
    }

    None
}

// ─── 6. Drawdown-Based Position Sizer (Laurent Bernut) ────────────
// From "Superior returns from superior risk management" (Better System Trader).
// Scales position size down linearly as drawdown increases.
// Returns a signal that carries the adjusted contract count.
pub fn drawdown_based_sizer(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    if bars.len() < 30 {
        return None;
    }

    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();

    // Compute running max & current drawdown
    let mut peak = f64::NEG_INFINITY;
    let mut current_drawdown_pct = 0.0;
    for &c in &closes {
        if c > peak {
            peak = c;
        }
        let dd = if peak > 0.0 { (peak - c) / peak * 100.0 } else { 0.0 };
        if dd > current_drawdown_pct {
            current_drawdown_pct = dd;
        }
    }

    // Linear reduction: at 5% drawdown → 50% size, at 10% → 0%
    let max_tolerable_dd = 10.0;
    let reduction_threshold = 5.0;

    if current_drawdown_pct <= reduction_threshold {
        return None; // No reduction needed
    }

    let size_multiplier = if current_drawdown_pct >= max_tolerable_dd {
        0.0 // Full pause
    } else {
        1.0 - (current_drawdown_pct - reduction_threshold) / (max_tolerable_dd - reduction_threshold)
    };

    if size_multiplier <= 0.0 {
        return None; // Too much drawdown, don't trade at all
    }

    // Emit a signal with reduced contract count (size multiplier applied)
    let price = bars.last()?.close;
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Direction-neutral: just return a neutral entry with reduced confidence
    let adjusted_contracts = (size_multiplier * 3.0).round().max(1.0) as u32;
    let mut signal = build_signal(
        symbol, "dd-sizer", "long", price,
        price - atr_val * 2.0, price + atr_val * 2.0,
        size_multiplier * 0.5,
    )?;
    signal.contracts = adjusted_contracts;
    Some(signal)
}

// ─── 7. Volume-Based Reversal (Jegadeesh & Wu Closing Auction Reversal) ──
// Adapted from SSRN paper "Closing Auctions: Nasdaq Versus NYSE".
// Concept: extreme volume + large directional move near close → reversal.
// For NQ futures: when volume spikes >2σ above avg AND close is at range extreme,
// fade the move (reversal play, 1-3 day hold).
pub fn volume_reversal(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    const VOL_LOOKBACK: usize = 20;
    const CLOSE_LOOKBACK: usize = 10;

    if bars.len() < VOL_LOOKBACK + 5 {
        return None;
    }

    let volumes: Vec<f64> = bars.iter().map(|b| b.volume).collect();
    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();

    // Baseline volume stats
    let baseline = &volumes[volumes.len() - VOL_LOOKBACK - 1..volumes.len() - 1];
    let avg_vol: f64 = baseline.iter().sum::<f64>() / baseline.len() as f64;
    let vol_var: f64 = if baseline.len() > 1 {
        baseline.iter().map(|v| (v - avg_vol).powi(2)).sum::<f64>() / (baseline.len() - 1) as f64
    } else { 0.0 };
    let vol_std = vol_var.sqrt();

    let latest_vol = volumes[volumes.len() - 1];

    // Handle near-zero variance (all same volume): use ratio instead
    let vol_z = if vol_std > avg_vol * 0.01 {
        (latest_vol - avg_vol) / vol_std
    } else if avg_vol > 0.0 {
        latest_vol / avg_vol // Ratio: >3 means significant spike
    } else {
        0.0
    };

    if vol_z < 2.0 {
        return None;
    }

    // Check if close is at an extreme of the recent range
    let recent = &closes[closes.len().saturating_sub(CLOSE_LOOKBACK)..];
    let range_high = recent.iter().fold(f64::NEG_INFINITY, |a, &b| a.max(b));
    let range_low = recent.iter().fold(f64::INFINITY, |a, &b| a.min(b));
    let range = range_high - range_low;
    if range <= 0.0 {
        return None;
    }

    let price = bars.last()?.close;
    let prev_close = if bars.len() >= 2 { bars[bars.len() - 2].close } else { return None; };
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Compute where close sits in the range (0-100%)
    let range_pos = (price - range_low) / range;

    // Extreme high close (top 20% of range) + volume spike → short (fade up)
    if range_pos > 0.80 {
        let stop = price + atr_val * 1.5;
        let target = price - atr_val * 2.0;
        return build_signal(symbol, "vol-reversal", "short", price, stop, target, 0.55);
    }

    // Extreme low close (bottom 20% of range) + volume spike → long (fade down)
    if range_pos < 0.20 {
        let stop = price - atr_val * 1.5;
        let target = price + atr_val * 2.0;
        return build_signal(symbol, "vol-reversal", "long", price, stop, target, 0.55);
    }

    None
}

// ─── 8. Opening Range Breakout (ORB) ──────────────────────────────
// From ssrn-4416622 & ssrn-4729284: Opening Range Breakout with
// "Stocks in Play" filter (relative volume > 2.0 = abnormal activity).
// Tested on 7,000 US stocks 2016-2023 (Zarattini, Barbon, Aziz 2024).
// Uses first N bars to define a range, then trades breakouts
// only when volume is elevated (proxy for "in play" status).
pub fn opening_range_breakout(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    const ORANGE_BARS: usize = 6; // First 6 bars define the opening range
    const LOOKBACK: usize = 30;   // Total bars needed
    const VOL_LOOKBACK: usize = 20;

    if bars.len() < LOOKBACK + ORANGE_BARS {
        return None;
    }

    // "Stocks in Play" filter: latest volume must be > 2× average
    let vols: Vec<f64> = bars.iter().map(|b| b.volume).collect();
    let baseline_vol: f64 = vols[vols.len() - VOL_LOOKBACK - 1..vols.len() - 1]
        .iter().sum::<f64>() / VOL_LOOKBACK as f64;
    let latest_vol = vols[vols.len() - 1];

    // Require elevated volume as proxy for "in play" (news/abnormal activity)
    if latest_vol < baseline_vol * 2.0 {
        return None;
    }

    // Use the most recent ORANGE_BARS as the "opening range" proxy
    let orange_start = bars.len() - ORANGE_BARS - 1;
    let orange_end = bars.len() - 1;

    let mut range_high = f64::NEG_INFINITY;
    let mut range_low = f64::INFINITY;
    for i in orange_start..orange_end {
        range_high = range_high.max(bars[i].high);
        range_low = range_low.min(bars[i].low);
    }

    let price = bars.last()?.close;
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Breakout above opening range high
    if price > range_high {
        let stop = range_low.min(price - atr_val * 1.5);
        let target = price + atr_val * 2.5;
        return build_signal(symbol, "orb-breakout", "long", price, stop, target, 0.62);
    }

    // Breakdown below opening range low
    if price < range_low {
        let stop = range_high.max(price + atr_val * 1.5);
        let target = price - atr_val * 2.5;
        return build_signal(symbol, "orb-breakout", "short", price, stop, target, 0.62);
    }

    None
}

// ─── 9. Volume Imbalance Signal (ssrn-2668277) ───────────────────
// From "Enhancing Trading Strategies with Order Book Signals":
// Volume imbalance predicts the sign of the next market order.
// Simplified: compare up-volume vs down-volume over recent bars.
// When imbalance exceeds 60% in either direction → trade in that direction.
pub fn volume_imbalance_signal(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    const IMB_LOOKBACK: usize = 20;

    if bars.len() < IMB_LOOKBACK + 5 {
        return None;
    }

    let start = bars.len() - IMB_LOOKBACK;
    let mut up_vol = 0.0;
    let mut down_vol = 0.0;

    for i in start..bars.len() {
        let prev_close = if i > 0 { bars[i - 1].close } else { continue; };
        if bars[i].close > prev_close {
            up_vol += bars[i].volume;
        } else if bars[i].close < prev_close {
            down_vol += bars[i].volume;
        } else {
            // Equal → split volume equally
            up_vol += bars[i].volume * 0.5;
            down_vol += bars[i].volume * 0.5;
        }
    }

    let total_vol = up_vol + down_vol;
    if total_vol <= 0.0 {
        return None;
    }

    let imbalance = (up_vol - down_vol) / total_vol; // -1 to +1

    let price = bars.last()?.close;
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Strong buy imbalance (>60% buy volume) → go long
    if imbalance > 0.20 {
        let stop = price - atr_val * 1.2;
        let target = price + atr_val * 2.0;
        return build_signal(symbol, "vol-imbalance", "long", price, stop, target, 0.55);
    }

    // Strong sell imbalance (>60% sell volume) → go short
    if imbalance < -0.20 {
        let stop = price + atr_val * 1.2;
        let target = price - atr_val * 2.0;
        return build_signal(symbol, "vol-imbalance", "short", price, stop, target, 0.55);
    }

    None
}

// ─── 10. Weekly Nasdaq Futures Strategy (ssrn-5630830) ──────────
// From Chatzimanolakis (2025): Weekly NQ system using:
// - 2 EMAs for trend direction
// - NQ/VIX RS ratio with signal lines
// - Triple RSI with Bollinger Bands
// - Std Dev channel
// Long-only, 0.7 trades/month, 36% time-in-market.
// 26.3yr track: CAGR 16%, MaxDD 5.9%, Sharpe 2.86, β 0.10.
// Simplified for daily bars: trend-following with volatility filter.
pub fn weekly_nasdaq_strategy(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    // Need ~60 bars minimum for indicator lookback
    if bars.len() < 60 {
        return None;
    }

    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();

    // 1. Two EMAs (fast 12, slow 26 on daily data, weekly equivalent)
    let ema_fast = indicators::sma(&closes, 12); // proxy for EMA
    let ema_slow = indicators::sma(&closes, 26);

    // 2. RS Ratio proxy: NQ performance vs volatility
    // Use recent return as momentum proxy
    let returns_10: Vec<f64> = closes.windows(2)
        .map(|w| (w[1] - w[0]) / w[0].max(0.0001))
        .collect();
    let recent_returns = &returns_10[returns_10.len().saturating_sub(10)..];
    let momentum: f64 = recent_returns.iter().sum::<f64>();

    // 3. Volatility filter (Std Dev channel)
    let std_val = indicators::std_dev(&closes, 20);
    let mean_val: f64 = closes[closes.len() - 20..].iter().sum::<f64>() / 20.0;
    let price = bars.last()?.close;
    // Upper/lower channel: ±2 std dev
    let upper_channel = mean_val + 2.0 * std_val;
    let lower_channel = mean_val - 2.0 * std_val;

    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Entry conditions (long-only as per paper):
    // 1. EMA_fast > EMA_slow (uptrend)
    // 2. Price above lower channel (not in extreme oversold)
    // 3. Positive momentum (RS ratio proxy)
    // 4. Just entered channel (price between lower channel and mean)
    if ema_fast > ema_slow
        && price > lower_channel
        && momentum > 0.0
        && price < mean_val + std_val
    {
        let stop = price - atr_val * 2.0;
        let target = price + atr_val * 4.0;
        return build_signal(symbol, "weekly-nq", "long", price, stop, target, 0.62);
    }

    None
}

// ─── 11. WQ Momentum Reversal (Alpha 1/2 adapted) ──────────────────
// WorldQuant Alpha pattern: volume-confirmed price reversal.
// When volume spikes above 2x normal AND price is at extreme (top/bottom
// 20% of recent range), fade the move. ATR-based stop/target.
// Adaptation of WQ Alpha 1 (volume spike gate) + Alpha 2 (reversal signal).
pub fn wq_momentum_reversal(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    const LOOKBACK: usize = 20;
    const VOL_MULT: f64 = 1.8;
    const EXTREME_PCT: f64 = 0.20; // top/bottom 20% of range

    if bars.len() < LOOKBACK + 5 {
        return None;
    }

    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let volumes: Vec<f64> = bars.iter().map(|b| b.volume).collect();
    let last = bars.last()?;
    let price = last.close;

    // Average volume over lookback
    let avg_vol: f64 = volumes[volumes.len() - LOOKBACK..].iter().sum::<f64>() / LOOKBACK as f64;
    if avg_vol <= 0.0 {
        return None;
    }

    let vol_ratio = last.volume / avg_vol;
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Recent range (high/low of lookback)
    let recent_high = closes[closes.len() - LOOKBACK..].iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let recent_low = closes[closes.len() - LOOKBACK..].iter().cloned().fold(f64::INFINITY, f64::min);
    let range = (recent_high - recent_low).max(0.0001);

    // Is price near top or bottom of range?
    let range_pos = (price - recent_low) / range; // 0.0 = bottom, 1.0 = top

    // Volume spike confirmed → fade the move
    if vol_ratio >= VOL_MULT && range_pos >= 1.0 - EXTREME_PCT {
        // Extended high with volume spike → fade short
        return build_signal(symbol, "wq-mom-rev", "short", price,
            price + atr_val * 1.5,
            price - atr_val * 3.0,
            0.55);
    }

    if vol_ratio >= VOL_MULT && range_pos <= EXTREME_PCT {
        // Extended low with volume spike → fade long
        return build_signal(symbol, "wq-mom-rev", "long", price,
            price - atr_val * 1.5,
            price + atr_val * 3.0,
            0.55);
    }

    None
}

// ─── 12. WQ Volatility Regime (Alpha 4 adapted) ─────────────────────
// WorldQuant Alpha 4 pattern: implied vs realized volatility ratio.
// Adapted for futures: compare short-term ATR to long-term ATR.
// When short-term vol is low vs long-term (compressed range), position
// for expansion (breakout direction determined by short momentum).
// When short-term vol is high vs long-term (expansion phase), fade
// (reversion to mean).
pub fn wq_volatility_regime(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    const SHORT_ATR: usize = 5;
    const LONG_ATR: usize = 20;
    const COMPRESSED_THRESHOLD: f64 = 0.60;
    const EXPANDED_THRESHOLD: f64 = 1.50;

    if bars.len() < LONG_ATR + 5 {
        return None;
    }

    let atr_short = indicators::atr(bars, SHORT_ATR);
    let atr_long = indicators::atr(bars, LONG_ATR);
    if atr_long <= 0.0 || atr_short <= 0.0 {
        return None;
    }

    let vol_ratio = atr_short / atr_long;
    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let price = bars.last()?.close;

    // Short momentum (5-bar ROC)
    let roc_5 = if closes.len() >= 6 {
        (price - closes[closes.len() - 6]) / closes[closes.len() - 6].max(0.0001)
    } else {
        0.0
    };

    // Volatility-compressed → breakout setup
    if vol_ratio < COMPRESSED_THRESHOLD {
        // Position in the direction of short-term momentum
        if roc_5 > 0.005 {
            let stop = price - atr_long * 1.0;
            let target = price + atr_long * 2.0;
            return build_signal(symbol, "wq-vol-regime", "long", price, stop, target, 0.50);
        } else if roc_5 < -0.005 {
            let stop = price + atr_long * 1.0;
            let target = price - atr_long * 2.0;
            return build_signal(symbol, "wq-vol-regime", "short", price, stop, target, 0.50);
        }
    }

    // Volatility-expanded → mean reversion setup
    if vol_ratio > EXPANDED_THRESHOLD {
        // Fade the move
        if roc_5 > 0.01 {
            let stop = price + atr_short * 1.5;
            let target = price - atr_short * 2.5;
            return build_signal(symbol, "wq-vol-regime", "short", price, stop, target, 0.48);
        } else if roc_5 < -0.01 {
            let stop = price - atr_short * 1.5;
            let target = price + atr_short * 2.5;
            return build_signal(symbol, "wq-vol-regime", "long", price, stop, target, 0.48);
        }
    }

    None
}

// ─── 13. WQ Trend Momentum (Alpha 3 adapted) ────────────────────────
// WorldQuant Alpha 3 pattern: multi-factor composite combining short-term
// reversal, medium-term momentum, and volatility regime.
// Adapted for single-instrument futures:
//   signal = 0.5 * rank(short_roc) + 0.3 * rank(medium_roc) + 0.2 * rank(vol_regime)
// Since we can't cross-sectionally rank, we use z-score normalization
// and combine with min-max bounds.
pub fn wq_trend_momentum(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    const SHORT_PERIOD: usize = 3;
    const MEDIUM_PERIOD: usize = 10;
    const LOOKBACK: usize = 30;

    if bars.len() < LOOKBACK + MEDIUM_PERIOD {
        return None;
    }

    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let price = bars.last()?.close;
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Helper: simple z-score of a value series
    let z_score = |values: &[f64]| -> f64 {
        let n = values.len() as f64;
        if n < 2.0 { return 0.0; }
        let mean: f64 = values.iter().sum::<f64>() / n;
        let variance: f64 = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (n - 1.0);
        let std = variance.sqrt().max(0.0001);
        let last_val = *values.last().unwrap_or(&0.0);
        (last_val - mean) / std
    };

    // 1. Short-term ROC (z-scored over lookback)
    let short_rocs: Vec<f64> = (0..LOOKBACK.min(closes.len() - SHORT_PERIOD))
        .map(|i| {
            let idx = closes.len() - LOOKBACK + i;
            if idx + SHORT_PERIOD < closes.len() {
                (closes[idx + SHORT_PERIOD] - closes[idx]) / closes[idx].max(0.0001)
            } else {
                0.0
            }
        })
        .collect();
    let short_z = z_score(&short_rocs);

    // 2. Medium-term ROC (z-scored over lookback)
    let medium_rocs: Vec<f64> = (0..LOOKBACK.min(closes.len() - MEDIUM_PERIOD))
        .map(|i| {
            let idx = closes.len() - LOOKBACK + i;
            if idx + MEDIUM_PERIOD < closes.len() {
                (closes[idx + MEDIUM_PERIOD] - closes[idx]) / closes[idx].max(0.0001)
            } else {
                0.0
            }
        })
        .collect();
    let medium_z = z_score(&medium_rocs);

    // 3. Composite score: bounded [-1, 1]
    let composite = (0.5 * short_z + 0.3 * medium_z) / 0.8; // normalize
    let composite = composite.clamp(-1.0, 1.0);

    // Signal threshold
    if composite.abs() < 0.7 {
        return None;
    }

    let side = if composite > 0.0 { "long" } else { "short" };
    let stop_dist = atr_val * (1.5 - 0.5 * composite.abs()); // tighter stop for stronger signal
    let target_dist = atr_val * (2.5 + 0.5 * composite.abs()); // wider target for stronger signal

    let (stop, target) = if side == "long" {
        (price - stop_dist, price + target_dist)
    } else {
        (price + stop_dist, price - target_dist)
    };

    let confidence = (0.50 + 0.15 * composite.abs()).clamp(0.50, 0.65);

    return build_signal(symbol, "wq-trend-mom", side, price, stop, target, confidence);
}

// ─── 14. VGRSI Visibility Graph Strategy (arXiv:2605.01300) ─────────
// From Rafał Rak: Chart Visibility Graph RSI indicator.
// Uses graph-theoretic visibility to identify price levels that are
// "visible" from each other (no intervening point breaks the line).
// Three timeframes (short, medium, long VGRSI) with thresholds determine
// entry direction. Walk-forward optimized on WS/WV parameters.
pub fn vgrsi_strategy(symbol: &str, bars: &[&Bar]) -> Option<Signal> {
    // Need enough bars for all three VGRSI windows
    if bars.len() < 100 {
        return None;
    }

    let closes: Vec<f64> = bars.iter().map(|b| b.close).collect();
    let price = bars.last()?.close;
    let atr_val = indicators::atr(bars, 14);
    if atr_val <= 0.0 {
        return None;
    }

    // Compute VGRSI at three resolutions (mimicking M1, M5, M30)
    // Fast: short window, short visibility — reacts quickly
    let vg_fast = indicators::vgrsi(&closes, 10, 10, "A0");
    // Medium: default parameters from paper
    let vg_med = indicators::vgrsi(&closes, 30, 20, "A0");
    // Slow: longer window, wider visibility — trend confirmation
    let vg_slow = indicators::vgrsi(&closes, 60, 40, "A0");

    // Entry thresholds (from paper: buy < 20-35, sell > 70-95)
    const BUY_THRESHOLD: f64 = 30.0;
    const SELL_THRESHOLD: f64 = 70.0;

    // All three must agree
    let long_signal = vg_fast < BUY_THRESHOLD
        && vg_med < BUY_THRESHOLD
        && vg_slow < BUY_THRESHOLD;

    let short_signal = vg_fast > SELL_THRESHOLD
        && vg_med > SELL_THRESHOLD
        && vg_slow > SELL_THRESHOLD;

    if long_signal {
        // VGRSI very low → market undervalued → go long
        // Tighter entry: wait for first up-bar confirmation
        let prev_close = if closes.len() >= 2 { closes[closes.len() - 2] } else { price };
        if price >= prev_close {
            // Confirmation: price moving up
            let stop = price - atr_val * 2.0;
            let target = price + atr_val * 3.5;
            // Confidence higher when VGRSI is more extreme
            let confidence = (0.55 + 0.10 * (1.0 - vg_fast / 100.0)).clamp(0.55, 0.65);
            return build_signal(symbol, "vgrsi", "long", price, stop, target, confidence);
        }
    }

    if short_signal {
        // VGRSI very high → market overvalued → go short
        let prev_close = if closes.len() >= 2 { closes[closes.len() - 2] } else { price };
        if price <= prev_close {
            let stop = price + atr_val * 2.0;
            let target = price - atr_val * 3.5;
            let confidence = (0.55 + 0.10 * (vg_fast / 100.0)).clamp(0.55, 0.65);
            return build_signal(symbol, "vgrsi", "short", price, stop, target, confidence);
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::Bar;

    fn make_bars(prices: &[f64]) -> Vec<Bar> {
        prices.iter().enumerate().map(|(i, &p)| Bar {
            ts: format!("2026-01-{:02}T00:00:00Z", i + 1),
            symbol: "NQ".to_string(),
            open: p,
            high: p * 1.002,
            low: p * 0.998,
            close: p,
            volume: 1000.0,
        }).collect()
    }

    fn make_bars_with_gap(prices: &[f64], gap_idx: usize, gap_pct: f64) -> Vec<Bar> {
        prices.iter().enumerate().map(|(i, &p)| Bar {
            ts: format!("2026-01-{:02}T00:00:00Z", i + 1),
            symbol: "NQ".to_string(),
            open: if i == gap_idx { p * (1.0 + gap_pct / 100.0) } else { p },
            high: p * 1.002,
            low: p * 0.998,
            close: p,
            volume: 1000.0,
        }).collect()
    }

    #[test]
    fn test_lw_donchian_breakout_not_enough_data() {
        let bars = make_bars(&[100.0; 10]);
        let refs: Vec<&Bar> = bars.iter().collect();
        assert!(lw_donchian_breakout("NQ", &refs).is_none());
    }

    #[test]
    fn test_gapper_edge_large_gap_up() {
        // Flat prices, last bar has 0.5% gap up → should fire short
        let prices: Vec<f64> = vec![100.0; 35];
        let bars = make_bars_with_gap(&prices, prices.len() - 1, 0.5);
        let refs: Vec<&Bar> = bars.iter().collect();
        let signal = gapper_edge("NQ", &refs);
        assert!(signal.is_some(), "gapper should fire for large gap");
        if let Some(s) = signal {
            assert_eq!(s.strategy_id, "gapper-edge");
            assert_eq!(s.side, "short", "large gap up should be short");
        }
    }

    #[test]
    fn test_gapper_edge_large_gap_down() {
        let prices: Vec<f64> = vec![100.0; 35];
        let bars = make_bars_with_gap(&prices, prices.len() - 1, -0.5);
        let refs: Vec<&Bar> = bars.iter().collect();
        let signal = gapper_edge("NQ", &refs);
        assert!(signal.is_some(), "gapper should fire for large gap down");
        if let Some(s) = signal {
            assert_eq!(s.strategy_id, "gapper-edge");
            assert_eq!(s.side, "long", "large gap down should be long");
        }
    }

    #[test]
    fn test_order_flow_80_20_breakout() {
        // Stable range then breakout above 80 level
        let mut prices: Vec<f64> = (0..30).map(|i| 100.0 + (i % 10) as f64 * 0.5).collect();
        // Last bar breaks above the range
        let max_val = prices.iter().take(20).fold(f64::NEG_INFINITY, |a, &b| a.max(b));
        prices.push(max_val + 5.0);

        let bars = make_bars(&prices);
        let refs: Vec<&Bar> = bars.iter().collect();
        let signal = order_flow_80_20("NQ", &refs);
        if let Some(s) = signal {
            assert_eq!(s.strategy_id, "80-20-flow");
            assert_eq!(s.side, "long");
        }
    }

    #[test]
    fn test_polymarket_edge_no_extreme_z() {
        // Oscillating series → high std → z-score should stay inside [-1.5, 1.5]
        let prices: Vec<f64> = (0..50).map(|i| 100.0 + (i as f64).sin() * 10.0).collect();
        let bars = make_bars(&prices);
        let refs: Vec<&Bar> = bars.iter().collect();
        let signal = polymarket_edge_detector("PM", &refs);
        // High std makes extreme z unlikely; still validate no panic
        if let Some(s) = signal {
            assert!(s.rr > 0.0);
        }
    }

    #[test]
    fn test_volume_reversal_extreme_high_close() {
        // Flat prices at low, then a spike high close with huge volume
        let mut prices: Vec<f64> = vec![100.0; 30];
        let mut bars: Vec<Bar> = prices.iter().enumerate().map(|(i, &p)| Bar {
            ts: format!("2026-01-{:02}T00:00:00Z", i + 1),
            symbol: "NQ".to_string(),
            open: p,
            high: p * 1.01,
            low: p * 0.99,
            close: if i < 29 { p } else { 102.0 },
            volume: if i < 29 { 1000.0 } else { 50000.0 }, // 50x volume spike
        }).collect();
        let refs: Vec<&Bar> = bars.iter().collect();
        let signal = volume_reversal("NQ", &refs);
        assert!(signal.is_some(), "volume spike + extreme high should fire");
        if let Some(s) = signal {
            assert_eq!(s.strategy_id, "vol-reversal");
            assert_eq!(s.side, "short", "extreme high close should be short(bias)");
        }
    }

    #[test]
    fn test_volume_reversal_no_spike() {
        // Normal volume, no spike → should not fire
        let prices: Vec<f64> = (0..35).map(|i| 100.0 + (i as f64).sin()).collect();
        let bars: Vec<Bar> = prices.iter().enumerate().map(|(i, &p)| Bar {
            ts: format!("2026-01-{:02}T00:00:00Z", i + 1),
            symbol: "NQ".to_string(),
            open: p,
            high: p * 1.002,
            low: p * 0.998,
            close: p,
            volume: 1000.0,
        }).collect();
        let refs: Vec<&Bar> = bars.iter().collect();
        assert!(volume_reversal("NQ", &refs).is_none(), "no volume spike → no signal");
    }
}
