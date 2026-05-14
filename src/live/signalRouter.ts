/**
 * signalRouter.ts — Routes session-aware ORB signals to ALL 4 accounts
 * 
 * Topstep $100K → TopstepX API (direct)
 * LucidFlex × 2 + FundedNext $100K → PickMyTrade webhook (copy trading)
 */

import { TopstepConnector } from './topstepConnector';
import { loadEnv } from '../config/env';

const PMT_WEBHOOK_URL = 'https://api.pickmytrade.trade/v2/add-trade-data-latest?t=16754';

export interface OrbSignal {
  ticker: string;      // 'MNQ' | 'MES' | 'ES' | 'NQ'
  action: 'buy' | 'sell';
  contracts: number;
  stopLoss?: number;
  takeProfit?: number;
}

class SignalRouter {
  private topstep: TopstepConnector;

  constructor() {
    this.topstep = new TopstepConnector();
  }

  /** Route a signal to all 4 accounts */
  async route(signal: OrbSignal): Promise<{ topstep: boolean; pmt: boolean }> {
    const result = { topstep: false, pmt: false };

    // 1. Topstep → direct API
    try {
      const tsResult = await this.topstep.placeOrder({
        symbol: signal.ticker,
        side: signal.action,
        quantity: signal.contracts,
        orderType: 'Market',
        timeInForce: 'Day'
      });
      result.topstep = tsResult?.orderId !== undefined;
      console.log(`[SignalRouter] Topstep: ${result.topstep ? '✅' : '❌'} (order #${tsResult?.orderId})`);
    } catch (err) {
      console.error('[SignalRouter] Topstep error:', err);
    }

    // 2. Tradovate accounts → PickMyTrade (copy trades to all 3)
    try {
      const pmtRes = await fetch(PMT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: signal.ticker,
          action: signal.action,
          qty: signal.contracts
        })
      });
      const pmtData = await pmtRes.json();
      result.pmt = pmtData?.error === false;
      console.log(`[SignalRouter] PickMyTrade: ${result.pmt ? '✅' : '❌'} (${pmtData?.res})`);
    } catch (err) {
      console.error('[SignalRouter] PickMyTrade error:', err);
    }

    return result;
  }

  /** Exit all positions on all accounts */
  async exitAll(symbol: string): Promise<void> {
    // Topstep exit
    try {
      await this.topstep.closeAllPositions(symbol);
    } catch {}

    // Tradovate exit via PMT
    try {
      await fetch(PMT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, action: 'exit', qty: 0 })
      });
    } catch {}
  }
}

// Export singleton
export const signalRouter = new SignalRouter();
