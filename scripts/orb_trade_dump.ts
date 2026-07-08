/**
 * orb_trade_dump.ts — runs the REAL evaluateProfile for orb-breakout-proven and
 * dumps the actual trade records so we can compare against the manual diag
 * (which showed ~41% WR). Reveals whether the real backtest engine mis-simulates ORB.
 */
import { resolve } from "node:path";
import { loadBarsFromCsv } from "../src/data/csv.js";
import { getConfig } from "../src/config.js";
import { NoopNewsGate } from "../src/news/base.js";
import { evaluateProfile } from "../src/engine/walkforward.js";
import { buildWalkforwardWindows } from "../src/engine/walkforward.js";
import { RESEARCH_PROFILES } from "../src/research/profiles.js";

async function main(): Promise<void> {
  const config = getConfig();
  const profile = RESEARCH_PROFILES.find((p) => p.id === "orb-breakout-proven")!;
  const bars = await loadBarsFromCsv(resolve("data/free/NQ-15m-2y-orb.csv"));
  const windows = buildWalkforwardWindows(bars, { embargoDays: 1 });
  console.error(`windows=${windows.length} train=${windows[0].train.length} test=${windows[0].test.length}`);

  const result = await evaluateProfile({ profile, baseConfig: config, windows, newsGate: new NoopNewsGate() });
  const all = [...result.trainTrades, ...result.testTrades];
  const reasons: Record<string, number> = {};
  let win = 0, loss = 0;
  for (const t of all) {
    reasons[t.exitReason] = (reasons[t.exitReason] ?? 0) + 1;
    if (t.rMultiple > 0) win++; else loss++;
  }
  console.log(JSON.stringify({
    totalTrades: all.length,
    win, loss, winRate: win / Math.max(1, all.length),
    reasons,
    sample: all.slice(0, 5).map((t) => ({ side: t.side, entry: t.entry, exit: t.exitPrice, reason: t.exitReason, r: Number(t.rMultiple.toFixed(3)) }))
  }, null, 2));
}
main().catch((e) => { console.error(e); process.exit(1); });
