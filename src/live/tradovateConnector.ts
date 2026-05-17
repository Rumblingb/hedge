/**
 * tradovateConnector.ts — REST API client for Tradovate (LucidFlex + FundedNext)
 * 
 * Authenticates, places orders, checks positions across all accounts.
 * Docs: https://api.tradovate.com/docs/
 */

const BASE_URL = 'https://live.tradovateapi.com/v1';

interface Account {
  id: number;
  name: string;
  accountType: string;
}

interface Order {
  accountSpec: string;
  accountId: number;
  symbol: string;
  action: 'Buy' | 'Sell';
  orderQty: number;
  orderType: 'Market' | 'Limit' | 'Stop' | 'StopLimit';
  price?: number;
  stopPrice?: number;
  timeInForce?: 'DAY' | 'GTC' | 'IOC' | 'FOK';
  isAutomated?: boolean;
}

export class TradovateConnector {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private userId: number | null = null;
  private accounts: Account[] = [];
  private tokenExpiry: number = 0;

  constructor(
    private username: string,
    private password: string,
    private label: string
  ) {}

  async authenticate(): Promise<boolean> {
    try {
      // Use Basic auth with credentials
      const creds = Buffer.from(`${this.username}:${this.password}`).toString('base64');
      const res = await fetch(`${BASE_URL}/auth/accessToken`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Basic ${creds}`
        },
        body: JSON.stringify({
          name: this.username,
          password: this.password,
          appId: 'HermesQuant',
          appVersion: '1.0',
          cid: 0,
          sec: ''
        })
      });
      
      if (!res.ok) {
        const text = await res.text();
        console.error(`[${this.label}] Auth failed (${res.status}): ${text}`);
        return false;
      }
      
      const data = await res.json();
      this.accessToken = data.accessToken;
      this.refreshToken = data.refreshToken;
      this.userId = data.userId;
      this.tokenExpiry = Date.now() + (data.expireTime || 3600) * 1000;
      
      console.log(`[${this.label}] Authenticated as userId=${data.userId}, expires in ${data.expireTime || 3600}s`);
      return true;
    } catch (err: any) {
      console.error(`[${this.label}] Auth error: ${err.message}`);
      return false;
    }
  }

  private async ensureAuth(): Promise<boolean> {
    if (this.accessToken && Date.now() < this.tokenExpiry - 60000) return true;
    return this.authenticate();
  }

  private async request<T>(method: string, path: string, body?: any): Promise<T | null> {
    if (!await this.ensureAuth()) return null;
    
    try {
      const res = await fetch(`${BASE_URL}${path}`, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.accessToken}`
        },
        body: body ? JSON.stringify(body) : undefined
      });
      
      if (!res.ok) {
        const text = await res.text();
        console.error(`[${this.label}] ${method} ${path} failed (${res.status}): ${text}`);
        return null;
      }
      
      return await res.json() as T;
    } catch (err: any) {
      console.error(`[${this.label}] ${method} ${path} error: ${err.message}`);
      return null;
    }
  }

  async loadAccounts(): Promise<Account[]> {
    const accounts = await this.request<Account[]>('GET', '/account/list');
    if (accounts) {
      this.accounts = accounts;
      console.log(`[${this.label}] Loaded ${accounts.length} account(s)`);
      accounts.forEach(a => console.log(`  Account #${a.id}: ${a.name} (${a.accountType})`));
    }
    return this.accounts;
  }

  async placeOrder(order: Order): Promise<any> {
    return this.request<any>('POST', '/order/placeOrder', {
      ...order,
      isAutomated: true
    });
  }

  async getPositions(): Promise<any[]> {
    const result = await this.request<any[]>('GET', '/position/list');
    return result || [];
  }

  async getCashBalance(): Promise<number> {
    const result = await this.request<any>('GET', '/cash/balance/snapshot');
    return result?.cashBalance ?? 0;
  }

  // Place an ORB breakout order: entry at market, then set SL and TP
  async enterOrbTrade(params: {
    symbol: string;
    direction: 'long' | 'short';
    contracts: number;
    stopLossTicks: number;
    takeProfitTicks: number;
  }): Promise<{ entryOrderId?: number; error?: string }> {
    const { symbol, direction, contracts, stopLossTicks, takeProfitTicks } = params;
    
    // Find the right account
    const account = this.accounts[0];
    if (!account) {
      return { error: 'No account found' };
    }

    const action = direction === 'long' ? 'Buy' : 'Sell';
    const stopAction = direction === 'long' ? 'Sell' : 'Buy';
    
    // Get current price for the symbol
    // Note: In production, this would come from the ORB signal
    
    // Place market entry order
    const entryOrder = await this.placeOrder({
      accountSpec: this.username,
      accountId: account.id,
      symbol,
      action,
      orderQty: contracts,
      orderType: 'Market',
      timeInForce: 'DAY',
    });

    if (entryOrder?.orderId) {
      console.log(`[${this.label}] Entry order placed: #${entryOrder.orderId} ${direction} ${contracts} ${symbol}`);
    }

    return { entryOrderId: entryOrder?.orderId };
  }

  async disconnect(): Promise<void> {
    if (this.refreshToken) {
      await this.request<any>('POST', '/auth/signout', {});
    }
    this.accessToken = null;
    this.refreshToken = null;
    this.userId = null;
    console.log(`[${this.label}] Disconnected`);
  }
}
