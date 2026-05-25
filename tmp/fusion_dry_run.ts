// Dry run: test fusion engine + classifyRegime with mock bars
import { classifyRegime, fuseStrategies } from "../engine/strategyFusion";
import type { Bar } from "../domain";

// Create realistic NQ mock bars (from recent data: ~29,200 area)
const basePrice = 29200;
const bars: Bar[] = [];
const now = Date.now();

// 20 bars of 15m data: slight uptrend
for (let i = 0; i < 20; i++) {
  const open = basePrice + i * 15 + (Math.random() - 0.5) * 30;
  const close = open + 20 + (Math.random() - 0.5) * 40;
  const high = Math.max(open, close) + Math.random() * 20;
  const low = Math.min(open, close) - Math.random() * 20;
  bars.push({
    ts: new Date(now - (20 - i) * 15 * 60 * 1000).toISOString(),
    symbol: "MNQ",
    open: Math.round(open * 100) / 100,
    high: Math.round(high * 100) / 100,
    low: Math.round(low * 100) / 100,
    close: Math.round(close * 100) / 100,
    volume: Math.floor(1000 + Math.random() * 5000),
  });
}

// Test regime classification
const regime = classifyRegime(bars);
console.log("=== REGIME ANALYSIS ===");
console.log(JSON.stringify(regime, null, 2));

// Test fusion
const context = {
  symbol: "MNQ",
  bar: bars[bars.length - 1],
  history: bars,
  sessionHistory: bars.slice(-10),
  config: { mode: "live" } as any,
  dailyTradeCount: 0,
  macro: {},
} as any;

const fusion = fuseStrategies(context, regime);
console.log("\n=== FUSION DECISION ===");
console.log("Selected:", fusion.selectedStrategy);
console.log("Safety lock:", fusion.safetyLock);
console.log("\nReasons:");
fusion.reasons.forEach((r: string) => console.log("  " + r));
console.log("\nRejected:");
fusion.rejectedStrategies.forEach((r: string) => console.log("  " + r));

if (fusion.signal) {
  console.log("\nSignal:", fusion.signal.side, fusion.signal.symbol, "@", fusion.signal.entry);
}
