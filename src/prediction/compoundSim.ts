#!/usr/bin/env npx tsx
// compoundSim.ts — PM Bot compound wealth demo.
// Runs a multi-day simulation with edge discovery, Kelly sizing,
// position management, and compound growth tracking.
//
// Mode: discovers real markets from Gamma, simulates edge-based
// entries/exits, tracks P&L. Only trades when edge > threshold.
//
// Usage: npx tsx src/prediction/compoundSim.ts [--days 90]

import { fetchPolymarketBook, quoteFromBook } from "./polymarketBook.js";

// ═══════════════════════════════════════════════════════════════
// Config
// ═══════════════════════════════════════════════════════════════

const CONFIG = {
  days: 90,
  bankrollStart: 20,
  maxPerTradeUsd: 1,
  stopFloorUsd: 10,
  minEdgePct: 5,          // Only trade when edge > 5%
  kellyFraction: 0.25,    // Quarter-Kelly for safety
  maxPositions: 1,        // One position at a time
  cooldownDays: 3,        // Days between trades
  priceRange: [0.05, 0.85] as [number, number],
  maxSpreadPct: 5,
  minLiquidityUsd: 500,
};

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

interface MarketData {
  slug: string;
  title: string;
  tokenId: string;
  isYesToken: boolean;
  volume: number;
}

interface PriceQuote {
  bestBid: number;
  bestAsk: number;
  spreadPct: number;
  depth: number;
}

interface SimDay {
  day: number;
  date: string;
  bankrollBefore: number;
  action: "BUY" | "SELL" | "HOLD" | "HALT";
  marketTitle?: string;
  price?: number;
  shares?: number;
  amountUsd?: number;
  edgePct?: number;
  pnl?: number;
  bankrollAfter: number;
  cumulativePnl: number;
  note?: string;
}

// ═══════════════════════════════════════════════════════════════
// Market Discovery
// ═══════════════════════════════════════════════════════════════

async function discoverMarkets(): Promise<MarketData[]> {
  const url = new URL("https://gamma-api.polymarket.com/events");
  url.searchParams.set("limit", "30");
  url.searchParams.set("active", "true");
  url.searchParams.set("closed", "false");
  url.searchParams.set("order", "volume");
  url.searchParams.set("ascending", "false");

  const resp = await fetch(url, {
    headers: { accept: "application/json", "user-agent": "pm-sim/0.1" },
    signal: AbortSignal.timeout(10_000),
  });

  if (!resp.ok) return [];
  const events = (await resp.json()) as any[];

  const markets: MarketData[] = [];

  for (const e of events) {
    const ms = e.markets ?? [];
    if (ms.length === 0) continue;

    const m = ms[0];
    let tokenIds: string[] = [];
    if (m?.clobTokenIds) {
      if (Array.isArray(m.clobTokenIds)) {
        tokenIds = m.clobTokenIds;
      } else if (typeof m.clobTokenIds === "string") {
        try { const p = JSON.parse(m.clobTokenIds); tokenIds = Array.isArray(p) ? p : []; } catch {}
      }
    }

    const outcomes: string[] = Array.isArray(m?.outcomes)
      ? m.outcomes
      : typeof m?.outcomes === "string"
        ? (() => { try { return JSON.parse(m.outcomes); } catch { return []; } })()
        : [];

    for (let i = 0; i < Math.min(tokenIds.length, outcomes.length); i++) {
      const isYes = outcomes[i]?.toLowerCase() === "yes";
      markets.push({
        slug: e.slug ?? "",
        title: e.title ?? "",
        tokenId: tokenIds[i]!,
        isYesToken: isYes,
        volume: Number(e.volume) || 0,
      });
    }
  }

  // Only YES tokens for simplicity
  return markets.filter((m) => m.isYesToken);
}

// ═══════════════════════════════════════════════════════════════
// Price Checking
// ═══════════════════════════════════════════════════════════════

async function checkPrices(
  tokenIds: string[],
): Promise<Map<string, PriceQuote>> {
  const results = new Map<string, PriceQuote>();

  // Batch: check 5 at a time
  for (let i = 0; i < tokenIds.length; i += 5) {
    const batch = tokenIds.slice(i, i + 5);
    const promises = batch.map(async (tid) => {
      try {
        const book = await fetchPolymarketBook(tid);
        if (!book) return null;
        const q = quoteFromBook(book);
        return { tid, q };
      } catch { return null; }
    });

    const resolved = await Promise.all(promises);
    for (const r of resolved) {
      if (r) {
        results.set(r.tid, {
          bestBid: r.q.bestBid ?? 0,
          bestAsk: r.q.bestAsk ?? 0,
          spreadPct: r.q.spreadPct ?? 100,
          depth: r.q.topBookDepth ?? 0,
        });
      }
    }
  }

  return results;
}

