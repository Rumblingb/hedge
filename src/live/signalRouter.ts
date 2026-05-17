/**
 * signalRouter.ts — Routes ORB signals to ALL accounts with scale-out TP
 * Reads pre_trade_decision.json for go/no-go, account isolation, and size.
 *
 * Topstep $100K → ProjectX adapter (5-step: entry + SL + TP1/TP2/TP3)
 * FundedNext $100K → PickMyTrade webhook
 * LucidFlex $50K × 2 → PickMyTrade webhook
 *
 * Scale-out TP (backtested best, weekend 2026-05-15):
 *   50% @ +50pts (limit), 30% @ +100pts (limit), 20% trail (30pt from +100)
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const DECISION_PATH = join(process.env.HOME || "~", ".rumbling-hedge/state/pre_trade_decision.json");

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
  stagger_min: number;
  warnings: string[];
}

function readPreTradeDecision(): PreTradeDecision | null {
  try {
    if (!existsSync(DECISION_PATH)) return null;
    const raw = readFileSync(DECISION_PATH, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

const PMT_WEBHOOKS = [
  { url: 'https://api.pickmytrade.trade/v2/add-trade-data-latest?t=16754', token: 'dgMK0fhqIbfSuZs4JTDvKg', label: 'FundedNext $100K' },
  { url: 'https://api.pickmytrade.trade/v2/add-trade-data-latest?t=16759', token: 'OTPJQ0Ok4SFbpaWFHFeAKg', label: 'LucidFlex $50K × 2' },
];

const TOPSTEP_USER = process.env.RH_TOPSTEP_USERNAME || 'vishar.rumbling@gmail.com';
const TOPSTEP_KEY = process.env.RH_TOPSTEP_API_KEY || '';
const TOPSTEP_BASE = 'https://api.topstepx.com';

let _topstepToken: string | null = null;

async function getTopstepToken(): Promise<string> {
  if (_topstepToken) return _topstepToken;
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
  if (process.env.RH_TOPSTEP_ACCOUNT_ID) {
    const match = process.env.RH_TOPSTEP_ACCOUNT_ID.match(/(\d+)$/);
    if (match) return Number(match[1]);
    return Number(process.env.RH_TOPSTEP_ACCOUNT_ID);
  }
  return 83651531;
}

export interface OrbSignal {
  ticker: string;
  action: 'buy' | 'sell' | 'exit';
  quantity: number;
  price?: number;
  entryPrice?: number;
  stopLoss?: number;
  takeProfit?: number;
}

class SignalRouter {
  async route(signal: OrbSignal): Promise<void> {
    // 1. Read pre-trade decision
    const decision = readPreTradeDecision();
    if (!decision) {
      console.warn('[SignalRouter] No pre-trade decision found — run pre_trade_check.py first');
    } else if (decision.decision === 'NO_TRADE') {
      console.log(`[SignalRouter] 🛑 Blocked by pre-trade: ${decision.conviction} ${decision.direction}`);
      return;
    } else {
      console.log(`[SignalRouter] ✅ Pre-trade OK: ${decision.decision} ${decision.direction} (${decision.contracts} MNQ)`);
      if (signal.action === 'exit') {
        console.log(`[SignalRouter] Exit signal received — routing to all accounts`);
      }
    }

    console.log(`\n[SignalRouter] Routing: ${signal.action} ${signal.quantity} ${signal.ticker}`);

    // 2. PickMyTrade — LucidFlex + FundedNext with IDENTICAL TP/SL
    //    Both accounts must receive exactly the same trade params to avoid self-hedging flag
    const pmtQuantity = String(signal.quantity);
    const pmtTP = signal.takeProfit ?? (signal.entryPrice ? Math.round(signal.entryPrice + 50) : 0);
    const pmtSL = signal.stopLoss ?? (signal.entryPrice ? Math.round(signal.entryPrice - 30) : 0);
    const pmtPrice = signal.price ? String(signal.price) : '0';

    for (const wh of PMT_WEBHOOKS) {
      try {
        const body = JSON.stringify({
          symbol: signal.ticker,
          strategy_name: 'orb-breakout',
          data: signal.action === 'exit' ? 'exit' : signal.action,
          quantity: pmtQuantity,
          price: pmtPrice,
          tp: pmtTP,
          sl: pmtSL,
          token: wh.token,
          pyramid: false,
          same_direction_ignore: false,
          reverse_order_close: false,
        });
        const res = await fetch(wh.url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body,
        });
        const text = await res.text();
        console.log(`[SignalRouter] ${wh.label}: ${res.ok ? '✅' : '❌'} ${text.slice(0, 60)}`);
      } catch (e: any) {
        console.error(`[SignalRouter] ${wh.label}: ❌ ${e.message?.slice(0, 60)}`);
      }
    }

    // 3. TopstepX direct API with scale-out TP
    try {
      const token = await getTopstepToken();
      const accId = await getTopstepAccountId();
      await this.placeTopstepScaleOut(token, accId, signal);
    } catch (e: any) {
      console.error(`[SignalRouter] Topstep error: ${e.message?.slice(0, 80)}`);
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
        side: tpSide, size: q3, trailPrice: 30,
        limitPrice: null, stopPrice: null
      });
    }
  }

  private async topstepOrder(token: string, accId: number, body: any): Promise<Response> {
    const res = await fetch(`${TOPSTEP_BASE}/api/Order/place`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    console.log(`[SignalRouter] Topstep ${body.type} ${body.side} q=${body.size}: ${res.ok ? '✅' : '❌'} ${text.slice(0, 80)}`);
    return res;
  }
}

export const signalRouter = new SignalRouter();
export default SignalRouter;
