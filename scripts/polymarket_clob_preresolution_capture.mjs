#!/usr/bin/env node
/**
 * Pre-resolution CLOB microstructure capturer (research-only, read-only).
 *
 * Why this exists (kanban t_d6a63517): the historical `BrockMisner/polymarket-btc-updown`
 * source orderbook is resolution-window-only — across 616 resolved BTC markets only
 * ~1,193 of 232,725 corpus rows carry microstructure, and 100% of those sit at
 * fraction-elapsed >= 0.83. That makes the resolved-label replay's forward mode
 * (frac<=0.5) yield 0 eligible rows, so the genuinely-new family
 * `clob-resolved-label-pre-resolution-resting-convergence` cannot clear the no-edge
 * contract on historical data. A live pre-resolution capture is the only viable fix.
 *
 * What this does differently from polymarket_clob_recorder.mjs:
 *   1. Captures BOTH outcome tokens (Yes/up AND No/down) per market, so resting-book
 *      depth imbalance can be computed pre-resolution (the recorder only tracked the
 *      single selected token).
 *   2. Emits `pre_resolution_book` snapshot records when the market is still open and
 *      fraction-elapsed <= --max-elig-frac (default 0.5). Each snapshot carries the
 *      up/down best bid/ask + depth, spread, and the computed frac + market_id.
 *   3. Records `market_meta` once per captured market: start_ts, end_ts, question,
 *      resolution token ids — the join keys the corpus builder needs later.
 *   4. Adds an OFFLINE `--replay-jsonl <path>` mode that replays a recorded
 *      market-channel jsonl through the exact same normalize/select/emit path, so the
 *      capture logic is testable without network. For fully deterministic offline tests
 *      you also pass `--market-times <json>` (market_id -> {start_ts,end_ts}) and
 *      `--labels <json>` (market_id -> 0/1 resolution); when those are absent the
 *      replay still emits snapshots but marks them `labelPending: true`.
 *
 * This script never signs orders, never loads keys, never writes broker artifacts.
 * It only appends normalized public market data to a jsonl file.
 *
 * Official market channel docs:
 * https://docs.polymarket.com/market-data/websocket/market-channel
 */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import WebSocket from "ws";
// Reuse the recorder's market-selection logic (the only stable export we need).
import { selectAssetsWithDiagnostics, storageSafetyDiagnostics } from "./polymarket_clob_recorder.mjs";

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const DEFAULT_OUT_DIR = path.resolve(REPO_ROOT, ".rumbling-hedge/prediction/clob/pre-resolution");
const DEFAULT_STATE_PATH = path.resolve(REPO_ROOT, ".rumbling-hedge/state/polymarket-clob-preresolution-capture.latest.json");
const WSS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market";

const DEFAULT_MAX_ELIG_FRAC = 0.5;

function toNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function dayStamp(date = new Date()) {
  return date.toISOString().slice(0, 10);
}

