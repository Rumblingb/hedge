#!/usr/bin/env node
// gengarMonitor.ts — Multi-period Gengar Brownian Motion scalper.
//
// Monitors BTC 5-min AND 15-min UP/DOWN markets on Polymarket.
// Volatility is period-adjusted: vol_T = vol_5m * sqrt(T/300)
//   - 5-min:  vol = 0.12 (12 bps)
//   - 15-min: vol = 0.208 (0.12 * sqrt(3))
//
// Market discovery: deterministic slugs btc-updown-{period}-{window_ts}
// Prices: Gamma API outcomePrices (fast, no separate CLOB book call)
// Binance: REST ticker for BTCUSDT
//
// Run: npx tsx src/prediction/gengarMonitor.ts

import { evaluateTick, type ScalperTick, type ScalperConfig } from "./oracleLagScalper.js";
import { fetchPolymarketQuote } from "./polymarketBook.js";
import { mkdir, appendFile, writeFile, readFile } from "node:fs/promises";
import { join } from "node:path";

const SIGNALS_PATH = join(process.cwd(), ".rumbling-hedge/journal/gengar-signals.jsonl");
const STATE_PATH = join(process.cwd(), ".rumbling-hedge/state/gengar-monitor.json");
const GAMMA_API = "https://gamma-api.polymarket.com";
const REQUIRE_CLOB = process.env.BILL_GENGAR_REQUIRE_CLOB !== "false";
const MAX_SPREAD_PCT = Number.parseFloat(process.env.BILL_GENGAR_MAX_SPREAD_PCT ?? "2");
const MIN_ASK_NOTIONAL = Number.parseFloat(process.env.BILL_GENGAR_MIN_ASK_NOTIONAL ?? "1");
const QUOTE_TIMEOUT_MS = Number.parseInt(process.env.BILL_GENGAR_CLOB_TIMEOUT_MS ?? "3000", 10);
const MAX_SIGNALS_PER_WINDOW_SIDE = Number.parseInt(process.env.BILL_GENGAR_MAX_SIGNALS_PER_WINDOW_SIDE ?? "1", 10);

interface PeriodConfig {
  name: string;          // "5m" or "15m"
  seconds: number;       // 300 or 900
  volBps: number;        // 0.12 or 0.208
}

const PERIODS: PeriodConfig[] = [
  { name: "5m", seconds: 300, volBps: 0.12 },
  { name: "15m", seconds: 900, volBps: 0.12 * Math.sqrt(3) }, // ≈ 0.208
];

