/**
 * orb_signal_debug.ts — isolate OrbBreakoutStrategy signal generation on the
 * normalized NQ 15m data. Counts raw signals (before guardrails) and breaks down
 * why none become trades. Pure strategy evaluation, no ensemble, no risk state.
 */
import { resolve } from "node:path";
import { loadBarsFromCsv } from "../src/data/csv.js";
import { OrbBreakoutStrategy } from "../src/strategies/orbBreakout.js";
import { chicagoDateKey, minutesFromCtTime } from "../src/utils/time.js";

async function main(): Promise<void> {
  const csvPath = resolve("data/free/NQ-15m-2y-orb.csv");
  const bars = await loadBarsFromCsv(csvPath);
  console.error(`loaded ${bars.length} bars`);

  const strat = new OrbBreakoutStrategy();
  const sessionHistoryByDay = new Map<string, any[]>();
  const historyBySymbol = new Map<string, any[]>();
  const sessionStartCt = "08:30";
  const startMin = (() => {
    const [h, m] = sessionStartCt.split(":").map(Number);
    return h * 60 + m;
  })();

  let signalAttempts = 0;
  let passRangeWindow = 0;
  let passVolume = 0;
  let passBreakout = 0;
  let passDailyCap = 0;
  let rawSignals = 0;
  const dayTradeCount = new Map<string, number>();

  for (const bar of bars) {
    const dayKey = chicagoDateKey(bar.ts);
    const history = historyBySymbol.get(bar.symbol) ?? [];
    const sessionKey = `${dayKey}:${bar.symbol}`;
    let sessionHistory = sessionHistoryByDay.get(sessionKey) ?? [];
    const dailyCount = dayTradeCount.get(dayKey) ?? 0;

    const ctx: any = {
      symbol: bar.symbol,
      bar,
      history,
      sessionHistory,
      config: { guardrails: { sessionStartCt } },
      news: null,
      macroContext: null,
      macro: null,
      dailyTradeCount: dailyCount
    };

    // Replicate the gating checks manually for diagnostics
    if (sessionHistory.length < 12) {
      // too early, skip
    } else {
      passRangeWindow++;
      const vol = bar.volume;
      const avgVol = sessionHistory.slice(-10).reduce((s: number, b: any) => s + b.volume, 0) / 10;
      if (avgVol > 0 && vol >= avgVol * 1.3) {
        passVolume++;
        const opening = sessionHistory.slice(0, 12);
        const rh = Math.max(...opening.map((b: any) => b.high));
        const rl = Math.min(...opening.map((b: any) => b.low));
        if (bar.close > rh || bar.close < rl) {
          passBreakout++;
        }
      }
    }
    if (dailyCount === 0) passDailyCap++;

    const sig = strat.generateSignal(ctx);
    if (sig) {
      rawSignals++;
      dayTradeCount.set(dayKey, dailyCount + 1);
    }
    signalAttempts++;

    sessionHistory.push(bar);
    history.push(bar);
    sessionHistoryByDay.set(sessionKey, sessionHistory);
    historyBySymbol.set(bar.symbol, history);
  }

  console.log(JSON.stringify({
    totalBars: bars.length,
    signalAttempts,
    rawSignals,
    passRangeWindow,
    passVolume,
    passBreakout,
    passDailyCap,
    note: "rawSignals = signals the strategy itself emits; if 0, strategy logic rejects"
  }, null, 2));
}

main().catch((e) => { console.error(e); process.exit(1); });
