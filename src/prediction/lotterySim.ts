#!/usr/bin/env npx tsx
// lotterySim.ts — Lottery ticket compound wealth demo.
//
// Uses the lotteryTicket.ts edge module to simulate compound growth
// from BTC 5-min lottery ticket positions only.
//
// Based on @marketing101's verified $382K strategy:
//   - Only BTC Up/Down 5-min markets, UP side only
//   - Entries at 3-30¢ with micro-sized positions
//   - Hold to resolution, no early exits
//
// Usage: npx tsx src/prediction/lotterySim.ts [--rounds 500]

import {
  generateLotterySignals,
  simulateResolution,
  DEFAULT_LOTTERY_CONFIG,
  estimateUpProbability,
  type LotteryPosition,
  type LotterySignal,
  type LotteryTicketConfig,
} from "./lotteryTicket.js";

// ═══════════════════════════════════════════════════════════════
// Config
// ═══════════════════════════════════════════════════════════════

interface SimConfig {
  rounds: number;           // Number of trading rounds to simulate
  bankrollStart: number;    // Starting bankroll in USD
  stopFloorUsd: number;     // Halt simulation if bankroll drops below
  maxOpenPositions: number;  // Max concurrent lottery positions
  lottery: LotteryTicketConfig;
}

const CONFIG: SimConfig = {
  rounds: 500,
  bankrollStart: 20,
  stopFloorUsd: 5,
  maxOpenPositions: 3,
  lottery: DEFAULT_LOTTERY_CONFIG,
};

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

interface SimRound {
  round: number;
  bankrollBefore: number;
  action: "BUY" | "RESOLVE_WIN" | "RESOLVE_LOSS" | "HOLD" | "HALT";
  marketTitle?: string;
  entryPrice?: number;
  shares?: number;
  costUsd?: number;
  pnl?: number;
  bankrollAfter: number;
  cumulativePnl: number;
  openPositions: number;
  note?: string;
}

// ═══════════════════════════════════════════════════════════════
// Simulation Engine
// ═══════════════════════════════════════════════════════════════

