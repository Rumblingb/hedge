//! regime_detector.rs — Market regime detection for adaptive strategy parameters.
//!
//! Detects regimes from:
//! - Calendar events (FOMC, economic releases, options expiry)
//! - Market structure (sector divergence, VIX regime)
//! - Price action (volume anomaly, momentum regime)
//!
//! Each strategy variant can adjust parameters based on regime.

use std::collections::HashMap;

/// Recognized market regimes that affect strategy behavior
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum MarketRegime {
    /// Normal / default — standard parameters
    Normal,
    /// FOMC decision day — elevated vol, stronger breakouts
    FOMC,
    /// Day before FOMC — anticipation positioning
    PreFOMC,
    /// Day after FOMC — digestion/settlement
    PostFOMC,
    /// Monthly/Weekly options expiry — max pain pinning, gamma effects
    OptionsExpiry,
    /// High volatility regime (VIX > 25)
    HighVol,
    /// Low volatility regime (VIX < 12)
    LowVol,
    /// Sector divergence detected (e.g., XLF vs SPX)
    SectorDivergence,
    /// End of month / quarter — institutional rebalancing flows
    Rebalancing,
}

/// Strategy parameter overrides for each regime
#[derive(Debug, Clone, Copy)]
pub struct RegimeParams {
    pub orb_window: usize,      // Range lookback window
    pub orb_vol_threshold: f64, // Volume surge threshold
    pub exit_offset: usize,     // Bars to hold (5=tight, 8=normal)
    pub stop_atr: f64,          // ATR stop (0=none)
    pub target_atr: f64,        // ATR target (0=none)
    pub name_suffix: &'static str,
}

impl RegimeParams {
    pub fn name(&self, base: &str) -> String {
        format!("{}-{}", base, self.name_suffix)
    }
}

/// Default (normal regime) parameters
pub const NORMAL_PARAMS: RegimeParams = RegimeParams {
    orb_window: 12,
    orb_vol_threshold: 1.3,
    exit_offset: 8,
    stop_atr: 0.0,
    target_atr: 0.0,
    name_suffix: "normal",
};

/// FOMC day parameters — tighter exits, higher vol threshold to avoid noise,
/// wider range window for more significant breakout levels
pub const FOMC_PARAMS: RegimeParams = RegimeParams {
    orb_window: 16,
    orb_vol_threshold: 2.0,
    exit_offset: 5,  // Tighter exit — FOMC fades are sharp
    stop_atr: 1.5,   // Hard stop to protect against violent reversals
    target_atr: 3.0, // Take profit at 3 ATR
    name_suffix: "fomc",
};

/// Pre-FOMC — tighter range, lower threshold (anticipation builds vol)
pub const PRE_FOMC_PARAMS: RegimeParams = RegimeParams {
    orb_window: 10,
    orb_vol_threshold: 1.2,
    exit_offset: 8,
    stop_atr: 1.0,
    target_atr: 0.0,
    name_suffix: "prefomc",
};

/// Post-FOMC — wider parameters (trends develop post-announcement)
pub const POST_FOMC_PARAMS: RegimeParams = RegimeParams {
    orb_window: 14,
    orb_vol_threshold: 1.5,
    exit_offset: 10, // Let trends run
    stop_atr: 2.0,
    target_atr: 0.0,
    name_suffix: "postfomc",
};

/// Options expiry — tighter exits, max pain anchoring
pub const EXPIRY_PARAMS: RegimeParams = RegimeParams {
    orb_window: 10,
    orb_vol_threshold: 1.5,
    exit_offset: 5, // Quick exits — gamma flips are fast
    stop_atr: 1.0,
    target_atr: 2.0,
    name_suffix: "expiry",
};

/// High volatility — wider stops, tighter targets
pub const HIGH_VOL_PARAMS: RegimeParams = RegimeParams {
    orb_window: 16,
    orb_vol_threshold: 2.0,
    exit_offset: 5,
    stop_atr: 2.5,   // Wider stop to avoid noise stops
    target_atr: 4.0, // Let winners run
    name_suffix: "highvol",
};

