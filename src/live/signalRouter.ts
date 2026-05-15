/**
 * signalRouter.ts — Routes ORB signals to ALL accounts
 * Topstep $100K → ProjectX adapter (auth + order via /api/Order/place)
 * FundedNext $100K → PickMyTrade webhook
 * LucidFlex $50K × 2 → PickMyTrade webhook
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

async function getTopstepAccountId(token: string): Promise<number> {
  // Try account list
  const res = await fetch(`${TOPSTEP_BASE}/api/accounts`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (res.ok) {
    const accounts: any = await res.json();
    if (Array.isArray(accounts) && accounts.length > 0) return accounts[0].id;
  }
  // Default: combine accounts have numeric suffix
  return 83651531;
}

export interface OrbSignal {
  ticker: string;
  action: 'buy' | 'sell' | 'exit';
  quantity: number;
  price?: number;
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

    // 2. TopstepX direct API
    try {
      const token = await getTopstepToken();
      const accId = await getTopstepAccountId(token);
      
      const orderBody = {
        accountId: accId,
        contractId: signal.ticker,
        type: 'Market',
        side: signal.action === 'buy' ? 'Buy' : signal.action === 'sell' ? 'Sell' : 'Sell',
        size: signal.quantity,
        limitPrice: null,
        stopPrice: null,
        trailPrice: null,
      };

      const res = await fetch(`${TOPSTEP_BASE}/api/Order/place`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify(orderBody),
      });
      const text = await res.text();
      console.log(`[SignalRouter] Topstep: ${res.ok ? '✅' : '❌'} (${res.status}) ${text.slice(0, 80)}`);
    } catch (e: any) {
      console.error(`[SignalRouter] Topstep error: ${e.message?.slice(0, 80)}`);
    }
  }
}

export const signalRouter = new SignalRouter();
export default SignalRouter;
