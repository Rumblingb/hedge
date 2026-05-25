// portfolio.rs — Institutional portfolio construction for multi-strategy futures trading.
//
// Implements three core components:
//   1. Kelly Capital Allocation — optimal multi-strategy sizing
//   2. Risk Parity (ERC) — equal risk contribution across strategies
//   3. CPPI Drawdown Control — capital protection with floor + multiplier
//
// All values are in "R" (risk multiples) to remain instrument-agnostic.

use crate::types::BacktestTrade;

// ─── 1. Kelly Capital Allocation ──────────────────────────────────────

/// Compute the full-Kelly fraction for a strategy given its win/loss history.
/// Uses the simplified formula: f* = (p * avgW - q * avgL) / (avgW * avgL)
/// where p = win rate, q = 1-p, avgW = average win size (in R), avgL = average loss size.
/// Returns the fraction of capital to allocate (0.0 to 1.0).
pub fn kelly_fraction(win_rate: f64, avg_win_r: f64, avg_loss_r: f64) -> f64 {
    if avg_win_r <= 0.0 || avg_loss_r <= 0.0 {
        return 0.0;
    }
    let p = win_rate.clamp(0.001, 0.999);
    let q = 1.0 - p;
    let kelly = (p * avg_win_r - q * avg_loss_r.abs()) / (avg_win_r * avg_loss_r.abs());
    // Quarter-Kelly for safety (institutional standard)
    (kelly * 0.25).clamp(0.0, 0.50)
}

/// Compute optimum fraction when edge and odds are known directly (e.g., PM markets).
pub fn kelly_bet(edge: f64, odds: f64, fraction: f64) -> f64 {
    // f = (p * (b+1) - 1) / b  where b = odds, p = prob = edge + 1/(b+1)
    if odds <= 0.0 || edge <= 0.0 {
        return 0.0;
    }
    let p = (edge + 1.0 / (odds + 1.0)).clamp(0.001, 0.999);
    let q = 1.0 - p;
    let kelly = (p * (odds + 1.0) - 1.0) / odds;
    (kelly * fraction).clamp(0.0, 1.0)
}

/// Allocate capital across N strategies using Kelly-optimal weights.
/// Returns a vec of allocation fractions that sum to <= 1.0.
pub fn kelly_allocate(strategy_stats: &[(f64, f64, f64)]) -> Vec<f64> {
    // strategy_stats: (win_rate, avg_win_r, avg_loss_r)
    let fractions: Vec<f64> = strategy_stats
        .iter()
        .map(|&(wr, aw, al)| kelly_fraction(wr, aw, al))
        .collect();

    let total: f64 = fractions.iter().sum();
    if total <= 0.0 {
        return vec![0.0; fractions.len()];
    }

    // Normalize to sum to 1.0 (full capital utilization)
    fractions.iter().map(|f| f / total).collect()
}

// ─── 2. Risk Parity (Equal Risk Contribution) ───────────────────────

/// Compute Equal Risk Contribution (ERC) weights for a portfolio of strategies.
/// Uses simplified approach: weight_i = 1 / vol_i / sum(1/vol_j)
/// where vol_i is estimated from trade returns.
pub fn erc_weights(trade_returns_by_strategy: &[&[f64]]) -> Vec<f64> {
    let n = trade_returns_by_strategy.len();
    if n == 0 {
        return vec![];
    }

    let mut inv_vols = Vec::with_capacity(n);
    for returns in trade_returns_by_strategy {
        let n_obs = returns.len();
        if n_obs < 5 {
            inv_vols.push(0.0);
            continue;
        }
        let mean: f64 = returns.iter().sum::<f64>() / n_obs as f64;
        let variance: f64 =
            returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / (n_obs - 1) as f64;
        let vol = variance.sqrt().max(0.0001);
        inv_vols.push(1.0 / vol);
    }

    let total: f64 = inv_vols.iter().sum();
    if total <= 0.0 {
        return vec![1.0 / n as f64; n];
    }

    inv_vols.iter().map(|iv| iv / total).collect()
}

// ─── 3. CPPI Drawdown Control ────────────────────────────────────────

/// CPPI (Constant Proportion Portfolio Insurance) state.
pub struct CppiState {
    /// Portfolio value in R units (starts at initial capital / risk-per-trade)
    pub value: f64,
    /// Floor value as fraction of peak (e.g., 0.85 = never lose more than 15%)
    pub floor_pct: f64,
    /// Multiplier (typically 3-5x)
    pub multiplier: f64,
    /// Peak value achieved
    pub peak: f64,
    /// Current exposure multiplier (cushion * multiplier / value)
    pub exposure_pct: f64,
}

impl CppiState {
    pub fn new(initial_value: f64, floor_pct: f64, multiplier: f64) -> Self {
        let value = initial_value.max(0.0);
        Self {
            value,
            floor_pct: floor_pct.clamp(0.0, 1.0),
            multiplier: multiplier.max(1.0),
            peak: value,
            exposure_pct: 1.0,
        }
    }

