/**
 * strategyEngineRunner.ts — THE BRIDGE
 * 
 * Runs every N minutes during NY session:
 *   1. Fetch live NQ bars (Polygon preferred, Yahoo fallback)
 *   2. Read GEX levels, inside-day XGBoost, DOM micro edges
 *   3. Run ALL GOLD/SILVER strategies via wctcEnsemble.generateSignal()
 *   4. Validate against pre-trade decision
 *   5. Route best signal to all accounts via signalRouter
 * 
 * This is the missing link between our proven strategies and live execution.
 */

import { buildDefaultEnsemble, buildStrategyCatalog } from "../strategies/wctcEnsemble.js";
import type { Bar, LabConfig, StrategyContext, StrategySignal, MacroContextSnapshot } from "../domain.js";
import { signalRouter } from "../live/signalRouter.js";
import type { OrbSignal } from "../live/signalRouter.js";
import { mkdir, appendFile, readFile } from "node:fs/promises";
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";

// ── Config ──

const LOG_DIR = join(process.cwd(), ".rumbling-hedge/logs");
const LOG_PATH = join(LOG_DIR, "strategy-engine-runner.log");
const STATE_DIR = join(process.cwd(), ".rumbling-hedge/state");
const INTERVAL_MS = 60_000;           // Check every 60s for a new bar
const BAR_INTERVAL_S = 900;            // 15m bars
const NY_OPEN = 9.5 * 60;             // 09:30 ET
const NY_CLOSE = 16 * 60;             // 16:00 ET

const YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/MNQ=F?interval=15m&range=5d";
const POLYGON_BARS_URL = "https://api.polygon.io/v2/aggs/ticker/MNQ/range/15/minute/2026-05-17/2026-05-18?adjusted=true&sort=asc&limit=200";

// ── Position tracking ──

interface TrackedPosition {
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  entryPrice: number;
  strategyId: string;
  entryTs: string;
  sl: number;
  tp: number;
}

let currentPosition: TrackedPosition | null = null;

// ── Logging ──

async function log(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  try {
    await appendFile(LOG_PATH, line + "\n");
  } catch {}
}

// ── Bar fetching ──

async function fetchBarsPolygon(): Promise<Bar[] | null> {
  try {
    const key = process.env.RH_POLYGON_API_KEY;
    if (!key) return null;
    const today = new Date();
    const fiveDaysAgo = new Date(today);
    fiveDaysAgo.setDate(fiveDaysAgo.getDate() - 5);
    const from = fiveDaysAgo.toISOString().split("T")[0];
    const to = today.toISOString().split("T")[0];
    const url = `https://api.polygon.io/v2/aggs/ticker/MNQ/range/15/minute/${from}/${to}?adjusted=true&sort=asc&limit=500`;
    
    const res = await fetch(url, { headers: { "Authorization": `Bearer ${key}` } });
    if (!res.ok) { await log(`Polygon fetch ${res.status}`); return null; }
    const data: any = await res.json();
    if (!data?.results?.length) return null;

    return data.results.map((r: any) => ({
      ts: new Date(r.t).toISOString(),
      symbol: "MNQ",
      open: r.o,
      high: r.h,
      low: r.l,
      close: r.c,
      volume: r.n || r.v || 0,
    }));
  } catch (e: any) {
    await log(`Polygon error: ${e.message?.slice(0, 80)}`);
    return null;
  }
}

async function fetchBarsYahoo(): Promise<Bar[] | null> {
  try {
    const res = await fetch(YAHOO_URL, { headers: { "User-Agent": "Mozilla/5.0" } });
    if (!res.ok) return null;
    const data: any = await res.json();
    const result = data?.chart?.result?.[0];
    if (!result) return null;

    const timestamps = result.timestamp || [];
    const quotes = result.indicators?.quote?.[0] || {};

    return timestamps.map((ts: number, i: number) => ({
      ts: new Date(ts * 1000).toISOString(),
      symbol: "MNQ",
      open: quotes.open?.[i],
      high: quotes.high?.[i],
      low: quotes.low?.[i],
      close: quotes.close?.[i],
      volume: quotes.volume?.[i] || 0,
    })).filter((b: any) => b.close != null);
  } catch {
    return null;
  }
}

