// makerSim.ts — Compound simulation for the Gengar maker strategy
//
// Runs a multi-day simulation:
// 1. Discover binary markets where NO is in the longshot zone (<20¢)
// 2. Apply gate chain (category, price, spread, liquidity, time-to-resolution)
// 3. Simulate fills and resolutions using Becker-validated win rates
// 4. Track bankroll compounding over time
//
// Based on: Becker (2026) "The Microstructure of Wealth Transfer in Prediction Markets"
// Analyzed 72M+ trades, proven structural maker-taker asymmetry.

import { generateMakerSignals, simulateResolution, formatSignal, type MakerConfig, DEFAULT_MAKER_CONFIG, type MakerSignal, type MakerPosition } from "./makerStrategy.js";

// ═══════════════════════════════════════════════════════════════
// Config
// ═══════════════════════════════════════════════════════════════

interface SimConfig {
  /** Number of simulation days */
  days: number;
  /** Starting bankroll in USD */
  startingBankroll: number;
  /** Maker strategy config */
  makerConfig: MakerConfig;
  /** Maximum concurrent positions */
  maxPositions: number;
  /** Resolve positions after N days (simplified) */
  resolutionDays: number;
}

const DEFAULT_SIM_CONFIG: SimConfig = {
  days: 30,
  startingBankroll: 20,
  makerConfig: DEFAULT_MAKER_CONFIG,
  maxPositions: 5,
  resolutionDays: 7,
};

// ═══════════════════════════════════════════════════════════════
// Runner
// ═══════════════════════════════════════════════════════════════

interface SimDay {
  day: number;
  bankrollBefore: number;
  signalsFound: number;
  signalsExecuted: number;
  positionsResolved: number;
  dailyPnl: number;
  bankrollAfter: number;
  positions: MakerPosition[];
}

