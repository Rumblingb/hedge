/**
 * Batch strategy test runner — fixed.
 * Tests each strategy individually against the ES 20yr and NQ 3yr datasets only.
 * Constructs a fully relaxed LabConfig inline instead of relying on getConfig() or env vars.
 */
import { buildStrategyCatalog } from "../src/strategies/wctcEnsemble.js";
import { runBacktest } from "../src/engine/backtest.js";
import { loadBarsFromCsv } from "../src/data/csv.js";
import { NoopNewsGate } from "../src/news/base.js";
import { writeFile } from "node:fs/promises";

// ── Datasets (ES 20yr + NQ 3yr only, 60m) ──
const DATASETS = {
  "NQ-60m-3yr":  "data/free/NQ-2022-2025-60m.csv",
  "ES-60m-20yr": "data/free/ES-2000-2019-60m.csv",
};

// ── Fully relaxed config — no env vars, no getConfig() ──
// All guardrails are set to permissive values so every strategy signal gets through.
const RELAXED_CONFIG = {
  mode: "backtest",
  accountPhase: "challenge",
  journalPath: "/dev/null",
  killSwitchPath: "/dev/null",
  enabledStrategies: [],
  guardrails: {
    allowedSymbols:              ["NQ", "ES", "MNQ", "MES"],
    sessionStartCt:              "00:00",
    lastEntryCt:                 "23:59",
    flatByCt:                    "23:59",
    minRr:                       0.5,
    maxRiskPerTradePct:          100,
    maxContracts:                999,
    maxTradesPerDay:             999,
    maxHoldMinutes:              9999,
    maxDailyLossR:               999,
    trailingMaxDrawdownR:        999,
    maxConsecutiveLosses:        999,
    newsProbabilityThreshold:    0.0,
    newsBlackoutMinutesBefore:   0,
    newsBlackoutMinutesAfter:    0,
  },
  executionCosts: {
    roundTripFeeRPerContract:    0.01,
    slippageRPerSidePerContract: 0.015,
    stressMultiplier:            1.0,
    stressBufferRPerTrade:       0,
  },
  executionEnv: {
    latencyMs:                  0,
    latencyJitterMs:            0,
    slippageTicksPerSide:       0,
    dataQualityPenaltyR:        0,
    maxSpreadTicks:             99,
    riskPerContractDollars:     300,
    slippageModel:              "ticks",
  },
  stopManagement: {
    enabled:                    false,
    breakEvenTriggerR:          99,
    breakEvenOffsetR:           0,
    runnerEnabled:              false,
    runnerTriggerR:             99,
    runnerTrailingDistanceR:    99,
  },
  tuning: {
    momentumLookbackBars:       6,
    momentumVolumeMultiplier:   1.05,
    reversionLookbackBars:      10,
    reversionVolumeMultiplier:  0,
    reversionWickToBody:        1.0,
    openingRangeVolumeMultiplier: 0,
    measuredMoveRr:             2.0,
    volatilityKillAtrMultiple:  4.5,
    pairsZEntry:                1.5,
    pairsLookbackBars:          15,
    volRegimeAtrFast:           3,
    volRegimeAtrSlow:           15,
    volRegimeThreshold:         1.2,
  },
  live: {
    enabled:                    false,
    demoOnly:                   true,
    readOnly:                   true,
  },
  polygon: {
    enabled:                    false,
  },
};

const catalog = buildStrategyCatalog();
const strategyIds = Object.keys(catalog);
console.log(`Catalog loaded: ${strategyIds.length} strategies\n`);

const allResults = [];
const minSignals = 5;
const newsGate = new NoopNewsGate();

for (const [dsName, csvPath] of Object.entries(DATASETS)) {
  const bars = await loadBarsFromCsv(csvPath);
  // Filter to NQ/ES bars only
  const symbolFilter = new Set(["NQ", "ES", "MNQ", "MES"]);
  const filteredBars = bars.filter((b) => symbolFilter.has(b.symbol));
  console.log(`=== ${dsName} (${filteredBars.length} bars of ${bars.length} total) ===`);

  for (const [strategyId, strategy] of Object.entries(catalog)) {
    try {
      const result = await runBacktest({
        bars: filteredBars,
        strategy,
        config: RELAXED_CONFIG,
        newsGate,
      });

      const trades = result.trades;
      const winners = trades.filter((t) => t.netRMultiple > 0).length;
      const losers = trades.filter((t) => t.netRMultiple <= 0).length;
      const totalR = trades.reduce((s, t) => s + t.netRMultiple, 0);
      const rWinners = trades.filter((t) => t.netRMultiple > 0).reduce((s, t) => s + t.netRMultiple, 0);
      const rLosers  = trades.filter((t) => t.netRMultiple <= 0).reduce((s, t) => s + t.netRMultiple, 0);
      const profitFactor = trades.length > 0 && rLosers < 0
        ? rWinners / Math.abs(rLosers)
        : trades.length > 0 && rLosers === 0
          ? rWinners > 0 ? Infinity : 0
          : 0;

      const avgR = trades.length > 0 ? totalR / trades.length : 0;

      const entry = {
        strategy: strategyId,
        dataset: dsName,
        bars: filteredBars.length,
        trades: trades.length,
        winners,
        losers,
        winRate: trades.length > 0 ? Number((winners / trades.length * 100).toFixed(1)) : 0,
        totalR: Number(totalR.toFixed(4)),
        avgR: Number(avgR.toFixed(4)),
        profitFactor: Number.isFinite(profitFactor) ? Number(profitFactor.toFixed(4)) : (profitFactor > 0 ? 999.9999 : 0),
      };

      allResults.push(entry);

      const status = trades.length >= minSignals
        ? (profitFactor > 1 ? "✅" : "⚠️")
        : (trades.length > 0 ? "🔶" : "❌");

      console.log(
        `${status} ${strategyId.padEnd(25)} | ${String(trades.length).padStart(3)} trades | ` +
        `WR=${entry.winRate}% | AvgR=${entry.avgR} | PF=${entry.profitFactor}`
      );
    } catch (e) {
      allResults.push({ strategy: strategyId, dataset: dsName, error: e.message });
      console.log(`❌ ${strategyId}: ${(e.message ?? String(e)).slice(0, 80)}`);
    }
  }
}

// Sort by profit factor descending (numeric sort, not string)
allResults.sort((a, b) => (b.profitFactor ?? 0) - (a.profitFactor ?? 0));

await writeFile(
  ".rumbling-hedge/state/strategy-batch-test-results.json",
  JSON.stringify(allResults, null, 2),
);
console.log(`\n\n=== COMPLETE: ${allResults.length} strategy×dataset combos tested ===`);
console.log("Results saved to .rumbling-hedge/state/strategy-batch-test-results.json");

// Print top 10
console.log("\n=== TOP 10 RESULTS BY PROFIT FACTOR (≥5 trades) ===");
for (const r of allResults.filter((r) => r.trades >= minSignals).slice(0, 10)) {
  console.log(
    `${r.strategy.padEnd(25)} | ${r.dataset.padEnd(15)} | ${String(r.trades).padStart(3)}t | ` +
    `WR=${r.winRate}% | R=${r.totalR} | PF=${r.profitFactor}`
  );
}
