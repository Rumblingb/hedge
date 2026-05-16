#!/usr/bin/env node
/**
 * orbRunner.ts — Runs the ORB execution pipeline every 15m during NY session.
 * Fetches NQ 15m bars from Yahoo Finance, checks breakout, routes signals.
 * 
 * Run: npx tsx src/engine/orbRunner.ts
 */

import { executeOrbCycle } from './orbExecutionPipeline.js';
import { mkdir, appendFile } from 'node:fs/promises';
import { join } from 'node:path';

const LOG_DIR = join(process.cwd(), '.rumbling-hedge/logs');
const LOG_PATH = join(LOG_DIR, 'orb-runner.log');
const INTERVAL_MS = 120_000; // Check every 2m for new bar (avoids Yahoo rate limit)
const BAR_INTERVAL = 900;   // 15m in seconds
const YAHOO_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/MNQ=F?interval=15m&range=5d';

let lastBarTime = 0;

async function log(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.log(line);
  await appendFile(LOG_PATH, line + '\n');
}

async function fetchBars(): Promise<{ bars: any[]; price: number; atr: number } | null> {
  try {
    const res = await fetch(YAHOO_URL, {
      headers: { 'User-Agent': 'Mozilla/5.0' }
    });
    if (!res.ok) return null;
    const data: any = await res.json();
    const result = data?.chart?.result?.[0];
    if (!result) return null;

    const timestamps = result.timestamp || [];
    const quotes = result.indicators?.quote?.[0] || {};
    const adjclose = result.indicators?.adjclose?.[0]?.adjclose || [];

    const bars = timestamps.map((ts: number, i: number) => ({
      ts: new Date(ts * 1000).toISOString(),
      open: quotes.open?.[i],
      high: quotes.high?.[i],
      low: quotes.low?.[i],
      close: quotes.close?.[i],
      volume: quotes.volume?.[i] || 0,
    })).filter((b: any) => b.close != null);

    if (bars.length < 20) return null;

    // Current price = last bar close
    const price = bars[bars.length - 1].close;

    // Simple ATR over last 14 bars
    const atrValues = [];
    for (let i = 1; i < Math.min(15, bars.length); i++) {
      const tr = Math.max(
        bars[i].high - bars[i].low,
        Math.abs(bars[i].high - bars[i - 1].close),
        Math.abs(bars[i].low - bars[i - 1].close)
      );
      atrValues.push(tr);
    }
    const atr = atrValues.reduce((s: number, v: number) => s + v, 0) / atrValues.length;

    return { bars, price, atr };
  } catch (e: any) {
    await log(`Fetch error: ${e.message?.slice(0, 100)}`);
    return null;
  }
}

async function run() {
  await mkdir(LOG_DIR, { recursive: true });
  await log('=== ORB Runner STARTED ===');
  await log(`NY session: 09:30-16:00 ET | Bar: ${BAR_INTERVAL}s | Check: ${INTERVAL_MS/1000}s`);

  while (true) {
    try {
      const now = new Date();
      const etMinutes = now.getUTCHours() * 60 + now.getUTCMinutes() - 4 * 60;
      const inSession = etMinutes >= 570 && etMinutes < 960; // 09:30-16:00

      if (!inSession) {
        // Outside session — check every 5 min instead
        await new Promise(r => setTimeout(r, 300_000));
        continue;
      }

      const data = await fetchBars();
      if (!data) {
        await new Promise(r => setTimeout(r, INTERVAL_MS));
        continue;
      }

      const { bars, price, atr } = data;
      const latestBarTime = new Date(bars[bars.length - 1].ts).getTime();

      // Only run when a new 15m bar forms
      const barCloseMinutes = Math.floor(etMinutes / 15) * 15 + 15; // next :00, :15, :30, :45
      if (etMinutes < barCloseMinutes) {
        await new Promise(r => setTimeout(r, INTERVAL_MS));
        continue;
      }

      // New bar detected — run cycle
      if (latestBarTime !== lastBarTime) {
        lastBarTime = latestBarTime;
        await log(`Running cycle | Price: ${price.toFixed(0)} | ATR: ${atr.toFixed(0)} | Bars: ${bars.length}`);
        await executeOrbCycle(bars, price, atr);
      }
    } catch (e: any) {
      await log(`Error: ${e.message?.slice(0, 200)}`);
    }

    await new Promise(r => setTimeout(r, INTERVAL_MS));
  }
}

run().catch(e => console.error('Fatal:', e));
