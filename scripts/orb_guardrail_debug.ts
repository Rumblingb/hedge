/**
 * orb_guardrail_debug.ts — confirm WHY ORB signals are rejected by the real
 * evaluateSignalGuardrails. Replays the guardrail decision on every raw ORB
 * signal emitted over the NQ 15m 2y dataset.
 */
import { resolve } from "node:path";
import { loadBarsFromCsv } from "../src/data/csv.js";
import { getConfig } from "../src/config.js";
import { NoopNewsGate } from "../src/news/base.js";
import { OrbBreakoutStrategy } from "../src/strategies/orbBreakout.js";
import { mergeProfile, RESEARCH_PROFILES } from "../src/research/profiles.js";
import { evaluateSignalGuardrails, createInitialRiskState, applyTradeToRiskState } from "../src/risk/guardrails.js";
import { chicagoDateKey } from "../src/utils/time.js";

async function main(): Promise<void> {
  const config = getConfig();
  const profile = RESEARCH_PROFILES.find((p) => p.id === "orb-breakout-proven")!;
  const merged = mergeProfile(config, profile);
  console.error("profile guardrails:", JSON.stringify(merged.guardrails));
  console.error("HARD maxHoldMinutes cap = 120 (from guardrails.ts)");

  const csvPath = resolve("data/free/NQ-15m-2y-orb.csv");
  const bars = await loadBarsFromCsv(csvPath);

  const strat = new OrbBreakoutStrategy();
  const sessionHistoryByDay = new Map<string, any[]>();
  const historyBySymbol = new Map<string, any[]>();
  const riskByDay = new Map<string, any>();
  const reasonsCount: Record<string, number> = {};
  const dayTradeCount = new Map<string, number>();
  let raw = 0;
  let allowed = 0;
  let sampleSignal: any = null;

  const newsGate = new NoopNewsGate();

  for (const bar of bars) {
    const dayKey = chicagoDateKey(bar.ts);
    const history = historyBySymbol.get(bar.symbol) ?? [];
    const sessionKey = `${dayKey}:${bar.symbol}`;
    const sessionHistory = sessionHistoryByDay.get(sessionKey) ?? [];
    const riskState = riskByDay.get(dayKey) ?? createInitialRiskState();

    const sig = strat.generateSignal({ symbol: bar.symbol, bar, history, sessionHistory, config: merged, news: null, macroContext: null, macro: null, dailyTradeCount: dayTradeCount.get(dayKey) ?? 0 } as any);
    if (sig) {
      raw++;
      if (!sampleSignal) sampleSignal = { maxHoldMinutes: sig.maxHoldMinutes, rr: sig.rr, contracts: sig.contracts, entry: sig.entry, stop: sig.stop, target: sig.target };
      const decision = evaluateSignalGuardrails({
        signal: { ...sig, meta: { ...sig.meta, barIntervalMinutes: 15 } },
        timestamp: bar.ts,
        guardrails: merged.guardrails,
        riskState,
        news: newsGate.score({ symbol: bar.symbol, ts: bar.ts, bar })
      });
      if (decision.allowed) {
        allowed++;
        riskByDay.set(dayKey, applyTradeToRiskState(riskState, 0.5));
      } else {
        for (const r of decision.reasons) reasonsCount[r] = (reasonsCount[r] ?? 0) + 1;
      }
    }
    sessionHistory.push(bar);
    history.push(bar);
    sessionHistoryByDay.set(sessionKey, sessionHistory);
    historyBySymbol.set(bar.symbol, history);
  }

  console.log(JSON.stringify({ raw, allowed, sampleSignal, rejectReasons: reasonsCount }, null, 2));
}

main().catch((e) => { console.error(e); process.exit(1); });
