/**
 * probe-60m-signals.ts — Evaluate three 60m GOLD strategies against a normalized CSV.
 *
 * Usage (from /Users/brain/hedge):
 *   npx tsx scripts/probe-60m-signals.ts [csvPath]
 *
 * Default CSV: data/free/ALL-6MARKETS-60m-60d-normalized.csv
 *
 * Outputs research-only JSON to stdout:
 *   { researchOnly, readyForExecution, results, latestBars }
 *
 * To run from the skill directory directly:
 *   cp ~/.hermes/skills/bill-system/scripts/probe-60m-signals.ts /Users/brain/hedge/scripts/
 *   cd /Users/brain/hedge && npx tsx scripts/probe-60m-signals.ts
 */

import * as fs from "node:fs";
import type { Bar } from "../src/domain.js";
import { OrbBreakout60m } from "../src/strategies/orbBreakout60m.js";
import { WqTrendMom60m } from "../src/strategies/wqTrendMom60m.js";
import { WqVolRegime60m } from "../src/strategies/wqVolRegime60m.js";

const CSV_PATH = process.argv[2] || "data/free/ALL-6MARKETS-60m-60d-normalized.csv";
const TARGET_SYMBOLS = ["NQ", "ES"];

const SAFETY = {
  researchOnly: true,
  advisoryOnly: true,
  writesOrders: false,
  touchesBroker: false,
  tradableSignal: false,
  promotedForExecution: false,
  readyForExecution: false,
  executionRole: "diagnostic_only",
  executionBlockReason: "probe-output-research-only",
};

// Read and parse CSV
const raw = fs.readFileSync(CSV_PATH, "utf-8");
const lines = raw.trim().split("\n");
const header = lines[0].split(",");

interface CsvRow { [key: string]: string }
const rows: CsvRow[] = [];
for (let i = 1; i < lines.length; i++) {
  const cols = lines[i].split(",");
  if (cols.length < 7) continue;
  const obj: CsvRow = {};
  for (let j = 0; j < header.length; j++) {
    obj[header[j]] = cols[j];
  }
  rows.push(obj);
}

// Group by symbol — column order may vary, try both positions
const bySymbol: Map<string, Bar[]> = new Map();
for (const r of rows) {
  const sym = r.symbol || r[Object.keys(r)[1]];
  if (!bySymbol.has(sym)) bySymbol.set(sym, []);
  bySymbol.get(sym)!.push({
    ts: r.ts || r[Object.keys(r)[2]],
    symbol: sym,
    open: Number(r.open || r[Object.keys(r)[3]]),
    high: Number(r.high || r[Object.keys(r)[4]]),
    low: Number(r.low || r[Object.keys(r)[5]]),
    close: Number(r.close || r[Object.keys(r)[6]]),
    volume: Number(r.volume || r[Object.keys(r)[7]] || 0),
  });
}

// Minimal LabConfig stub
const configStub: any = {
  symbol: "NQ",
  executionEnv: { mode: "paper", broker: "tradovate", accountId: "" },
  stopManagement: { type: "trailing", atrMultiplier: 1.2, breakevenAtR: 0, trailAtR: 0 },
  tuning: { enabled: false },
  live: { enabled: false },
  polygon: { enabled: false, apiKey: "" },
};

const strategies = [
  new OrbBreakout60m(),
  new WqTrendMom60m(),
  new WqVolRegime60m(),
];

const results: any[] = [];
const latestBars: Record<string, string> = {};

for (const sym of TARGET_SYMBOLS) {
  const bars = bySymbol.get(sym);
  if (!bars || bars.length < 20) {
    results.push({ symbol: sym, ...SAFETY, error: `not enough bars: ${bars?.length ?? 0}` });
    continue;
  }
  latestBars[sym] = bars[bars.length - 1].ts;

  for (const strat of strategies) {
    const ctx = {
      symbol: sym,
      bar: bars[bars.length - 1],
      history: bars,
      sessionHistory: bars.slice(-20),
      config: { ...configStub, symbol: sym } as any,
      dailyTradeCount: 0,
    };

    try {
      const signal = strat.generateSignal(ctx);
      results.push({
        symbol: sym,
        strategyId: strat.id,
        ...SAFETY,
        signal: signal ? {
          side: signal.side,
          entry: signal.entry,
          stop: signal.stop,
          target: signal.target,
          rr: signal.rr,
          confidence: signal.confidence,
        } : null,
      });
    } catch (e: any) {
      results.push({ symbol: sym, strategyId: strat.id, ...SAFETY, error: e?.message ?? String(e) });
    }
  }
}

process.stdout.write(JSON.stringify({ ...SAFETY, results, latestBars }, null, 2) + "\n");