async function runSimulation(rounds: number): Promise<SimRound[]> {
  let bankroll = CONFIG.bankrollStart;
  let cumulativePnl = 0;
  const results: SimRound[] = [];
  const positions: LotteryPosition[] = [];
  let buyCount = 0;

  console.log(`\n╔══════════════════════════════════════════════╗`);
  console.log(`║   PM BOT — Lottery Ticket Compound Demo     ║`);
  console.log(`║   ${rounds} rounds | $${CONFIG.bankrollStart} bankroll | Micro-Kelly           ║`);
  console.log(`╚══════════════════════════════════════════════╝\n`);

  console.log("[sim] Discovering BTC 5-min markets...");

  for (let round = 1; round <= rounds; round++) {
    const bankrollBefore = bankroll;

    // Halt check
    if (bankroll < CONFIG.stopFloorUsd) {
      results.push({
        round, bankrollBefore, action: "HALT",
        bankrollAfter: bankroll, cumulativePnl, openPositions: positions.length,
        note: `Stop floor $${CONFIG.stopFloorUsd} hit`,
      });
      console.log(`[sim] Round ${round}: HALTED — $${bankroll.toFixed(2)} < $${CONFIG.stopFloorUsd}`);
      break;
    }

    // Step 1: Resolve any positions that would have ended
    // Lottery tickets resolve at the end of their 5-min window
    // Simulate: each round has a small chance of resolution
    const resolvedNow: LotteryPosition[] = [];
    const remaining: LotteryPosition[] = [];

    for (const pos of positions) {
      // ~20% chance per round that a 5-min window has closed (with many rounds/day)
      const resolveChance = 0.15;
      if (Math.random() < resolveChance || positions.length > CONFIG.maxOpenPositions * 3) {
        const resolved = simulateResolution(pos);
        resolvedNow.push(resolved);
        
        bankroll += resolved.payout;
        cumulativePnl += resolved.pnl;

        const icon = resolved.won ? "🟢" : "🔴";
        const pnlStr = resolved.won
          ? `+$${resolved.pnl.toFixed(2)} (${((resolved.pnl / resolved.costUsd) * 100).toFixed(0)}%)`
          : `-$${Math.abs(resolved.pnl).toFixed(2)}`;

        results.push({
          round,
          bankrollBefore: bankroll - resolved.payout + resolved.costUsd,
          action: resolved.won ? "RESOLVE_WIN" : "RESOLVE_LOSS",
          marketTitle: resolved.marketTitle,
          entryPrice: resolved.entryPrice,
          shares: resolved.shares,
          costUsd: resolved.costUsd,
          pnl: resolved.pnl,
          bankrollAfter: bankroll,
          cumulativePnl,
          openPositions: remaining.length,
          note: `${icon} ${pnlStr} | Entry: ${(resolved.entryPrice * 100).toFixed(0)}¢ | Roll: $${bankroll.toFixed(2)}`,
        });

        if (resolved.won) {
          console.log(
            `[sim] Round ${round}: 🟢 WIN  ${resolved.marketTitle.slice(0, 40)} | ` +
            `${(resolved.entryPrice * 100).toFixed(0)}¢ | ${resolved.shares.toFixed(1)} shares | ` +
            `+$${resolved.pnl.toFixed(2)} (${((resolved.pnl / resolved.costUsd) * 100).toFixed(0)}%) | ` +
            `Roll: $${bankroll.toFixed(2)}`
          );
        }
      } else {
        remaining.push(pos);
      }
    }

    // Update positions array
    positions.length = 0;
    positions.push(...remaining);

    // Step 2: Enter new lottery positions if capacity available
    if (positions.length < CONFIG.maxOpenPositions && bankroll > CONFIG.stopFloorUsd * 2) {
      // Every ~5 rounds, scan for new signals (don't hammer the API)
      if (round % 5 === 1 || positions.length === 0) {
        try {
          // Estimate UP probability from BTC data
          // In simulation, use a stable estimate based on historical BTC drift
          const upProb = 0.515; // BTC UP ~51.5% of 5-min windows

          const signals = await generateLotterySignals(upProb, CONFIG.lottery);
          
          // Take best signal that we're not already in
          for (const signal of signals) {
            if (positions.length >= CONFIG.maxOpenPositions) break;
            
            // Don't enter the same market twice
            if (positions.some(p => p.tokenId === signal.tokenId)) continue;
            
            // Check bankroll can handle it
            if (signal.costUsd > bankroll * 0.1) continue; // Max 10% of bankroll per position
            
            bankroll -= signal.costUsd;
            positions.push({
              tokenId: signal.tokenId,
              marketTitle: signal.marketTitle,
              entryPrice: signal.marketPrice,
              shares: signal.shares,
              costUsd: signal.costUsd,
              entryTs: Date.now(),
              resolved: false,
              won: null,
              payout: 0,
              pnl: 0,
            });

            buyCount++;
            results.push({
              round,
              bankrollBefore: bankroll + signal.costUsd,
              action: "BUY",
              marketTitle: signal.marketTitle,
              entryPrice: signal.marketPrice,
              shares: signal.shares,
              costUsd: signal.costUsd,
              bankrollAfter: bankroll,
              cumulativePnl,
              openPositions: positions.length,
              note: `Edge: ${signal.edge.toFixed(1)}% | Entry: ${(signal.marketPrice * 100).toFixed(0)}¢ | #${buyCount}`,
            });

            console.log(
              `[sim] Round ${round}: 🎫 BUY  ${signal.marketTitle.slice(0, 40)} | ` +
              `${(signal.marketPrice * 100).toFixed(0)}¢ | ${signal.shares.toFixed(1)} shares | ` +
              `$${signal.costUsd.toFixed(2)} | Edge ${signal.edge.toFixed(1)}% | ` +
              `Positions: ${positions.length} | Roll: $${bankroll.toFixed(2)}`
            );
          }
        } catch (err: any) {
          if (round % 25 === 1) {
            console.log(`[sim] Round ${round}: API scan skipped (${err.message?.slice(0, 60)})`);
          }
        }
      }

      // If no signals found this round, record HOLD
      if (!results[results.length - 1] || results[results.length - 1].round !== round) {
        results.push({
          round, bankrollBefore, action: "HOLD",
          bankrollAfter: bankroll, cumulativePnl, openPositions: positions.length,
          note: `Positions: ${positions.length} | Roll: $${bankroll.toFixed(2)}`,
        });
      }
    } else if (positions.length === 0) {
      // No positions, nothing to do
      if (!results[results.length - 1] || results[results.length - 1].round !== round) {
        results.push({
          round, bankrollBefore, action: "HOLD",
          bankrollAfter: bankroll, cumulativePnl, openPositions: 0,
          note: `Waiting for signals`,
        });
      }
    }
  }

  return results;
}

// ═══════════════════════════════════════════════════════════════
// Analysis & Display
// ═══════════════════════════════════════════════════════════════

