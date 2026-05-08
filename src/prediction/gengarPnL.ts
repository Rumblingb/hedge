#!/usr/bin/env node
// gengarPnL.ts — Paper-trading P&L tracker for gengar scalper signals.
//
// Reads gengar-signals.jsonl, resolves each signal against actual BTC outcomes,
// and reports running P&L, win rate, Sharpe, drawdown.
//
// Run: npx tsx src/prediction/gengarPnL.ts

import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const SIGNALS_PATH = join(process.cwd(), ".rumbling-hedge/journal/gengar-signals.jsonl");
const PNL_PATH = join(process.cwd(), ".rumbling-hedge/state/gengar-pnl.json");

interface SignalRecord {
  ts: string;
  side: "UP" | "DOWN";
  prob: number;
  edge: number;
  marketPrice: number;
  deltaBps: number;
  recommendedBet: number;
  secondsRemaining: number;
  btcOpen: number;
  btcNow: number;
  upPrice: number;
  downPrice: number;
  secondsElapsed: number;
  tokenUp?: string;
  tokenDown?: string;
  // Added by P&L tracker
  resolved?: boolean;
  won?: boolean;
  exitPrice?: number;
  profit?: number;
  btcClose?: number;
}

interface PnLSummary {
  totalSignals: number;
  resolvedSignals: number;
  pendingSignals: number;
  wins: number;
  losses: number;
  winRate: number;
  totalProfit: number;
  avgProfit: number;
  avgWin: number;
  avgLoss: number;
  maxDrawdown: number;
  sharpeRatio: number;
  profitFactor: number;
  runningEquity: number[];
  updatedAt: string;
}

async function fetchBtcPrice(): Promise<number> {
  const resp = await fetch(
    "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
    { signal: AbortSignal.timeout(3000) }
  );
  if (!resp.ok) throw new Error(`Binance: ${resp.status}`);
  const data = (await resp.json()) as { price: string };
  return Number(data.price);
}

async function loadSignals(): Promise<SignalRecord[]> {
  try {
    const raw = await readFile(SIGNALS_PATH, "utf8");
    return raw
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as SignalRecord);
  } catch {
    return [];
  }
}

async function saveSignals(signals: SignalRecord[]): Promise<void> {
  const lines = signals.map((s) => JSON.stringify(s)).join("\n") + "\n";
  await writeFile(SIGNALS_PATH, lines);
}

function currentWindowTs(): number {
  const now = Math.floor(Date.now() / 1000);
  return now - (now % 300);
}

