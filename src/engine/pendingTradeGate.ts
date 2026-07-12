import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { StrategySignal } from "../domain.js";
import type { RegimeAnalysis } from "./strategyFusion.js";

export type PendingTradeStatus = "WAITING_CONFIRMATION" | "ARMED" | "FIRED" | "EXPIRED" | "BLOCKED";

export interface PendingTradeRecord {
  fingerprint: string;
  status: PendingTradeStatus;
  symbol: string;
  strategyId: string;
  side: StrategySignal["side"];
  session: RegimeAnalysis["session"];
  detectedAt: string;
  lastSeenAt: string;
  earliestFireAt: string;
  expiresAt: string;
  observations: number;
  initialEntry: number;
  lastEntry: number;
  initialConfidence: number;
  lastConfidence: number;
  reason: string;
  firedAt?: string;
}

export interface PendingTradeState {
  updatedAt: string;
  records: PendingTradeRecord[];
}

export interface PendingTradeGateDecision {
  allowed: boolean;
  action: "wait" | "fire" | "block";
  fingerprint: string;
  reason: string;
  record: PendingTradeRecord;
}

export interface PendingTradeGateOptions {
  path?: string;
  now?: Date;
  signal: StrategySignal;
  regime: RegimeAnalysis;
  signalTs: string;
  atrPoints: number;
  biasDirection?: "LONG" | "SHORT" | "FLAT" | null;
}

const DEFAULT_STATE_PATH = ".rumbling-hedge/state/pending-trades.json";
const NY_WAIT_MINUTES = 15;
const ASIA_LONDON_WAIT_MINUTES = 30;
const DEFAULT_EXPIRY_MINUTES_AFTER_READY = 30;
const MAX_CHASE_ATR = 0.6;
const MAX_ADVERSE_ATR = 0.75;

function statePath(path?: string): string {
  return resolve(path ?? process.env.BILL_PENDING_TRADE_STATE_PATH ?? DEFAULT_STATE_PATH);
}

function readState(pathname: string): PendingTradeState {
  if (!existsSync(pathname)) {
    return { updatedAt: new Date(0).toISOString(), records: [] };
  }

  try {
    const parsed = JSON.parse(readFileSync(pathname, "utf8")) as Partial<PendingTradeState>;
    return {
      updatedAt: typeof parsed.updatedAt === "string" ? parsed.updatedAt : new Date(0).toISOString(),
      records: Array.isArray(parsed.records) ? parsed.records as PendingTradeRecord[] : []
    };
  } catch {
    return { updatedAt: new Date(0).toISOString(), records: [] };
  }
}

function writeState(pathname: string, state: PendingTradeState): void {
  mkdirSync(dirname(pathname), { recursive: true });
  writeFileSync(pathname, `${JSON.stringify(state, null, 2)}\n`, "utf8");
}

function addMinutes(date: Date, minutes: number): Date {
  return new Date(date.getTime() + minutes * 60_000);
}

function waitMinutesForSession(session: RegimeAnalysis["session"]): number {
  return session === "asia" || session === "london" ? ASIA_LONDON_WAIT_MINUTES : NY_WAIT_MINUTES;
}

function barBucket(ts: string): string {
  const parsed = Date.parse(ts);
  if (!Number.isFinite(parsed)) return "unknown-bar";
  const bucketMs = 15 * 60_000;
  return new Date(Math.floor(parsed / bucketMs) * bucketMs).toISOString();
}

export function pendingTradeFingerprint(args: {
  signal: StrategySignal;
  regime: RegimeAnalysis;
  signalTs: string;
}): string {
  const { signal, regime, signalTs } = args;
  return [
    signal.symbol,
    signal.strategyId,
    signal.side,
    regime.session,
    barBucket(signalTs)
  ].join("|");
}

function expireOldRecords(records: PendingTradeRecord[], now: Date): PendingTradeRecord[] {
  return records.map((record) => {
    if ((record.status === "WAITING_CONFIRMATION" || record.status === "ARMED") && Date.parse(record.expiresAt) < now.getTime()) {
      return {
        ...record,
        status: "EXPIRED" as const,
        reason: "pending trade expired before confirmation/routing"
      };
    }
    return record;
  });
}

function movementCheck(record: PendingTradeRecord, signal: StrategySignal, atrPoints: number): string | null {
  const safeAtr = Number.isFinite(atrPoints) && atrPoints > 0 ? atrPoints : Math.max(Math.abs(record.initialEntry) * 0.0025, 1);
  const movement = signal.entry - record.initialEntry;
  const chased = record.side === "long" ? movement > safeAtr * MAX_CHASE_ATR : movement < -safeAtr * MAX_CHASE_ATR;
  const adverse = record.side === "long" ? movement < -safeAtr * MAX_ADVERSE_ATR : movement > safeAtr * MAX_ADVERSE_ATR;

  if (chased) return `entry moved too far without pullback (${Math.abs(movement).toFixed(2)}pts)`;
  if (adverse) return `bias weakened during wait (${Math.abs(movement).toFixed(2)}pts adverse)`;
  return null;
}

