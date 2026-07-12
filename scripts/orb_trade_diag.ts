/**
 * orb_trade_diag.ts — manual ORB trade simulation on NQ 15m to understand the
 * win/loss R distribution. Reuses the real OrbBreakoutStrategy + backtest exit
 * semantics (entry at signal.entry, exit on stop/target/timeout/flat).
 */
import { resolve } from "node:path";
import { loadBarsFromCsv } from "../src/data/csv.js";
import { getConfig } from "../src/config.js";
import { NoopNewsGate } from "../src/news/base.js";
import { OrbBreakoutStrategy } from "../src/strategies/orbBreakout.js";
import { mergeProfile, RESEARCH_PROFILES } from "../src/research/profiles.js";
import { evaluateSignalGuardrails, createInitialRiskState, applyTradeToRiskState } from "../src/risk/guardrails.js";
import { chicagoDateKey, minutesFromCtTime } from "../src/utils/time.js";
import { getMarketSessionWindow } from "../src/utils/sessions.js";

const RR_STOP = 1.5; // ATR stop
const RR_TARGET = 3.0; // ATR target

async function main(): Promise<void> {
  const config = getConfig();
  const profile = RESEARCH_PROFILES.find((p) => p.id === "orb-breakout-proven")!;
  const merged = mergeProfile(config, profile);
  const bars = await loadBarsFromCsv(resolve("data/free/NQ-15m-2y-orb.csv"));
  const strat = new OrbBreakoutStrategy();
  const news = new NoopNewsGate();

  const sessionHistoryByDay = new Map<string, any[]>();
  const historyBySymbol = new Map<string, any[]>();
  const riskByDay = new Map<string, any>();
  const dayTradeCount = new Map<string, number>();

  let wins = 0, losses = 0, scratches = 0;
  let winR = 0, lossR = 0;
  const rList: number[] = [];

  let active: any = null;

  for (const bar of bars) {
    const dayKey = chicagoDateKey(bar.ts);
    const sessionKey = `${dayKey}:${bar.symbol}`;
    const sessionHistory = sessionHistoryByDay.get(sessionKey) ?? [];
    const history = historyBySymbol.get(bar.symbol) ?? [];
    const riskState = riskByDay.get(dayKey) ?? createInitialRiskState();
    const dCount = dayTradeCount.get(dayKey) ?? 0;

    // first, check exit of active trade
    if (active) {
      const atr = active.atr;
      const stop = active.side === "long" ? active.entry - RR_STOP * atr : active.entry + RR_STOP * atr;
      const target = active.side === "long" ? active.entry + RR_TARGET * atr : active.entry - RR_TARGET * atr;
      const flat = minutesFromCtTime(bar.ts, getMarketSessionWindow(bar.symbol, merged.guardrails.sessionStartCt).startCt) > (15 * 60 + 10);
      const elapsed = (new Date(bar.ts).getTime() - new Date(active.entryTs).getTime()) / 60000;
      let exited = false, r = 0;
      if (active.side === "long") {
        if (bar.low <= stop) { r = -(RR_STOP); exited = true; }
        else if (bar.high >= target) { r = RR_TARGET; exited = true; }
      } else {
        if (bar.high >= stop) { r = -(RR_STOP); exited = true; }
        else if (bar.low <= target) { r = RR_TARGET; exited = true; }
      }
      if (!exited && (flat || elapsed >= 120)) { r = (bar.close - active.entry) / (active.side === "long" ? 1 : -1) / atr; exited = true; }
      if (exited) {
        if (r > 0.01) { wins++; winR += r; } else if (r < -0.01) { losses++; lossR += r; } else scratches++;
        rList.push(r);
        riskByDay.set(dayKey, applyTradeToRiskState(riskState, r));
        active = null;
      }
    }

    // generate new signal
    const sig = strat.generateSignal({ symbol: bar.symbol, bar, history, sessionHistory, config: merged, news: null, macroContext: null, macro: null, dailyTradeCount: dCount } as any);
    if (sig && !active) {
      const decision = evaluateSignalGuardrails({ signal: { ...sig, meta: { ...sig.meta, barIntervalMinutes: 15 } }, timestamp: bar.ts, guardrails: merged.guardrails, riskState, news: news.score({ symbol: bar.symbol, ts: bar.ts, bar }) });
      if (decision.allowed) {
        const atr = (sig.meta?.atr as number) ?? 1;
        active = { side: sig.side, entry: sig.entry, entryTs: bar.ts, atr };
      }
    }

    sessionHistory.push(bar); history.push(bar);
    sessionHistoryByDay.set(sessionKey, sessionHistory);
    historyBySymbol.set(bar.symbol, history);
    dayTradeCount.set(dayKey, dCount + (active ? 0 : 0)); // updated below
  }

  const total = wins + losses + scratches;
  console.log(JSON.stringify({
    total, wins, losses, scratches,
    winRate: wins / Math.max(1, total),
    avgWinR: winR / Math.max(1, wins),
    avgLossR: lossR / Math.max(1, losses),
    netR: winR + lossR,
    expectancyR: (winR + lossR) / Math.max(1, total)
  }, null, 2));
}
main().catch((e) => { console.error(e); process.exit(1); });
