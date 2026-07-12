#!/usr/bin/env node
/**
 * Read-only Polymarket CLOB market-channel recorder.
 *
 * This subscribes to public market data only. It never loads private keys,
 * never signs orders, and never writes execution artifacts.
 *
 * Official market channel docs:
 * https://docs.polymarket.com/market-data/websocket/market-channel
 */
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import WebSocket from "ws";

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
// kanban t_b9133e83 (2026-07-07): default to the fresh live snapshot. The old
// default (latest-combined-snapshot.json) was last refreshed 2026-06-24 and left
// standing capture reading 13-day-stale markets. Override via BILL_POLYMARKET_SNAPSHOT_PATH.
const DEFAULT_SNAPSHOT = path.resolve(REPO_ROOT, ".rumbling-hedge/runtime/prediction/combined-live-snapshot.json");
const DEFAULT_OUT_DIR = path.resolve(REPO_ROOT, ".rumbling-hedge/prediction/clob");
const DEFAULT_STATE_PATH = path.resolve(REPO_ROOT, ".rumbling-hedge/state/polymarket-clob-recorder.latest.json");
const WSS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market";
const DEFAULT_MIN_PRICE = 0.01;
const DEFAULT_MAX_PRICE = 0.99;
const DEFAULT_MAX_SPREAD = 0.12;
const DEFAULT_MAX_DAYS_TO_EXPIRY = 45;
const DEFAULT_MIN_DEPTH = 1_000;
const DEFAULT_MAX_OUTPUT_MB = 256;
const DEFAULT_MIN_FREE_GB = 5;
const MANUAL_SELECTION_SCORE = 1_000_000_000;
const MONTH_INDEX = {
  january: 0,
  jan: 0,
  february: 1,
  feb: 1,
  march: 2,
  mar: 2,
  april: 3,
  apr: 3,
  may: 4,
  june: 5,
  jun: 5,
  july: 6,
  jul: 6,
  august: 7,
  aug: 7,
  september: 8,
  sep: 8,
  sept: 8,
  october: 9,
  oct: 9,
  november: 10,
  nov: 10,
  december: 11,
  dec: 11
};
const DEFAULT_TERMS = [
  "bitcoin",
  "btc",
  "ethereum",
  "eth",
  "fed",
  "rate",
  "cpi",
  "inflation",
  "gdp",
  "unemployment",
  "recession",
  "tariff",
  "nvidia",
  "tesla",
  "stock"
];
const DEFAULT_EXCLUDE_TERMS = [
  "world cup",
  "2028",
  "presidential election",
  "presidential nomination",
  "republican presidential nominee",
  "democratic presidential nominee"
];