function createRecord(options: PendingTradeGateOptions, fingerprint: string, now: Date): PendingTradeRecord {
  const waitMinutes = waitMinutesForSession(options.regime.session);
  const earliestFireAt = addMinutes(now, waitMinutes);
  const expiresAt = addMinutes(earliestFireAt, DEFAULT_EXPIRY_MINUTES_AFTER_READY);
  return {
    fingerprint,
    status: "WAITING_CONFIRMATION",
    symbol: options.signal.symbol,
    strategyId: options.signal.strategyId,
    side: options.signal.side,
    session: options.regime.session,
    detectedAt: now.toISOString(),
    lastSeenAt: now.toISOString(),
    earliestFireAt: earliestFireAt.toISOString(),
    expiresAt: expiresAt.toISOString(),
    observations: 1,
    initialEntry: options.signal.entry,
    lastEntry: options.signal.entry,
    initialConfidence: options.signal.confidence,
    lastConfidence: options.signal.confidence,
    reason: `waiting ${waitMinutes}m for ${options.regime.session} confirmation`
  };
}

function biasBlockReason(signal: StrategySignal, biasDirection?: "LONG" | "SHORT" | "FLAT" | null): string | null {
  if (!biasDirection) return null;
  if (biasDirection === "FLAT") return "pre-trade bias is FLAT";
  const expectedSide = biasDirection === "LONG" ? "long" : "short";
  return signal.side === expectedSide
    ? null
    : `signal side ${signal.side} conflicts with pre-trade bias ${biasDirection}`;
}

export function evaluatePendingTradeGate(options: PendingTradeGateOptions): PendingTradeGateDecision {
  const now = options.now ?? new Date();
  const pathname = statePath(options.path);
  const fingerprint = pendingTradeFingerprint(options);
  const state = readState(pathname);
  state.records = expireOldRecords(state.records, now);
  const biasReason = biasBlockReason(options.signal, options.biasDirection);

  const index = state.records.findIndex((record) => record.fingerprint === fingerprint);
  if (index === -1) {
    const record = createRecord(options, fingerprint, now);
    if (biasReason) {
      record.status = "BLOCKED";
      record.reason = biasReason;
    }
    state.records.push(record);
    state.updatedAt = now.toISOString();
    writeState(pathname, state);
    return {
      allowed: false,
      action: biasReason ? "block" : "wait",
      fingerprint,
      reason: record.reason,
      record
    };
  }

  const record = state.records[index]!;

  if (record.status === "FIRED") {
    return {
      allowed: false,
      action: "block",
      fingerprint,
      reason: "duplicate signal already fired for this window",
      record
    };
  }

  if (record.status === "EXPIRED" || record.status === "BLOCKED") {
    return {
      allowed: false,
      action: "block",
      fingerprint,
      reason: record.reason,
      record
    };
  }

  const movementReason = movementCheck(record, options.signal, options.atrPoints);
  const updated: PendingTradeRecord = {
    ...record,
    lastSeenAt: now.toISOString(),
    observations: record.observations + 1,
    lastEntry: options.signal.entry,
    lastConfidence: options.signal.confidence
  };

  if (biasReason) {
    updated.status = "BLOCKED";
    updated.reason = biasReason;
    state.records[index] = updated;
    state.updatedAt = now.toISOString();
    writeState(pathname, state);
    return {
      allowed: false,
      action: "block",
      fingerprint,
      reason: biasReason,
      record: updated
    };
  }

  if (movementReason) {
    updated.status = "BLOCKED";
    updated.reason = movementReason;
    state.records[index] = updated;
    state.updatedAt = now.toISOString();
    writeState(pathname, state);
    return {
      allowed: false,
      action: "block",
      fingerprint,
      reason: movementReason,
      record: updated
    };
  }

  if (now.getTime() < Date.parse(updated.earliestFireAt)) {
    updated.reason = `waiting until ${updated.earliestFireAt}`;
    state.records[index] = updated;
    state.updatedAt = now.toISOString();
    writeState(pathname, state);
    return {
      allowed: false,
      action: "wait",
      fingerprint,
      reason: updated.reason,
      record: updated
    };
  }

  updated.status = "ARMED";
  updated.reason = "wait elapsed and signal still confirms";
  state.records[index] = updated;
  state.updatedAt = now.toISOString();
  writeState(pathname, state);
  return {
    allowed: true,
    action: "fire",
    fingerprint,
    reason: updated.reason,
    record: updated
  };
}

export function markPendingTradeFired(args: {
  path?: string;
  fingerprint: string;
  now?: Date;
  reason?: string;
}): PendingTradeRecord | null {
  const now = args.now ?? new Date();
  const pathname = statePath(args.path);
  const state = readState(pathname);
  const index = state.records.findIndex((record) => record.fingerprint === args.fingerprint);
  if (index === -1) return null;

  const updated: PendingTradeRecord = {
    ...state.records[index]!,
    status: "FIRED",
    firedAt: now.toISOString(),
    reason: args.reason ?? "routed after pending-trade confirmation"
  };
  state.records[index] = updated;
  state.updatedAt = now.toISOString();
  writeState(pathname, state);
  return updated;
}
