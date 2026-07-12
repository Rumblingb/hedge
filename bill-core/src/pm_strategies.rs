/// Polymarket BTC UP/DOWN prediction market strategies.
/// Based on proven open-source bots and academic research.

/// Error function approximation (Abramowitz and Stegun 7.1.26).
fn erf(x: f64) -> f64 {
    let sign = if x >= 0.0 { 1.0 } else { -1.0 };
    let x = x.abs();
    let a1 = 0.254829592;
    let a2 = -0.284496736;
    let a3 = 1.421413741;
    let a4 = -1.453152027;
    let a5 = 1.061405429;
    let p = 0.3275911;
    let t = 1.0 / (1.0 + p * x);
    let y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (-x * x).exp();
    sign * y
}

/// Gengar Bot Strategy: Brownian Motion Model for Polymarket BTC 5-min UP/DOWN.
///
/// Edge: Polymarket reprices BTC markets with a lag behind Binance.
/// Strategy: When BTC moves significantly in the 5-min window, buy the correct
/// side before Polymarket's order book catches up.
///
/// Calibrated (gengar bot v13, +55% ROC, 100% WR on clean data):
/// - vol: 0.12 (percentage points, i.e., 0.12% = 12 bps)
/// - min_prob: 0.80
/// - min_edge: 0.05 (5% edge between prob and price)
/// - min_btc_delta: 0.06% (6 bps minimum BTC move)
/// - max_price: 0.90, min_price: 0.50
/// - entry window: 240s to 10s remaining
/// - kelly_fraction: 0.25, min_bet: $5, max_bet: $25
pub struct BtcBrownianMotion {
    pub btc_open_price: f64,
    pub btc_current_price: f64,
    pub seconds_elapsed: f64,
    pub seconds_total: f64,
    pub up_price: f64,
    pub down_price: f64,
}

impl BtcBrownianMotion {
    /// BTC delta as percentage points (0.05 = 0.05%, matching gengar convention).
    pub fn delta_pct_bps(&self) -> f64 {
        if self.btc_open_price <= 0.0 {
            return 0.0;
        }
        ((self.btc_current_price - self.btc_open_price) / self.btc_open_price) * 100.0
    }

    /// Brownian motion probability using gengar's exact formula:
    /// time_factor = seconds_remaining / 300
    /// effective_vol = vol * sqrt(time_factor)
    /// z = |delta| / effective_vol
    /// prob = 0.5 * (1 + erf(z / sqrt(2)))
    pub fn prob_up(&self, vol: f64) -> f64 {
        let time_factor = (self.seconds_remaining() / self.seconds_total).max(1.0 / 300.0);
        let effective_vol = vol * time_factor.sqrt();
        if effective_vol <= 0.0 {
            return if self.delta_pct_bps() > 0.0 { 1.0 } else { 0.0 };
        }
        let z = self.delta_pct_bps().abs() / effective_vol;
        let prob = 0.5 * (1.0 + erf(z / (2.0_f64).sqrt()));
        prob.clamp(0.01, 0.99)
    }

    pub fn seconds_remaining(&self) -> f64 {
        (self.seconds_total - self.seconds_elapsed).max(0.0)
    }

    /// Full gengar gate chain. Returns kelly_bet_pct if all gates pass.
    pub fn evaluate(&self, realized_vol: Option<f64>) -> Option<TradeDecision> {
        let vol = realized_vol.unwrap_or(0.12); // 0.12% = 12 bps
        let min_btc_delta: f64 = 0.06; // 0.06% minimum BTC move
        let min_prob: f64 = 0.80;
        let min_edge: f64 = 0.05; // 5% edge between prob and price
        let max_price: f64 = 0.90;
        let min_price: f64 = 0.50;
        let entry_window_start: f64 = 240.0;
        let entry_window_end: f64 = 10.0;

        // Gate 0: Entry window (240s → 10s remaining)
        let remaining = self.seconds_remaining();
        if remaining > entry_window_start || remaining < entry_window_end {
            return None;
        }

        // Gate 1: Minimum BTC delta
        let delta = self.delta_pct_bps();
        if delta.abs() < min_btc_delta {
            return None;
        }

        // Gate 2: Price in range
        let side = if delta > 0.0 { "UP" } else { "DOWN" };
        let market_price = if delta > 0.0 {
            self.up_price
        } else {
            self.down_price
        };
        if market_price > max_price || market_price < min_price {
            return None;
        }

        // Gate 3: Probability
        // Gengar's prob_up computes P(trend continues) for both directions.
        // P(N(-δ, σ²) < 0) = P(N(+δ, σ²) > 0) by symmetry — same formula, uses abs(delta).
        let prob = self.prob_up(vol);
        if prob < min_prob {
            return None;
        }

        // Gate 4: Minimum edge
        let edge = prob - market_price;
        if edge < min_edge {
            return None;
        }

        // Kelly sizing
        let b = (1.0 - market_price) / market_price.max(0.01);
        let q = 1.0 - prob;
        let kelly = (b * prob - q) / b.max(0.01);
        if kelly <= 0.0 {
            return None;
        }
        let kelly_bet = kelly * 0.25; // Quarter-Kelly

        Some(TradeDecision {
            side: side.to_string(),
            prob,
            edge,
            market_price,
            delta_bps: delta,
            kelly_bet,
            seconds_remaining: remaining,
        })
    }
}

pub struct TradeDecision {
    pub side: String,
    pub prob: f64,
    pub edge: f64,
    pub market_price: f64,
    pub delta_bps: f64,
    pub kelly_bet: f64,
    pub seconds_remaining: f64,
}