function displayResults(results: SimRound[], elapsedSec: number) {
  const buys = results.filter((r) => r.action === "BUY");
  const wins = results.filter((r) => r.action === "RESOLVE_WIN");
  const losses = results.filter((r) => r.action === "RESOLVE_LOSS");
  const resolved = [...wins, ...losses];
  const end = results[results.length - 1]!;

  // Compute statistics
  const totalWon = wins.reduce((s, r) => s + (r.pnl ?? 0), 0);
  const totalLost = losses.reduce((s, r) => s + Math.abs(r.pnl ?? 0), 0);
  const winRate = resolved.length > 0 ? wins.length / resolved.length : 0;
  const avgWin = wins.length > 0 ? totalWon / wins.length : 0;
  const avgLoss = losses.length > 0 ? totalLost / losses.length : 0;

  // Check for big wins (>100% ROI)
  const bigWins = wins.filter((r) => r.costUsd && r.pnl && r.pnl / r.costUsd > 1.0);
  const bestWin = wins.length > 0
    ? wins.reduce((best, r) => {
        const roi = r.costUsd && r.pnl ? r.pnl / r.costUsd : 0;
        return roi > best.roi ? { roi, pnl: r.pnl ?? 0, round: r.round, entryPrice: r.entryPrice ?? 0 } : best;
      }, { roi: 0, pnl: 0, round: 0, entryPrice: 0 })
    : null;

  console.log(`\n${"═".repeat(60)}`);
  console.log("  LOTTERY TICKET COMPOUND — RESULTS");
  console.log(`${"═".repeat(60)}`);

  console.log(`\n  Simulation: ${results.length} rounds in ${elapsedSec.toFixed(0)}s`);
  console.log(`  Trades:     ${buys.length} entries, ${resolved.length} exits`);
  console.log(`  Wins:       ${wins.length} | Losses: ${losses.length} | Pending: ${buys.length - resolved.length}`);
  console.log(`  Win rate:   ${(winRate * 100).toFixed(1)}%`);
  console.log(`  Avg win:    $${avgWin.toFixed(2)} | Avg loss: $${avgLoss.toFixed(2)}`);
  console.log(`  Bankroll:   $${CONFIG.bankrollStart.toFixed(2)} → $${end.bankrollAfter.toFixed(2)}`);
  console.log(`  Total PnL:  $${end.cumulativePnl.toFixed(2)} (${((end.cumulativePnl / CONFIG.bankrollStart) * 100).toFixed(1)}%)`);

  if (bestWin && bestWin.roi > 0) {
    console.log(`  Best win:   +$${bestWin.pnl.toFixed(2)} (${(bestWin.roi * 100).toFixed(0)}% ROI, entry ${(bestWin.entryPrice * 100).toFixed(0)}¢, round ${bestWin.round})`);
  }
  console.log(`  Big wins:   ${bigWins.length} (>100% ROI)`);

  // Lottery economics
  if (resolved.length > 0) {
    const totalBets = resolved.reduce((s, r) => s + (r.costUsd ?? 0), 0);
    const netReturn = end.cumulativePnl;
    const roi = totalBets > 0 ? (netReturn / totalBets) * 100 : 0;
    console.log(`  Total bet:  $${totalBets.toFixed(2)} | Net: $${netReturn.toFixed(2)} | ROI: ${roi.toFixed(1)}%`);
  }

  // Projections
  console.log(`\n${"─".repeat(60)}`);
  console.log("  COMPOUND PROJECTIONS");
  console.log(`${"─".repeat(60)}`);

  const resolvedCount = resolved.length;
  const avgROIPerTrade = resolvedCount > 0 ? end.cumulativePnl / resolvedCount : 0;
  const tradesPerRound = resolvedCount / Math.max(1, results.length);

  if (avgROIPerTrade > 0) {
    for (const [label, trades] of [["100 trades", 100], ["500 trades", 500], ["1,000 trades", 1000]] as const) {
      const projPnl = avgROIPerTrade * trades;
      const projRoll = CONFIG.bankrollStart + projPnl;
      console.log(`  ${label.padEnd(12)}: $${projRoll.toFixed(2)}`);
    }
  } else {
    console.log("  ⚠️  Negative expectancy — projections skipped");
  }

  // Recent activity
  console.log(`\n${"─".repeat(60)}`);
  console.log("  RECENT ACTIVITY (last 15 events)");
  console.log(`${"─".repeat(60)}`);

  const recent = results.filter((r) => r.action !== "HOLD").slice(-15);
  for (const r of recent) {
    const icon = r.action === "BUY" ? "🎫"
      : r.action === "RESOLVE_WIN" ? "🟢"
      : r.action === "RESOLVE_LOSS" ? "🔴"
      : "⬛";
    const detail = r.marketTitle
      ? ` ${r.marketTitle.slice(0, 30)} | ${r.costUsd ? `$${r.costUsd.toFixed(2)}` : ''}`
      : "";
    console.log(`  R${String(r.round).padStart(3)} ${icon} ${r.action.padEnd(12)} | $${r.bankrollAfter.toFixed(2)}${detail} ${r.note ? "| " + r.note : ""}`);
  }

  console.log(`\n${"═".repeat(60)}`);
  console.log("  EDGE: Structural long-shot bias in BTC 5-min binaries");
  console.log(`  Based on @marketing101 +$382K verified strategy`);
  console.log(`${"═".repeat(60)}\n`);
}

// ═══════════════════════════════════════════════════════════════
// Main
// ═══════════════════════════════════════════════════════════════

async function main() {
  const args = process.argv.slice(2);
  const roundsIdx = args.indexOf("--rounds");
  const rounds = roundsIdx >= 0 && roundsIdx + 1 < args.length
    ? parseInt(args[roundsIdx + 1]!, 10) || 500
    : 500;

  const start = Date.now();
  const results = await runSimulation(rounds);
  const elapsed = (Date.now() - start) / 1000;

  displayResults(results, elapsed);
}

main().catch((err) => {
  console.error("[lotterySim] Fatal:", err);
  process.exit(1);
});
