// Dry run: test strategyFusion directly from src
import "./strategyFusion.js";

console.log("=== Fusion Engine Imported Successfully ===");

// Test classifyRegime directly
import { classifyRegime, fuseStrategies } from "./strategyFusion.js";
import type { Bar } from "../domain.js";

const basePrice = 29200;
const bars: Bar[] = [];
const now = Date.now();

for (let i = 0; i < 20; i++) {
  const open = basePrice + i * 15 + (Math.random() - 0.5) * 30;
  const close = open + 20 + (Math.random() - 0.5) * 40;
  bars.push({
    ts: new Date(now - (20 - i) * 15 * 60 * 1000).toISOString(),
    symbol: "MNQ",
    open,
    high: Math.max(open, close) + Math.random() * 20,
    low: Math.min(open, close) - Math.random() * 20,
    close,
    volume: Math.floor(1000 + Math.random() * 5000),
  } as any);
}

const regime = classifyRegime(bars);
console.log("\n=== REGIME ===");
console.log(JSON.stringify(regime, null, 2));

const ctx = {
  symbol: "MNQ",
  bar: bars[bars.length - 1],
  history: bars,
  sessionHistory: bars.slice(-10),
  config: { mode: "live" } as any,
  dailyTradeCount: 0,
  macro: {},
} as any;

const fusion = fuseStrategies(ctx, regime);
console.log("\n=== FUSION ===");
console.log("Selected:", fusion.selectedStrategy);
console.log("Safety:", fusion.safetyLock);
fusion.reasons.forEach((r: string) => console.log("  " + r));