interface MonitorState {
  totalSignals: number;
  lastWindowTs: Record<string, number>;  // period_name → last window ts
  btcOpen: Record<string, number>;       // period_name → btc at window open
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

function currentWindowTs(periodSec: number): number {
  const now = Math.floor(Date.now() / 1000);
  return now - (now % periodSec);
}

function marketSlug(periodName: string, windowTs: number): string {
  return `btc-updown-${periodName}-${windowTs}`;
}

function signalWindowKey(periodName: string, windowTs: number, side: string): string {
  return `${periodName}:${windowTs}:${side}`;
}

function periodSignalCount(counts: Record<string, number>, periodName: string): number {
  return Object.entries(counts)
    .filter(([key]) => key.startsWith(`${periodName}:`))
    .reduce((sum, [, count]) => sum + count, 0);
}

async function fetchMarket(periodName: string, windowTs: number): Promise<{
  tokenIdUp: string;
  tokenIdDown: string;
  upPrice: number;
  downPrice: number;
  windowEnd: number;
} | null> {
  const slug = marketSlug(periodName, windowTs);
  try {
    const url = `${GAMMA_API}/events?slug=${encodeURIComponent(slug)}`;
    const resp = await fetch(url, {
      headers: { "User-Agent": "gengar-monitor/0.2" },
      signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) return null;
    const events = (await resp.json()) as Array<Record<string, unknown>>;
    if (!events || events.length === 0) return null;

    const event = events[0]!;
    const markets = event.markets as Array<Record<string, unknown>> | undefined;
    if (!markets || markets.length === 0) return null;

    const market = markets[0]!;
    let clobTokenIds: string[] = [];
    const rawTokens = market.clobTokenIds;
    if (typeof rawTokens === "string") {
      try { clobTokenIds = JSON.parse(rawTokens); } catch { return null; }
    } else if (Array.isArray(rawTokens)) {
      clobTokenIds = rawTokens.map(String);
    }
    if (clobTokenIds.length < 2) return null;

    let outcomes: string[] = [];
    const rawOutcomes = market.outcomes;
    if (typeof rawOutcomes === "string") {
      try { outcomes = JSON.parse(rawOutcomes); } catch { outcomes = []; }
    } else if (Array.isArray(rawOutcomes)) {
      outcomes = rawOutcomes.map(String);
    }

    let prices: number[] = [];
    const rawPrices = market.outcomePrices;
    if (typeof rawPrices === "string") {
      try { prices = JSON.parse(rawPrices).map(Number); } catch { prices = []; }
    } else if (Array.isArray(rawPrices)) {
      prices = rawPrices.map(Number);
    }

    let tokenUp = clobTokenIds[0]!;
    let tokenDown = clobTokenIds[1]!;
    let upPrice = 0.50;
    let downPrice = 0.50;

    for (let i = 0; i < Math.min(outcomes.length, prices.length); i++) {
      if (outcomes[i]?.toLowerCase() === "up") {
        tokenUp = clobTokenIds[i] ?? tokenUp;
        upPrice = prices[i] ?? upPrice;
      } else if (outcomes[i]?.toLowerCase() === "down") {
        tokenDown = clobTokenIds[i] ?? tokenDown;
        downPrice = prices[i] ?? downPrice;
      }
    }

    return {
      tokenIdUp: tokenUp,
      tokenIdDown: tokenDown,
      upPrice: Math.max(0.01, Math.min(0.99, upPrice)),
      downPrice: Math.max(0.01, Math.min(0.99, downPrice)),
      windowEnd: windowTs + PERIODS.find(p => p.name === periodName)!.seconds,
    };
  } catch {
    return null;
  }
}

async function run() {
  await mkdir(join(process.cwd(), ".rumbling-hedge/journal"), { recursive: true });
  await mkdir(join(process.cwd(), ".rumbling-hedge/state"), { recursive: true });

  console.log("[gengar-monitor] Starting multi-period scalper...");
  console.log(`[gengar-monitor] Periods: ${PERIODS.map(p => p.name + "(" + p.volBps.toFixed(3) + "bps)").join(", ")}`);

  let state: MonitorState = {
    totalSignals: 0,
    lastWindowTs: {},
    btcOpen: {},
  };

  try {
    const raw = await readFile(STATE_PATH, "utf8");
    const saved = JSON.parse(raw);
    state.totalSignals = saved.totalSignals ?? 0;
    // Handle old format (lastWindowTs was a number) vs new (Record)
    if (typeof saved.lastWindowTs === "object" && saved.lastWindowTs !== null) {
      state.lastWindowTs = saved.lastWindowTs;
    }
    if (typeof saved.btcOpen === "object" && saved.btcOpen !== null) {
      state.btcOpen = saved.btcOpen;
    }
  } catch {}

  let signalsThisWindow: Record<string, number> = {};
  let loopCount = 0;

  console.log(`[gengar-monitor] Total lifetime signals: ${state.totalSignals}`);
  console.log("[gengar-monitor] Monitoring loop started.");

  while (true) {
    try {
      const btcNow = await fetchBtcPrice();

      for (const period of PERIODS) {
        const windowTs = currentWindowTs(period.seconds);
        const prevTs = state.lastWindowTs[period.name] ?? 0;
        const secondsElapsed = Math.floor(Date.now() / 1000) - windowTs;

        // New window: set BTC open only if window is fresh
        if (windowTs !== prevTs) {
          const closedCount = periodSignalCount(signalsThisWindow, period.name);
          if (closedCount > 0) {
            console.log(`[${period.name}] Window closed: ${closedCount} signal(s)`);
          }
          state.lastWindowTs[period.name] = windowTs;
          for (const key of Object.keys(signalsThisWindow)) {
            if (key.startsWith(`${period.name}:`)) delete signalsThisWindow[key];
          }

          // Only enter if window is fresh (< 10% elapsed)
          if (secondsElapsed > period.seconds * 0.1) {
            continue; // Skip stale window, wait for next one
          }
          state.btcOpen[period.name] = btcNow;
          console.log(`[${period.name}] New window ${windowTs}: btc=${btcNow.toFixed(0)}`);
        }

        const btcOpen = state.btcOpen[period.name];
        if (!btcOpen || btcOpen <= 0) continue;

        // Fetch market
        const market = await fetchMarket(period.name, windowTs);
        if (!market) continue;

        // Periodic status
        if (loopCount % 10 === 0 && period.name === "15m") {
          console.log(`[${period.name}] Market: UP=${market.upPrice.toFixed(3)} DOWN=${market.downPrice.toFixed(3)} ` +
            `elapsed=${secondsElapsed}s btc=${btcNow.toFixed(0)}`);
        }

        // Build scalper config with period-adjusted vol
        const config: ScalperConfig = {
          ...{ vol: period.volBps, minProb: 0.80, minEdge: 0.05, minBtcDelta: 0.06,
               maxPrice: 0.90, minPrice: 0.50, entryWindowStart: period.seconds * 0.8,
               entryWindowEnd: 10, kellyFraction: 0.25, minBet: 7, maxBet: 25 },
        };

        const tick: ScalperTick = {
          btcOpen,
          btcNow,
          upPrice: market.upPrice,
          downPrice: market.downPrice,
          secondsElapsed,
          secondsTotal: period.seconds,
          ts: Date.now(),
        };

        const signal = evaluateTick(tick, config);
        if (!signal) continue;

        if (!signal.skipReason) {
          const tokenId = signal.side === "UP" ? market.tokenIdUp : market.tokenIdDown;
          const sideSignalKey = signalWindowKey(period.name, windowTs, signal.side);
          if ((signalsThisWindow[sideSignalKey] ?? 0) >= MAX_SIGNALS_PER_WINDOW_SIDE) {
            continue;
          }

          let quote = null;
          try {
            quote = await fetchPolymarketQuote(tokenId, QUOTE_TIMEOUT_MS);
          } catch {
            quote = null;
          }

          if (!quote?.bestAsk) {
            if (REQUIRE_CLOB) {
              console.log(`[${period.name}] Skip ${signal.side}: no executable CLOB ask`);
              continue;
            }
          }

          if (quote?.spreadPct !== undefined && quote.spreadPct > MAX_SPREAD_PCT) {
            console.log(`[${period.name}] Skip ${signal.side}: spread=${quote.spreadPct.toFixed(2)}pct > ${MAX_SPREAD_PCT}`);
            continue;
          }

          const askNotional = (quote?.askSize ?? 0) * (quote?.bestAsk ?? 0);
          if (quote?.bestAsk !== undefined && askNotional < Math.max(MIN_ASK_NOTIONAL, config.minBet)) {
            console.log(`[${period.name}] Skip ${signal.side}: ask_notional=$${askNotional.toFixed(2)} < $${Math.max(MIN_ASK_NOTIONAL, config.minBet).toFixed(2)}`);
            continue;
          }

          const executableTick: ScalperTick = quote?.bestAsk !== undefined
            ? {
                ...tick,
                upPrice: signal.side === "UP" ? quote.bestAsk : tick.upPrice,
                downPrice: signal.side === "DOWN" ? quote.bestAsk : tick.downPrice,
              }
            : tick;
          const executableSignal = evaluateTick(executableTick, config);
          if (!executableSignal || executableSignal.skipReason) {
            console.log(`[${period.name}] Skip ${signal.side}: executable ${executableSignal?.skipReason ?? "no_signal"}`);
            continue;
          }

          const entry = {
            ts: new Date().toISOString(),
            period: period.name,
            ...executableSignal,
            btcOpen,
            btcNow,
            gammaMarketPrice: signal.marketPrice,
            upPrice: market.upPrice,
            downPrice: market.downPrice,
            secondsElapsed,
            tokenUp: market.tokenIdUp,
            tokenDown: market.tokenIdDown,
            tokenId,
            executablePrice: executableSignal.marketPrice,
            quoteStatus: quote ? "ok" : "missing",
            bestBid: quote?.bestBid,
            bestAsk: quote?.bestAsk,
            spreadPct: quote?.spreadPct,
            topBookDepth: quote?.topBookDepth,
            bidSize: quote?.bidSize,
            askSize: quote?.askSize,
          };

          await appendFile(SIGNALS_PATH, JSON.stringify(entry) + "\n");
          signalsThisWindow[sideSignalKey] = (signalsThisWindow[sideSignalKey] ?? 0) + 1;
          state.totalSignals++;

          console.log(
            `[SIGNAL ${state.totalSignals}] [${period.name}] ${executableSignal.side} | ` +
            `prob=${executableSignal.prob.toFixed(3)} edge=${executableSignal.edge.toFixed(3)} ` +
            `ask=${executableSignal.marketPrice.toFixed(3)} gamma=${signal.marketPrice.toFixed(3)} ` +
            `spread=${quote?.spreadPct?.toFixed(2) ?? "na"}pct delta=${executableSignal.deltaBps.toFixed(2)}bps ` +
            `bet=$${executableSignal.recommendedBet.toFixed(0)} remaining=${executableSignal.secondsRemaining.toFixed(0)}s`
          );
        }

        // Quietly log market activity every ~30s per period
        if (secondsElapsed % 30 < 3) {
          // Skip verbose logging — only log on signals or window changes
        }
      }

      // Save state periodically
      if (state.totalSignals > 0 && state.totalSignals % 10 === 0) {
        await writeFile(STATE_PATH, JSON.stringify({
          totalSignals: state.totalSignals,
          lastWindowTs: state.lastWindowTs,
          btcOpen: state.btcOpen,
        }));
      }
    } catch (err) {
      console.error(`[gengar-monitor] Error: ${(err as Error).message}`);
    }

    loopCount++;
    if (loopCount % 20 === 0) {
      const now = Math.floor(Date.now() / 1000);
      console.log(`[gengar-monitor] Heartbeat: loop ${loopCount}, ` +
        `${PERIODS.map(p => `${p.name}=${now - currentWindowTs(p.seconds)}s`).join(", ")}`);
    }
    await sleep(3000);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

run().catch((err) => {
  console.error("[gengar-monitor] Fatal:", err);
  process.exit(1);
});