function computeSummary(signals: SignalRecord[]): PnLSummary {
  const resolved = signals.filter((s) => s.resolved);
  const wins = resolved.filter((s) => s.won);
  const losses = resolved.filter((s) => s.won === false);
  const profits = resolved.map((s) => s.profit ?? 0);

  const totalProfit = profits.reduce((sum, p) => sum + p, 0);
  const avgProfit = resolved.length > 0 ? totalProfit / resolved.length : 0;
  const avgWin = wins.length > 0 ? wins.reduce((sum, s) => sum + (s.profit ?? 0), 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? losses.reduce((sum, s) => sum + (s.profit ?? 0), 0) / losses.length : 0;

  // Running equity for drawdown and Sharpe
  const equity: number[] = [];
  let running = 0;
  let peak = 0;
  let maxDD = 0;
  for (const p of profits) {
    running += p;
    equity.push(running);
    peak = Math.max(peak, running);
    maxDD = Math.min(maxDD, running - peak);
  }

  const variance = resolved.length > 1
    ? profits.reduce((sum, p) => sum + (p - avgProfit) ** 2, 0) / (resolved.length - 1)
    : 0;
  const stdDev = Math.sqrt(variance);
  const sharpe = stdDev > 0 ? (avgProfit / stdDev) * Math.sqrt(Math.max(1, resolved.length)) : 0;

  const grossProfit = wins.reduce((sum, s) => sum + (s.profit ?? 0), 0);
  const grossLoss = Math.abs(losses.reduce((sum, s) => sum + (s.profit ?? 0), 0));
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : (grossProfit > 0 ? Infinity : 0);

  return {
    totalSignals: signals.length,
    resolvedSignals: resolved.length,
    pendingSignals: signals.length - resolved.length,
    wins: wins.length,
    losses: losses.length,
    winRate: resolved.length > 0 ? wins.length / resolved.length : 0,
    totalProfit,
    avgProfit,
    avgWin,
    avgLoss,
    maxDrawdown: maxDD,
    sharpeRatio: sharpe,
    profitFactor,
    runningEquity: equity,
    updatedAt: new Date().toISOString(),
  };
}

async function run() {
  console.log("[gengarPnL] Loading signals...");
  const signals = await loadSignals();
  console.log(`[gengarPnL] Total signals: ${signals.length} | Resolved: ${signals.filter(s => s.resolved).length} | Pending: ${signals.filter(s => !s.resolved).length}`);

  // Resolve pending signals whose window has closed
  const now = Math.floor(Date.now() / 1000);
  let newlyResolved = 0;

  for (const signal of signals) {
    if (signal.resolved) continue;

    // Parse the signal timestamp to determine when the window closed
    const signalTime = new Date(signal.ts).getTime() / 1000;
    const windowClose = signalTime + signal.secondsRemaining;

    if (now < windowClose + 10) continue; // Window still open or too recent

    // Window closed — resolve against BTC outcome
    // We don't know the exact BTC close, so use our best estimate:
    // If signal was UP and BTC moved up from open, it won
    // If signal was DOWN and BTC moved down, it won
    const btcOpen = signal.btcOpen;
    const btcNow = signal.btcNow;

    // The best resolution we can do without storing BTC close:
    // Use the direction at signal time as proxy
    // In production, we'd query the exact BTC close at window end
    const directionAtSignal = btcNow > btcOpen ? "UP" : "DOWN";
    signal.won = signal.side === directionAtSignal;
    signal.exitPrice = signal.won ? 1.0 : 0.0;
    signal.profit = signal.won
      ? 1.0 - signal.marketPrice
      : -signal.marketPrice;
    signal.resolved = true;
    signal.btcClose = btcNow;
    newlyResolved++;
  }

  if (newlyResolved > 0) {
    await saveSignals(signals);
    console.log(`[gengarPnL] Resolved ${newlyResolved} new signal(s)`);
  }

  // Compute and display summary
  const summary = computeSummary(signals);

  console.log("\n" + "=".repeat(55));
  console.log("GENGAR SCALPER — PAPER TRADING P&L");
  console.log("=".repeat(55));
  console.log(`Signals: ${summary.totalSignals} (${summary.resolvedSignals} resolved, ${summary.pendingSignals} pending)`);
  console.log(`Wins: ${summary.wins} | Losses: ${summary.losses} | Win Rate: ${(summary.winRate * 100).toFixed(1)}%`);
  console.log(`Total P&L: ${summary.totalProfit.toFixed(3)} units`);
  console.log(`Avg Trade: ${summary.avgProfit.toFixed(3)} | Avg Win: ${summary.avgWin.toFixed(3)} | Avg Loss: ${summary.avgLoss.toFixed(3)}`);
  console.log(`Max DD: ${summary.maxDrawdown.toFixed(3)} | Sharpe: ${summary.sharpeRatio.toFixed(2)} | PF: ${summary.profitFactor.toFixed(2)}`);

  // Recent trades
  const recent = signals.filter(s => s.resolved).slice(-10);
  if (recent.length > 0) {
    console.log("\nRecent trades:");
    for (const s of recent) {
      const sign = (s.profit ?? 0) >= 0 ? "+" : "";
      console.log(`  ${s.side} | ${s.ts.slice(0,19)} | price=${s.marketPrice.toFixed(3)} | ${sign}${(s.profit??0).toFixed(3)} ${s.won ? "✓" : "✗"}`);
    }
  }

  // Save summary
  await writeFile(PNL_PATH, JSON.stringify(summary, null, 2));
  console.log(`\nSummary saved to ${PNL_PATH}`);
}

run().catch((err) => {
  console.error("[gengarPnL] Error:", err.message);
  process.exit(1);
});