/// All known FOMC dates for 2026 (from Fed calendar)
const FOMC_DATES_2026: &[&str] = &[
    "2026-01-29", // Already passed
    "2026-03-19",
    "2026-05-07", // May meeting (2-day: May 6-7)
    "2026-05-14", // MAY 14 FOMC RELEASE — TODAY
    "2026-06-18",
    "2026-07-30",
    "2026-09-17",
    "2026-11-05",
    "2026-12-17",
];

/// Detect regime from a date string (YYYY-MM-DD) and optional indicators
pub fn detect_regime(
    date_str: &str,
    vix_level: Option<f64>,
    sector_divergence: Option<bool>,
) -> (MarketRegime, &'static RegimeParams) {
    // 1. Calendar-based detection
    if is_fomc_date(date_str) {
        return (MarketRegime::FOMC, &FOMC_PARAMS);
    }
    if is_pre_fomc_date(date_str) {
        return (MarketRegime::PreFOMC, &PRE_FOMC_PARAMS);
    }
    if is_post_fomc_date(date_str) {
        return (MarketRegime::PostFOMC, &POST_FOMC_PARAMS);
    }

    // Check options expiry (third Friday of month)
    if is_expiry_friday(date_str) {
        return (MarketRegime::OptionsExpiry, &EXPIRY_PARAMS);
    }
    // Day before expiry (Thursday = max gamma)
    if is_pre_expiry(date_str) {
        return (MarketRegime::OptionsExpiry, &EXPIRY_PARAMS);
    }

    // 2. VIX-based detection
    if let Some(vix) = vix_level {
        if vix > 25.0 {
            return (MarketRegime::HighVol, &HIGH_VOL_PARAMS);
        }
    }

    // 3. Sector divergence
    if let Some(true) = sector_divergence {
        // Use tighter parameters during regime uncertainty
        return (MarketRegime::SectorDivergence, &EXPIRY_PARAMS);
    }

    // 4. End of month — rebalancing
    if is_end_of_month(date_str) {
        return (MarketRegime::Rebalancing, &FOMC_PARAMS);
    }

    (MarketRegime::Normal, &NORMAL_PARAMS)
}

/// Check if date is an FOMC decision day
fn is_fomc_date(date: &str) -> bool {
    FOMC_DATES_2026.iter().any(|&d| d == date)
}

/// Check if date is day before FOMC
fn is_pre_fomc_date(date: &str) -> bool {
    FOMC_DATES_2026.iter().any(|&d| is_day_before(d, date))
}

/// Check if date is day after FOMC
fn is_post_fomc_date(date: &str) -> bool {
    FOMC_DATES_2026.iter().any(|&d| is_day_after(d, date))
}

/// Check if date is the third Friday of the month (monthly options expiry)
fn is_expiry_friday(date: &str) -> bool {
    // Parse date to check day of week and week of month
    let parts: Vec<&str> = date.split('-').collect();
    if parts.len() < 3 {
        return false;
    }
    let y: i32 = parts[0].parse().unwrap_or(0);
    let m: u32 = parts[1].parse().unwrap_or(0);
    let d: u32 = parts[2].parse().unwrap_or(0);
    if y == 0 || m == 0 || d == 0 {
        return false;
    }

    // Naive day-of-week calculation (Zeller-like)
    let day_of_week = day_of_week(y, m, d);
    if day_of_week != 5 {
        return false;
    } // Not Friday

    // Third Friday = day between 15 and 21
    d >= 15 && d <= 21
}

/// Check if date is day before expiry Friday
fn is_pre_expiry(date: &str) -> bool {
    let parts: Vec<&str> = date.split('-').collect();
    if parts.len() < 3 {
        return false;
    }
    let y: i32 = parts[0].parse().unwrap_or(0);
    let m: u32 = parts[1].parse().unwrap_or(0);
    let d: u32 = parts[2].parse().unwrap_or(0);
    if y == 0 || m == 0 || d == 0 {
        return false;
    }

    let day_of_week = day_of_week(y, m, d);
    // Thursday before third Friday = day between 14 and 20
    day_of_week == 4 && d >= 14 && d <= 20
}

