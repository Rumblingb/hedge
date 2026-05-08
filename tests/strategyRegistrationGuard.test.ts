/**
 * PERMANENT GUARD: Validates that every strategy in the catalog is also in
 * SUPPORTED_STRATEGY_IDS, and every strategy file with a Strategy class is
 * registered in the catalog. Prevents orphaned strategies from being invisible
 * to the factory, walkforward, and live-readiness pipelines.
 *
 * Run: npx vitest run tests/strategyRegistrationGuard.test.ts
 */
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { SUPPORTED_STRATEGY_IDS } from "../src/domain.js";
import { buildStrategyCatalog } from "../src/strategies/wctcEnsemble.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const STRATEGY_DIR = join(__dirname, "..", "src", "strategies");

/** Strategies that export Strategy classes but are intentionally excluded from the catalog.
 *  Add IDs here ONLY if they're thin stubs, deprecated, or meta-strategies.
 *  Every addition must include a reason.
 *
 *  Categories:
 *  - THIN_STUB: Retail pattern-detection, no economic rationale, would be noise in factory
 *  - META: Meta-strategy built from catalog dynamically
 *  - DEPRECATED: Retired strategy, kept for reference
 *  - MACRO_ONLY: Requires live macro data unavailable in backtest (deferred until macro pipeline works) */
const EXCLUDED_FROM_CATALOG = new Set<string>([
  // --- META ---
  "wctc-ensemble",           // META: Built dynamically from catalog

  // --- DEPRECATED ---
  "overnight-hold",          // DEPRECATED: No economic thesis on 1-min bars
  "power-hour",              // DEPRECATED: Pattern-detection noise

  // --- THIN STUBS (retail pattern-detection, would add noise to factory) ---
  // Chart patterns
  "breakout-retest", "volume-spike", "market-structure", "trendline-break",
  "multi-timeframe", "head-shoulders", "double-top-bottom", "flag-pennant",
  "wedge-breakout",
  // Indicator-based
  "adx-trend", "donchian-breakout", "ichimoku", "macd-crossover", "keltner-channel",
  "stochastic", "heikin-ashi", "false-breakout",
  "inside-bar", "pin-bar", "engulfing-pattern",
  "delta-divergence", "rsi-divergence",
  // Scalping / prop retail
  "scalping", "tick-scalp", "zscore-mean-rev", "open-drive-fade",
  "time-based-exit", "range-bound-scalp",
  "prop-fvg-scalp", "prop-liq-grab", "prop-orb-scalp", "prop-vwap-bounce",
  "prop-momentum-scalp",
  // Pattern-based
  "enhanced-orb", "gap-fade",
  "market-open-drive", "market-profile", "supply-demand",
  "news-spike-fade", "seasonality",
  // Event stubs (no real event data feed)
  "opening-auction", "closing-auction",
  "pre-fomc-drift", "post-fomc-fade", "nfp-reaction",
  "cpi-reaction", "opec-fade", "eia-inventory",
  // Novel/experimental with no evidence
  "rl-inspired", "uncertainty-sizing", "ensemble-meta",

  // --- MACRO ONLY (require live data feeds unavailable in backtest) ---
  "carry-trade",             // MACRO_ONLY: Needs cost-of-carry / interest rate data
  "zero-dte-flow",           // MACRO_ONLY: Needs options flow data
  "vol-skew",                // MACRO_ONLY: Needs options chain
  "credit-spread",           // MACRO_ONLY: Needs bond data
  "gold-silver-ratio",       // MACRO_ONLY: Cross-asset ratio needs multi-symbol bars
  "copper-gold-ratio",       // MACRO_ONLY: Cross-asset ratio
  "oil-crack-spread",        // MACRO_ONLY: Needs multi-commodity data
  "natgas-seasonality",      // MACRO_ONLY: Single-commodity seasonal (works but thin)
  "btc-correlation",         // MACRO_ONLY: Needs BTC data
  "fed-put-strategy",        // MACRO_ONLY: Needs Fed calendar + macro
  "event-arbitrage",         // MACRO_ONLY: Needs live event feed
  "cot-positioning",         // MACRO_ONLY: Needs COT data (available but not wired to backtest)
  "vix-term-structure",      // MACRO_ONLY: Needs VIX term structure
  "gamma-pin",               // MACRO_ONLY: Needs options gamma data
  "dark-pool-print",         // MACRO_ONLY: Needs dark pool data (unavailable)
  "block-trade-fade",        // MACRO_ONLY: Needs block trade feed
  "auction-imbalance",       // MACRO_ONLY: Needs auction data (unavailable)
  "yield-curve-steepen",     // MACRO_ONLY: Needs yield curve data
  "inflation-breakeven",     // MACRO_ONLY: Needs inflation data
  "dollar-smile",            // MACRO_ONLY: Needs FX data
  "risk-parity-rebalance",   // MACRO_ONLY: Needs multi-asset rebalance calendar
  "volatility-of-vol",       // MACRO_ONLY: Needs VIX/options
  "correlation-switch",      // MACRO_ONLY: Needs multi-asset correlation
  "momentum-crash",          // MACRO_ONLY: Needs factor data
  "liquidity-cascade",       // MACRO_ONLY: Needs liquidity metrics
  "dispersion-trading",      // MACRO_ONLY: Needs options dispersion
  "pairs-convergence",       // MACRO_ONLY: Needs pairs identification
  "implied-correlation",     // MACRO_ONLY: Needs options IV data
  "tail-risk",               // MACRO_ONLY: Needs options data
  "regime-probability",      // MACRO_ONLY: Needs regime model
  "overnight-drift",         // MACRO_ONLY: Needs overnight session data
  "pre-market-reversal",     // MACRO_ONLY: Needs pre-market data
  "initial-balance",         // MACRO_ONLY: Needs IB data
  "econ-surprise",           // MACRO_ONLY: Needs economic calendar
  "put-call-signal",         // MACRO_ONLY: Needs options P/C ratio
  "order-flow-imbalance",    // MACRO_ONLY: Needs order flow (ticks not available)
  "hawkes-process",          // MACRO_ONLY: Needs tick data
  "harnet-vol",              // MACRO_ONLY: Needs options vol
  "optimal-execution",       // MACRO_ONLY: Execution algo, not signal
  "gamma-scalp",             // MACRO_ONLY: Needs gamma exposure data
  "vol-premium",             // MACRO_ONLY: Needs VIX futures
  "renko-momentum",          // MACRO_ONLY: Needs Renko bars (not generated)
  "event-driven",            // MACRO_ONLY: Needs live event calendar
  "vol-targeted-momentum",   // MACRO_ONLY: Meta-wrapper, not standalone

  // --- ASPIRATIONAL (planned but not yet implemented with real edge) ---
  "momentum-ignition",       // ASPIRATIONAL: Concept only, no unique implementation
  "value-area-rotation",     // ASPIRATIONAL: Volume profile concept, not implementable
  "algo-execution",          // ASPIRATIONAL: Execution algo concept
  "cross-venue-arb",         // ASPIRATIONAL: PM cross-venue already handled separately
]);

