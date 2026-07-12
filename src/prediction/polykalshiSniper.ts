#!/usr/bin/env tsx
// polykalshiSniper.ts — Polykalshi-style oracle sniping monitor for Polymarket.
//
// Ported from 0xPr0f/polykalshi-bot/src/strategies/oracle_snipe.rs
//
// Concept: Polymarket crypto UP/DOWN markets resolve based on Chainlink BTC/USD
// (which tracks Binance BTC price). Near close, the orderbook lags behind the
// real price. If direction is clear (close > open = Up), buy the underpriced side.
//
// Uses tiered thresholds that become more aggressive as market close approaches:
//   - Tier 1 (60s-20s): require >= 0.2% price move, limit orders
//   - Tier 2 (20s-10s): require >= 0.1% price move, limit orders
//   - Tier 3 (10s-0s):  require >= 0.05% price move, IOC orders
//
// Market discovery: deterministic slugs {asset}-updown-{interval}-{window_ts}
//   Supports: 5-min (300s), 15-min (900s), 4-hr (14400s) windows.
//
// Run: npx tsx src/prediction/polykalshiSniper.ts

import { mkdir, appendFile, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import {
  type OracleSnipeConfig,
  type SnipeAsset,
  type SnipeInterval,
  type SnipeMarket,
  type TickerSnapshot,
  type SnipeSignal,
  type SnipeResolution,
  DEFAULT_SNIPE_CONFIG,
  SNIPE_ASSETS,
  SNIPE_INTERVALS,
  intervalSeconds,
  binanceSymbol,
} from "./oracleSnipeTypes.js";

// ── Constants ─────────────────────────────────────────────────

const GAMMA_API = "https://gamma-api.polymarket.com";
const SIGNALS_PATH = join(process.cwd(), ".rumbling-hedge/journal/polykalshi-signals.jsonl");
const STATE_PATH = join(process.cwd(), ".rumbling-hedge/state/polykalshi-sniper.json");
const RESOLUTIONS_PATH = join(process.cwd(), ".rumbling-hedge/journal/polykalshi-resolutions.jsonl");

// How often to refresh market metadata (seconds)
const MARKET_REFRESH_INTERVAL = 120;
// How often to poll when far from any close (seconds)
const IDLE_POLL_INTERVAL = 30;
// How often to poll when near close (seconds)
const ACTIVE_POLL_INTERVAL = 2;
// Max signals per asset/interval/window side
const MAX_SIGNALS_PER_WINDOW_SIDE = 1;

// ── Types ──────────────────────────────────────────────────────

interface SniperState {
  totalSignals: number;
  lastRefreshTs: number;
  nextCloseTs: number;
}

interface GammaMarket {
  id: string;
  question: string;
  conditionId: string;
  outcomes: string | string[];
  outcomePrices: string | number[];
  clobTokenIds: string | string[];
  endDate: string;
}

interface GammaEvent {
  id: string;
  slug: string;
  title: string;
  endDate: string;
  restricted: boolean;
  markets?: GammaMarket[];
}

interface BinanceKline {
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

// ── Helpers ────────────────────────────────────────────────────

function parseJsonArray<T>(raw: string | T[] | undefined): T[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function slugForWindow(asset: SnipeAsset, interval: SnipeInterval, windowTs: number): string {
  return `${asset}-updown-${interval}-${windowTs}`;
}

function currentWindowTs(interval: SnipeInterval): number {
  const secs = intervalSeconds(interval);
  const now = nowSeconds();
  return now - (now % secs);
}

// ── Gamma: Fetch Market by Slug ────────────────────────────────
//
// Polymarket creates deterministic slugs for crypto up/down markets:
//   {asset}-updown-{interval}-{window_ts}
// Example: btc-updown-15m-1782341100
//
// We use the Gamma events endpoint with the exact slug.
// This is far more reliable than tag/search-based discovery.

async function fetchMarketBySlug(
  asset: SnipeAsset,
  interval: SnipeInterval,
  windowTs: number,
): Promise<SnipeMarket | null> {
  const slug = slugForWindow(asset, interval, windowTs);
  try {
    const url = new URL(`${GAMMA_API}/events`);
    url.searchParams.set("slug", slug);
    const resp = await fetch(url, {
      headers: { accept: "application/json", "user-agent": "rumbling-hedge/0.1" },
      signal: AbortSignal.timeout(8000),
    });
    if (!resp.ok) return null;
    const events = (await resp.json()) as GammaEvent[];
    if (!events || events.length === 0) return null;

    const event = events[0]!;
    const firstMarket = event.markets?.[0];
    if (!firstMarket || !firstMarket.conditionId) return null;

    const outcomes = parseJsonArray<string>(firstMarket.outcomes);
    const prices = parseJsonArray<number | string>(firstMarket.outcomePrices).map(Number);
    const clobTokenIds = parseJsonArray<string>(firstMarket.clobTokenIds);

    if (outcomes.length < 2 || clobTokenIds.length < 2) return null;

    // Parse close time from endDate
    let closesAt = 0;
    if (event.endDate) {
      const parsed = Date.parse(event.endDate);
      if (!isNaN(parsed)) closesAt = Math.floor(parsed / 1000);
    }
    if (!closesAt) {
      closesAt = windowTs + intervalSeconds(interval);
    }

    // Map Up/Down to token IDs
    let tokenIdUp = clobTokenIds[0]!;
    let tokenIdDown = clobTokenIds[1]!;
    let upPrice = 0.50;
    let downPrice = 0.50;

    for (let i = 0; i < Math.min(outcomes.length, prices.length, clobTokenIds.length); i++) {
      const o = (outcomes[i] ?? "").toLowerCase();
      if (o === "up") {
        tokenIdUp = clobTokenIds[i]!;
        upPrice = Math.max(0.01, Math.min(0.99, Number.isFinite(prices[i]) ? prices[i]! : 0.50));
      } else if (o === "down") {
        tokenIdDown = clobTokenIds[i]!;
        downPrice = Math.max(0.01, Math.min(0.99, Number.isFinite(prices[i]) ? prices[i]! : 0.50));
      }
    }

    return {
      eventTitle: event.title ?? "unknown",
      marketQuestion: firstMarket.question ?? "unknown",
      conditionId: firstMarket.conditionId,
      tokenIdUp,
      tokenIdDown,
      upPrice,
      downPrice,
      closesAt,
      asset,
      interval,
    };
  } catch {
    return null;
  }
}

/**
 * Discover all active markets for the given assets and intervals.
 * Uses deterministic slug patterns to look up the current and next window.
 */
async function discoverAllMarkets(
  assets: SnipeAsset[],
  intervals: SnipeInterval[],
): Promise<SnipeMarket[]> {
  const results: SnipeMarket[] = [];
  const seen = new Set<string>();

  for (const asset of assets) {
    for (const interval of intervals) {
      // Check current window and next window (some markets may be created slightly ahead)
      const now = nowSeconds();
      const current = currentWindowTs(interval);
      const stride = intervalSeconds(interval);

      for (const windowTs of [current, current + stride]) {
        // Skip if window is in the future (market might not exist yet)
        if (windowTs > now + 60) continue;

        const market = await fetchMarketBySlug(asset, interval, windowTs);
        if (!market) continue;

        const key = `${asset}:${interval}:${market.conditionId}`;
        if (seen.has(key)) continue;
        seen.add(key);
        results.push(market);
      }
    }
  }

  return results;
}

// ── Binance: Price Feeds ───────────────────────────────────────

async function fetchBinancePrice(symbol: string): Promise<number | null> {
  try {
    const url = `https://api.binance.com/api/v3/ticker/price?symbol=${encodeURIComponent(symbol)}`;
    const resp = await fetch(url, {
      signal: AbortSignal.timeout(3000),
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as { price: string };
    const price = Number(data.price);
    return Number.isFinite(price) ? price : null;
  } catch {
    return null;
  }
}

async function fetchBinanceKline(
  symbol: string,
  interval: string,
): Promise<BinanceKline | null> {
  try {
    const url =
      `https://api.binance.com/api/v3/klines?symbol=${encodeURIComponent(symbol)}` +
      `&interval=${encodeURIComponent(interval)}&limit=1`;
    const resp = await fetch(url, {
      signal: AbortSignal.timeout(3000),
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as Array<[number, string, string, string, string, string]>;
    if (!data || data.length === 0) return null;
    const k = data[0]!;
    return { open: k[1]!, high: k[2]!, low: k[3]!, close: k[4]!, volume: k[5]! };
  } catch {
    return null;
  }
}

async function buildTicker(
  asset: SnipeAsset,
  interval: SnipeInterval,
): Promise<TickerSnapshot | null> {
  const symbol = binanceSymbol(asset);
  const klineInterval = interval; // Binance uses same notation: 5m, 15m, 1h

  const [price, kline] = await Promise.all([
    fetchBinancePrice(symbol),
    fetchBinanceKline(symbol, klineInterval),
  ]);

  if (!price || !kline) return null;

  const open = Number(kline.open);
  const close = Number(kline.close);

  if (!Number.isFinite(open) || !Number.isFinite(close)) return null;

  const priceChangePct = open > 0 ? ((price - open) / open) * 100 : 0;

  // Simple confidence: how far price has moved relative to a baseline vol estimate
  // BTC: ~0.12% per 5-min, ~0.208% per 15-min, ~0.33% per 1h
  const baselineVol = interval === "5m" ? 0.12 : interval === "15m" ? 0.208 : 0.33;
  const confidence = Math.min(1.0, Math.abs(priceChangePct) / baselineVol);

  const predictedOutcome = close >= open ? "Up" : "Down";

  return {
    price,
    klineOpen: open,
    klineClose: close,
    priceChangePct,
    predictedOutcome,
    confidence,
  };
}

// ── Core Evaluation ────────────────────────────────────────────

function calcFee(price: number, sizeUsd: number, feeRate: number): number {
  return price * sizeUsd * feeRate;
}

/**
 * Evaluate a single market with the polykalshi tiered threshold logic.
 */
function evaluateMarket(
  market: SnipeMarket,
  ticker: TickerSnapshot,
  config: OracleSnipeConfig,
): SnipeSignal {
  const now = nowSeconds();
  const secsToClose = Math.max(0, market.closesAt - now);

  // Determine time tier — aggressive thresholds as close approaches
  const tierDefs: Array<{ min: number; max: number; tier: 1 | 2 | 3; ioc: boolean; threshold: number }> = [
    { min: config.tier2Seconds, max: config.tier1Seconds, tier: 1, ioc: false, threshold: config.tier1ThresholdPct },
    { min: config.tier3Seconds, max: config.tier2Seconds, tier: 2, ioc: false, threshold: config.tier2ThresholdPct },
    { min: 0, max: config.tier3Seconds, tier: 3, ioc: true, threshold: config.tier3ThresholdPct },
  ];

  const activeTier = tierDefs.find((t) => secsToClose > t.min && secsToClose <= t.max);
  if (!activeTier) {
    return {
      ts: now, asset: market.asset, interval: market.interval,
      market, ticker, timeTier: 1, useIoc: false, threshold: 0,
      priceChangePct: ticker.priceChangePct, predictedOutcome: ticker.predictedOutcome,
      targetPrice: 0, fee: 0, totalCost: 0, netProfit: 0, isProfitable: false,
      passed: false, reason: `NOT_IN_WINDOW(${secsToClose}s>${config.tier1Seconds}s)`,
    };
  }

  const { tier, ioc, threshold } = activeTier;

  // Gate: price change threshold
  const absChange = Math.abs(ticker.priceChangePct);
  if (absChange < threshold) {
    return {
      ts: now, asset: market.asset, interval: market.interval,
      market, ticker, timeTier: tier, useIoc: ioc, threshold,
      priceChangePct: ticker.priceChangePct, predictedOutcome: ticker.predictedOutcome,
      targetPrice: 0, fee: 0, totalCost: 0, netProfit: 0, isProfitable: false,
      passed: false,
      reason: `LOW_DELTA_T${tier}(${absChange.toFixed(3)}%<${threshold.toFixed(2)}%)`,
    };
  }

  // Determine which token to buy
  const targetPrice = ticker.predictedOutcome === "Up" ? market.upPrice : market.downPrice;
  const fee = calcFee(targetPrice, config.maxPositionSize, config.feeRate);
  const totalCost = targetPrice * config.maxPositionSize + fee;
  const payout = config.maxPositionSize;
  const netProfit = payout - totalCost;
  const isProfitable = netProfit > 0;

  if (!isProfitable) {
    const entryCents = targetPrice * 100;
    const feeCents = (fee / config.maxPositionSize) * 100;
    return {
      ts: now, asset: market.asset, interval: market.interval,
      market, ticker, timeTier: tier, useIoc: ioc, threshold,
      priceChangePct: ticker.priceChangePct, predictedOutcome: ticker.predictedOutcome,
      targetPrice, fee, totalCost, netProfit, isProfitable,
      passed: false,
      reason: `NO_PROFIT(cost=${entryCents.toFixed(2)}¢+fee=${feeCents.toFixed(2)}¢>100¢)`,
    };
  }

  // PASSED all gates
  const profitCents = (netProfit / config.maxPositionSize) * 100;
  return {
    ts: now, asset: market.asset, interval: market.interval,
    market, ticker, timeTier: tier, useIoc: ioc, threshold,
    priceChangePct: ticker.priceChangePct, predictedOutcome: ticker.predictedOutcome,
    targetPrice, fee, totalCost, netProfit, isProfitable,
    passed: true,
    reason: `SNIPE_T${tier}${ioc ? "_IOC" : ""}(${ticker.priceChangePct >= 0 ? "+" : ""}${ticker.priceChangePct.toFixed(3)}%,profit=${profitCents.toFixed(2)}¢)`,
  };
}

// ── Logging ────────────────────────────────────────────────────

async function logSignal(signal: SnipeSignal): Promise<void> {
  const line = JSON.stringify({
    ts: signal.ts,
    asset: signal.asset,
    interval: signal.interval,
    conditionId: signal.market.conditionId,
    tokenIdUp: signal.market.tokenIdUp,
    tokenIdDown: signal.market.tokenIdDown,
    predictedOutcome: signal.predictedOutcome,
    timeTier: signal.timeTier,
    useIoc: signal.useIoc,
    threshold: signal.threshold,
    priceChangePct: signal.priceChangePct,
    targetPrice: signal.targetPrice,
    netProfit: signal.netProfit,
    passed: signal.passed,
    reason: signal.reason,
    upPrice: signal.market.upPrice,
    downPrice: signal.market.downPrice,
    binancePrice: signal.ticker.price,
    klineOpen: signal.ticker.klineOpen,
    klineClose: signal.ticker.klineClose,
  }) + "\n";

  try {
    await appendFile(SIGNALS_PATH, line);
  } catch {
    await mkdir(join(process.cwd(), ".rumbling-hedge/journal"), { recursive: true });
    await appendFile(SIGNALS_PATH, line);
  }
}

async function logResolution(res: SnipeResolution): Promise<void> {
  const line = JSON.stringify(res) + "\n";
  try {
    await appendFile(RESOLUTIONS_PATH, line);
  } catch {
    await mkdir(join(process.cwd(), ".rumbling-hedge/journal"), { recursive: true });
    await appendFile(RESOLUTIONS_PATH, line);
  }
}

async function checkResolutions(): Promise<void> {
  try {
    const raw = await readFile(RESOLUTIONS_PATH, "utf8");
    const lines = raw.trim().split("\n").filter(Boolean);
    if (lines.length === 0) return;

    const updated: string[] = [];
    for (const line of lines) {
      const res = JSON.parse(line) as SnipeResolution;
      if (res.actualOutcome !== null) {
        updated.push(line);
        continue;
      }
      if (nowSeconds() < res.closesAt + 5) {
        updated.push(line);
        continue;
      }

      const symbol = binanceSymbol(res.asset);
      const kline = await fetchBinanceKline(symbol, res.interval);
      if (!kline) { updated.push(line); continue; }

      const close = Number(kline.close);
      const open = Number(kline.open);
      if (!Number.isFinite(close) || !Number.isFinite(open)) { updated.push(line); continue; }

      const actualOutcome: "Up" | "Down" = close >= open ? "Up" : "Down";
      const won = actualOutcome === res.prediction;
      const entryCents = res.entryPrice * 100;
      const actualPnlCents = won ? 100 - entryCents - res.feeCents : -(entryCents + res.feeCents);

      const resolved: SnipeResolution = { ...res, actualOutcome, won, actualPnlCents: Math.round(actualPnlCents * 100) / 100 };
      updated.push(JSON.stringify(resolved));
      console.log(`[mock-resolution] ${won ? "WON" : "LOST"} ${res.conditionId}: predicted=${res.prediction} actual=${actualOutcome} PnL=${actualPnlCents.toFixed(2)}¢`);
    }

    await writeFile(RESOLUTIONS_PATH, updated.join("\n") + "\n");
  } catch {
    // File may not exist yet
  }
}

// ── State Persistence ──────────────────────────────────────────

async function loadState(): Promise<SniperState> {
  try {
    const raw = await readFile(STATE_PATH, "utf8");
    return JSON.parse(raw) as SniperState;
  } catch {
    return { totalSignals: 0, lastRefreshTs: 0, nextCloseTs: 0 };
  }
}

async function saveState(state: SniperState): Promise<void> {
  await mkdir(join(process.cwd(), ".rumbling-hedge/state"), { recursive: true });
  await writeFile(STATE_PATH, JSON.stringify(state, null, 2));
}

// ── Main Loop ──────────────────────────────────────────────────

async function run() {
  await mkdir(join(process.cwd(), ".rumbling-hedge/journal"), { recursive: true });
  await mkdir(join(process.cwd(), ".rumbling-hedge/state"), { recursive: true });

  const config: OracleSnipeConfig = {
    ...DEFAULT_SNIPE_CONFIG,
    ...(process.env.BILL_SNIPE_SECONDS_BEFORE_CLOSE
      ? { secondsBeforeClose: Number(process.env.BILL_SNIPE_SECONDS_BEFORE_CLOSE) } : {}),
    ...(process.env.BILL_SNIPE_MIN_CONFIDENCE
      ? { minConfidence: Number(process.env.BILL_SNIPE_MIN_CONFIDENCE) } : {}),
    ...(process.env.BILL_SNIPE_MAX_POSITION
      ? { maxPositionSize: Number(process.env.BILL_SNIPE_MAX_POSITION) } : {}),
  };

  let state = await loadState();
  // Track active markets: {asset:interval:windowTs → SnipeMarket}
  const activeMarkets = new Map<string, SnipeMarket>();
  // Track which window-side combos we've already signaled
  const signaledWindows = new Set<string>();

  console.log("[polykalshi-sniper] Starting oracle sniping monitor...");
  console.log(`[polykalshi-sniper] Assets: ${SNIPE_ASSETS.join(", ")}`);
  console.log(`[polykalshi-sniper] Intervals: ${SNIPE_INTERVALS.join(", ")}`);
  console.log(`[polykalshi-sniper] Tier thresholds: ${config.tier1ThresholdPct}% / ${config.tier2ThresholdPct}% / ${config.tier3ThresholdPct}%`);
  console.log(`[polykalshi-sniper] Total lifetime signals: ${state.totalSignals}`);

  let loopCount = 0;

  while (true) {
    try {
      const now = nowSeconds();
      const secsToAnyClose = Math.max(0, state.nextCloseTs - now);
      const isNearClose = secsToAnyClose <= config.secondsBeforeClose;
      const pollMs = isNearClose ? ACTIVE_POLL_INTERVAL * 1000 : IDLE_POLL_INTERVAL * 1000;

      // ── Market Discovery (periodic refresh) ──
      if (state.lastRefreshTs === 0 || now - state.lastRefreshTs > MARKET_REFRESH_INTERVAL) {
        const discovered = await discoverAllMarkets([...SNIPE_ASSETS], [...SNIPE_INTERVALS]);

        activeMarkets.clear();
        for (const m of discovered) {
          const key = `${m.asset}:${m.interval}:${currentWindowTs(m.interval)}`;
          activeMarkets.set(key, m);
        }

        state.nextCloseTs = Math.min(
          ...discovered.filter(m => m.closesAt > now).map(m => m.closesAt),
          Infinity,
        );
        if (!Number.isFinite(state.nextCloseTs)) state.nextCloseTs = 0;
        state.lastRefreshTs = now;

        console.log(`[polykalshi-sniper] Discovered ${activeMarkets.size} active markets, next close in ${Math.max(0, state.nextCloseTs - now)}s`);
        await saveState(state);
      }

      // ── Periodic status ──
      if (loopCount % 20 === 0) {
        console.log(`[polykalshi-sniper] ${activeMarkets.size} active markets, next close in ${secsToAnyClose}s, poll=${isNearClose ? `${ACTIVE_POLL_INTERVAL}s active` : `${IDLE_POLL_INTERVAL}s idle`}`);
      }

      // ── Clean stale signaled windows ──
      for (const key of signaledWindows) {
        const parts = key.split(":");
        if (parts.length >= 4) {
          const winTs = Number(parts[3]);
          if (now > winTs + intervalSeconds(parts[1] as SnipeInterval)) {
            signaledWindows.delete(key);
          }
        }
      }

      // ── Skip if not near any close ──
      if (!isNearClose) {
        await new Promise((r) => setTimeout(r, pollMs));
        loopCount++;
        continue;
      }

      // ── Check mock resolutions ──
      if (loopCount % 5 === 0) await checkResolutions();

      // ── Process markets near close ──
      const targets: SnipeMarket[] = [];
      for (const market of activeMarkets.values()) {
        if (market.closesAt > now && market.closesAt - now <= config.secondsBeforeClose) {
          targets.push(market);
        }
      }

      if (targets.length === 0) {
        await new Promise((r) => setTimeout(r, pollMs));
        loopCount++;
        continue;
      }

      if (loopCount % 10 === 0) console.log(`[polykalshi-sniper] ${targets.length} markets in snipe window`);

      await Promise.all(
        targets.map(async (market) => {
          const ticker = await buildTicker(market.asset, market.interval);
          if (!ticker || ticker.confidence < config.minConfidence) return;

          const signal = evaluateMarket(market, ticker, config);
          await logSignal(signal);

          if (!signal.passed) return;

          // Deduplicate: one signal per window-side
          const signalKey = `${market.asset}:${market.interval}:${currentWindowTs(market.interval)}:${ticker.predictedOutcome}`;
          if (signaledWindows.has(signalKey)) return;
          signaledWindows.add(signalKey);

          state.totalSignals++;
          console.log(
            `[${market.asset}:${market.interval}] ${signal.reason} ` +
            `| side=${ticker.predictedOutcome} price=${signal.targetPrice.toFixed(3)} ` +
            `binance=${ticker.price.toFixed(0)} change=${ticker.priceChangePct >= 0 ? "+" : ""}${ticker.priceChangePct.toFixed(3)}%`,
          );

          // Spawn mock resolution
          await logResolution({
            conditionId: signal.market.conditionId,
            asset: signal.asset,
            interval: signal.interval,
            closesAt: signal.market.closesAt,
            prediction: signal.predictedOutcome,
            entryPrice: signal.targetPrice,
            feeCents: (signal.fee / signal.market.upPrice) * 100,
            foundAt: signal.ts,
            actualOutcome: null,
            won: null,
            actualPnlCents: null,
          });

          await saveState(state);
        }),
      );

      loopCount++;
      await new Promise((r) => setTimeout(r, pollMs));
    } catch (err) {
      console.error(`[polykalshi-sniper] Error: ${err instanceof Error ? err.message : String(err)}`);
      await new Promise((r) => setTimeout(r, 5000));
    }
  }
}

export { discoverAllMarkets, buildTicker, fetchBinancePrice, fetchBinanceKline, evaluateMarket };

// Only run as main entry point, not when imported
const isMainModule = process.argv[1]?.endsWith("polykalshiSniper.ts") || process.argv[1]?.endsWith("polykalshiSniper.js");
if (isMainModule) {
  run().catch((err) => {
    console.error("[polykalshi-sniper] Fatal:", err);
    process.exit(1);
  });
}