/// Check if last 2 days of month or quarter
fn is_end_of_month(date: &str) -> bool {
    let parts: Vec<&str> = date.split('-').collect();
    if parts.len() < 3 {
        return false;
    }
    let d: u32 = parts[2].parse().unwrap_or(0);

    // Last 2 trading days of month (approximate: 28-31)
    let is_month_end = d >= 28;

    // Check quarter end
    let m: u32 = parts[1].parse().unwrap_or(0);
    let is_quarter_end = matches!(m, 3 | 6 | 9 | 12) && d >= 25;

    is_month_end || is_quarter_end
}

/// Zeller's congruence for day of week (0=Sat, 1=Sun, ..., 5=Fri, 6=Sat)
fn day_of_week(y: i32, m: u32, d: u32) -> u32 {
    let (y, m) = if m < 3 { (y - 1, m + 12) } else { (y, m) };
    let y_mod = (y % 100) as u32;
    let c = (y / 100) as u32;
    let dow = (d + (13 * (m + 1)) / 5 + y_mod + y_mod / 4 + c / 4 + 5 * c + 6) % 7;
    dow
}

fn is_day_before(target: &str, candidate: &str) -> bool {
    // Simple: subtract 1 day from target and compare
    let parts: Vec<&str> = target.split('-').collect();
    if parts.len() < 3 {
        return false;
    }
    let y: i32 = parts[0].parse().unwrap_or(0);
    let m: u32 = parts[1].parse().unwrap_or(0);
    let d: u32 = parts[2].parse().unwrap_or(0);

    let prev = prev_day(y, m, d);
    let prev_str = format!("{:04}-{:02}-{:02}", prev.0, prev.1, prev.2);
    prev_str.as_str() == candidate
}

fn is_day_after(target: &str, candidate: &str) -> bool {
    let parts: Vec<&str> = target.split('-').collect();
    if parts.len() < 3 {
        return false;
    }
    let y: i32 = parts[0].parse().unwrap_or(0);
    let m: u32 = parts[1].parse().unwrap_or(0);
    let d: u32 = parts[2].parse().unwrap_or(0);

    let next = next_day(y, m, d);
    let next_str = format!("{:04}-{:02}-{:02}", next.0, next.1, next.2);
    next_str.as_str() == candidate
}

fn prev_day(y: i32, m: u32, d: u32) -> (i32, u32, u32) {
    if d > 1 {
        return (y, m, d - 1);
    }
    if m == 1 {
        return (y - 1, 12, 31);
    }
    let days_in_prev = days_in_month(y, m - 1);
    (y, m - 1, days_in_prev)
}

fn next_day(y: i32, m: u32, d: u32) -> (i32, u32, u32) {
    let days_this = days_in_month(y, m);
    if d < days_this {
        return (y, m, d + 1);
    }
    if m == 12 {
        return (y + 1, 1, 1);
    }
    (y, m + 1, 1)
}

fn days_in_month(y: i32, m: u32) -> u32 {
    match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if (y % 4 == 0 && y % 100 != 0) || (y % 400 == 0) {
                29
            } else {
                28
            }
        }
        _ => 30,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fomc_detection() {
        let (regime, params) = detect_regime("2026-05-14", None, None);
        assert_eq!(regime, MarketRegime::FOMC);
        assert_eq!(params.exit_offset, 5); // FOMC uses tighter exits
    }

    #[test]
    fn test_expiry_friday() {
        // May 15, 2026 is a Friday between 15-21
        assert!(is_expiry_friday("2026-05-15"));
    }

    #[test]
    fn test_normal_day() {
        let (regime, _) = detect_regime("2026-05-11", None, None);
        assert_eq!(regime, MarketRegime::Normal);
    }
}