// Local arg parser (recorder's parseArgs is not exported).
function parseArgs(argv) {
  const opts = {
    snapshot: process.env.BILL_POLYMARKET_SNAPSHOT_PATH || path.resolve(REPO_ROOT, ".rumbling-hedge/runtime/prediction/combined-live-snapshot.json"),
    outDir: process.env.BILL_POLYMARKET_PR_OUT_DIR || DEFAULT_OUT_DIR,
    statePath: process.env.BILL_POLYMARKET_PR_STATE_PATH || DEFAULT_STATE_PATH,
    durationSec: Number.parseInt(process.env.BILL_POLYMARKET_CLOB_DURATION_SEC || "120", 10),
    maxAssets: Number.parseInt(process.env.BILL_POLYMARKET_CLOB_MAX_ASSETS || "24", 10),
    terms: (process.env.BILL_POLYMARKET_CLOB_TERMS || "bitcoin,btc,ethereum,eth").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean),
    minPrice: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MIN_PRICE || "0.01"),
    maxPrice: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MAX_PRICE || "0.99"),
    maxSpread: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MAX_SPREAD || "0.12"),
    maxDaysToExpiry: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MAX_DAYS_TO_EXPIRY || "45"),
    minTopBookDepth: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MIN_TOP_BOOK_DEPTH || "1000"),
    maxOutputMb: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MAX_OUTPUT_MB || "256"),
    minFreeGb: Number.parseFloat(process.env.BILL_POLYMARKET_CLOB_MIN_FREE_GB || "5"),
    requireExpiry: process.env.BILL_POLYMARKET_CLOB_REQUIRE_EXPIRY !== "false",
    requireSnapshotBook: process.env.BILL_POLYMARKET_CLOB_REQUIRE_SNAPSHOT_BOOK !== "false",
    tokenIds: [],
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--snapshot" && next) opts.snapshot = path.resolve(next), i += 1;
    else if (arg === "--out-dir" && next) opts.outDir = path.resolve(next), i += 1;
    else if (arg === "--state-path" && next) opts.statePath = path.resolve(next), i += 1;
    else if (arg === "--duration-sec" && next) opts.durationSec = Number.parseInt(next, 10), i += 1;
    else if (arg === "--max-assets" && next) opts.maxAssets = Number.parseInt(next, 10), i += 1;
    else if (arg === "--terms" && next) opts.terms = next.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean), i += 1;
    else if (arg === "--min-price" && next) opts.minPrice = Number.parseFloat(next), i += 1;
    else if (arg === "--max-price" && next) opts.maxPrice = Number.parseFloat(next), i += 1;
    else if (arg === "--max-spread" && next) opts.maxSpread = Number.parseFloat(next), i += 1;
    else if (arg === "--max-days-to-expiry" && next) opts.maxDaysToExpiry = Number.parseFloat(next), i += 1;
    else if (arg === "--min-top-book-depth" && next) opts.minTopBookDepth = Number.parseFloat(next), i += 1;
    else if (arg === "--max-elig-frac" && next) opts.maxEligFrac = Number.parseFloat(next), i += 1;
    else if (arg === "--replay-jsonl" && next) opts.replayJsonl = path.resolve(next), i += 1;
    else if (arg === "--market-times" && next) opts.marketTimesPath = path.resolve(next), i += 1;
    else if (arg === "--labels" && next) opts.labelsPath = path.resolve(next), i += 1;
  }
  opts.maxEligFrac = Number.parseFloat(process.env.BILL_POLYMARKET_PR_MAX_ELIG_FRAC || String(DEFAULT_MAX_ELIG_FRAC));
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--max-elig-frac" && argv[i + 1]) opts.maxEligFrac = Number.parseFloat(argv[i + 1]);
  }
  if (!Number.isFinite(opts.maxEligFrac) || opts.maxEligFrac <= 0 || opts.maxEligFrac >= 1) opts.maxEligFrac = DEFAULT_MAX_ELIG_FRAC;
  if (!Number.isFinite(opts.durationSec) || opts.durationSec <= 0) opts.durationSec = 120;
  if (!Number.isFinite(opts.maxAssets) || opts.maxAssets <= 0) opts.maxAssets = 24;
  opts.captureBothSides = true;
  return opts;
}

