/**
 * orbExecutionPipeline.ts — Connects ORB signal generator → signal router
 * 
 * Runs every 15m during NY session. When ORB triggers a breakout signal,
 * routes it to all accounts via PickMyTrade webhooks + Topstep API.
 */

import { signalRouter, OrbSignal } from '../live/signalRouter';
import { detectRegime } from '../strategies/regimeOrbBreakout';

const NY_OPEN = 9.5 * 60;   // 09:30 ET in minutes
const NY_CLOSE = 16 * 60;   // 16:00 ET
const DEFAULT_QTY = 3;

/** Calculate ATR-based stop loss and take profit */
function calcSLTP(price: number, atr: number, direction: 'buy' | 'sell', config: {
  stopAtr: number;   // default: 1.5
  targetAtr: number; // default: 2.0
}) {
  const { stopAtr = 1.5, targetAtr = 2.0 } = config;
  if (direction === 'buy') {
    return {
      sl: +(price - stopAtr * atr).toFixed(2),
      tp: +(price + targetAtr * atr).toFixed(2)
    };
  } else {
    return {
      sl: +(price + stopAtr * atr).toFixed(2),
      tp: +(price - targetAtr * atr).toFixed(2)
    };
  }
}

/** Main execution: called every 15m bar close */
export async function executeOrbCycle(bars: any[], currentPrice: number, atr: number): Promise<void> {
  const now = new Date();
  const minutes = now.getUTCHours() * 60 + now.getUTCMinutes();
  const etMinutes = minutes - 4 * 60; // UTC → ET

  // Regime check: detect FOMC for position scaling
  const { regime, config: regimeCfg, signalBlocked } = detectRegime(new Date());
  
  if (signalBlocked) {
    console.log(`[ORB] FOMC blackout window. Skipping.`);
    return;
  }

  // Position scale based on regime
  const positionScale = regimeCfg.positionScale || 1.0;
  const scaledQty = Math.max(1, Math.round(DEFAULT_QTY * positionScale));

  // Session gate: Only trade during NY session
  if (etMinutes < NY_OPEN || etMinutes >= NY_CLOSE) {
    console.log(`[ORB] NY session closed (${Math.floor(etMinutes/60)}:${String(etMinutes%60).padStart(2,'0')} ET). Skipping.`);
    return;
  }

  // Regime check: skip if London/premarket
  const hour = Math.floor(etMinutes / 60);
  if (hour < 9 || hour >= 16) {
    console.log(`[ORB] Outside NY hours. Skipping.`);
    return;
  }

  // Generate ORB signal from bars
  const sessionBars = bars.filter((b: any) => {
    const t = new Date(b.ts);
    const m = t.getUTCHours() * 60 + t.getUTCMinutes() - 4 * 60;
    return m >= NY_OPEN;
  });

  if (sessionBars.length < 12) {
    console.log(`[ORB] Not enough session bars (${sessionBars.length}/12). Skipping.`);
    return;
  }

  const rangeHigh = Math.max(...sessionBars.slice(0, 12).map((b: any) => b.high));
  const rangeLow = Math.min(...sessionBars.slice(0, 12).map((b: any) => b.low));
  const volume = sessionBars.slice(0, 12).reduce((s: number, b: any) => s + b.volume, 0) / 12;
  const lastBar = sessionBars[sessionBars.length - 1];
  const avgVol = bars.slice(-50).reduce((s: number, b: any) => s + b.volume, 0) / 50;

  let signal: OrbSignal | null = null;

  // LONG: close breaks above range high with above-average volume
  if (lastBar.close > rangeHigh && lastBar.volume > avgVol * regimeCfg.volThreshold) {
    signal = { ticker: 'MNQ', action: 'buy', quantity: scaledQty, price: lastBar.close };
  }
  // SHORT: close breaks below range low with above-average volume
  else if (lastBar.close < rangeLow && lastBar.volume > avgVol * regimeCfg.volThreshold) {
    signal = { ticker: 'MNQ', action: 'sell', quantity: scaledQty, price: lastBar.close };
  }
  // EXIT: bar closes back inside range
  else if (lastBar.close >= rangeLow && lastBar.close <= rangeHigh) {
    signal = { ticker: 'MNQ', action: 'exit', quantity: 0 };
  }

  if (!signal) {
    console.log(`[ORB] No signal. Range: ${rangeLow.toFixed(0)}-${rangeHigh.toFixed(0)}, Close: ${lastBar.close.toFixed(0)}, Vol: ${(lastBar.volume / avgVol).toFixed(1)}x avg`);
    return;
  }

  // Add SL/TP for entry signals using regime config
  if (signal.action === 'buy' || signal.action === 'sell') {
    const { sl, tp } = calcSLTP(signal.price!, atr, signal.action, { 
      stopAtr: regimeCfg.stopAtr || 1.5, 
      targetAtr: regimeCfg.targetAtr || 2.0 
    });
    signal.stopLoss = sl;
    signal.takeProfit = tp;
    console.log(`[ORB] [${regime.toUpperCase()}] ${signal.action.toUpperCase()} ${signal.quantity} ${signal.ticker} @ ${signal.price}`);
    console.log(`[ORB] SL: ${sl}, TP: ${tp} (scale: ${positionScale}x, ATR: ${atr.toFixed(0)})`);
  }

  // Route to all accounts
  await signalRouter.route(signal);
  console.log(`[ORB] Cycle complete at ${now.toISOString()}\n`);
}
