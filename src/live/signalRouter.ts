/**
 * signalRouter.ts — Routes session-aware ORB signals to ALL accounts
 * 
 * Topstep $100K → TopstepX API (direct)
 * FundedNext $100K → PickMyTrade t=16754
 * LucidFlex $50K × 2 → PickMyTrade t=16759
 */

const PMT_WEBHOOKS = [
  { url: 'https://api.pickmytrade.trade/v2/add-trade-data-latest?t=16754', token: 'dgMK0fhqIbfSuZs4JTDvKg', label: 'FundedNext $100K' },
  { url: 'https://api.pickmytrade.trade/v2/add-trade-data-latest?t=16759', token: 'OTPJQ0Ok4SFbpaWFHFeAKg', label: 'LucidFlex $50K × 2' },
];

export interface OrbSignal {
  ticker: string;
  action: 'buy' | 'sell' | 'exit';
  quantity: number;
  price?: number;
  stopLoss?: number;
  takeProfit?: number;
}

class SignalRouter {
  /** Route a signal to all connected accounts */
  async route(signal: OrbSignal): Promise<void> {
    console.log(`\n[SignalRouter] Routing: ${signal.action} ${signal.quantity} ${signal.ticker}`);

    // 1. PickMyTrade webhooks (Tradovate accounts)
    for (const wh of PMT_WEBHOOKS) {
      try {
        const body: any = {
          symbol: signal.ticker,
          strategy_name: 'orb-breakout',
          date: new Date().toISOString(),
          data: signal.action === 'exit' ? 'exit' : signal.action,
          quantity: String(signal.quantity),
          risk_percentage: 0,
          price: signal.price || 0,
          tp: signal.takeProfit || 0,
          sl: signal.stopLoss || 0,
          token: wh.token,
          pyramid: false,
          same_direction_ignore: false,
          reverse_order_close: signal.action === 'exit',
          multiple_accounts: [{ token: wh.token, account_id: '', risk_percentage: 0, quantity_multiplier: 1 }]
        };
        
        const res = await fetch(wh.url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        const data = await res.json();
        console.log(`  ${wh.label}: ${data?.error === false ? '✅' : '❌'} ${data?.res || ''}`);
      } catch (err: any) {
        console.error(`  ${wh.label}: ❌ ${err.message}`);
      }
    }

    // 2. Topstep direct API would go here
    console.log(`[SignalRouter] Done\n`);
  }

  /** Full exit on all accounts */
  async exitAll(ticker: string): Promise<void> {
    await this.route({ ticker, action: 'exit', quantity: 0 });
  }
}

export const signalRouter = new SignalRouter();
