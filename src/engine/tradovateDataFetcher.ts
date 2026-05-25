/**
 * tradeovateDataFetcher.ts — Real-time NQ data via Tradovate REST API
 * 
 * Uses LucidFlex Tradovate credentials to authenticate and fetch
 * real-time CME futures quotes with zero delay.
 */

const TRADOVATE_LIVE = 'https://live.tradovateapi.com/v1';
const TRADOVATE_MD = 'https://md.tradovateapi.com/v1';

// NQ futures symbol -> Tradovate contract mapping
// Tradovate uses 'NQM6' for Jun 2026, 'NQU6' for Sep 2026 etc.
// The '!' suffix means current front-month (like TV's NQ1!)
const NQ_SYMBOLS = ['NQ', 'MNQ'];

interface AuthResponse {
  accessToken: string;
  refreshToken: string;
  userId: number;
  expireTime: number;
  mdAccessToken?: string;
}

interface QuoteResponse {
  symbol: string;
  bid: number;
  ask: number;
  lastPrice: number;
  highPrice: number;
  lowPrice: number;
  prevClose: number;
  openPrice: number;
  totalVolume: number;
  timestamp: string;
  tradeTime: string;
}

export class TradovateDataFetcher {
  private accessToken: string | null = null;
  private mdAccessToken: string | null = null;
  private tokenExpiry = 0;
  private login: string;
  private password: string;

  constructor(login: string, password: string) {
    this.login = login;
    this.password = password;
  }

  async authenticate(): Promise<boolean> {
    try {
      // Tradovate uses "name" (login/username) + "password" + "appId" + "appVersion"
      const res = await fetch(`${TRADOVATE_LIVE}/auth/accesstoken`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: this.login,
          password: this.password,
          appId: 'HermesQuant',
          appVersion: '1.0.0',
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        console.error(`[TradovateData] Auth failed (${res.status}): ${text}`);
        return false;
      }

      const data: AuthResponse = await res.json();
      this.accessToken = data.accessToken;
      this.mdAccessToken = data.mdAccessToken || null;
      // expireTime is seconds from now
      this.tokenExpiry = Date.now() + (data.expireTime || 3600) * 1000;
      
      console.log(`[TradovateData] Authenticated as userId=${data.userId}, token expires in ${data.expireTime || 3600}s`);
      if (this.mdAccessToken) {
        console.log(`[TradovateData] MD access token received — real-time data available`);
      }
      return true;
    } catch (err: any) {
      console.error(`[TradovateData] Auth error: ${err.message}`);
      return false;
    }
  }

  private async ensureAuth(): Promise<boolean> {
    if (this.accessToken && Date.now() < this.tokenExpiry - 120000) return true;
    return this.authenticate();
  }

  /**
   * Get a real-time quote for NQ futures
   * Uses the md.tradovateapi.com endpoint which gives real-time CME data
   */
  async getNQQuote(): Promise<QuoteResponse | null> {
    if (!await this.ensureAuth()) return null;

    try {
      // Try getting quote for front-month NQ
      // Tradovate MD endpoint: GET /md/quote/{symbol}
      const authToken = this.mdAccessToken || this.accessToken;
      
      const res = await fetch(`${TRADOVATE_MD}/quote?symbols=NQM6,MNQM6`, {
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Accept': 'application/json',
        },
      });

      if (!res.ok) {
        const text = await res.text();
        console.error(`[TradovateData] Quote failed (${res.status}): ${text}`);
        return null;
      }

      const data = await res.json();
      console.log(`[TradovateData] Quote response:`, JSON.stringify(data).slice(0, 300));
      return data;
    } catch (err: any) {
      console.error(`[TradovateData] Quote error: ${err.message}`);
      return null;
    }
  }

  /**
   * Get contract list to find NQ contract IDs and current front month
   */
  async findNQContract(): Promise<any[]> {
    if (!await this.ensureAuth()) return [];

    try {
      const res = await fetch(`${TRADOVATE_LIVE}/contract/list`, {
        headers: {
          'Authorization': `Bearer ${this.accessToken}`,
          'Accept': 'application/json',
        },
      });

      if (!res.ok) {
        const text = await res.text();
        console.error(`[TradovateData] Contract list failed (${res.status}): ${text}`);
        return [];
      }

      const contracts = await res.json();
      // Filter for NQ contracts
      const nqContracts = contracts.filter((c: any) => 
        c.name?.startsWith('NQ') || c.name?.startsWith('MNQ')
      );
      console.log(`[TradovateData] Found ${nqContracts.length} NQ/MNQ contracts`);
      nqContracts.slice(0, 5).forEach((c: any) => 
        console.log(`  Contract: ${c.name} (id=${c.id}, expiry=${c.expirationDate?.slice(0,10)})`)
      );
      return nqContracts;
    } catch (err: any) {
      console.error(`[TradovateData] Contract list error: ${err.message}`);
      return [];
    }
  }
}

// CLI test
async function main() {
  const login = process.env.RH_LUCID_1_LOGIN || '';
  const password = process.env.RH_LUCID_1_PASSWORD || '';
  
  if (!login || !password) {
    console.error('Missing TRADOVATE_LOGIN/PASSWORD env vars');
    process.exit(1);
  }

  const fetcher = new TradovateDataFetcher(login, password);
  
  console.log('[Test] Authenticating with Tradovate...');
  const authed = await fetcher.authenticate();
  if (!authed) {
    console.error('[Test] ❌ Auth failed — LucidFlex credentials may not work for direct Tradovate API');
    process.exit(1);
  }
  
  console.log('[Test] ✅ Auth succeeded!');
  
  console.log('[Test] Finding NQ contracts...');
  const contracts = await fetcher.findNQContract();
  
  console.log('[Test] Getting NQ quote...');
  const quote = await fetcher.getNQQuote();
  
  if (quote) {
    console.log('[Test] ✅ Quote received!');
  } else {
    console.log('[Test] ❌ Quote failed');
  }
  
  process.exit(0);
}

// Only run as main
if (require.main === module) {
  main().catch(console.error);
}
