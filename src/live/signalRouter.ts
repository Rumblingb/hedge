/**
 * signalRouter.ts — Routes ORB signals to ALL accounts with scale-out TP
 * Topstep $100K → ProjectX adapter (5-step: entry + SL + TP1/TP2/TP3)
 * FundedNext $100K → PickMyTrade webhook
 * LucidFlex $50K × 2 → PickMyTrade webhook
 *
 * Scale-out TP (backtested best, weekend 2026-05-15):
 *   50% @ +50pts (limit), 30% @ +100pts (limit), 20% trail (30pt from +100)
 */

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

// Try to resolve the correct Topstep account ID
// env RH_TOPSTEP_ACCOUNT_ID takes priority, then /api/accounts, then hardcoded fallback
async function getTopstepAccountId(token: string): Promise<number> {
  if (process.env.RH_TOPSTEP_ACCOUNT_ID) return Number(process.env.RH_TOPSTEP_ACCOUNT_ID);
  try {
    const res = await fetch(`${TOPSTEP_BASE}/api/accounts`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      const accounts: any = await res.json();
      if (Array.isArray(accounts) && accounts.length > 0) return accounts[0].id;
    }
  } catch {}
  return 83651531; // fallback from env
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
    console.log(`\n[SignalRouter] Routing: ${signal.action} ${signal.quantity} ${signal.ticker}`);

    // 1. PickMyTrade webhooks (LucidFlex + FundedNext)
    for (const wh of PMT_WEBHOOKS) {
      try {
        const body = JSON.stringify({
          symbol: signal.ticker, strategy_name: 'orb-breakout',
          date: new Date().toISOString(),
          data: signal.action === 'exit' ? 'exit' : signal.action,
          quantity: String(signal.quantity),
          price: signal.price ? String(signal.price) : '0',
          tp: signal.takeProfit ?? 0, sl: signal.stopLoss ?? 0,
          token: wh.token, pyramid: false,
          same_direction_ignore: false, reverse_order_close: false,
        });
        const res = await fetch(wh.url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body });
        const text = await res.text();
        console.log(`[SignalRouter] ${wh.label}: ✅ (${res.status})`);
      } catch (e: any) {
        console.error(`[SignalRouter] ${wh.label}: ❌ ${e.message?.slice(0, 60)}`);
      }
    }

    // 2. TopstepX direct API with scale-out TP
    try {
      const token = await getTopstepToken();
      const accId = await getTopstepAccountId(token);
      await this.placeTopstepScaleOut(token, accId, signal);
    } catch (e: any) {
      console.error(`[SignalRouter] Topstep error: ${e.message?.slice(0, 80)}`);
    }
  }

  private async placeTopstepScaleOut(token: string, accId: number, signal: OrbSignal): Promise<void> {
    if (signal.action === 'exit') {
      await this.topstepOrder(token, accId, { accountId: accId, contractId: signal.ticker, type: 'Market', side: 'Sell', size: signal.quantity, limitPrice: null, stopPrice: null, trailPrice: null });
      console.log(`[SignalRouter] Topstep exit sent`);
      return;
    }

    // Step 1: Market entry
    const entryRes = await this.topstepOrder(token, accId, {
      accountId: accId, contractId: signal.ticker, type: 'Market',
      side: signal.action === 'buy' ? 'Buy' : 'Sell', size: signal.quantity,
      limitPrice: null, stopPrice: null, trailPrice: null
    });
    console.log(`[SignalRouter] Topstep entry: ${entryRes.ok ? '✅' : '❌'} (${entryRes.status})`);
    if (!entryRes.ok) return;

    // Step 2: Stop-loss — full size, opposite side
    if (signal.stopLoss) {
      const stopSide = signal.action === 'buy' ? 'Sell' : 'Buy';
      await this.topstepOrder(token, accId, {
        accountId: accId, contractId: signal.ticker, type: 'Stop',
        side: stopSide, size: signal.quantity,
        stopPrice: signal.stopLoss, limitPrice: null, trailPrice: null
      });
    }

    // Scale-out TP: 50%@+50, 30%@+100, 20% trail(30pt)
    if (!signal.entryPrice) return;
    const tpSide = signal.action === 'buy' ? 'Sell' : 'Buy';
    const tp1 = signal.entryPrice + (signal.action === 'buy' ? 50 : -50);
    const tp2 = signal.entryPrice + (signal.action === 'buy' ? 100 : -100);
    const q1 = Math.max(1, Math.floor(signal.quantity * 0.5));
    const q2 = Math.max(1, Math.floor(signal.quantity * 0.3));
    const q3 = Math.max(0, signal.quantity - q1 - q2);

    // TP1: 50% at +50pts
    await this.topstepOrder(token, accId, {
      accountId: accId, contractId: signal.ticker, type: 'Limit',
      side: tpSide, size: q1, limitPrice: tp1, stopPrice: null, trailPrice: null
    });

    // TP2: 30% at +100pts
    await this.topstepOrder(token, accId, {
      accountId: accId, contractId: signal.ticker, type: 'Limit',
      side: tpSide, size: q2, limitPrice: tp2, stopPrice: null, trailPrice: null
    });

    // TP3: 20% trailing stop
    if (q3 > 0) {
      const trailStart = signal.entryPrice + (signal.action === 'buy' ? 100 : -100);
      await this.topstepOrder(token, accId, {
        accountId: accId, contractId: signal.ticker, type: 'TrailingStop',
        side: tpSide, size: q3, trailPrice: 30, triggerStopPrice: trailStart,
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
    console.log(`[SignalRouter] Topstep order ${body.type} ${body.side} qty=${body.size}: ${res.ok ? '✅' : '❌'} ${text.slice(0, 80)}`);
    return res;
  }
}

export const signalRouter = new SignalRouter();
export default SignalRouter;
