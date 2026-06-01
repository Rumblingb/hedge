/**
 * signalRouter.ts — Routes signals to ALL accounts
 *
 * Topstep $100K → TopstepX API direct (scale-out TP: entry + SL + 3 TP brackets)
 * LucidFlex $50K × 2 → PickMyTrade webhook v2 (dollar SL/TP from signal)
 * FundedNext $100K → PickMyTrade webhook v2 (dollar SL/TP from signal)
 *
 * Scale-out TP (backtested best, weekend 2026-05-15):
 *   50% @ +50pts (limit), 30% @ +100pts (limit), 20% trail (30pt from +100)
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const DECISION_PATH = process.env.BILL_PRE_TRADE_DECISION_PATH
  ?? join(process.env.HOME || "~", ".rumbling-hedge/state/pre_trade_decision.json");
const MAX_DECISION_AGE_MS = Number(process.env.BILL_PRE_TRADE_MAX_AGE_MS ?? 10 * 60 * 1000);
const MAX_ROUTER_CONTRACTS = Number(process.env.BILL_SIGNAL_ROUTER_MAX_CONTRACTS ?? 1);
const STATE_DIR = process.env.BILL_STATE_DIR ?? join(process.cwd(), ".rumbling-hedge/state");

interface PreTradeDecision {
  timestamp: string;
  decision: "TRADE" | "REDUCED" | "NO_TRADE";
  direction: "LONG" | "SHORT" | "FLAT";
  conviction: "HIGH" | "MEDIUM" | "LOW";
  contracts: number;
  sl_pts: number;
  tp1_pts: number;
  tp2_pts: number;
  trail_pts: number;
  account_split: Record<string, number>;
  warnings: string[];
  insideDayProbability?: number;
  macroContext?: any;
}

export function readPreTradeDecision(path = DECISION_PATH): PreTradeDecision | null {
  try {
    if (!existsSync(path)) return null;
    return JSON.parse(readFileSync(path, "utf8"));
  } catch { return null; }
}

function envTrue(name: string): boolean {
  return /^(1|true|yes|on)$/i.test(String(process.env[name] ?? "").trim());
}

function envFlag(env: NodeJS.ProcessEnv, name: string): boolean {
  return /^(1|true|yes|on)$/i.test(String(env[name] ?? "").trim());
}

export function billTradingDateKey(now = new Date(), timeZone = process.env.BILL_TRADING_TIMEZONE || "Europe/London"): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;
  if (!year || !month || !day) {
    return now.toISOString().slice(0, 10);
  }
  return `${year}-${month}-${day}`;
}

export function todayDailyPlanPath(env: NodeJS.ProcessEnv = process.env, now = new Date()): string {
  const day = billTradingDateKey(now, env.BILL_TRADING_TIMEZONE || "Europe/London");
  return env.BILL_DAILY_PLAN_PATH
    ?? `/Users/brain/Documents/memorybrain/Agent-Hermes/daily/${day}-bill-trading-plan.md`;
}

function machineControlLines(text: string): Set<string> {
  return new Set(text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
}

function readTextSafe(path: string): string {
  try {
    if (!existsSync(path)) return "";
    return readFileSync(path, "utf8");
  } catch {
    return "";
  }
}

function readJsonSafe(path: string): any {
  try {
    if (!existsSync(path)) return {};
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return {};
  }
}

export interface SignalRouterGateInputs {
  env?: NodeJS.ProcessEnv;
  dailyPlanText?: string;
  monitor?: any;
  liveReadinessGate?: any;
  maxContracts?: number;
  now?: Date;
}

export function evaluateSignalRouterExecutionGate(
  signal: OrbSignal,
  inputs: SignalRouterGateInputs = {}
): { ok: boolean; reason?: string; blockers: string[] } {
  const env = inputs.env ?? process.env;
  const maxContracts = inputs.maxContracts ?? MAX_ROUTER_CONTRACTS;
  const dailyPlanText = inputs.dailyPlanText ?? readTextSafe(todayDailyPlanPath(env, inputs.now));
  const monitor = inputs.monitor ?? readJsonSafe(join(env.BILL_STATE_DIR ?? STATE_DIR, "topstep-100k-monitor.latest.json"));
  const liveReadinessGate = inputs.liveReadinessGate ?? readJsonSafe(join(env.BILL_STATE_DIR ?? STATE_DIR, "live-readiness-gate.latest.json"));
  const controlLines = machineControlLines(dailyPlanText);
  const blockers: string[] = [];

  if (!envFlag(env, "BILL_SIGNAL_ROUTER_ENABLED")) {
    blockers.push("BILL_SIGNAL_ROUTER_ENABLED is not true");
  }
  if (!envFlag(env, "BILL_SIGNAL_ROUTER_LEGACY_FANOUT_ENABLED")) {
    blockers.push("BILL_SIGNAL_ROUTER_LEGACY_FANOUT_ENABLED is not true");
  }
  if (!envFlag(env, "BILL_ENABLE_FUTURES_DEMO_EXECUTION")) {
    blockers.push("BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true");
  }
  if (envFlag(env, "RH_TOPSTEP_READ_ONLY")) {
    blockers.push("RH_TOPSTEP_READ_ONLY is true");
  }
  if (envFlag(env, "RH_LIVE_EXECUTION_ENABLED")) {
    blockers.push("live execution flag is enabled; SignalRouter is demo-only");
  }
  if (!dailyPlanText) {
    blockers.push("daily plan missing or unreadable");
  } else {
    if (dailyPlanText.includes("No new Bill/Hermes orders approved")) {
      blockers.push("daily plan explicitly says no new Bill/Hermes orders approved");
    }
    if (!controlLines.has("BILL_ROUTE_APPROVAL: APPROVED")) {
      blockers.push("daily plan lacks BILL_ROUTE_APPROVAL: APPROVED");
    }
    if (!controlLines.has("BROKER_RECONCILIATION: GREEN")) {
      blockers.push("daily plan lacks BROKER_RECONCILIATION: GREEN");
    }
  }
  if (monitor?.status !== "OK") {
    blockers.push(`Topstep monitor is not OK: ${monitor?.status ?? "missing"}`);
  }
  if ((monitor?.hard_blockers ?? []).length > 0) {
    blockers.push("Topstep monitor has hard blockers");
  }
  if ((monitor?.warnings ?? []).length > 0) {
    blockers.push("Topstep monitor warnings require reconciliation");
  }
  if (liveReadinessGate?.readyForDemoExpansion !== true) {
    blockers.push("live-readiness gate does not allow demo expansion");
  }
  if (!Number.isFinite(signal.quantity) || signal.quantity < 1 || signal.quantity > maxContracts) {
    blockers.push(`signal quantity ${signal.quantity} outside router cap ${maxContracts}`);
  }
  if (signal.action !== "exit" && (!Number.isFinite(signal.stopLoss) || !Number.isFinite(signal.takeProfit))) {
    blockers.push("entry signal missing explicit stopLoss/takeProfit");
  }

  return { ok: blockers.length === 0, reason: blockers[0], blockers };
}

function executionGate(signal: OrbSignal): { ok: boolean; reason?: string } {
  const decision = evaluateSignalRouterExecutionGate(signal);
  if (!decision.ok) {
    return { ok: false, reason: decision.blockers.join("; ") };
  }
  return { ok: true };
}

// ── PickMyTrade v2 — single webhook with multiple_accounts array ──

interface PickMyTradeWebhook {
  url: string;
  token: string;
  label: string;
  accounts?: Array<{
    token: string;
    account_id: string;
    risk_percentage?: number;
    quantity_multiplier?: number;
  }>;
}

function loadPickMyTradeWebhooks(): PickMyTradeWebhook[] {
  const raw = process.env.BILL_PICKMYTRADE_WEBHOOKS_JSON;
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item: any) => ({
        url: String(item?.url ?? ""),
        token: String(item?.token ?? ""),
        label: String(item?.label ?? "PickMyTrade"),
        accounts: item?.accounts,
      }))
      .filter((item) => item.url.startsWith("https://") && item.token.length > 0);
  } catch {
    return [];
  }
}

// ── Topstep ──

const TOPSTEP_USER = process.env.RH_TOPSTEP_USERNAME || '';
const TOPSTEP_KEY = process.env.RH_TOPSTEP_API_KEY || '';
const TOPSTEP_BASE = 'https://api.topstepx.com';

let _topstepToken: string | null = null;

async function getTopstepToken(): Promise<string> {
  if (_topstepToken) return _topstepToken;
  if (!TOPSTEP_USER || !TOPSTEP_KEY) throw new Error("Topstep credentials are not configured");
  const res = await fetch(`${TOPSTEP_BASE}/api/Auth/loginKey`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userName: TOPSTEP_USER, apiKey: TOPSTEP_KEY })
  });
  const data: any = await res.json();
  if (!data?.token) throw new Error('Topstep auth failed');
  _topstepToken = data.token;
  return data.token;
}

async function getTopstepAccountId(): Promise<number> {
  const raw = process.env.RH_TOPSTEP_ACCOUNT_ID;
  if (!raw) throw new Error('RH_TOPSTEP_ACCOUNT_ID not set — export it explicitly');
  const match = raw.match(/(\d+)$/);
  if (match) return Number(match[1]);
  return Number(raw);
}

// ── Shared types ──

export interface OrbSignal {
  ticker: string;
  action: 'buy' | 'sell' | 'exit';
  quantity: number;
  price?: number;
  entryPrice?: number;
  stopLoss?: number;
  takeProfit?: number;
}

export function validatePreTradeDecision(
  decision: PreTradeDecision | null,
  signal: OrbSignal,
  now = new Date()
): { ok: boolean; reason?: string } {
  if (!decision) return { ok: false, reason: "missing pre-trade decision" };
  if (decision.decision !== "TRADE") return { ok: false, reason: `pre-trade decision is ${decision.decision}` };
  if (decision.direction !== "LONG" && decision.direction !== "SHORT") {
    return { ok: false, reason: `pre-trade direction is ${decision.direction}` };
  }
  if (signal.action !== "exit") {
    const expectedAction = decision.direction === "LONG" ? "buy" : "sell";
    if (signal.action !== expectedAction) {
      return { ok: false, reason: `signal action ${signal.action} conflicts with ${decision.direction}` };
    }
  }
  const ts = Date.parse(decision.timestamp);
  if (!Number.isFinite(ts)) return { ok: false, reason: "pre-trade timestamp is invalid" };
  const ageMs = now.getTime() - ts;
  if (ageMs < -60_000) return { ok: false, reason: "pre-trade timestamp is in the future" };
  if (ageMs > MAX_DECISION_AGE_MS) return { ok: false, reason: "pre-trade decision is stale" };
  if (!Number.isFinite(decision.contracts) || decision.contracts < 1) {
    return { ok: false, reason: "pre-trade contracts are invalid" };
  }
  if (signal.quantity > decision.contracts) {
    return { ok: false, reason: `signal quantity ${signal.quantity} exceeds pre-trade size ${decision.contracts}` };
  }
  if (decision.warnings.some((warning) => /STALE DATA|Market closed|force/i.test(warning))) {
    return { ok: false, reason: "pre-trade decision contains blocking warning" };
  }
  return { ok: true };
}

// ── Signal Router ──

class SignalRouter {
  async route(signal: OrbSignal): Promise<void> {
    const execution = executionGate(signal);
    if (!execution.ok) {
      console.warn(`[SignalRouter] Shadow-only: ${execution.reason}`);
      return;
    }

    const decision = readPreTradeDecision();
    const preTrade = validatePreTradeDecision(decision, signal);
    if (!preTrade.ok) {
      console.warn(`[SignalRouter] Blocked by pre-trade gate: ${preTrade.reason}`);
      return;
    }
    console.log(`[SignalRouter] Pre-trade OK: ${decision!.decision} ${decision!.direction} (${decision!.contracts} MNQ)`);
    if (signal.action === 'exit') {
      console.log(`[SignalRouter] Exit signal — routing to all accounts`);
    }
    console.log(`\n[SignalRouter] Routing: ${signal.action} ${signal.quantity} ${signal.ticker}`);

    // 1. PickMyTrade v2 — sends dollar SL/TP from strategy signal
    await this.routePickMyTrade(signal);

    // 2. TopstepX direct API with scale-out TP
    try {
      const token = await getTopstepToken();
      const accId = await getTopstepAccountId();
      await this.placeTopstepScaleOut(token, accId, signal);
    } catch (e: any) {
      console.error(`[SignalRouter] Topstep error: ${e.message?.slice(0, 80)}`);
    }
  }

  private async routePickMyTrade(signal: OrbSignal): Promise<void> {
    if (!envTrue("BILL_PICKMYTRADE_ENABLED")) {
      console.log(`[SignalRouter] PickMyTrade disabled — skipping`);
      return;
    }

    const webhooks = loadPickMyTradeWebhooks();
    if (webhooks.length === 0) {
      console.log(`[SignalRouter] No PickMyTrade webhooks configured — skipping`);
      return;
    }

    for (const wh of webhooks) {
      try {
          // Dollar SL/TP — calculated from entry price for MNQ ($5/pt)
          const pricePerPoint = 5;
          const slDollars = (signal.stopLoss && signal.entryPrice)
            ? Math.round(Math.abs(signal.entryPrice - signal.stopLoss) * pricePerPoint * signal.quantity)
            : 0;
          const tpDollars = (signal.takeProfit && signal.entryPrice)
            ? Math.round(Math.abs(signal.entryPrice - signal.takeProfit) * pricePerPoint * signal.quantity)
            : 0;
          const baseBody: any = {
          symbol: signal.ticker,
          strategy_name: "hermes-agentic",
          date: new Date().toISOString(),
          data: signal.action === 'exit' ? 'exit' : signal.action,
          quantity: String(signal.quantity),
          price: signal.price ? String(signal.price) : "0",
          tp: 0,
          sl: 0,
          percentage_tp: 0,
          dollar_tp: tpDollars,
          percentage_sl: 0,
          dollar_sl: slDollars,
          trail: 0,
          trail_stop: 0,
          trail_trigger: 0,
          trail_freq: 0,
          update_tp: false,
          update_sl: false,
          breakeven: 0,
          breakeven_offset: 0,
          token: wh.token,
          pyramid: true,
          same_direction_ignore: false,
          reverse_order_close: false,
        };

        // If accounts array is provided, use multiple_accounts format
        if (wh.accounts && wh.accounts.length > 0) {
          baseBody.multiple_accounts = wh.accounts.map((a) => ({
            token: a.token,
            account_id: a.account_id,
            risk_percentage: a.risk_percentage ?? 0,
            quantity_multiplier: a.quantity_multiplier ?? 1,
          }));
        }

        const res = await fetch(wh.url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(baseBody),
        });
        const text = await res.text();
        // Rate limit protection
        if (res.status === 429) {
          console.warn(`[SignalRouter] ${wh.label}: ⏳ rate limited — retrying in 3s`);
          await new Promise((r) => setTimeout(r, 3000));
          const retry = await fetch(wh.url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(baseBody),
          });
          const retryText = await retry.text();
          console.log(`[SignalRouter] ${wh.label}: ${retry.ok ? '✅' : '❌'} ${retryText.slice(0, 80)}`);
        } else {
          console.log(`[SignalRouter] ${wh.label}: ${res.ok ? '✅' : '❌'} ${text.slice(0, 80)}`);
        }
      } catch (e: any) {
        console.error(`[SignalRouter] ${wh.label}: ❌ ${e.message?.slice(0, 80)}`);
      }
    }
  }

  private async placeTopstepScaleOut(token: string, accId: number, signal: OrbSignal): Promise<void> {
    if (signal.action === 'exit') {
      await this.topstepOrder(token, accId, { accountId: accId, contractId: signal.ticker, type: 'Market', side: 'Sell', size: signal.quantity, limitPrice: null, stopPrice: null, trailPrice: null });
      return;
    }

    // Entry
    const entryRes = await this.topstepOrder(token, accId, {
      accountId: accId, contractId: signal.ticker, type: 'Market',
      side: signal.action === 'buy' ? 'Buy' : 'Sell', size: signal.quantity,
      limitPrice: null, stopPrice: null, trailPrice: null
    });
    if (!entryRes.ok) return;

    // SL — full size
    if (signal.stopLoss) {
      const stopSide = signal.action === 'buy' ? 'Sell' : 'Buy';
      await this.topstepOrder(token, accId, {
        accountId: accId, contractId: signal.ticker, type: 'Stop',
        side: stopSide, size: signal.quantity,
        stopPrice: signal.stopLoss, limitPrice: null, trailPrice: null
      });
    }

    // Scale-out TP
    if (!signal.entryPrice) return;
    const tpSide = signal.action === 'buy' ? 'Sell' : 'Buy';
    const tp1 = signal.entryPrice + (signal.action === 'buy' ? 50 : -50);
    const tp2 = signal.entryPrice + (signal.action === 'buy' ? 100 : -100);
    const q1 = Math.max(1, Math.floor(signal.quantity * 0.5));
    const q2 = Math.max(1, Math.floor(signal.quantity * 0.3));
    const q3 = Math.max(0, signal.quantity - q1 - q2);

    await this.topstepOrder(token, accId, {
      accountId: accId, contractId: signal.ticker, type: 'Limit',
      side: tpSide, size: q1, limitPrice: tp1, stopPrice: null, trailPrice: null
    });

    await this.topstepOrder(token, accId, {
      accountId: accId, contractId: signal.ticker, type: 'Limit',
      side: tpSide, size: q2, limitPrice: tp2, stopPrice: null, trailPrice: null
    });

    if (q3 > 0) {
      await this.topstepOrder(token, accId, {
        accountId: accId, contractId: signal.ticker, type: 'TrailingStop',
        side: tpSide, size: q3, stopPrice: null, limitPrice: null,
        trailPrice: tp2 + (signal.action === 'buy' ? 30 : -30)
      });
    }
  }

  private async topstepOrder(token: string, accId: number, body: any): Promise<Response> {
    const res = await fetch(`${TOPSTEP_BASE}/api/Trading/placeOrder`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    if (!res.ok) {
      console.error(`[TopstepOrder] ❌ ${body.type} ${body.side} ${body.size}: ${text.slice(0, 80)}`);
    }
    return res;
  }
}

export const signalRouter = new SignalRouter();
export default SignalRouter;