    /// Update after a trade result. Returns the new exposure percentage for the next trade.
    pub fn update(&mut self, trade_r: f64) -> f64 {
        self.value += trade_r;
        self.peak = self.peak.max(self.value);

        let floor = self.peak * self.floor_pct;
        let cushion = (self.value - floor).max(0.0);
        let cushion_pct = if self.value > 0.0 {
            cushion / self.value
        } else {
            0.0
        };

        // CPPI: exposure = multiplier * cushion
        self.exposure_pct = (self.multiplier * cushion_pct).clamp(0.0, 2.0);

        // Stepped drawdown reduction
        let dd_from_peak = if self.peak > 0.0 {
            (self.peak - self.value) / self.peak
        } else {
            0.0
        };

        if dd_from_peak > 0.20 {
            self.exposure_pct = 0.0; // Full stop at 20% drawdown
        } else if dd_from_peak > 0.10 {
            self.exposure_pct = self.exposure_pct * 0.5; // Half size at 10%
        } else if dd_from_peak > 0.05 {
            self.exposure_pct = self.exposure_pct * 0.75; // 75% at 5%
        }

        self.exposure_pct
    }

    /// Whether trading should continue (value above floor).
    pub fn is_alive(&self) -> bool {
        self.value > self.peak * self.floor_pct
    }
}

// ─── 4. VIX Term Structure Regime Detector ──────────────────────────

/// VIX term structure regimes for ES/NQ position sizing.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum VixRegime {
    /// Steep contango: VX1 << VX2 — low vol, risk-on environment
    SteepContango,
    /// Mild contango: VX1 < VX2 — normal conditions
    MildContango,
    /// Flat: VX1 ≈ VX2 — transition zone
    Flat,
    /// Mild backwardation: VX1 > VX2 — elevated fear
    MildBackwardation,
    /// Steep backwardation: VX1 >> VX2 — panic / crisis
    SteepBackwardation,
}

/// Detect VIX term structure regime from front-month (VX1) and second-month (VX2) futures.
/// Returns the regime and recommended position sizing multiplier for ES and NQ.
pub fn detect_vix_regime(vx1: f64, vx2: f64) -> (VixRegime, f64, f64) {
    if vx1 <= 0.0 || vx2 <= 0.0 {
        return (VixRegime::Flat, 0.5, 0.5); // No data → conservative
    }

    let slope = (vx2 - vx1) / vx1; // Normalized slope

    if slope > 0.08 {
        // Steep contango — risk-on, low vol
        (VixRegime::SteepContango, 1.0, 0.8)
    } else if slope > 0.03 {
        // Mild contango — normal risk-on
        (VixRegime::MildContango, 0.8, 0.6)
    } else if slope < -0.08 {
        // Steep backwardation — panic
        (VixRegime::SteepBackwardation, 0.3, 0.0)
    } else if slope < -0.03 {
        // Mild backwardation — elevated fear
        (VixRegime::MildBackwardation, 0.5, 0.2)
    } else {
        // Flat — transition
        (VixRegime::Flat, 0.6, 0.5)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kelly_fraction_coinflip() {
        // A 55/45 coin flip with 1:1 payout → small edge
        let f = kelly_fraction(0.55, 1.0, 1.0);
        assert!(
            f > 0.01 && f < 0.20,
            "quarter-kelly of edge should be small"
        );
    }

    #[test]
    fn test_kelly_fraction_no_edge() {
        let f = kelly_fraction(0.50, 1.0, 1.0);
        assert_eq!(f, 0.0, "no edge → no bet");
    }

    #[test]
    fn test_kelly_bet() {
        let bet = kelly_bet(0.05, 1.0, 0.25);
        assert!(bet > 0.0 && bet < 0.25, "quarter-Kelly with edge");
    }

    #[test]
    fn test_cppi_basic() {
        let mut cppi = CppiState::new(100.0, 0.85, 3.0);
        assert!(cppi.is_alive());
        let exp = cppi.update(-5.0); // -5R loss
        assert!(exp > 0.0, "should still have exposure after small loss");
        assert!(exp < 1.0, "exposure should reduce after loss");
    }

    #[test]
    fn test_cppi_death() {
        let mut cppi = CppiState::new(100.0, 0.85, 3.0);
        cppi.update(-20.0); // Below floor
        assert!(!cppi.is_alive(), "20% loss should kill CPPI");
    }

    #[test]
    fn test_vix_contango() {
        let (regime, es_sz, nq_sz) = detect_vix_regime(15.0, 17.0); // 13% contango
        assert_eq!(regime, VixRegime::SteepContango);
        assert!((es_sz - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_vix_backwardation() {
        let (regime, _, nq_sz) = detect_vix_regime(35.0, 28.0); // 20% backwardation
        assert_eq!(regime, VixRegime::SteepBackwardation);
        assert!((nq_sz - 0.0).abs() < 0.01, "NQ should be flat in panic");
    }

    #[test]
    fn test_erc_weights() {
        let s1_returns = vec![1.0, -0.5, 0.8, -0.3, 1.2]; // ~0.85 vol
        let s2_returns = vec![0.1, -0.05, 0.08, -0.03, 0.12]; // ~0.085 vol
        let weights = erc_weights(&[&s1_returns, &s2_returns]);
        assert_eq!(weights.len(), 2);
        // Lower-vol strategy gets higher weight
        assert!(weights[1] > weights[0], "lower vol should get more weight");
    }
}