export async function runMakerSim(
  config: Partial<SimConfig> = {},
): Promise<{ days: SimDay[]; summary: Record<string, any> }> {
  const cfg: SimConfig = { ...DEFAULT_SIM_CONFIG, ...config };
  const days: SimDay[] = [];
  let bankroll = cfg.startingBankroll;
  const positions: MakerPosition[] = [];
  const tradedTokens = new Set<string>(); // Avoid buying same market repeatedly

  console.log(`[makerSim] Starting ${cfg.days}-day simulation. Bankroll: $${bankroll.toFixed(2)}`);
  console.log(`[makerSim] Maker config: maxEntry=$0.${cfg.makerConfig.maxEntryPrice * 100}, bankroll=$0.${cfg.makerConfig.maxBetUsd}/trade`);
  console.log();

  for (let day = 1; day <= cfg.days; day++) {
    const bankrollBefore = bankroll;
    let dailyPnl = 0;
    let signalsFound = 0;
    let signalsExecuted = 0;
    let positionsResolved = 0;

    // Resolve positions that have aged past resolutionDays
    // Simulate: each day, some positions resolve
    for (let i = positions.length - 1; i >= 0; i--) {
      const pos = positions[i]!;
      const ageDays = (Date.now() - pos.entryTs) / (1000 * 60 * 60 * 24);
      if (ageDays >= cfg.resolutionDays || Math.random() < 0.05) {
        const resolved = simulateResolution(pos);
        positions.splice(i, 1);
        dailyPnl += resolved.pnl;
        bankroll += resolved.pnl;
        positionsResolved++;
      }
    }

    // Generate new signals (limit to maxPositions)
    if (positions.length < cfg.maxPositions && bankroll >= cfg.makerConfig.minBetUsd) {
      try {
        const signals = await generateMakerSignals(cfg.makerConfig);
        signalsFound = signals.length;

        for (const signal of signals) {
          if (tradedTokens.has(signal.tokenId)) continue; // Already traded
          if (signal.costUsd > bankroll) continue; // Can't afford
          if (positions.length >= cfg.maxPositions) break; // At capacity

          signalsExecuted++;
          bankroll -= signal.costUsd;
          dailyPnl -= signal.costUsd; // PnL reflects cost basis
          tradedTokens.add(signal.tokenId);

          positions.push({
            tokenId: signal.tokenId,
            marketTitle: signal.marketTitle,
            category: signal.category,
            entryPrice: signal.noPrice,
            shares: signal.shares,
            costUsd: signal.costUsd,
            entryTs: Date.now() - (day - 1) * 24 * 60 * 60 * 1000, // Backdate to day start
            resolved: false,
            won: null,
            payout: 0,
            pnl: 0,
          });

          console.log(`  [Day ${day}] BUY NO: ${formatSignal(signal)}`);
        }
      } catch (err) {
        console.error(`  [Day ${day}] Signal error: ${(err as Error).message}`);
      }
    }

    const bankrollAfter = bankroll;

    days.push({
      day,
      bankrollBefore,
      signalsFound,
      signalsExecuted,
      positionsResolved,
      dailyPnl: Math.round(dailyPnl * 100) / 100,
      bankrollAfter,
      positions: [...positions],
    });

    // Summary every 10 days
    if (day % 10 === 0 || day === cfg.days) {
      console.log(`[Day ${day}] Bankroll: $${bankroll.toFixed(2)} | PnL: $${(bankroll - cfg.startingBankroll).toFixed(2)} | Positions: ${positions.length}`);
    }
  }

  // Resolve remaining positions
  let finalPnl = 0;
  for (const pos of positions) {
    const resolved = simulateResolution(pos);
    finalPnl += resolved.pnl;
    bankroll += resolved.pnl;
  }

  const totalReturn = bankroll - cfg.startingBankroll;
  const returnPct = ((bankroll / cfg.startingBankroll) - 1) * 100;

  const summary = {
    startingBankroll: cfg.startingBankroll,
    endingBankroll: Math.round(bankroll * 100) / 100,
    totalReturn: Math.round(totalReturn * 100) / 100,
    returnPct: Math.round(returnPct * 100) / 100,
    totalSignals: days.reduce((sum, d) => sum + d.signalsFound, 0),
    totalExecuted: days.reduce((sum, d) => sum + d.signalsExecuted, 0),
    totalResolved: days.reduce((sum, d) => sum + d.positionsResolved, 0) + positions.length,
    finalPositions: positions.length,
    days: cfg.days,
    config: {
      maxEntry: cfg.makerConfig.maxEntryPrice,
      maxBet: cfg.makerConfig.maxBetUsd,
      kelly: cfg.makerConfig.kellyFraction,
    },
  };

  console.log();
  console.log("═══════════════════════════════════════════");
  console.log("  MAKER STRATEGY SIMULATION COMPLETE");
  console.log("═══════════════════════════════════════════");
  console.log(`  Start:   $${summary.startingBankroll.toFixed(2)}`);
  console.log(`  End:     $${summary.endingBankroll.toFixed(2)}`);
  console.log(`  Return:  $${summary.totalReturn.toFixed(2)} (${summary.returnPct}%)`);
  console.log(`  Trades:  ${summary.totalExecuted} executed / ${summary.totalSignals} signals`);
  console.log(`  Resolve: ${summary.totalResolved}`);
  console.log("═══════════════════════════════════════════");

  return { days, summary };
}

// ═══════════════════════════════════════════════════════════════
// CLI Entrypoint
// ═══════════════════════════════════════════════════════════════

async function main() {
  const args = process.argv.slice(2);
  const days = parseInt(args.find((a) => a.startsWith("--days="))?.split("=")[1] ?? "30");
  const bankroll = parseFloat(args.find((a) => a.startsWith("--bankroll="))?.split("=")[1] ?? "20");
  const live = args.includes("--live");

  console.log("[makerSim] Gengar Maker Strategy Simulator");
  console.log(`[makerSim] Mode: ${live ? "LIVE DATA" : "DRY RUN (real Gamma scan, simulated fills)"}`);
  console.log();

  const result = await runMakerSim({ days, startingBankroll: bankroll });

  // Show daily breakdown
  if (args.includes("--verbose")) {
    console.log("\nDaily Breakdown:");
    for (const d of result.days) {
      const status = d.positionsResolved > 0 ? "⚡" : (d.signalsExecuted > 0 ? "📊" : "—");
      console.log(
        `  Day ${String(d.day).padStart(3)}: ${status} ` +
        `bankroll $${d.bankrollBefore.toFixed(2)}→$${d.bankrollAfter.toFixed(2)} ` +
        `| signals: ${d.signalsFound} | exec: ${d.signalsExecuted} | ` +
        `resolve: ${d.positionsResolved} | PnL: $${d.dailyPnl.toFixed(2)}`
      );
    }
  }
}

main().catch(console.error);