// --- normalizeEvent / updateBookState: local copies (recorder's are not exported) ---
function topLevels(levels, sortDirection, limit = 8) {
  return (Array.isArray(levels) ? levels : [])
    .map((level) => ({ price: toNumber(level.price), size: toNumber(level.size) }))
    .filter((level) => level.price != null && level.size != null && level.price > 0 && level.price < 1 && level.size > 0)
    .sort((a, b) => sortDirection * (a.price - b.price))
    .slice(0, limit)
    .map((level) => ({ price: String(level.price), size: String(level.size) }));
}
function levelSummary(levels, sortDirection) {
  const normalized = (Array.isArray(levels) ? levels : [])
    .map((level) => ({ price: toNumber(level.price), size: toNumber(level.size) }))
    .filter((level) => level.price != null && level.size != null && level.price > 0 && level.price < 1 && level.size > 0)
    .sort((a, b) => sortDirection * (a.price - b.price));
  return normalized[0] || null;
}
function normalizeEvent(message) {
  const eventType = message.event_type || message.eventType || "unknown";
  const base = { localTs: new Date().toISOString(), eventType, market: message.market, assetId: message.asset_id, exchangeTs: message.timestamp };
  if (eventType === "book") return { ...base, bids: topLevels(message.bids, -1), asks: topLevels(message.asks, 1), hash: message.hash };
  if (eventType === "price_change") return { ...base, priceChanges: Array.isArray(message.price_changes) ? message.price_changes : [] };
  if (eventType === "best_bid_ask") return { ...base, bestBid: toNumber(message.best_bid), bestAsk: toNumber(message.best_ask), spread: toNumber(message.spread) };
  if (eventType === "last_trade_price") return { ...base, price: toNumber(message.price), size: toNumber(message.size), side: message.side, feeRateBps: toNumber(message.fee_rate_bps) };
  return { ...base, raw: message };
}
function updateBookState(bookState, record) {
  const assetId = record.assetId;
  if (!assetId) return;
  const current = bookState.get(assetId) || {};
  if (record.eventType === "book") {
    const bid = levelSummary(record.bids, -1);
    const ask = levelSummary(record.asks, 1);
    bookState.set(assetId, { ...current, assetId, bestBid: bid?.price, bidSize: bid?.size, bestAsk: ask?.price, askSize: ask?.size, spread: bid && ask ? Number((ask.price - bid.price).toFixed(6)) : undefined, lastBookLocalTs: record.localTs, lastExchangeTs: record.exchangeTs });
    return;
  }
  if (record.eventType === "best_bid_ask") {
    bookState.set(assetId, { ...current, assetId, bestBid: record.bestBid ?? current.bestBid, bestAsk: record.bestAsk ?? current.bestAsk, spread: record.spread ?? current.spread, lastBbaLocalTs: record.localTs, lastExchangeTs: record.exchangeTs });
    return;
  }
  if (record.eventType === "price_change") {
    for (const change of record.priceChanges || []) {
      const changeAsset = change.asset_id;
      if (!changeAsset) continue;
      const changeCurrent = bookState.get(changeAsset) || {};
      const bestBid = toNumber(change.best_bid);
      const bestAsk = toNumber(change.best_ask);
      bookState.set(changeAsset, { ...changeCurrent, assetId: changeAsset, bestBid: bestBid ?? changeCurrent.bestBid, bestAsk: bestAsk ?? changeCurrent.bestAsk, spread: bestBid != null && bestAsk != null ? Number((bestAsk - bestBid).toFixed(6)) : changeCurrent.spread, lastPriceChangeLocalTs: record.localTs, lastExchangeTs: record.exchangeTs });
    }
    return;
  }
  if (record.eventType === "last_trade_price") {
    bookState.set(assetId, { ...current, assetId, lastTradePrice: record.price, lastTradeSize: record.size, lastTradeSide: record.side, lastTradeLocalTs: record.localTs, lastExchangeTs: record.exchangeTs });
  }
}

/** Expand single-token selection into both outcome tokens of the same market. */
function expandToBothSides(rows, assets) {
  const byMarket = new Map();
  for (const row of rows) {
    const mid = row?.marketId || row?.market_id || row?.externalId;
    if (!mid) continue;
    if (!byMarket.has(mid)) byMarket.set(mid, []);
    byMarket.get(mid).push(row);
  }
  const expanded = new Map();
  for (const asset of assets) {
    // find the market this token belongs to via snapshot rows
    const match = [...byMarket.entries()].find(([, rs]) => rs.some((r) => r.clobTokenId === asset.tokenId));
    if (!match) {
      expanded.set(asset.tokenId, { ...asset, siblingTokenId: null });
      continue;
    }
    const [mid, rs] = match;
    const others = rs.filter((r) => r.clobTokenId !== asset.tokenId);
    const sibling = others[0] || null;
    expanded.set(asset.tokenId, {
      ...asset,
      marketId: mid,
      siblingTokenId: sibling ? sibling.clobTokenId : null,
      siblingQuestion: sibling ? (sibling.marketQuestion || sibling.eventTitle) : null,
    });
  }
  return Array.from(expanded.values());
}

async function loadJsonMaybe(p) {
  if (!p) return null;
  try {
    return JSON.parse(await fs.readFile(p, "utf8"));
  } catch {
    return null;
  }
}

function fracOf(marketId, nowMs, marketTimes) {
  const mt = marketTimes?.[String(marketId)] || marketTimes?.[marketId];
  if (!mt || !mt.start_ts || !mt.end_ts) return null;
  const start = Number(mt.start_ts);
  const end = Number(mt.end_ts);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
  const elapsed = nowMs - start;
  return Math.min(1, Math.max(0, elapsed / (end - start)));
}