describe("Strategy registration guard", () => {
  const catalog = buildStrategyCatalog();
  const catalogIds = new Set(Object.keys(catalog));
  const supportedSet = new Set<string>(SUPPORTED_STRATEGY_IDS);

  it("every strategy in the catalog must be in SUPPORTED_STRATEGY_IDS", () => {
    const missing: string[] = [];
    for (const id of catalogIds) {
      if (!supportedSet.has(id)) {
        missing.push(id);
      }
    }
    if (missing.length > 0) {
      throw new Error(
        `These strategy IDs are in the catalog but NOT in SUPPORTED_STRATEGY_IDS in domain.ts:\n` +
        `  ${missing.join(", ")}\n` +
        `Add them to SUPPORTED_STRATEGY_IDS in src/domain.ts.`
      );
    }
  });

  it("every Strategy class in src/strategies/ must be in the catalog (or excluded)", () => {
    const strategyFiles = readdirSync(STRATEGY_DIR).filter(
      (f) => f.endsWith(".ts") && f !== "wctcEnsemble.ts"
    );

    const orphaned: string[] = [];

    for (const file of strategyFiles) {
      const content = readFileSync(join(STRATEGY_DIR, file), "utf-8");
      // Find all `public readonly id = "x"` or `public id = "x"` declarations
      const idMatches = content.matchAll(
        /public\s+(?:readonly\s+)?id\s*=\s*"([^"]+)"/g
      );
      for (const match of idMatches) {
        const id = match[1];
        if (!catalogIds.has(id) && !EXCLUDED_FROM_CATALOG.has(id)) {
          orphaned.push(`${id} (from ${file})`);
        }
      }
    }

    if (orphaned.length > 0) {
      throw new Error(
        `These Strategy class IDs are NOT registered in buildStrategyCatalog():\n` +
        `  ${orphaned.join("\n  ")}\n` +
        `Either:\n` +
        `  1. Import and register them in src/strategies/wctcEnsemble.ts, OR\n` +
        `  2. Add their ID to EXCLUDED_FROM_CATALOG in this test with a reason.\n` +
        `They will be INVISIBLE to the strategy factory, walkforward, and live-readiness.`
      );
    }
  });

  it("catalog entry count matches documented expectations", () => {
    // This is a canary — if the catalog shrinks unexpectedly, it fails.
    // Update the expected count when intentionally adding/removing strategies.
    const minExpected = 50; // We have 54 as of 2026-05-08
    expect(catalogIds.size).toBeGreaterThanOrEqual(minExpected);
  });
});