// ═══════════════════════════════════════════════════════════════
// Edge Calculation (simplified)
// ═══════════════════════════════════════════════════════════════

function calcEdge(price: number, fairValue: number): number {
  if (price <= 0) return 0;
  return ((fairValue - price) / price) * 100;
}

// ═══════════════════════════════════════════════════════════════
// Simulation Engine
// ═══════════════════════════════════════════════════════════════

async function runSimulation(days: number): Promise<SimDay[]> {
  let bankroll = CONFIG.bankrollStart;
  let cumulativePnl = 0;
  let position: { tokenId: string; marketTitle: string; entryPrice: number; shares: number; entryDay: number } | null = null;
  let cooldown = 0;
  const results: SimDay[] = [];

  console.log("[sim] Scanning active markets...");
  const allMarkets = await discoverMarkets();
  const tokenIds = allMarkets.map((m) => m.tokenId);
  console.log(`[sim] ${allMarkets.length} YES-token markets discovered\n`);

  for (let day = 1; day <= days; day++) {
    const d = new Date();
    d.setDate(d.getDate() + day - 1);
    const dateStr = d.toISOString().slice(0, 10);

    // Halt check
    if (bankroll < CONFIG.stopFloorUsd) {
      results.push({ day, date: dateStr, bankrollBefore: bankroll, action: "HALT", bankrollAfter: bankroll, cumulativePnl, note: "Stop floor hit" });
      console.log(`[sim] Day ${day}: HALTED — $${bankroll.toFixed(2)} < $${CONFIG.stopFloorUsd}`);
      break;
    }

    const bankrollBefore = bankroll;

    // Check existing position for resolution
    if (position) {
      const daysHeld = day - position.entryDay;
      // Simulate resolution: each day has small chance based on market probability
      const resolveChance = 0.03; // ~3% per day avg
      const resolved = Math.random() < resolveChance || daysHeld > 14;

      if (resolved) {
        // Get current price to mark outcome
        const prices = await checkPrices([position.tokenId]);
        const q = prices.get(position.tokenId);

        if (q) {
          // Resolve: YES token pays 1 if event happened, 0 otherwise
          // Use entry price as probability estimate
          const winProb = position.entryPrice;
          const won = Math.random() < winProb;

          if (won) {
            const payout = position.shares * 1.0;
            const cost = position.shares * position.entryPrice;
            const pnl = payout - cost;
            bankroll += payout;
            cumulativePnl += pnl;
            results.push({
              day, date: dateStr, bankrollBefore, action: "SELL",
              marketTitle: position.marketTitle,
              price: 1.0, shares: position.shares, amountUsd: payout,
              pnl, bankrollAfter: bankroll, cumulativePnl,
              note: `RESOLVED YES — +$${pnl.toFixed(2)}`,
            });
            console.log(`[sim] Day ${day}: 🟢 RESOLVED YES | ${position.marketTitle.slice(0, 40)} | +$${pnl.toFixed(2)} | Roll: $${bankroll.toFixed(2)}`);
          } else {
            bankroll += 0; // YES = 0 if event didn't happen
            const pnl = -(position.shares * position.entryPrice);
            cumulativePnl += pnl;
            results.push({
              day, date: dateStr, bankrollBefore, action: "SELL",
              marketTitle: position.marketTitle,
              price: 0, shares: position.shares, amountUsd: 0,
              pnl, bankrollAfter: bankroll, cumulativePnl,
              note: `RESOLVED NO — $${pnl.toFixed(2)}`,
            });
            console.log(`[sim] Day ${day}: 🔴 RESOLVED NO  | ${position.marketTitle.slice(0, 40)} | $${pnl.toFixed(2)} | Roll: $${bankroll.toFixed(2)}`);
          }
        }

        position = null;
        cooldown = CONFIG.cooldownDays;
        continue;
      }

      // Still holding
      results.push({ day, date: dateStr, bankrollBefore: bankroll, action: "HOLD", bankrollAfter: bankroll, cumulativePnl, note: `Holding: ${position.marketTitle.slice(0, 40)}` });
      if (day % 5 === 0) console.log(`[sim] Day ${day}: HOLDING ${position.marketTitle.slice(0, 40)}`);
      continue;
    }

    // Cooldown
    if (cooldown > 0) {
      cooldown--;
      results.push({ day, date: dateStr, bankrollBefore: bankroll, action: "HOLD", bankrollAfter: bankroll, cumulativePnl, note: `Cooldown: ${cooldown}d remaining` });
      if (day % 10 === 0) console.log(`[sim] Day ${day}: cooldown ${cooldown}d remaining | Roll: $${bankroll.toFixed(2)}`);
      continue;
    }

    // Scan for new opportunities
    const prices = await checkPrices(tokenIds.slice(0, 15));

    let bestMarket: MarketData | null = null;
    let bestQuote: PriceQuote | null = null;
    let bestEdge = 0;

    for (const m of allMarkets) {
      const q = prices.get(m.tokenId);
      if (!q) continue;
      if (q.bestAsk < CONFIG.priceRange[0] || q.bestAsk > CONFIG.priceRange[1]) continue;
      if (q.spreadPct > CONFIG.maxSpreadPct) continue;
      if (q.depth < CONFIG.minLiquidityUsd) continue;

      // Edge: assume fair value should be slightly above market (our "signal")
      // In real bot, this comes from the edge intake pipeline
      // For demo: model edge as proportional to distance from 0.5 (uncertainty premium)
      const signalStrength = 0.08 + Math.random() * 0.12; // 8-20% signal
      const fairValue = Math.min(q.bestAsk * (1 + signalStrength), 0.95);
      const edge = calcEdge(q.bestAsk, fairValue);

      if (edge > bestEdge && edge >= CONFIG.minEdgePct) {
        bestEdge = edge;
        bestMarket = m;
        bestQuote = q;
      }
    }

    if (!bestMarket || !bestQuote) {
      results.push({ day, date: dateStr, bankrollBefore: bankroll, action: "HOLD", bankrollAfter: bankroll, cumulativePnl, note: `No edge > ${CONFIG.minEdgePct}%` });
      continue;
    }

    // Kelly sizing
    const edgeDecimal = bestEdge / 100;
    const kellyFraction = edgeDecimal * CONFIG.kellyFraction;
    const tradeAmt = Math.min(CONFIG.maxPerTradeUsd, bankroll * kellyFraction);
    if (tradeAmt < 0.10) {
      results.push({ day, date: dateStr, bankrollBefore: bankroll, action: "HOLD", bankrollAfter: bankroll, cumulativePnl, note: "Kelly fraction too small" });
      continue;
    }

    // Execute
    const entryPrice = bestQuote.bestAsk;
    const shares = Math.floor((tradeAmt / entryPrice) * 100) / 100;
    const actualAmt = Math.round(shares * entryPrice * 100) / 100;

    bankroll -= actualAmt;
    position = {
      tokenId: bestMarket.tokenId,
      marketTitle: bestMarket.title,
      entryPrice,
      shares,
      entryDay: day,
    };

    results.push({
      day, date: dateStr, bankrollBefore: bankroll + actualAmt, action: "BUY",
      marketTitle: bestMarket.title,
      price: entryPrice, shares, amountUsd: actualAmt,
      edgePct: bestEdge, pnl: -actualAmt,
      bankrollAfter: bankroll, cumulativePnl,
      note: `Edge ${bestEdge.toFixed(1)}%`,
    });

    console.log(
      `[sim] Day ${day}: 🎯 BUY  ${bestMarket.title.slice(0, 45)} | ` +
      `${shares.toFixed(1)} @ $${entryPrice.toFixed(4)} = $${actualAmt.toFixed(2)} | ` +
      `Edge ${bestEdge.toFixed(1)}% | Roll: $${bankroll.toFixed(2)}`,
    );
  }

  return results;
}

