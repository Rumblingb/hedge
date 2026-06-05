//! session_schedule.rs — Daily trading session intelligence for adaptive strategy execution.
//!
//! Maps market sessions (Asia, London, NY open, NY afternoon, close) to:
//! - Optimal strategy types and orb-breakout parameter sets
//! - Expected volatility/ATR behavior
//! - Key macro event windows
//! - Position sizing adjustments

/// Market session identifiers
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TradingSession {
    Asia,
    LondonOpen,
    LondonNyOverlap,
    UsPreMarket,
    NyMorning,
    UsAfternoon,
    UsPowerHour,
    UsEvening,
}

/// Strategy configuration for a given session
#[derive(Debug, Clone, Copy)]
pub struct SessionConfig {
    pub primary_tf_minutes: u32,
    pub secondary_tf_minutes: u32,
    pub regime: &'static str,
    pub style: &'static str,
    pub size_mult: f64,
    pub max_hold_minutes: u32,
}

/// Get the current trading session from UTC time components
pub fn current_session(utc_hour: u32, utc_min: u32, weekday: u32) -> (TradingSession, &'static SessionConfig) {
    // Convert UTC to ET (UTC-4 during EDT — May 2026)
    let et_total_min = ((utc_hour + 24 - 4) % 24) * 60 + utc_min;

    // Weekend
    if weekday >= 5 {
        return (TradingSession::UsEvening, &WEEKEND_CONFIG);
    }

    match et_total_min {
        t if t >= 1140 || t < 180  => (TradingSession::Asia, &ASIA_CONFIG),
        t if t < 300                 => (TradingSession::LondonOpen, &LONDON_CONFIG),
        t if t < 420                 => (TradingSession::LondonNyOverlap, &LONDON_NY_CONFIG),
        t if t < 570                 => (TradingSession::UsPreMarket, &US_PRE_CONFIG),
        t if t < 720                 => (TradingSession::NyMorning, &NY_MORNING_CONFIG),
        t if t < 930                 => (TradingSession::UsAfternoon, &US_AFTERNOON_CONFIG),
        t if t < 960                 => (TradingSession::UsPowerHour, &US_POWER_HOUR_CONFIG),
        _                            => (TradingSession::UsEvening, &US_EVENING_CONFIG),
    }
}

// Session configs — same as before but without chrono dependency
const ASIA_CONFIG: SessionConfig = SessionConfig {
    primary_tf_minutes: 30, secondary_tf_minutes: 60,
    regime: "normal", style: "mean-reversion",
    size_mult: 0.5, max_hold_minutes: 480,
};

const LONDON_CONFIG: SessionConfig = SessionConfig {
    primary_tf_minutes: 15, secondary_tf_minutes: 30,
    regime: "prefomc", style: "breakout",
    size_mult: 0.75, max_hold_minutes: 240,
};

const LONDON_NY_CONFIG: SessionConfig = SessionConfig {
    primary_tf_minutes: 5, secondary_tf_minutes: 15,
    regime: "normal", style: "breakout",
    size_mult: 1.0, max_hold_minutes: 120,
};

const US_PRE_CONFIG: SessionConfig = SessionConfig {
    primary_tf_minutes: 15, secondary_tf_minutes: 30,
    regime: "normal", style: "range",
    size_mult: 0.5, max_hold_minutes: 240,
};

const NY_MORNING_CONFIG: SessionConfig = SessionConfig {
    primary_tf_minutes: 15, secondary_tf_minutes: 5,
    regime: "normal", style: "breakout",
    size_mult: 1.0, max_hold_minutes: 240,
};

const US_AFTERNOON_CONFIG: SessionConfig = SessionConfig {
    primary_tf_minutes: 30, secondary_tf_minutes: 60,
    regime: "normal", style: "mean-reversion",
    size_mult: 0.75, max_hold_minutes: 240,
};

const US_POWER_HOUR_CONFIG: SessionConfig = SessionConfig {
    primary_tf_minutes: 5, secondary_tf_minutes: 15,
    regime: "expiry", style: "momentum",
    size_mult: 0.5, max_hold_minutes: 30,
};

const US_EVENING_CONFIG: SessionConfig = SessionConfig {
    primary_tf_minutes: 60, secondary_tf_minutes: 240,
    regime: "normal", style: "range",
    size_mult: 0.25, max_hold_minutes: 1440,
};

const WEEKEND_CONFIG: SessionConfig = SessionConfig {
    primary_tf_minutes: 60, secondary_tf_minutes: 240,
    regime: "normal", style: "none",
    size_mult: 0.0, max_hold_minutes: 0,
};

/// Generate the daily trading plan
pub fn daily_trading_plan(date_str: &str, utc_hour: u32, utc_min: u32, weekday: u32) -> String {
    let (session, config) = current_session(utc_hour, utc_min, weekday);

    let weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    let day_name = if (weekday as usize) < weekday_names.len() { weekday_names[weekday as usize] } else { "?" };

    let mut plan = format!("=== DAILY TRADING PLAN: {} ({}) ===\n", date_str, day_name);

    // Current session
    plan.push_str(&format!(
        "Current session: {:?}\n  TF: {}m / {}m secondary\n  Style: {}\n  Size: {}×\n  Max hold: {}m\n",
        session, config.primary_tf_minutes, config.secondary_tf_minutes,
        config.style, config.size_mult, config.max_hold_minutes,
    ));

    plan
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ny_morning() {
        // 2026-05-14 14:30 UTC = 10:30 ET = NY morning (Thu=4)
        let (sess, _) = current_session(14, 30, 4);
        assert_eq!(sess, TradingSession::NyMorning);
    }

    #[test]
    fn test_power_hour() {
        // 2026-05-14 19:45 UTC = 15:45 ET = Power hour (Thu=4)
        let (sess, _) = current_session(19, 45, 4);
        assert_eq!(sess, TradingSession::UsPowerHour);
    }

    #[test]
    fn test_asia() {
        // 2026-05-15 00:00 UTC = 20:00 ET = Asia (Fri=5 — but Asia runs through weekend boundary)
        let (sess, _) = current_session(0, 0, 4); // Thu
        assert_eq!(sess, TradingSession::Asia);
    }
}
