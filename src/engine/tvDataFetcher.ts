/**
 * tvDataFetcher.ts — Real-time NQ data via TradingView's WebSocket.
 * 
 * Uses patched tradingview-scraper (dist/TradingViewWebSocket.js) which reads
 * TV_SESSION env var and connects to prodata endpoint with session cookie.
 * Falls back to public feed (10min delay) if TV_SESSION is not set.
 * Falls back to Yahoo if TV unavailable entirely.
 */

import type { Bar } from "../domain.js";

const TV_SYMBOL = "CME_MINI:NQ1!";
const TV_SESSION = process.env.TV_SESSION || "";
const YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/MNQ=F?interval=15m&range=5d";
const NY_OPEN = 9.5 * 60;
const NY_CLOSE = 16 * 60;

let _tvClient: any = null;
let _lastQuote: any = null;
let _lastQuoteTime = 0;

async function getTVClient(): Promise<any> {
  if (_tvClient) return _tvClient;
  const { TradingViewAPI } = await import("tradingview-scraper");
  const client = new TradingViewAPI();
  await client.setup();
  await new Promise((r) => setTimeout(r, 3000));
  _tvClient = client;
  return client;
}

async function fetchQuoteTV(): Promise<{ bid: number; ask: number; last: number; session: string; updateMode: string } | null> {
  try {
    const now = Date.now();
    if (_lastQuote && now - _lastQuoteTime < 5_000) return _lastQuote;

    const client = await getTVClient();
    const data = await client.getTicker(TV_SYMBOL);
    await new Promise((r) => setTimeout(r, 2000));

    const td = data?.tickerData;
    if (!td?.lp) return null;

    const quote = {
      bid: td.bid ?? 0,
      ask: td.ask ?? 0,
      last: td.lp,
      session: td.current_session ?? "unknown",
      updateMode: td.update_mode ?? "unknown",
    };
    _lastQuote = quote;
    _lastQuoteTime = now;
    return quote;
  } catch {
    return null;
  }
}

/**
 * Fetch current NQ price from TradingView (session-authenticated if available).
 */
export async function fetchBars(): Promise<Bar[] | null> {
  const quote = await fetchQuoteTV();
  if (quote) {
    const bar: Bar = {
      ts: new Date().toISOString(),
      symbol: "MNQ",
      open: quote.last,
      high: quote.last,
      low: quote.last,
      close: quote.last,
      volume: 0,
    };
    const isRealtime = quote.updateMode === "realtime";
    console.log(`[TV] NQ: $${quote.last.toFixed(2)} | Bid: $${quote.bid.toFixed(2)} | Ask: $${quote.ask.toFixed(2)} | ${quote.session}${isRealtime ? " [REALTIME]" : " [delayed]"}`);
    return [bar];
  }

  // Fallback: Yahoo
  try {
    const res = await fetch(YAHOO_URL, { headers: { "User-Agent": "Mozilla/5.0" } });
    if (!res.ok) return null;
    const data: any = await res.json();
    const result = data?.chart?.result?.[0];
    if (!result) return null;

    const timestamps = result.timestamp || [];
    const quotes = result.indicators?.quote?.[0] || {};
    return timestamps
      .map((ts: number, i: number) => ({
        ts: new Date(ts * 1000).toISOString(),
        symbol: "MNQ",
        open: quotes.open?.[i],
        high: quotes.high?.[i],
        low: quotes.low?.[i],
        close: quotes.close?.[i],
        volume: quotes.volume?.[i] || 0,
      }))
      .filter((b: any) => b.close != null);
  } catch {
    return null;
  }
}

export function isInSession(): boolean {
  const now = new Date();
  const day = now.getUTCDay();
  if (day === 0 || day === 6) return false;
  const etMin = now.getUTCHours() * 60 + now.getUTCMinutes() - 4 * 60;
  return etMin >= NY_OPEN && etMin < NY_CLOSE;
}

export async function cleanupTV(): Promise<void> {
  if (_tvClient) {
    try { await _tvClient.cleanup(); } catch {}
    _tvClient = null;
  }
}
