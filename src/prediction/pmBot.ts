// pmBot.ts — Unified PM trading bot.
//
// Reads edges from edge intake, filters by capital-preservation rules,
// verifies markets on Gamma, checks CLOB books, and executes via ClobClient
// with a viem WalletClient signer.
//
// Capital preservation:
//   - 1% max per trade by default
//   - Bill prediction bankroll from env
//   - Stop if bankroll falls below the configured floor
//   - Track cumulative PnL
//
// Pre-trade checks:
//   - Edge > 5%
//   - Liquidity (top-of-book depth) > $500
//   - Spread < 2%
//
// Edge sources: prediction-edge-intake.latest.json (paper-watch edges only)
// Credentials: .rumbling-hedge/credentials/polymarket.json (bot_wallet_address, bot_private_key, api_key, api_secret, api_passphrase)
// Fills log: .rumbling-hedge/runtime/prediction/fills.jsonl

import { readFile, mkdir, appendFile } from "node:fs/promises";
import { resolve, dirname, join } from "node:path";
import { type PredictionDiscoveredEdge, type PredictionEdgeIntakeReport } from "./edgeIntake.js";
import { fetchPolymarketBook, quoteFromBook } from "./polymarketBook.js";

// ── viem imports ──────────────────────────────────────────────
import {
  createWalletClient,
  http,
  type WalletClient,
  type Account,
  type Chain,
  type Transport,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { polygon } from "viem/chains";

// ── ClobClient (dynamic import — ESM module) ─────────────────
let ClobClientClass: any = null;
let Side: any = null;
let OrderType: any = null;

async function loadClobClient(): Promise<boolean> {
  if (ClobClientClass) return true;
  try {
    const mod = await import("@polymarket/clob-client-v2");
    ClobClientClass = mod.ClobClient;
    Side = mod.Side;
    OrderType = mod.OrderType;
    return true;
  } catch {
    return false;
  }
}

// ── Types ─────────────────────────────────────────────────────

export interface PmBotConfig {
  /** When true, simulate everything but don't submit real orders. */
  dryRun: boolean;
  /** Maximum notional per trade in USD. */
  maxPerTradeUsd: number;
  /** Total bankroll in USD. */
  bankrollUsd: number;
  /** Stop-loss bankroll floor in USD — bot halts if cumulative PnL drops below this. */
  stopFloorUsd: number;
  /** Minimum net edge percentage to qualify a trade. */
  minEdgePct: number;
  /** Minimum top-of-book depth (bid + ask size) in USD to qualify. */
  minLiquidityUsd: number;
  /** Maximum bid-ask spread percentage to qualify. */
  maxSpreadPct: number;
  /** Path to edge intake report. */
  edgeIntakePath: string;
  /** Path to Polymarket credentials JSON. */
  credentialsPath: string;
  /** Path to fills journal (JSONL). */
  fillsPath: string;
  /** CLOB host. */
  clobHost: string;
  /** Chain ID (137 = Polygon). */
  chainId: number;
  /** Gamma API base URL. */
  gammaApiUrl: string;
}

export const DEFAULT_CONFIG: PmBotConfig = {
  dryRun: true,
  maxPerTradeUsd: 1,
  bankrollUsd: 100,
  stopFloorUsd: 50,
  minEdgePct: 5,
  minLiquidityUsd: 500,
  maxSpreadPct: 2,
  edgeIntakePath: resolve(
    process.env.BILL_POLYMARKET_EDGE_INTAKE_PATH ??
    ".rumbling-hedge/state/prediction-edge-intake.latest.json"
  ),
  credentialsPath: resolve(".rumbling-hedge/credentials/polymarket.json"),
  fillsPath: resolve(".rumbling-hedge/runtime/prediction/fills.jsonl"),
  clobHost: "https://clob.polymarket.com",
  chainId: 137,
  gammaApiUrl: "https://gamma-api.polymarket.com",
};

function readNumberEnv(key: string, fallback: number): number {
  const raw = process.env[key];
  if (!raw) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function buildPmBotConfigFromEnv(): Partial<PmBotConfig> {
  const bankrollUsd = readNumberEnv("BILL_PREDICTION_BANKROLL", DEFAULT_CONFIG.bankrollUsd);
  const maxPerTradeUsd = readNumberEnv(
    "BILL_PM_MAX_PER_TRADE_USD",
    Math.max(0.01, Number((bankrollUsd * 0.01).toFixed(2)))
  );
  return {
    bankrollUsd,
    maxPerTradeUsd,
    stopFloorUsd: readNumberEnv("BILL_PM_STOP_FLOOR_USD", bankrollUsd * 0.5),
    minEdgePct: readNumberEnv("BILL_PM_MIN_IMPLIED_EDGE_PCT", DEFAULT_CONFIG.minEdgePct),
    minLiquidityUsd: readNumberEnv("BILL_PM_MIN_LIQUIDITY_USD", DEFAULT_CONFIG.minLiquidityUsd),
    maxSpreadPct: readNumberEnv("BILL_PM_MAX_SPREAD_PCT", DEFAULT_CONFIG.maxSpreadPct)
  };
}

export interface PmCredentials {
  bot_wallet_address: string;
  bot_private_key: string;
  api_key: string;
  api_secret: string;
  api_passphrase: string;
  wallet_address?: string;
  private_key?: string;
  builder_address?: string;
  relayer_api_key?: string;
  relayer_address?: string;
}

export interface GammaMarket {
  id?: string;
  question?: string;
  description?: string;
  outcomes?: string[] | string;
  outcomePrices?: number[] | string;
  clobTokenIds?: string[] | string;
  active?: boolean;
  closed?: boolean;
  endDate?: string;
  liquidity?: number | string;
  volume24hr?: number | string;
}

export interface GammaEvent {
  id?: string;
  title?: string;
  slug?: string;
  endDate?: string;
  markets?: GammaMarket[];
}

export interface ResolvedEdge {
  edge: PredictionDiscoveredEdge;
  /** Whether the Gamma lookup succeeded and market is active. */
  gammaOk: boolean;
  /** Raw Gamma event data. */
  gammaEvent?: GammaEvent;
  /** Raw Gamma market data. */
  gammaMarket?: GammaMarket;
  /** CLOB token ID for the Yes/No outcome we need to trade. */
  clobTokenId?: string;
  /** Live best bid from CLOB book. */
  bestBid?: number;
  /** Live best ask from CLOB book. */
  bestAsk?: number;
  /** Live spread percentage. */
  spreadPct?: number;
  /** Live top-of-book depth in USD. */
  topBookDepth?: number;
  /** Calculated net edge percentage (from live prices). */
  liveEdgePct?: number;
  /** Pre-trade check verdicts. */
  checks: PmBotCheck[];
  /** Whether the edge passed all pre-trade checks. */
  ready: boolean;
}

export interface PmBotCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface PmFillRecord {
  ts: string;
  edgeId: string;
  marketSlug: string;
  clobTokenId: string;
  side: "BUY" | "SELL";
  price: number;
  amountUsd: number;
  shares: number;
  orderId: string;
  status: "FILLED" | "DRY_RUN" | "REJECTED" | "FAILED";
  dryRun: boolean;
  bankrollBefore: number;
  bankrollAfter: number;
  cumulativePnl: number;
  error?: string;
}

export interface PmBotReport {
  command: "pm-bot";
  generatedAt: string;
  dryRun: boolean;
  bankrollStart: number;
  bankrollEnd: number;
  cumulativePnl: number;
  edgesLoaded: number;
  paperWatchEdges: number;
  edgesResolved: number;
  edgesReady: number;
  fillsAttempted: number;
  fillsSucceeded: number;
  fills: PmFillRecord[];
  halted: boolean;
  haltReason?: string;
  errors: string[];
}

// ── Helpers ───────────────────────────────────────────────────

function parseJsonArray<T = unknown>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? (parsed as T[]) : [];
    } catch {
      return [];
    }
  }
  return [];
}

function toNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

async function readJsonFile<T>(path: string): Promise<T | null> {
  try {
    const raw = await readFile(path, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function resolveCwd(p: string): string {
  return resolve(p);
}

// ── Edge Loading ──────────────────────────────────────────────

async function loadEdges(config: PmBotConfig): Promise<{
  report: PredictionEdgeIntakeReport | null;
  edges: PredictionDiscoveredEdge[];
  error?: string;
}> {
  const path = resolveCwd(config.edgeIntakePath);
  const report = await readJsonFile<PredictionEdgeIntakeReport>(path);
  if (!report) {
    return { report: null, edges: [], error: `Edge intake not found at ${path}` };
  }
  const edges = (report.topEdges ?? []).filter((e) => e.verdict === "paper-watch");
  return { report, edges };
}

// ── Gamma Lookup ──────────────────────────────────────────────

async function fetchGammaEvent(slug: string, config: PmBotConfig): Promise<GammaEvent | null> {
  const url = new URL(`${config.gammaApiUrl}/events`);
  url.searchParams.set("slug", slug);
  try {
    const resp = await fetch(url, {
      headers: {
        accept: "application/json",
        "user-agent": "rumbling-hedge-pmbot/0.1",
      },
      signal: AbortSignal.timeout(10_000),
    });
    if (!resp.ok) return null;
    const events = (await resp.json()) as GammaEvent[];
    return events.length > 0 ? events[0]! : null;
  } catch {
    return null;
  }
}

function resolveClobTokenId(market: GammaMarket, direction: string): string | undefined {
  const outcomes = parseJsonArray<string>(market.outcomes);
  const tokenIds = parseJsonArray<string>(market.clobTokenIds);

  // If there's exactly one token and one outcome, use it
  if (tokenIds.length === 1 && outcomes.length <= 1) return tokenIds[0];

  // Match by outcome label (case-insensitive)
  const dir = direction.toLowerCase();
  for (let i = 0; i < Math.min(outcomes.length, tokenIds.length); i++) {
    const outcome = (outcomes[i] ?? "").toLowerCase();
    // For "buy No" direction on near-certainty edges, we want the "No" token
    if (outcome === dir || (dir === "no" && outcome === "no")) {
      return tokenIds[i];
    }
    // For "buy Yes" direction
    if (outcome === "yes" && dir === "yes") {
      return tokenIds[i];
    }
  }

  // Fallback: return first token
  return tokenIds[0];
}

function parseEdgeDirection(edge: PredictionDiscoveredEdge): "yes" | "no" {
  const d = edge.direction.toLowerCase();
  if (d.includes("no") || d.includes("short") || d.includes("sell")) return "no";
  return "yes";
}

function parseEdgeMagnitude(edge: PredictionDiscoveredEdge): number | null {
  if (edge.edgeMagnitude === null || edge.edgeMagnitude === undefined) return null;
  const raw = String(edge.edgeMagnitude).replace(/%/g, "").trim();
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

// ── Edge Resolution ───────────────────────────────────────────

async function resolveEdge(
  edge: PredictionDiscoveredEdge,
  config: PmBotConfig,
): Promise<ResolvedEdge> {
  const checks: PmBotCheck[] = [];
  const result: ResolvedEdge = {
    edge,
    gammaOk: false,
    checks,
    ready: false,
  };

  // Determine side early — used for token resolution and edge calc
  const direction = parseEdgeDirection(edge);

  // Resolve each market slug — use the first one with a valid result
  for (const slug of edge.marketSlugs) {
    const event = await fetchGammaEvent(slug, config);
    if (!event) {
      checks.push({ name: "gamma-lookup", passed: false, detail: `Slug not found: ${slug}` });
      continue;
    }

    const markets = event.markets ?? [];
    if (markets.length === 0) {
      checks.push({ name: "gamma-markets", passed: false, detail: `No markets in event: ${slug}` });
      continue;
    }

    const market = markets[0]!;
    const closed = market.closed === true || (typeof market.closed === "string" && market.closed === "true");
    if (closed) {
      checks.push({ name: "gamma-active", passed: false, detail: `Market closed: ${slug}` });
      continue;
    }

    const tokenId = resolveClobTokenId(market, direction);
    if (!tokenId) {
      checks.push({ name: "gamma-clob-token", passed: false, detail: `No CLOB token ID for ${direction}: ${slug}` });
      continue;
    }

    result.gammaOk = true;
    result.gammaEvent = event;
    result.gammaMarket = market;
    result.clobTokenId = tokenId;
    checks.push({ name: "gamma-lookup", passed: true, detail: `Found: ${slug}` });
    checks.push({ name: "gamma-active", passed: true, detail: `Market active: ${slug}` });
    break;
  }

  if (!result.gammaOk || !result.clobTokenId) {
    // Gamma lookup failed for all slugs
    if (!checks.some((c) => c.name === "gamma-lookup")) {
      checks.push({ name: "gamma-lookup", passed: false, detail: "No market slugs" });
    }
    return result;
  }

  // Fetch CLOB book
  try {
    const book = await fetchPolymarketBook(result.clobTokenId);
    if (!book) {
      checks.push({ name: "clob-book", passed: false, detail: "Failed to fetch CLOB book" });
      return result;
    }

    const quote = quoteFromBook(book);
    result.bestBid = quote.bestBid;
    result.bestAsk = quote.bestAsk;
    result.spreadPct = quote.spreadPct;
    result.topBookDepth = quote.topBookDepth;

    checks.push({
      name: "clob-book",
      passed: true,
      detail: `bid=${quote.bestBid?.toFixed(4) ?? "N/A"} ask=${quote.bestAsk?.toFixed(4) ?? "N/A"}`,
    });

    // Spread check
    const spreadOk = result.spreadPct !== undefined && result.spreadPct <= config.maxSpreadPct;
    checks.push({
      name: "spread",
      passed: spreadOk,
      detail: spreadOk
        ? `Spread ${result.spreadPct?.toFixed(2)}% <= ${config.maxSpreadPct}%`
        : `Spread ${result.spreadPct?.toFixed(2) ?? "N/A"}% > ${config.maxSpreadPct}%`,
    });

    // Liquidity check (top-of-book depth)
    const depthOk = result.topBookDepth !== undefined && result.topBookDepth >= config.minLiquidityUsd;
    checks.push({
      name: "liquidity",
      passed: depthOk,
      detail: depthOk
        ? `Depth $${result.topBookDepth?.toFixed(0)} >= $${config.minLiquidityUsd}`
        : `Depth $${result.topBookDepth?.toFixed(0) ?? "N/A"} < $${config.minLiquidityUsd}`,
    });

    // Edge percentage check
    const magnitudePct = parseEdgeMagnitude(edge);
    const edgePct = magnitudePct ?? calculateLiveEdge(result, direction);
    result.liveEdgePct = edgePct ?? undefined;
    const edgeOk = edgePct !== null && edgePct !== undefined && edgePct >= config.minEdgePct;
    checks.push({
      name: "edge",
      passed: edgeOk,
      detail: edgeOk
        ? `Edge ${edgePct?.toFixed(2)}% >= ${config.minEdgePct}%`
        : `Edge ${edgePct?.toFixed(2) ?? "N/A"}% < ${config.minEdgePct}%`,
    });

    result.ready = spreadOk && depthOk && edgeOk;
  } catch (err) {
    checks.push({
      name: "clob-book",
      passed: false,
      detail: `CLOB fetch error: ${(err as Error).message}`,
    });
  }

  return result;
}

function calculateLiveEdge(
  resolved: ResolvedEdge,
  direction: "yes" | "no",
): number | undefined | null {
  // For a "buy No" direction on near-certainty edges, the edge is:
  //   ((1 - price) / price) * 100  → yield percentage
  // For "buy Yes": ((fairValue - price) / price) * 100
  // Without a separate fair-value source, we use the bestBid/Ask as market price
  // and assume fair value = 1.0 for "no" on near-certainty edges.
  const price = direction === "no" ? resolved.bestAsk : resolved.bestAsk;
  if (price === undefined || price <= 0 || price >= 1) return null;

  if (direction === "no") {
    // Buying "No" → fair value is 1.0 at resolution
    // Edge = ((1 - price) / price) * 100
    return Number((((1 - price) / price) * 100).toFixed(2));
  } else {
    // Buying "Yes" → need a reference fair value; use midpoint as conservative estimate
    const bid = resolved.bestBid;
    const mid = bid !== undefined ? (bid + price) / 2 : price;
    if (mid >= 1) return null;
    return Number((((1 - mid) / mid) * 100).toFixed(2));
  }
}

// ── ClobClient Initialization ─────────────────────────────────

async function createViemWalletClient(
  privateKey: string,
): Promise<WalletClient<Transport, Chain, Account>> {
  const account = privateKeyToAccount(privateKey as `0x${string}`);
  return createWalletClient({
    account,
    chain: polygon,
    transport: http(),
  }) as WalletClient<Transport, Chain, Account>;
}

async function initClobClient(
  config: PmBotConfig,
  walletClient: WalletClient<Transport, Chain, Account>,
): Promise<{ client: any; funderAddress: string } | null> {
  const ok = await loadClobClient();
  if (!ok) {
    console.error("[pmBot] Failed to load @polymarket/clob-client-v2");
    return null;
  }

  const creds = await readJsonFile<PmCredentials>(resolveCwd(config.credentialsPath));
  if (!creds) {
    console.error(`[pmBot] Credentials not found at ${config.credentialsPath}`);
    return null;
  }

  const funderAddress = creds.builder_address ?? creds.bot_wallet_address;
  if (!funderAddress) {
    console.error("[pmBot] Missing bot_wallet_address in credentials");
    return null;
  }

  try {
    const client = new ClobClientClass({
      host: config.clobHost,
      chain: config.chainId,
      signer: walletClient,
      creds: {
        key: creds.api_key,
        secret: creds.api_secret,
        passphrase: creds.api_passphrase,
      },
      funderAddress,
    });

    console.log(`[pmBot] ClobClient initialized. Funder: ${funderAddress}`);
    return { client, funderAddress };
  } catch (e) {
    console.error(`[pmBot] ClobClient init failed: ${(e as Error).message}`);
    return null;
  }
}

// ── Order Execution ───────────────────────────────────────────

async function executeTrade(
  resolved: ResolvedEdge,
  clob: { client: any; funderAddress: string },
  config: PmBotConfig,
  bankrollBefore: number,
): Promise<PmFillRecord> {
  const baseRecord: PmFillRecord = {
    ts: new Date().toISOString(),
    edgeId: resolved.edge.id,
    marketSlug: resolved.edge.marketSlugs[0] ?? "unknown",
    clobTokenId: resolved.clobTokenId ?? "unknown",
    side: "BUY",
    price: 0,
    amountUsd: 0,
    shares: 0,
    orderId: "",
    status: "REJECTED",
    dryRun: config.dryRun,
    bankrollBefore,
    bankrollAfter: bankrollBefore,
    cumulativePnl: 0,
  };

  const direction = parseEdgeDirection(resolved.edge);

  // Determine entry price: use bestAsk for buys
  const entryPrice = resolved.bestAsk;
  if (entryPrice === undefined || entryPrice <= 0 || entryPrice >= 1) {
    return { ...baseRecord, error: "No valid entry price from CLOB book" };
  }

  // Calculate shares within maxPerTradeUsd
  const maxNotional = Math.min(config.maxPerTradeUsd, bankrollBefore);
  if (maxNotional < config.maxPerTradeUsd && maxNotional <= 0.01) {
    return {
      ...baseRecord,
      error: `Insufficient bankroll: $${bankrollBefore.toFixed(2)}`,
      status: "REJECTED",
    };
  }

  const rawShares = Math.floor((maxNotional / entryPrice) * 100) / 100;
  if (rawShares < 0.01) {
    return {
      ...baseRecord,
      price: entryPrice,
      error: `Notional too small: $${maxNotional.toFixed(2)} at ${entryPrice.toFixed(4)}`,
      status: "REJECTED",
    };
  }

  const amountUsd = Math.round(rawShares * entryPrice * 100) / 100;
  if (amountUsd < 1) {
    return {
      ...baseRecord,
      price: entryPrice,
      amountUsd,
      error: `Order below $1 Polymarket minimum: $${amountUsd.toFixed(2)}`,
      status: "REJECTED",
    };
  }

  const priceCents = Math.round(entryPrice * 100);
  const shares = Math.floor((amountUsd * 100) / priceCents);
  if (shares < 1) {
    return {
      ...baseRecord,
      price: entryPrice,
      amountUsd,
      error: "Cannot afford even 1 share",
      status: "REJECTED",
    };
  }

  const cleanAmount = (shares * priceCents) / 100;

  // DRY RUN
  if (config.dryRun) {
    return {
      ...baseRecord,
      side: "BUY",
      price: entryPrice,
      amountUsd: cleanAmount,
      shares,
      orderId: `DRY-${Date.now()}`,
      status: "DRY_RUN",
      bankrollAfter: bankrollBefore,
      cumulativePnl: 0,
    };
  }

  // LIVE execution — use market order through AMM (CLOB limit orders are dormant)
  try {
    const result = await clob.client.createAndPostMarketOrder({
      tokenID: resolved.clobTokenId,
      amount: shares,
      side: "buy"
    });

    // Market orders return different format — check for success
    const orderId = result?.orderID ?? result?.order_id ?? result?.id ?? "";
    const status = orderId ? "FILLED" : (result?.error ? "FAILED" : "PENDING");
    
    if (!orderId && !result?.error) {
      // Order may have succeeded — check for transaction hash
      const txHash = result?.transactionHash ?? result?.txHash ?? result?.hash ?? "";
      if (txHash) {
        return {
          ...baseRecord,
          side: "BUY",
          price: entryPrice,
          amountUsd: cleanAmount,
          shares,
          orderId: txHash,
          status: "FILLED",
          bankrollAfter: bankrollBefore - cleanAmount,
          cumulativePnl: -cleanAmount,
        };
      }
      return {
        ...baseRecord,
        side: "BUY",
        price: entryPrice,
        amountUsd: cleanAmount,
        shares,
        status: "FAILED",
        error: "No orderID or txHash in market order response: " + JSON.stringify(result).slice(0, 200),
      };
    }

    return {
      ...baseRecord,
      side: "BUY",
      price: entryPrice,
      amountUsd: cleanAmount,
      shares,
      orderId,
      status: result?.error ? "FAILED" : "FILLED",
      error: result?.error ?? undefined,
      bankrollAfter: result?.error ? bankrollBefore : bankrollBefore - cleanAmount,
      cumulativePnl: result?.error ? 0 : -cleanAmount,
    };
  } catch (e) {
    const msg = (e as Error).message;
    return {
      ...baseRecord,
      side: "BUY",
      price: entryPrice,
      amountUsd: cleanAmount,
      shares,
      status: "FAILED",
      error: msg,
    };
  }
}

// ── Fills Journal ─────────────────────────────────────────────

async function appendFill(fill: PmFillRecord, config: PmBotConfig): Promise<void> {
  const path = resolveCwd(config.fillsPath);
  await mkdir(dirname(path), { recursive: true });
  await appendFile(path, `${JSON.stringify(fill)}\n`, "utf8");
}

// ── Main Bot Logic ────────────────────────────────────────────

export async function runPmBot(config: Partial<PmBotConfig> = {}): Promise<PmBotReport> {
  const cfg = { ...DEFAULT_CONFIG, ...buildPmBotConfigFromEnv(), ...config };
  const errors: string[] = [];
  const fills: PmFillRecord[] = [];

  let bankroll = cfg.bankrollUsd;
  let cumulativePnl = 0;
  let halted = false;
  let haltReason: string | undefined;

  console.log(`[pmBot] Starting. Dry run: ${cfg.dryRun}. Bankroll: $${bankroll.toFixed(2)}`);

  // 1. Load edges
  const { report, edges, error: loadError } = await loadEdges(cfg);
  if (loadError) {
    errors.push(loadError);
    return {
      command: "pm-bot",
      generatedAt: new Date().toISOString(),
      dryRun: cfg.dryRun,
      bankrollStart: cfg.bankrollUsd,
      bankrollEnd: bankroll,
      cumulativePnl,
      edgesLoaded: 0,
      paperWatchEdges: 0,
      edgesResolved: 0,
      edgesReady: 0,
      fillsAttempted: 0,
      fillsSucceeded: 0,
      fills,
      halted: true,
      haltReason: loadError,
      errors,
    };
  }

  const totalEdges = report?.totalRawEdges ?? 0;
  console.log(`[pmBot] Loaded ${totalEdges} edges, ${edges.length} paper-watch`);

  // 2. Initialize ClobClient (if not dry run)
  let clob: { client: any; funderAddress: string } | null = null;
  if (!cfg.dryRun) {
    const creds = await readJsonFile<PmCredentials>(resolveCwd(cfg.credentialsPath));
    if (!creds || !creds.bot_private_key) {
      errors.push("Missing bot credentials for live mode");
      halted = true;
      haltReason = "Missing bot credentials";
    } else {
      try {
        const walletClient = await createViemWalletClient(creds.bot_private_key);
        clob = await initClobClient(cfg, walletClient);
        if (!clob) {
          errors.push("Failed to initialize ClobClient");
          // Continue in dry-run-esque mode — just skip execution
        }
      } catch (e) {
        errors.push(`Wallet init failed: ${(e as Error).message}`);
      }
    }
  }

  // 3. Resolve edges and execute
  let resolvedCount = 0;
  let readyCount = 0;
  let attemptedCount = 0;
  let succeededCount = 0;

  for (const edge of edges) {
    if (halted) break;

    // Capital preservation: stop if bankroll below floor
    if (bankroll < cfg.stopFloorUsd) {
      halted = true;
      haltReason = `Bankroll $${bankroll.toFixed(2)} below stop floor $${cfg.stopFloorUsd}`;
      console.log(`[pmBot] HALTED: ${haltReason}`);
      break;
    }

    console.log(`[pmBot] Resolving edge: ${edge.id} (${edge.title.slice(0, 60)})`);
    const resolved = await resolveEdge(edge, cfg);
    resolvedCount++;

    if (!resolved.ready) {
      const failed = resolved.checks.filter((c) => !c.passed);
      console.log(
        `[pmBot]   SKIP: ${failed.map((c) => `${c.name}=${c.detail}`).join("; ")}`,
      );
      continue;
    }

    readyCount++;
    console.log(`[pmBot]   READY. Executing...`);

    const bankrollBefore = bankroll;
    const fill = await executeTrade(resolved, clob ?? { client: null, funderAddress: "" }, cfg, bankrollBefore);
    attemptedCount++;

    if (fill.status === "FILLED" || fill.status === "DRY_RUN") {
      if (fill.status === "FILLED") {
        bankroll = bankrollBefore - fill.amountUsd;
        cumulativePnl -= fill.amountUsd;
      }
      fill.bankrollAfter = bankroll;
      fill.cumulativePnl = cumulativePnl;
      succeededCount++;
      console.log(`[pmBot]   ${fill.status}: ${fill.shares} shares @ $${fill.price.toFixed(4)} = $${fill.amountUsd.toFixed(2)}`);
    } else {
      fill.bankrollAfter = bankroll;
      fill.cumulativePnl = cumulativePnl;
      console.log(`[pmBot]   ${fill.status}: ${fill.error}`);
    }

    fills.push(fill);
    await appendFill(fill, cfg);
  }

  console.log(`[pmBot] Done. Bankroll: $${bankroll.toFixed(2)}. PnL: $${cumulativePnl.toFixed(2)}. Fills: ${succeededCount}/${attemptedCount}`);

  return {
    command: "pm-bot",
    generatedAt: new Date().toISOString(),
    dryRun: cfg.dryRun,
    bankrollStart: cfg.bankrollUsd,
    bankrollEnd: bankroll,
    cumulativePnl,
    edgesLoaded: totalEdges,
    paperWatchEdges: edges.length,
    edgesResolved: resolvedCount,
    edgesReady: readyCount,
    fillsAttempted: attemptedCount,
    fillsSucceeded: succeededCount,
    fills,
    halted,
    haltReason,
    errors,
  };
}

// ── CLI entrypoint ────────────────────────────────────────────

export async function runPmBotCli(args: string[]): Promise<void> {
  const dryRun = !args.includes("--live");
  const makerMode = args.includes("--maker");
  
  if (makerMode) {
    // ── Maker Strategy Mode ──────────────────────────────────
    console.log(`[pmBot] Maker strategy mode. Dry run: ${dryRun}`);
    const { generateMakerSignals, formatSignal, DEFAULT_MAKER_CONFIG } = await import("./makerStrategy.js");
    
    const signals = await generateMakerSignals(DEFAULT_MAKER_CONFIG);
    console.log(`\nMaker signals: ${signals.length}\n`);
    
    for (const signal of signals) {
      console.log(`  ${formatSignal(signal)}`);
    }
    
    if (!dryRun && signals.length > 0) {
      // Live execution via CLOB adapter
      console.log("\n[pmBot] LIVE maker execution not yet implemented. Dry-run only.");
    }
    
    // Log to fills journal
    const fillsPath = resolve(".rumbling-hedge/runtime/prediction/fills.jsonl");
    await mkdir(dirname(fillsPath), { recursive: true });
    for (const signal of signals) {
      await appendFile(fillsPath, JSON.stringify({
        ts: new Date().toISOString(),
        edgeId: `maker-${signal.tokenId}`,
        marketSlug: signal.marketTitle,
        clobTokenId: signal.tokenId,
        side: "BUY",
        price: signal.noPrice,
        amountUsd: signal.costUsd,
        shares: signal.shares,
        orderId: `MAKER-DRY-${Date.now()}`,
        status: "DRY_RUN",
        dryRun: true,
        bankrollBefore: 0,
        bankrollAfter: 0,
        cumulativePnl: 0,
        strategy: "maker",
        category: signal.category,
        edge: signal.edge,
      }) + "\n", "utf8");
    }
    
    console.log(`\nLogged ${signals.length} maker signals to fills journal.`);
    return;
  }
  
  // ── Standard Edge-Based Mode ──────────────────────────────
  if (args.includes("--live")) {
    console.log("[pmBot] LIVE mode requested. Real orders may be placed.");
  }
  const report = await runPmBot({ dryRun });
  console.log(JSON.stringify(report, null, 2));
}