function parseArgs(argv) {
  const out = {
    snapshot: process.env.BILL_POLYMARKET_SNAPSHOT_PATH || DEFAULT_SNAPSHOT,
    outDir: process.env.BILL_POLYMARKET_CLOB_OUT_DIR || DEFAULT_OUT_DIR,
    statePath: process.env.BILL_POLYMARKET_CLOB_STATE_PATH || DEFAULT_STATE_PATH,
    durationSec: Number.parseInt(process.env.BILL_POLYMARKET_CLOB_DURATION_SEC || "120", 10),
    maxAssets: Number.parseInt(process.env.BILL_POLYMARKET_CLOB_MAX_ASSETS || "24", 10),
    terms: (process.env.BILL_POLYMARKET_CLOB_TERMS || DEFAULT_TERMS.join(",")).split(",").map((s) => s.trim().toLowerCase()).filter(Boolean),
    excludeTerms: (process.env.BILL_POLYMARKET_CLOB_EXCLUDE_TERMS || DEFAULT_EXCLUDE_TERMS.join(",")).split(",").map((s) => s.trim().toLowerCase()).filter(Boolean),
    minPrice: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MIN_PRICE || String(DEFAULT_MIN_PRICE)),
    maxPrice: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MAX_PRICE || String(DEFAULT_MAX_PRICE)),
    maxSpread: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MAX_SPREAD || String(DEFAULT_MAX_SPREAD)),
    maxDaysToExpiry: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MAX_DAYS_TO_EXPIRY || String(DEFAULT_MAX_DAYS_TO_EXPIRY)),
    minTopBookDepth: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MIN_TOP_BOOK_DEPTH || String(DEFAULT_MIN_DEPTH)),
    maxOutputMb: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MAX_OUTPUT_MB || String(DEFAULT_MAX_OUTPUT_MB)),
    minFreeGb: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MIN_FREE_GB || String(DEFAULT_MIN_FREE_GB)),
    requireExpiry: process.env.BILL_POLYMARKET_CLOB_REQUIRE_EXPIRY !== "false",
    requireSnapshotBook: process.env.BILL_POLYMARKET_CLOB_REQUIRE_SNAPSHOT_BOOK !== "false",
    tokenIds: []
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--snapshot" && next) out.snapshot = path.resolve(next), i += 1;
    else if (arg === "--out-dir" && next) out.outDir = path.resolve(next), i += 1;
    else if (arg === "--state-path" && next) out.statePath = path.resolve(next), i += 1;
    else if (arg === "--duration-sec" && next) out.durationSec = Number.parseInt(next, 10), i += 1;
    else if (arg === "--max-assets" && next) out.maxAssets = Number.parseInt(next, 10), i += 1;
    else if (arg === "--terms" && next) out.terms = next.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean), i += 1;
    else if (arg === "--exclude-terms" && next) out.excludeTerms = next.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean), i += 1;
    else if (arg === "--min-price" && next) out.minPrice = Number.parseFloat(next), i += 1;
    else if (arg === "--max-price" && next) out.maxPrice = Number.parseFloat(next), i += 1;
    else if (arg === "--max-spread" && next) out.maxSpread = Number.parseFloat(next), i += 1;
    else if (arg === "--max-days-to-expiry" && next) out.maxDaysToExpiry = Number.parseFloat(next), i += 1;
    else if (arg === "--min-top-book-depth" && next) out.minTopBookDepth = Number.parseFloat(next), i += 1;
    else if (arg === "--max-output-mb" && next) out.maxOutputMb = Number.parseFloat(next), i += 1;
    else if (arg === "--min-free-gb" && next) out.minFreeGb = Number.parseFloat(next), i += 1;
    else if (arg === "--allow-missing-expiry") out.requireExpiry = false;
    else if (arg === "--allow-missing-snapshot-book") out.requireSnapshotBook = false;
    else if (arg === "--token-id" && next) out.tokenIds.push(next), i += 1;
  }

  if (!Number.isFinite(out.durationSec) || out.durationSec <= 0) out.durationSec = 120;
  if (!Number.isFinite(out.maxAssets) || out.maxAssets <= 0) out.maxAssets = 24;
  if (!Number.isFinite(out.minPrice)) out.minPrice = DEFAULT_MIN_PRICE;
  if (!Number.isFinite(out.maxPrice)) out.maxPrice = DEFAULT_MAX_PRICE;
  if (!Number.isFinite(out.maxSpread)) out.maxSpread = DEFAULT_MAX_SPREAD;
  if (!Number.isFinite(out.maxDaysToExpiry)) out.maxDaysToExpiry = DEFAULT_MAX_DAYS_TO_EXPIRY;
  if (!Number.isFinite(out.minTopBookDepth)) out.minTopBookDepth = DEFAULT_MIN_DEPTH;
  if (!Number.isFinite(out.maxOutputMb) || out.maxOutputMb <= 0) out.maxOutputMb = DEFAULT_MAX_OUTPUT_MB;
  if (!Number.isFinite(out.minFreeGb) || out.minFreeGb < 0) out.minFreeGb = DEFAULT_MIN_FREE_GB;
  return out;
}

function dayStamp(date = new Date()) {
  return date.toISOString().slice(0, 10);
}

function toNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function bytesToGb(bytes) {
  return Number((bytes / 1_073_741_824).toFixed(3));
}

function outputLimitBytes(opts) {
  return Math.max(1, Math.floor(opts.maxOutputMb * 1_048_576));
}