/** Build a pre_resolution_book snapshot from current dual-token book state. */
function emitPreResolutionSnapshot(asset, bookState, nowMs, marketTimes, labels) {
  const upAssetId = asset.tokenId;
  const downAssetId = asset.siblingTokenId;
  if (!downAssetId) return null;
  const up = bookState.get(upAssetId);
  const down = bookState.get(downAssetId);
  if (!up || !down) return null;
  const upBid = toNumber(up.bestBid);
  const upAsk = toNumber(up.bestAsk);
  const downBid = toNumber(down.bestBid);
  const downAsk = toNumber(down.bestAsk);
  const upBidSize = toNumber(up.bidSize) ?? 0;
  const upAskSize = toNumber(up.askSize) ?? 0;
  const downBidSize = toNumber(down.bidSize) ?? 0;
  const downAskSize = toNumber(down.askSize) ?? 0;
  if (upBid == null || upAsk == null || downBid == null || downAsk == null) return null;
  if (upBid <= 0 || upAsk <= 0 || downBid <= 0 || downAsk <= 0) return null;
  const upDepth = upBidSize + upAskSize;
  const downDepth = downBidSize + downAskSize;
  const frac = fracOf(asset.marketId, nowMs, marketTimes);
  if (frac == null) {
    // No market-time context (live mode before resolver): emit with frac null, labelPending.
    return {
      localTs: new Date(nowMs).toISOString(),
      eventType: "pre_resolution_book",
      marketId: String(asset.marketId),
      upAssetId: String(upAssetId),
      downAssetId: String(downAssetId),
      upBestBid: upBid,
      upBestAsk: upAsk,
      downBestBid: downBid,
      downBestAsk: downAsk,
      upBidDepth: upBidSize,
      upAskDepth: upAskSize,
      downBidDepth: downBidSize,
      downAskDepth: downAskSize,
      upDepthImbalance: safeRatio(upBidSize, upAskSize),
      downDepthImbalance: safeRatio(downBidSize, downAskSize),
      avgSpread: (upAsk - upBid + (downAsk - downBid)) / 2,
      frac: null,
      labelPending: true,
    };
  }
  const label = labels ? labels[String(asset.marketId)] ?? labels[asset.marketId] : undefined;
  return {
    localTs: new Date(nowMs).toISOString(),
    eventType: "pre_resolution_book",
    marketId: String(asset.marketId),
    upAssetId: String(upAssetId),
    downAssetId: String(downAssetId),
    upBestBid: upBid,
    upBestAsk: upAsk,
    downBestBid: downBid,
    downBestAsk: downAsk,
    upBidDepth: upBidSize,
    upAskDepth: upAskSize,
    downBidDepth: downBidSize,
    downAskDepth: downAskSize,
    upDepthImbalance: safeRatio(upBidSize, upAskSize),
    downDepthImbalance: safeRatio(downBidSize, downAskSize),
    avgSpread: (upAsk - upBid + (downAsk - downBid)) / 2,
    frac: Number(frac.toFixed(6)),
    labelPending: label === undefined,
    target_up_win: label === undefined ? null : (label === 1 ? 1 : 0),
  };
}

function safeRatio(a, b) {
  const x = Number(a) || 0;
  const y = Number(b) || 0;
  const denom = x + y;
  if (denom <= 0) return null;
  return Number(((x - y) / denom).toFixed(6));
}

function marketMetaRecord(asset, marketTimes, labels) {
  const mt = marketTimes?.[String(asset.marketId)] || marketTimes?.[asset.marketId];
  const label = labels ? labels[String(asset.marketId)] ?? labels[asset.marketId] : undefined;
  return {
    localTs: new Date().toISOString(),
    eventType: "market_meta",
    marketId: String(asset.marketId),
    upAssetId: String(asset.tokenId),
    downAssetId: String(asset.siblingTokenId),
    question: asset.question || asset.siblingQuestion || null,
    start_ts: mt ? Number(mt.start_ts) : null,
    end_ts: mt ? Number(mt.end_ts) : null,
    target_up_win: label === undefined ? null : (label === 1 ? 1 : 0),
    labelPending: label === undefined,
  };
}

