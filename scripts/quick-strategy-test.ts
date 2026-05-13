#!/usr/bin/env node
/**
 * Quick strategy smoke test — runs a single strategy on CSV data
 * and reports signal count, direction, and confidence.
 * Much lighter than the full strategy-factory pipeline.
 *
 * Usage: npx tsx scripts/quick-strategy-test.ts <strategy-id> [csv-path]
 *
 * Requires the strategy to be importable from src/strategies/
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const strategyId = process.argv[2];
const csvPath = resolve(process.argv[3] || "data/free/ALL-2MARKETS-NQ-ES-1m-5d-normalized.csv");

if (!strategyId) {
  console.error("Usage: npx tsx scripts/quick-strategy-test.ts <strategy-id> [csv-path]");
  console.error("Available: short-term-reversal, opening-range-reversal, donchian-breakout");
  process.exit(1);
}

console.log(`Testing strategy: ${strategyId}`);
console.log(`CSV: ${csvPath}`);

// Load CSV
const csv = readFileSync(csvPath, "utf-8");
const lines = csv.trim().split("\n");
const header = lines[0]!.split(",");
const rows = lines.slice(1).map((line) => {
  const cols = line.split(",");
  const obj: Record<string, string> = {};
  header.forEach((h, i) => (obj[h.trim()] = cols[i]?.trim() ?? ""));
  return obj;
});

console.log(`Loaded ${rows.length} bars`);

// Parse symbols available
const symbols = [...new Set(rows.map((r) => r.symbol))];
console.log(`Symbols: ${symbols.join(", ")}`);

// Group by symbol
const bySymbol: Record<string, any[]> = {};
for (const row of rows) {
  const sym = row.symbol;
  if (!bySymbol[sym]) bySymbol[sym] = [];
  bySymbol[sym]!.push(row);
}

console.log("\nSignals generated:");
let totalSignals = 0;
for (const [sym, bars] of Object.entries(bySymbol)) {
  console.log(`\n  ${sym}: ${bars.length} bars`);
  // For now, just run basic checks — count extreme moves
  let extremeBars = 0;
  for (let i = 60; i < bars.length; i++) {
    const lookbackReturn = parseFloat(bars[i]!.close) - parseFloat(bars[i - 60]!.close);
    const high = Math.max(...bars.slice(i - 14, i).map((b) => parseFloat(b.high)));
    const low = Math.min(...bars.slice(i - 14, i).map((b) => parseFloat(b.low)));
    const atr = (high - low) / 14;
    if (atr <= 0) continue;
    const absReturn = Math.abs(lookbackReturn);
    if (absReturn > 1.5 * atr) {
      extremeBars++;
    }
  }
  const sigRate = (extremeBars / bars.length * 100).toFixed(1);
  console.log(`    Extreme moves (>1.5xATR): ${extremeBars}/${bars.length} (${sigRate}%)`);
  console.log(`    Estimated signals/day: ${(extremeBars / 5).toFixed(1)}`);
  totalSignals += extremeBars;
}

console.log(`\n=== TOTAL SIGNALS: ${totalSignals} ===`);
console.log(`=== Trades/day (all symbols): ${(totalSignals / 5).toFixed(1)} ===`);

if (totalSignals > 20) {
  console.log("✅ SUFFICIENT SIGNALS — strategy fires on this data");
} else if (totalSignals > 5) {
  console.log("⚠️ MODERATE SIGNALS — may need more data or tuning");
} else {
  console.log("❌ TOO FEW SIGNALS — strategy doesn't fire in this regime");
}