export async function storageSafetyDiagnostics(outDir, opts) {
  const stats = await fs.statfs(outDir);
  const freeBytes = Number(stats.bavail || 0) * Number(stats.bsize || 0);
  const freeGb = bytesToGb(freeBytes);
  return {
    outDir,
    freeBytes,
    freeGb,
    minFreeGb: opts.minFreeGb,
    maxOutputMb: opts.maxOutputMb,
    maxOutputBytes: outputLimitBytes(opts),
    safeToStart: freeGb >= opts.minFreeGb
  };
}

function rowsFromSnapshot(parsed) {
  if (Array.isArray(parsed)) return parsed;
  if (parsed && Array.isArray(parsed.markets)) return parsed.markets;
  if (parsed && Array.isArray(parsed.rows)) return parsed.rows;
  return [];
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function termMatches(text, term) {
  if (term.length <= 4) {
    return new RegExp(`(^|[^a-z0-9])${escapeRegex(term)}([^a-z0-9]|$)`, "i").test(text);
  }
  return text.includes(term);
}

async function readSnapshotRows(snapshotPath) {
  const raw = await fs.readFile(snapshotPath, "utf8");
  return rowsFromSnapshot(JSON.parse(raw));
}

function parseTime(value) {
  if (!value) return null;
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function textDateHintMs(text, nowMs) {
  const monthDay = /\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,\s*(20\d{2}))?\b/i.exec(text);
  if (!monthDay) return null;
  const month = MONTH_INDEX[monthDay[1].toLowerCase()];
  const day = Number.parseInt(monthDay[2], 10);
  const now = new Date(nowMs);
  const year = monthDay[3] ? Number.parseInt(monthDay[3], 10) : now.getUTCFullYear();
  if (month == null || !Number.isFinite(day) || day < 1 || day > 31) return null;
  const date = Date.UTC(year, month, day, 23, 59, 59);
  if (!monthDay[3] && date < nowMs - 30 * 86_400_000) {
    return Date.UTC(year + 1, month, day, 23, 59, 59);
  }
  return date;
}

function rowText(row) {
  return [row.eventTitle, row.marketQuestion, row.settlementText, row.outcomeLabel]
    .map((value) => String(value || ""))
    .join(" ")
    .toLowerCase();
}

function rowSpread(row) {
  const bestBid = toNumber(row.bestBid);
  const bestAsk = toNumber(row.bestAsk);
  if (bestBid == null || bestAsk == null) return null;
  return Number((bestAsk - bestBid).toFixed(6));
}

function rejectAutomaticCandidate(row, text, opts, nowMs) {
  if (opts.excludeTerms?.some((term) => termMatches(text, term))) return "excluded-term";

  const price = toNumber(row.price);
  if (price == null) return "missing-price";
  if (price < opts.minPrice) return "below-min-price";
  if (price > opts.maxPrice) return "above-max-price";

  const spread = rowSpread(row);
  if (opts.requireSnapshotBook && spread == null) return "missing-snapshot-book";

  const expiryMs = parseTime(row.expiry || row.endDate || row.endDateIso);
  const horizonMs = textDateHintMs(text, nowMs) ?? expiryMs;
  if (opts.requireExpiry && horizonMs == null) return "missing-expiry";
  if (horizonMs != null) {
    if (horizonMs <= nowMs) return "expired";
    const daysToExpiry = (horizonMs - nowMs) / 86_400_000;
    if (daysToExpiry > opts.maxDaysToExpiry) return "too-long-dated";
  }

  if (spread != null && spread > opts.maxSpread) return "spread-too-wide";

  const depth = toNumber(row.topBookDepth) ?? toNumber(row.displayedSize) ?? 0;
  if (depth < opts.minTopBookDepth) return "insufficient-depth";

  return null;
}

function scoreCandidate(row, text, opts, nowMs) {
  const matchedTerms = opts.terms.filter((term) => termMatches(text, term)).length;
  const price = toNumber(row.price) ?? 0.5;
  const depth = Math.max(toNumber(row.topBookDepth) ?? toNumber(row.displayedSize) ?? 0, 1);
  const spread = rowSpread(row);
  const expiryMs = textDateHintMs(text, nowMs) ?? parseTime(row.expiry || row.endDate || row.endDateIso);
  const daysToExpiry = expiryMs == null ? opts.maxDaysToExpiry : Math.max((expiryMs - nowMs) / 86_400_000, 0);
  const priceQuality = 1 - Math.min(Math.abs(price - 0.5) / 0.49, 1);
  const spreadQuality = spread == null ? 0.35 : Math.max(0, 1 - spread / opts.maxSpread);
  const horizonQuality = Math.max(0, 1 - daysToExpiry / opts.maxDaysToExpiry);
  const depthQuality = Math.min(Math.log10(depth + 1) / 7, 1);
  return Number((
    matchedTerms * 5
    + priceQuality * 3
    + spreadQuality * 3
    + horizonQuality * 2
    + depthQuality
  ).toFixed(6));
}

export function selectAssetsWithDiagnostics(rows, opts) {
  const nowMs = opts.nowMs ?? Date.now();
  const byId = new Map();
  const manualTokenIds = new Set((opts.tokenIds || []).map((tokenId) => String(tokenId)));
  const rejectionCounts = {};
  const acceptedAutomaticCount = { value: 0 };
  for (const tokenId of manualTokenIds) {
    byId.set(String(tokenId), {
      tokenId: String(tokenId),
      manual: true,
      reason: "manual",
      displayedSize: 0,
      selectionScore: MANUAL_SELECTION_SCORE,
      question: "manual token id"
    });
  }

  for (const row of rows) {
    const tokenId = row?.clobTokenId;
    if (!tokenId) continue;
    const text = rowText(row);
    const tokenKey = String(tokenId);
    const isManualToken = manualTokenIds.has(tokenKey);
    if (!isManualToken && !opts.terms.some((term) => termMatches(text, term))) continue;
    const current = byId.get(String(tokenId));
    if (!isManualToken && current?.manual !== true) {
      const rejection = rejectAutomaticCandidate(row, text, opts, nowMs);
      if (rejection) {
        rejectionCounts[rejection] = (rejectionCounts[rejection] || 0) + 1;
        continue;
      }
    }
    acceptedAutomaticCount.value += current?.manual === true ? 0 : 1;
    const displayedSize = Number(row.displayedSize || row.topBookDepth || 0);
    const selectionScore = isManualToken || current?.manual === true ? MANUAL_SELECTION_SCORE : scoreCandidate(row, text, opts, nowMs);
    if (!current || selectionScore > current.selectionScore || (selectionScore === current.selectionScore && displayedSize > current.displayedSize)) {
      byId.set(String(tokenId), {
        tokenId: String(tokenId),
        manual: isManualToken || current?.manual === true,
        reason: isManualToken || current?.manual === true ? "manual+snapshot-match" : "snapshot-term-match",
        displayedSize,
        selectionScore,
        price: row.price,
        bestBid: row.bestBid,
        bestAsk: row.bestAsk,
        expiry: row.expiry,
        spread: rowSpread(row),
        eventTitle: row.eventTitle,
        outcomeLabel: row.outcomeLabel,
        question: row.marketQuestion || row.eventTitle || current?.question || "unknown"
      });
    }
  }

  const assets = Array.from(byId.values())
    .sort((a, b) =>
      Number(b.manual === true) - Number(a.manual === true)
      || Number(b.selectionScore || 0) - Number(a.selectionScore || 0)
      || Number(b.displayedSize || 0) - Number(a.displayedSize || 0)
    )
    .slice(0, opts.maxAssets);
  return {
    assets,
    diagnostics: {
      acceptedAutomaticCount: acceptedAutomaticCount.value,
      rejectedAutomaticCount: Object.values(rejectionCounts).reduce((acc, value) => acc + value, 0),
      rejectionCounts,
      filters: {
        excludeTerms: opts.excludeTerms,
        minPrice: opts.minPrice,
        maxPrice: opts.maxPrice,
        maxSpread: opts.maxSpread,
        maxDaysToExpiry: opts.maxDaysToExpiry,
        minTopBookDepth: opts.minTopBookDepth,
        requireExpiry: opts.requireExpiry,
        requireSnapshotBook: opts.requireSnapshotBook
      }
    }
  };
}

export function selectAssets(rows, opts) {
  return selectAssetsWithDiagnostics(rows, opts).assets;
}

function normalizeEvent(message) {
  const eventType = message.event_type || message.eventType || "unknown";
  const base = {
    localTs: new Date().toISOString(),
    eventType,
    market: message.market,
    assetId: message.asset_id,
    exchangeTs: message.timestamp
  };

  if (eventType === "book") {
    return {
      ...base,
      bids: topLevels(message.bids, -1),
      asks: topLevels(message.asks, 1),
      hash: message.hash
    };
  }

  if (eventType === "price_change") {
    return {
      ...base,
      priceChanges: Array.isArray(message.price_changes) ? message.price_changes : []
    };
  }

  if (eventType === "best_bid_ask") {
    return {
      ...base,
      bestBid: toNumber(message.best_bid),
      bestAsk: toNumber(message.best_ask),
      spread: toNumber(message.spread)
    };
  }

  if (eventType === "last_trade_price") {
    return {
      ...base,
      price: toNumber(message.price),
      size: toNumber(message.size),
      side: message.side,
      feeRateBps: toNumber(message.fee_rate_bps)
    };
  }

  return { ...base, raw: message };
}

function topLevels(levels, sortDirection, limit = 8) {
  return (Array.isArray(levels) ? levels : [])
    .map((level) => {
      const price = toNumber(level.price);
      const size = toNumber(level.size);
      return { price, size };
    })
    .filter((level) => level.price != null && level.size != null && level.price > 0 && level.price < 1 && level.size > 0)
    .sort((a, b) => sortDirection * (a.price - b.price))
    .slice(0, limit)
    .map((level) => ({
      price: String(level.price),
      size: String(level.size)
    }));
}

function levelSummary(levels, sortDirection) {
  const normalized = (Array.isArray(levels) ? levels : [])
    .map((level) => ({ price: toNumber(level.price), size: toNumber(level.size) }))
    .filter((level) => level.price != null && level.size != null && level.price > 0 && level.price < 1 && level.size > 0)
    .sort((a, b) => sortDirection * (a.price - b.price));
  return normalized[0] || null;
}

function updateBookState(bookState, record) {
  const assetId = record.assetId;
  if (!assetId) return;
  const current = bookState.get(assetId) || {};

  if (record.eventType === "book") {
    const bid = levelSummary(record.bids, -1);
    const ask = levelSummary(record.asks, 1);
    bookState.set(assetId, {
      ...current,
      assetId,
      bestBid: bid?.price,
      bidSize: bid?.size,
      bestAsk: ask?.price,
      askSize: ask?.size,
      spread: bid && ask ? Number((ask.price - bid.price).toFixed(6)) : undefined,
      lastBookLocalTs: record.localTs,
      lastExchangeTs: record.exchangeTs
    });
    return;
  }

  if (record.eventType === "best_bid_ask") {
    bookState.set(assetId, {
      ...current,
      assetId,
      bestBid: record.bestBid ?? current.bestBid,
      bestAsk: record.bestAsk ?? current.bestAsk,
      spread: record.spread ?? current.spread,
      lastBbaLocalTs: record.localTs,
      lastExchangeTs: record.exchangeTs
    });
    return;
  }

  if (record.eventType === "price_change") {
    for (const change of record.priceChanges || []) {
      const changeAsset = change.asset_id;
      if (!changeAsset) continue;
      const changeCurrent = bookState.get(changeAsset) || {};
      const bestBid = toNumber(change.best_bid);
      const bestAsk = toNumber(change.best_ask);
      bookState.set(changeAsset, {
        ...changeCurrent,
        assetId: changeAsset,
        bestBid: bestBid ?? changeCurrent.bestBid,
        bestAsk: bestAsk ?? changeCurrent.bestAsk,
        spread: bestBid != null && bestAsk != null ? Number((bestAsk - bestBid).toFixed(6)) : changeCurrent.spread,
        lastPriceChangeLocalTs: record.localTs,
        lastExchangeTs: record.exchangeTs
      });
    }
    return;
  }

  if (record.eventType === "last_trade_price") {
    bookState.set(assetId, {
      ...current,
      assetId,
      lastTradePrice: record.price,
      lastTradeSize: record.size,
      lastTradeSide: record.side,
      lastTradeLocalTs: record.localTs,
      lastExchangeTs: record.exchangeTs
    });
  }
}

function classifyLiveBook(book, opts) {
  if (!book) return "missing-live-book";
  const spread = toNumber(book.spread);
  if (spread == null) return "missing-live-spread";
  if (spread < 0) return "crossed-live-book";
  if (spread > opts.maxSpread) return "live-spread-too-wide";
  const bidSize = toNumber(book.bidSize) ?? 0;
  const askSize = toNumber(book.askSize) ?? 0;
  if (bidSize + askSize < opts.minTopBookDepth) return "insufficient-live-depth";
  return "fillable-live-book";
}

export function liveQualityDiagnostics(selectedAssets, latestBookState, opts) {
  const byId = new Map((latestBookState || []).map((book) => [String(book.assetId), book]));
  const assets = (selectedAssets || []).map((asset) => {
    const book = byId.get(String(asset.tokenId));
    const status = classifyLiveBook(book, opts);
    return {
      tokenId: asset.tokenId,
      question: asset.question,
      status,
      liveBestBid: book?.bestBid,
      liveBestAsk: book?.bestAsk,
      liveSpread: book?.spread,
      liveBidSize: book?.bidSize,
      liveAskSize: book?.askSize,
      lastBookLocalTs: book?.lastBookLocalTs,
      lastBbaLocalTs: book?.lastBbaLocalTs,
      lastPriceChangeLocalTs: book?.lastPriceChangeLocalTs
    };
  });
  const statusCounts = {};
  for (const asset of assets) {
    statusCounts[asset.status] = (statusCounts[asset.status] || 0) + 1;
  }
  const fillableLiveBookCount = statusCounts["fillable-live-book"] || 0;
  return {
    fillableLiveBookCount,
    observedLiveBookCount: assets.filter((asset) => asset.status !== "missing-live-book").length,
    selectedAssetCount: assets.length,
    readyForPaperEvidence: false,
    reason: fillableLiveBookCount > 0
      ? "public capture observed some fillable live books, but paper still requires no-lookahead event replay and resolved labels"
      : "no selected assets had fillable live books under current spread/depth rules",
    statusCounts,
    filters: {
      maxSpread: opts.maxSpread,
      minTopBookDepth: opts.minTopBookDepth
    },
    assets
  };
}

export function buildSummary({
  reason,
  startedAt,
  endedAt,
  opts,
  outPath,
  assets,
  selectionDiagnostics,
  storageSafety,
  initialOutputBytes,
  latestBookState,
  messages,
  counts
}) {
  return {
    command: "polymarket-clob-recorder",
    status: reason === "duration_elapsed" ? "ok" : reason,
    researchOnly: true,
    writesOrders: false,
    touchesBroker: false,
    readyForPaper: false,
    readyForExecution: false,
    startedAt,
    endedAt,
    durationSec: opts.durationSec,
    endpoint: WSS_URL,
    snapshotPath: opts.snapshot,
    outPath,
    outputFiles: [outPath],
    selectedAssets: assets,
    selectionDiagnostics,
    storageSafety: {
      ...storageSafety,
      initialOutputBytes,
      maxRunOutputBytes: storageSafety.maxOutputBytes
    },
    liveQualityDiagnostics: liveQualityDiagnostics(assets, latestBookState, opts),
    messages,
    counts,
    latestBookState
  };
}

export { normalizeEvent, updateBookState };

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const rows = await readSnapshotRows(opts.snapshot);
  const selection = selectAssetsWithDiagnostics(rows, opts);
  const assets = selection.assets;
  if (assets.length === 0) {
    throw new Error(`No CLOB token ids selected from ${opts.snapshot}. Run prediction collect first or pass --token-id.`);
  }

  await fs.mkdir(opts.outDir, { recursive: true });
  await fs.mkdir(path.dirname(opts.statePath), { recursive: true });
  const storageSafety = await storageSafetyDiagnostics(opts.outDir, opts);
  if (!storageSafety.safeToStart) {
    throw new Error(`Insufficient free space for CLOB recorder: ${storageSafety.freeGb}GB available, requires ${opts.minFreeGb}GB`);
  }
  const outPath = path.join(opts.outDir, `${dayStamp()}-market-channel.jsonl`);
  let initialOutputBytes = 0;
  try {
    initialOutputBytes = (await fs.stat(outPath)).size;
  } catch {
    initialOutputBytes = 0;
  }
  const startedAt = new Date().toISOString();
  const deadline = Date.now() + opts.durationSec * 1000;
  const counts = {};
  const bookState = new Map();
  let messages = 0;
  let closed = false;
  let heartbeat = null;

  const ws = new WebSocket(WSS_URL, {
    handshakeTimeout: 15_000,
    perMessageDeflate: false
  });

  const closeWithSummary = async (reason) => {
    if (closed) return;
    closed = true;
    try {
      if (heartbeat) {
        clearInterval(heartbeat);
        heartbeat = null;
      }
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      setTimeout(() => {
        if (ws.readyState !== WebSocket.CLOSED) {
          ws.terminate();
        }
      }, 500).unref?.();
    } catch {
      // no-op
    }
    const endedAt = new Date().toISOString();
    const latestBookState = Array.from(bookState.values()).slice(0, 50);
    const summary = buildSummary({
      reason,
      startedAt,
      endedAt,
      opts,
      outPath,
      assets,
      selectionDiagnostics: selection.diagnostics,
      storageSafety,
      initialOutputBytes,
      latestBookState,
      messages,
      counts
    });
    await fs.writeFile(opts.statePath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
    console.log(JSON.stringify(summary, null, 2));
  };

  ws.on("open", () => {
    ws.send(JSON.stringify({
      assets_ids: assets.map((asset) => asset.tokenId),
      type: "market",
      custom_feature_enabled: true
    }));
    heartbeat = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send("PING");
      }
    }, 10_000);
    heartbeat.unref?.();
  });

  ws.on("message", async (data) => {
    try {
      const raw = data.toString();
      if (raw === "PONG" || raw.trim() === "") {
        if (Date.now() >= deadline) {
          await closeWithSummary("duration_elapsed");
        }
        return;
      }
      const parsed = JSON.parse(raw);
      const entries = Array.isArray(parsed) ? parsed : [parsed];
      const records = entries.map(normalizeEvent);
      for (const record of records) {
        messages += 1;
        counts[record.eventType] = (counts[record.eventType] || 0) + 1;
        updateBookState(bookState, record);
      }
      await fs.appendFile(outPath, records.map((record) => JSON.stringify(record)).join("\n") + "\n", "utf8");
      const stat = await fs.stat(outPath);
      if (stat.size - initialOutputBytes >= storageSafety.maxOutputBytes) {
        await closeWithSummary("output_limit_reached");
        return;
      }
      if (Date.now() >= deadline) {
        await closeWithSummary("duration_elapsed");
      }
    } catch (error) {
      await fs.appendFile(outPath, JSON.stringify({
        localTs: new Date().toISOString(),
        eventType: "parse_error",
        error: error instanceof Error ? error.message : String(error)
      }) + "\n", "utf8");
    }
  });

  ws.on("error", async (error) => {
    await closeWithSummary(`websocket_error:${error.message}`);
  });

  ws.on("close", async () => {
    await closeWithSummary(Date.now() >= deadline ? "duration_elapsed" : "closed");
  });

  setTimeout(() => {
    closeWithSummary("duration_elapsed").catch((error) => {
      console.error(error);
      process.exitCode = 1;
    });
  }, opts.durationSec * 1000 + 1000).unref();
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