/// Cross-Platform Arbitrage: Polymarket ↔ Kalshi BTC 1-hour UP/DOWN.
///
/// Edge: Same question, different venue, different pricing.
/// BUY the cheaper side on one venue, SELL (or buy opposite) on the other.
/// If combined cost < $1.00, guaranteed profit at resolution.
pub struct CrossVenueArb {
    pub poly_up: f64,    // Polymarket BTC UP price
    pub poly_down: f64,  // Polymarket BTC DOWN price
    pub kalshi_yes: f64, // Kalshi BTC UP price
    pub kalshi_no: f64,  // Kalshi BTC DOWN price
}

impl CrossVenueArb {
    /// Check arbitrage: buy UP on cheaper venue, buy DOWN on cheaper venue.
    /// If poly_up + kalshi_no < 1.0 → arb on UP.
    /// If kalshi_yes + poly_down < 1.0 → arb on DOWN.
    pub fn find_arbitrage(&self) -> Option<ArbOpportunity> {
        let cost_up_arb = self.poly_up + self.kalshi_no;
        let cost_down_arb = self.kalshi_yes + self.poly_down;

        let min_edge = 0.005; // 0.5% minimum after fees

        if cost_up_arb < 1.0 - min_edge {
            return Some(ArbOpportunity {
                direction: "UP".to_string(),
                buy_venue: "polymarket".to_string(),
                buy_price: self.poly_up,
                hedge_venue: "kalshi".to_string(),
                hedge_price: self.kalshi_no,
                total_cost: cost_up_arb,
                guaranteed_return: (1.0 - cost_up_arb) / cost_up_arb,
            });
        }

        if cost_down_arb < 1.0 - min_edge {
            return Some(ArbOpportunity {
                direction: "DOWN".to_string(),
                buy_venue: "kalshi".to_string(),
                buy_price: self.kalshi_yes,
                hedge_venue: "polymarket".to_string(),
                hedge_price: self.poly_down,
                total_cost: cost_down_arb,
                guaranteed_return: (1.0 - cost_down_arb) / cost_down_arb,
            });
        }

        None
    }
}

pub struct ArbOpportunity {
    pub direction: String,
    pub buy_venue: String,
    pub buy_price: f64,
    pub hedge_venue: String,
    pub hedge_price: f64,
    pub total_cost: f64,
    pub guaranteed_return: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_erf() {
        // erf(0) = 0, erf(∞) = 1
        assert!(erf(0.0).abs() < 0.001);
        assert!((erf(1.0) - 0.8427).abs() < 0.01);
        assert!((erf(-1.0) + 0.8427).abs() < 0.01);
    }

    #[test]
    fn test_brownian_motion_no_edge() {
        // No BTC movement → should not enter
        let model = BtcBrownianMotion {
            btc_open_price: 74000.0,
            btc_current_price: 74000.0,
            seconds_elapsed: 60.0,
            seconds_total: 300.0,
            up_price: 0.50,
            down_price: 0.55,
        };
        assert!(model.evaluate(None).is_none());
    }

    #[test]
    fn test_brownian_motion_strong_signal() {
        // BTC +0.5% move within window → should fire
        let model = BtcBrownianMotion {
            btc_open_price: 74000.0,
            btc_current_price: 74370.0, // +0.5% = 50 bps
            seconds_elapsed: 120.0,
            seconds_total: 300.0,
            up_price: 0.65,
            down_price: 0.38,
        };
        let result = model.evaluate(None);
        assert!(result.is_some());
        let d = result.unwrap();
        assert_eq!(d.side, "UP");
        assert!(d.kelly_bet > 0.0 && d.kelly_bet < 1.0);
    }

    #[test]
    fn test_brownian_motion_price_out_of_range() {
        // Strong move but price too high
        let model = BtcBrownianMotion {
            btc_open_price: 74000.0,
            btc_current_price: 74370.0,
            seconds_elapsed: 120.0,
            seconds_total: 300.0,
            up_price: 0.95, // Above max_price=0.90
            down_price: 0.08,
        };
        assert!(model.evaluate(None).is_none());
    }

    #[test]
    fn test_brownian_motion_outside_window() {
        // Too early in the window
        let model = BtcBrownianMotion {
            btc_open_price: 74000.0,
            btc_current_price: 74370.0,
            seconds_elapsed: 10.0, // Only 10s elapsed = 290s remaining > 240
            seconds_total: 300.0,
            up_price: 0.65,
            down_price: 0.38,
        };
        assert!(model.evaluate(None).is_none());
    }

    #[test]
    fn test_brownian_motion_delta_too_small() {
        let model = BtcBrownianMotion {
            btc_open_price: 74000.0,
            btc_current_price: 74010.0, // Only 0.0135% < min_btc_delta=0.06%
            seconds_elapsed: 120.0,
            seconds_total: 300.0,
            up_price: 0.52,
            down_price: 0.52,
        };
        assert!(model.evaluate(None).is_none());
    }

    #[test]
    fn test_cross_venue_arb() {
        let arb = CrossVenueArb {
            poly_up: 0.45,
            poly_down: 0.58,
            kalshi_yes: 0.52,
            kalshi_no: 0.50,
        };
        // poly_up (0.45) + kalshi_no (0.50) = 0.95 < 1.0 → arb!
        let result = arb.find_arbitrage();
        assert!(result.is_some());
        let opp = result.unwrap();
        assert!(opp.total_cost < 1.0);
        assert!(opp.guaranteed_return > 0.0);
    }

    #[test]
    fn test_cross_venue_no_arb() {
        let arb = CrossVenueArb {
            poly_up: 0.52,
            poly_down: 0.52,
            kalshi_yes: 0.53,
            kalshi_no: 0.51,
        };
        // All combinations > 1.0 → no arb
        assert!(arb.find_arbitrage().is_none());
    }
}