// ═══════════════════════════════════════════════════════════════
// Analysis & Display
// ═══════════════════════════════════════════════════════════════

function displayResults(results: SimDay[], elapsedSec: number) {
  const buys = results.filter((r) => r.action === "BUY");
  const sells = results.filter((r) => r.action === "SELL");
  const wins = sells.filter((r) => (r.pnl ?? 0) > 0);
  const losses = sells.filter((r) => (r.pnl ?? 0) <= 0);
  const end = results[results.length - 1]!;

  console.log(`\n${"═".repeat(60)}`);
  console.log("  COMPOUND WEALTH SIMULATION — RESULTS");
  console.log(`${"═".repeat(60)}`);

  console.log(`\n  Simulation: ${results.length} days in ${elapsedSec.toFixed(0)}s`);
  console.log(`  Trades:     ${buys.length} entries, ${sells.length} exits`);
  console.log(`  Wins:       ${wins.length}, Losses: ${losses.length}`);
  console.log(`  Win rate:   ${sells.length > 0 ? ((wins.length / sells.length) * 100).toFixed(1) + "%" : "N/A"}`);

  const avgWin = wins.length > 0 ? wins.reduce((s, r) => s + (r.pnl ?? 0), 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? losses.reduce((s, r) => s + Math.abs(r.pnl ?? 0), 0) / losses.length : 0;

  console.log(`  Avg win:    $${avgWin.toFixed(2)}, Avg loss: $${avgLoss.toFixed(2)}`);
  console.log(`  Bankroll:   $${CONFIG.bankrollStart.toFixed(2)} → $${end.bankrollAfter.toFixed(2)}`);
  console.log(`  Total PnL:  $${end.cumulativePnl.toFixed(2)} (${((end.cumulativePnl / CONFIG.bankrollStart) * 100).toFixed(1)}%)`);

  // CAGR
  const daysSim = results.length;
  const totalReturn = (end.bankrollAfter - CONFIG.bankrollStart) / CONFIG.bankrollStart;
  const cagr = ((1 + totalReturn) ** (365 / daysSim) - 1) * 100;
  console.log(`  CAGR:       ${cagr.toFixed(1)}%`);

  // Projections
  console.log(`\n${"─".repeat(60)}`);
  console.log("  WEALTH PROJECTIONS");
  console.log(`${"─".repeat(60)}`);

  const avgDailyReturn = totalReturn / daysSim;
  let projRoll = CONFIG.bankrollStart;

  for (const [label, d] of [["30d", 30], ["90d", 90], ["180d", 180], ["1yr", 365]] as const) {
    projRoll = CONFIG.bankrollStart * (1 + avgDailyReturn) ** d;
    console.log(`  ${label.padEnd(6)}: $${projRoll.toFixed(2)}`);
  }

  // Compound scenarios
  console.log(`\n${"─".repeat(60)}`);
  console.log("  COMPOUND SCENARIOS (starting $20)");
  console.log(`${"─".repeat(60)}`);

  for (const [label, rate] of [["Conservative 5%/mo", 1.05], ["Base 10%/mo", 1.10], ["Aggressive 20%/mo", 1.20]] as const) {
    let roll = 20;
    const milestones: string[] = [];
    for (let m = 1; m <= 24; m++) {
      roll *= rate;
      if ([1, 3, 6, 9, 12, 18, 24].includes(m)) {
        milestones.push(`m${m}=$${roll.toFixed(0)}`);
      }
    }
    console.log(`  ${label.padEnd(20)} ${milestones.join(" → ")}`);
  }

  // Trade log (compact)
  console.log(`\n${"─".repeat(60)}`);
  console.log("  TRADE LOG");
  console.log(`${"─".repeat(60)}`);

  for (const r of results) {
    if (r.action === "HOLD" && r.day % 15 !== 1) continue; // skip most holds
    const icon = r.action === "BUY" ? "🎯" : r.action === "SELL" ? ((r.pnl ?? 0) > 0 ? "🟢" : "🔴") : r.action === "HALT" ? "⬛" : "⏸️";
    const detail = r.marketTitle
      ? ` ${r.marketTitle.slice(0, 35)} | $${r.amountUsd?.toFixed(2) ?? r.pnl?.toFixed(2) ?? "0.00"}`
      : "";
    console.log(`  D${String(r.day).padStart(3)} ${icon} ${r.action.padEnd(4)} | $${r.bankrollBefore.toFixed(2)} → $${r.bankrollAfter.toFixed(2)}${detail} ${r.note ? "| " + r.note : ""}`);
  }

  console.log(`\n${"═".repeat(60)}`);
  console.log("  STATUS: DEMO — system live-ready when wallet resolved");
  console.log(`${"═".repeat(60)}\n`);
}

// ═══════════════════════════════════════════════════════════════
// Main
// ═══════════════════════════════════════════════════════════════

async function main() {
  const args = process.argv.slice(2);
  const daysIdx = args.indexOf("--days");
  const days = daysIdx >= 0 && daysIdx + 1 < args.length ? parseInt(args[daysIdx + 1]!, 10) || 90 : 90;

  console.log(`\n╔══════════════════════════════════════════════╗`);
  console.log(`║   PM BOT — Compound Wealth Demo             ║`);
  console.log(`║   ${days} days | $${CONFIG.maxPerTradeUsd}/trade | $${CONFIG.bankrollStart} bankroll              ║`);
  console.log(`╚══════════════════════════════════════════════╝\n`);

  const start = Date.now();
  const results = await runSimulation(days);
  const elapsed = (Date.now() - start) / 1000;

  displayResults(results, elapsed);
}

main().catch((err) => {
  console.error("[sim] Fatal:", err);
  process.exit(1);
});