async function fetchBars(): Promise<Bar[] | null> {
  // Polygon first (reliable), Yahoo fallback (delayed)
  const polygon = await fetchBarsPolygon();
  if (polygon && polygon.length >= 20) {
    await log(`Fetched ${polygon.length} bars from Polygon`);
    return polygon;
  }
  return await fetchBarsYahoo();
}

// ── Signal file readers ──

function readJsonFile(path: string): any {
  try {
    if (!existsSync(path)) return null;
    return JSON.parse(readFileSync(path, "utf8"));
  } catch { return null; }
}

function getAtr(bars: Bar[]): number {
  if (bars.length < 15) return 50; // fallback
  let sum = 0;
  for (let i = 1; i < Math.min(15, bars.length); i++) {
    const tr = Math.max(
      bars[i].high - bars[i].low,
      Math.abs(bars[i].high - bars[i - 1].close),
      Math.abs(bars[i].low - bars[i - 1].close)
    );
    sum += tr;
  }
  return sum / Math.min(14, bars.length - 1);
}

function signalToOrbSignal(signal: StrategySignal): OrbSignal {
  return {
    ticker: signal.symbol,
    action: signal.side === "long" ? "buy" : "sell",
    quantity: signal.contracts,
    entryPrice: signal.entry,
    price: signal.entry,
    stopLoss: signal.stop,
    takeProfit: signal.target,
  };
}

// ── Main cycle ──