export async function runCapture(opts) {
  // Selection always uses the snapshot (it carries clobTokenId + market pairing).
  // In replay mode the replayJsonl is only the event stream used to reconstruct book state.
  const snapRaw = await fs.readFile(opts.snapshot, "utf8");
  const snapParsed = JSON.parse(snapRaw);
  const rows = Array.isArray(snapParsed) ? snapParsed : snapParsed.markets || snapParsed.rows || [];

  const selection = selectAssetsWithDiagnostics(rows, opts);
  const assets = expandToBothSides(rows, selection.assets);
  if (assets.length === 0) throw new Error("No CLOB tokens selected.");

  await fs.mkdir(opts.outDir, { recursive: true });
  await fs.mkdir(path.dirname(opts.statePath), { recursive: true });
  const marketTimes = await loadJsonMaybe(opts.marketTimesPath);
  const labels = await loadJsonMaybe(opts.labelsPath);
  const outPath = path.join(opts.outDir, `${dayStamp()}-preresolution-market-channel.jsonl`);

  const bookState = new Map();
  const records = [];
  // emit market_meta for join keys
  for (const asset of assets) {
    if (asset.siblingTokenId) records.push(marketMetaRecord(asset, marketTimes, labels));
  }

  const nowMs = Date.now();
  // offline replay: replay every record through normalize/update, then snapshot-eligible
  if (opts.replayJsonl) {
    const raw = await fs.readFile(opts.replayJsonl, "utf8");
    const lines = raw.split(/\n/).map((l) => l.trim()).filter(Boolean);
    for (const line of lines) {
      let parsed;
      try { parsed = JSON.parse(line); } catch { continue; }
      const entries = Array.isArray(parsed) ? parsed : [parsed];
      for (const e of entries) {
        const rec = normalizeEvent(e);
        if (rec.assetId) updateBookState(bookState, rec);
      }
    }
    // after replay, emit one pre_resolution_book snapshot per dual-side asset eligible by frac
    for (const asset of assets) {
      if (!asset.siblingTokenId) continue;
      const snap = emitPreResolutionSnapshot(asset, bookState, nowMs, marketTimes, labels);
      if (!snap) continue;
      if (marketTimes && snap.frac != null && snap.frac > opts.maxEligFrac) continue;
      records.push(snap);
    }
  } else {
    // live WS mode — same emit logic on a timer
    const ws = new WebSocket(WSS_URL, { handshakeTimeout: 15_000, perMessageDeflate: false });
    const deadline = nowMs + opts.durationSec * 1000;
    const emitTick = () => {
      const t = Date.now();
      for (const asset of assets) {
        if (!asset.siblingTokenId) continue;
        const snap = emitPreResolutionSnapshot(asset, bookState, t, marketTimes, labels);
        if (!snap) continue;
        if (marketTimes && snap.frac != null && snap.frac > opts.maxEligFrac) continue;
        records.push(snap);
      }
    };
    await new Promise((resolve) => {
      ws.on("open", () => {
        ws.send(JSON.stringify({
          assets_ids: assets.map((a) => a.tokenId),
          type: "market",
          custom_feature_enabled: true,
        }));
        setInterval(emitTick, 5_000).unref?.();
      });
      ws.on("message", (data) => {
        try {
          const parsed = JSON.parse(data.toString());
          const entries = Array.isArray(parsed) ? parsed : [parsed];
          for (const e of entries) {
            const rec = normalizeEvent(e);
            if (rec.assetId) updateBookState(bookState, rec);
          }
        } catch { /* ignore */ }
        if (Date.now() >= deadline) { ws.close(); resolve(); }
      });
      ws.on("error", () => { resolve(); });
      ws.on("close", () => resolve());
      setTimeout(resolve, opts.durationSec * 1000 + 1000).unref?.();
    });
  }

  await fs.appendFile(outPath, records.map((r) => JSON.stringify(r)).join("\n") + "\n", "utf8");
  const summary = {
    command: "polymarket-clob-preresolution-capture",
    researchOnly: true,
    writesOrders: false,
    touchesBroker: false,
    mode: opts.replayJsonl ? "offline-replay" : "live-ws",
    outPath,
    maxEligFrac: opts.maxEligFrac,
    dualSideAssets: assets.filter((a) => a.siblingTokenId).length,
    preResolutionSnapshots: records.filter((r) => r.eventType === "pre_resolution_book").length,
    marketMetaRecords: records.filter((r) => r.eventType === "market_meta").length,
    labelledSnapshots: records.filter((r) => r.eventType === "pre_resolution_book" && r.labelPending === false).length,
  };
  await fs.writeFile(opts.statePath, JSON.stringify(summary, null, 2) + "\n", "utf8");
  return summary;
}

export { parseArgs, DEFAULT_MAX_ELIG_FRAC };

// CLI entry
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  runCapture(parseArgs(process.argv.slice(2)))
    .then((s) => { console.log(JSON.stringify(s, null, 2)); })
    .catch((e) => { console.error(e instanceof Error ? e.message : String(e)); process.exitCode = 1; });
}
