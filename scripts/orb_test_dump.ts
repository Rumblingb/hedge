/**
 * orb_test_dump.ts — runs the REAL runBacktest with the ORB ensemble on the
 * walk-forward TEST (OOS) window and dumps trade records to compare against the
 * manual diag. Reveals whether the real engine mis-simulates ORB.
 */
import { resolve } from "node:path";
import { loadBarsFromCsv } from "../src/data/csv.js";
import { getConfig } from "../src/config.js";
import { NoopNewsGate } from "../src/news/base.js";
import { runBacktest } from "../src/engine/backtest.js";
import { buildDefaultEnsemble } from "../src/strategies/wctcEnsemble.js";
import { buildWalkforwardWindows } from "../src/engine/walkforward.js";
import { mergeProfile, RESEARCH_PROFILES } from "../src/research/profiles.js";

async function main(): Promise<void> {
  const config = getConfig();
  const profile = RESEARCH_PROFILES.find((p) => p.id === "orb-breakout-proven")!;
  const merged = mergeProfile(config, profile);
  const bars = await loadBarsFromCsv(resolve("data/free/NQ-15m-2y-orb.csv"));
  const windows = buildWalkforwardWindows(bars, { embargoDays: 1 });
  const strategy = buildDefaultEnsemble(merged);

  let allTest: any[] = [];
  for (let i = 0; i < windows.length; i++) {
    const r = await runBacktest({ bars: windows[i].test, strategy, config: merged, newsGate: new NoopNewsGate() });
    console.error(`window ${i}: test trades=${r.trades.length}`);
    allTest.push(...r.trades);
  }
  const reasons: Record<string, number> = {};
  let win = 0, loss = 0;
  for (const t of allTest) {
    reasons[t.exitReason] = (reasons[t.exitReason] ?? 0) + 1;
    if (t.rMultiple > 0) win++; else loss++;
  }
  console.log(JSON.stringify({
    total: allTest.length, win, loss,
    winRate: win / Math.max(1, allTest.length),
    reasons,
    sample: allTest.slice(0, 6).map((t) => ({ side: t.side, entry: Number(t.entry.toFixed(2)), exit: Number(t.exitPrice.toFixed(2)), reason: t.exitReason, r: Number(t.rMultiple.toFixed(3)), entryTs: t.entryTs }))
  }, null, 2));
}
main().catch((e) => { console.error(e); process.exit(1); });