async function runCycle() {
  const now = new Date();
  const etMinutes = now.getUTCHours() * 60 + now.getUTCMinutes() - 4 * 60;

  // 1. Session gate — only trade Mon-Fri during NY hours
  const dayOfWeek = now.getUTCDay(); // 0=Sun, 1=Mon, ... 6=Sat
  if (dayOfWeek === 0 || dayOfWeek === 6) {
    // Weekend — skip entirely
    return;
  }
  if (etMinutes < NY_OPEN || etMinutes >= NY_CLOSE) {
    if (currentPosition) {
      await log(`Session close — exiting tracked position ${currentPosition.quantity} ${currentPosition.symbol}`);
      await signalRouter.route({ ticker: currentPosition.symbol, action: "exit", quantity: currentPosition.quantity });
      currentPosition = null;
    }
    return;
  }

  // 2. Fetch bars
  const bars = await fetchBars();
  if (!bars || bars.length < 20) {
    await log("Insufficient bars — skipping cycle");
    return;
  }

  const atr = getAtr(bars);
  const currentBar = bars[bars.length - 1];
  const sessionBars = bars.filter((b) => {
    const t = new Date(b.ts);
    const m = t.getUTCHours() * 60 + t.getUTCMinutes() - 4 * 60;
    return m >= NY_OPEN;
  });

  // 3. Read confluence signals
  const gex = readJsonFile(join(STATE_DIR, "gex_levels.json"));
  const insideDay = readJsonFile(join(STATE_DIR, "inside_day_prediction.json"));
  const dom = readJsonFile(join(STATE_DIR, "dom_micro_edges.json"));
  const preTrade = readJsonFile(join(STATE_DIR, "pre_trade_decision.json"));

  // 4. Build context for strategies
  const config: LabConfig = {
    mode: "live",
    accountPhase: (process.env.RH_ACCOUNT_PHASE as any) || "challenge",
    journalPath: join(process.cwd(), ".rumbling-hedge/journal.jsonl"),
    killSwitchPath: join(process.cwd(), ".rumbling-hedge/kill-switch.json"),
    enabledStrategies: (process.env.RH_ENABLED_STRATEGIES || "").split(",").filter(Boolean),
    guardrails: {
      allowedSymbols: ["MNQ", "NQ"],
      sessionStartCt: "09:30",
      lastEntryCt: "15:00",
      flatByCt: "15:45",
      minRr: Number(process.env.RH_MIN_RR || 0.5),
      maxRiskPerTradePct: 2.0,
      maxContracts: Number(process.env.RH_MAX_CONTRACTS || 3),
      maxTradesPerDay: Number(process.env.RH_MAX_TRADES_PER_DAY || 1),
      maxHoldMinutes: Number(process.env.RH_MAX_HOLD_MINUTES || 30),
      maxDailyLossR: Number(process.env.RH_MAX_DAILY_LOSS_R || 1),
      trailingMaxDrawdownR: 3,
      maxConsecutiveLosses: Number(process.env.RH_MAX_CONSECUTIVE_LOSSES || 1),
      newsProbabilityThreshold: Number(process.env.RH_NEWS_THRESHOLD || 0.65),
      newsBlackoutMinutesBefore: Number(process.env.RH_NEWS_BLACKOUT_MINUTES_BEFORE || 5),
      newsBlackoutMinutesAfter: Number(process.env.RH_NEWS_BLACKOUT_MINUTES_AFTER || 5),
    },
    executionCosts: {
      roundTripFeeRPerContract: Number(process.env.RH_FEE_R_PER_CONTRACT || 0.02),
      slippageRPerSidePerContract: Number(process.env.RH_SLIPPAGE_R_PER_SIDE || 0.05),
      stressMultiplier: Number(process.env.RH_STRESS_MULTIPLIER || 1.5),
      stressBufferRPerTrade: Number(process.env.RH_STRESS_BUFFER_R || 0.5),
    },
    executionEnv: {
      latencyMs: 50,
      latencyJitterMs: 20,
      slippageTicksPerSide: 1,
      dataQualityPenaltyR: 0.1,
      maxSpreadTicks: 1,
      riskPerContractDollars: Number(process.env.RH_EXECUTION_RISK_PER_CONTRACT_USD || 350),
      slippageModel: (process.env.RH_EXECUTION_SLIPPAGE_MODEL as any) || "dollars",
    },
    stopManagement: {
      enabled: process.env.RH_STOP_MGMT_ENABLED === "true",
      breakEvenTriggerR: Number(process.env.RH_BREAK_EVEN_TRIGGER_R || 1.0),
      breakEvenOffsetR: Number(process.env.RH_BREAK_EVEN_OFFSET_R || 0.15),
      runnerEnabled: process.env.RH_RUNNER_ENABLED === "true",
      runnerTriggerR: Number(process.env.RH_RUNNER_TRIGGER_R || 1.8),
      runnerTrailingDistanceR: Number(process.env.RH_RUNNER_TRAILING_DISTANCE_R || 0.5),
    },
    tuning: {
      momentumLookbackBars: 20,
      momentumVolumeMultiplier: 1.5,
      reversionLookbackBars: 10,
      reversionVolumeMultiplier: 1.5,
      reversionWickToBody: 2.0,
      openingRangeVolumeMultiplier: 1.5,
      measuredMoveRr: 2.0,
      volatilityKillAtrMultiple: 3.0,
      pairsZEntry: 2.0,
      pairsLookbackBars: 20,
      volRegimeAtrFast: 14,
      volRegimeAtrSlow: 50,
      volRegimeThreshold: 1.5,
    },
    live: {
      enabled: true,
      username: process.env.RH_TOPSTEP_USERNAME,
      accountId: process.env.RH_TOPSTEP_ACCOUNT_ID,
      apiKey: process.env.RH_TOPSTEP_API_KEY,
      demoOnly: process.env.RH_TOPSTEP_DEMO_ONLY === "true",
      readOnly: process.env.RH_TOPSTEP_READ_ONLY === "true",
    },
    polygon: {
      enabled: Boolean(process.env.RH_POLYGON_API_KEY),
      apiKey: process.env.RH_POLYGON_API_KEY,
    },
  };

  const context: StrategyContext = {
    symbol: "MNQ",
    bar: currentBar,
    history: bars,
    sessionHistory: sessionBars,
    config,
    dailyTradeCount: 0,
    macroContext: preTrade?.macroContext || undefined,
    macro: {
      hmmRegime: dom?.regime || undefined,
    },
  };

  // 5. Inside-day gate — suppress breakouts when range compression detected
  const insideDayProb = insideDay?.probability || 0;
  if (insideDayProb > 0.6) {
    await log(`Inside-day: ${(insideDayProb * 100).toFixed(0)}% — breakout suppression active`);
  }

  // 6. Run ALL GOLD/SILVER strategies via ensemble
  const ensemble = buildDefaultEnsemble();
  let bestSignal: StrategySignal | null = null;
  try {
    bestSignal = ensemble.generateSignal(context);
  } catch (e: any) {
    await log(`Ensemble error: ${e.message?.slice(0, 100)}`);
  }

  if (!bestSignal) {
    await log(`No signal from any strategy. Inside-day: ${(insideDayProb * 100).toFixed(0)}%`);
    return;
  }

  // 7. Log what triggered
  await log(
    `Signal: ${bestSignal.strategyId} | ${bestSignal.side.toUpperCase()} ${bestSignal.symbol}` +
    ` | Entry: ${bestSignal.entry} | SL: ${bestSignal.stop} | TP: ${bestSignal.target}` +
    ` | R/R: ${bestSignal.rr.toFixed(2)} | Confidence: ${(bestSignal.confidence * 100).toFixed(0)}%`
  );

  // 8. Inside-day suppression override check
  if (insideDayProb > 0.6 && bestSignal.confidence < 0.8) {
    await log(`Suppressed by inside-day (${(insideDayProb * 100).toFixed(0)}%) — confidence ${(bestSignal.confidence * 100).toFixed(0)}% too low`);
    return;
  }

  // 9. Pre-trade decision override
  if (preTrade?.decision === "NO_TRADE") {
    await log(`Pre-trade says NO_TRADE — respecting`);
    return;
  }
  if (preTrade?.decision === "REDUCED" && bestSignal.contracts > (preTrade.contracts || 1)) {
    bestSignal.contracts = preTrade.contracts || 1;
    await log(`Pre-trade: REDUCED mode — sizing to ${bestSignal.contracts} contracts`);
  }

  // 10. Route to all accounts
  const orbSig = signalToOrbSignal(bestSignal);
  await signalRouter.route(orbSig);

  // Track position
  currentPosition = {
    symbol: bestSignal.symbol,
    side: bestSignal.side === "long" ? "buy" : "sell",
    quantity: bestSignal.contracts,
    entryPrice: bestSignal.entry,
    strategyId: bestSignal.strategyId,
    entryTs: new Date().toISOString(),
    sl: bestSignal.stop,
    tp: bestSignal.target,
  };

  await log(`Position opened: ${currentPosition.side} ${currentPosition.quantity} ${currentPosition.symbol} @ ${currentPosition.entryPrice}`);
}

// ── Main loop ──

async function main() {
  await mkdir(LOG_DIR, { recursive: true });
  await log("═".repeat(60));
  await log("STRATEGY ENGINE RUNNER STARTED");
  await log(`NY session: 09:30-16:00 ET | Bar: ${BAR_INTERVAL_S}s | Check interval: ${INTERVAL_MS / 1000}s`);
  await log(`Enabled strategies: ${process.env.RH_ENABLED_STRATEGIES || "ALL GOLD/SILVER"}`);
  await log("═".repeat(60));

  while (true) {
    try {
      await runCycle();
    } catch (e: any) {
      await log(`Cycle error: ${e.message?.slice(0, 200)}`);
    }
    await new Promise((r) => setTimeout(r, INTERVAL_MS));
  }
}

main().catch((e) => console.error("Fatal:", e));
