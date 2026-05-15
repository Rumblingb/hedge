/**
 * orbExecutionPipeline.ts — ORB signal generator → route to all accounts
 * 
 * Position tracking included. Every entry has SL+TP. Exits use tracked
 * position size. Never leaves orphaned orders.
 */

import { signalRouter, OrbSignal } from '../live/signalRouter';
import { detectRegime } from '../strategies/regimeOrbBreakout';

const NY_OPEN = 9.5 * 60;
const NY_CLOSE = 16 * 60;
const DEFAULT_QTY = 3;

// Position tracker — ensures exits use correct contract count
let _currentPosition: { ticker: string; side: 'long'; quantity: number } | null = null;

function calcSLTP(price: number, atr: number, direction: 'buy' | 'sell', config: {
  stopAtr: number; targetAtr: number;
}) {
  const { stopAtr = 1.5, targetAtr = 2.0 } = config;
  if (direction === 'buy') {
    return { sl: +(price - stopAtr * atr).toFixed(2), tp: +(price + targetAtr * atr).toFixed(2) };
  } else {
    return { sl: +(price + stopAtr * atr).toFixed(2), tp: +(price - targetAtr * atr).toFixed(2) };
  }
}

export async function executeOrbCycle(bars: any[], currentPrice: number, atr: number): Promise<void> {
  const now = new Date();
  const minutes = now.getUTCHours() * 60 + now.getUTCMinutes();
  const etMinutes = minutes - 4 * 60;

  // Regime check
  const { regime, config: regimeCfg, signalBlocked } = detectRegime(now);
  if (signalBlocked) {
    console.log(`[ORB] FOMC blackout. Skipping.`);
    return;
  }

  const positionScale = regimeCfg.positionScale || 1.0;
  const scaledQty = Math.max(1, Math.round(DEFAULT_QTY * positionScale));

  // Session gate
  if (etMinutes < NY_OPEN || etMinutes >= NY_CLOSE) {
    // Force exit everything at close
    if (_currentPosition) {
      console.log(`[ORB] Session close — forcing exit of ${_currentPosition.quantity} ${_currentPosition.ticker}`);
      await signalRouter.route({ ticker: _currentPosition.ticker, action: 'exit', quantity: _currentPosition.quantity });
      _currentPosition = null;
    }
    return;
  }

  // Bar processing
  const sessionBars = bars.filter((b: any) => {
    const t = new Date(b.ts);
    const m = t.getUTCHours() * 60 + t.getUTCMinutes() - 4 * 60;
    return m >= NY_OPEN;
  });

  if (sessionBars.length < 12) {
    console.log(`[ORB] Not enough session bars (${sessionBars.length}/12).`);
    return;
  }

  const rangeHigh = Math.max(...sessionBars.slice(0, 12).map((b: any) => b.high));
  const rangeLow = Math.min(...sessionBars.slice(0, 12).map((b: any) => b.low));
  const lastBar = sessionBars[sessionBars.length - 1];
  const avgVol = bars.slice(-50).reduce((s: number, b: any) => s + b.volume, 0) / 50;

  let signal: OrbSignal | null = null;

  // Exit if in position and bar closes back in range
  if (_currentPosition && lastBar.close >= rangeLow && lastBar.close <= rangeHigh) {
    signal = { ticker: 'MNQ', action: 'exit', quantity: _currentPosition.quantity };
  }
  // LONG breakout
  else if (!_currentPosition && lastBar.close > rangeHigh && lastBar.volume > avgVol * regimeCfg.volThreshold) {
    signal = { ticker: 'MNQ', action: 'buy', quantity: scaledQty, price: lastBar.close };
  }
  // SHORT breakout
  else if (!_currentPosition && lastBar.close < rangeLow && lastBar.volume > avgVol * regimeCfg.volThreshold) {
    signal = { ticker: 'MNQ', action: 'sell', quantity: scaledQty, price: lastBar.close };
  }

  if (!signal) {
    console.log(`[ORB] No signal. Range: ${rangeLow.toFixed(0)}-${rangeHigh.toFixed(0)}, Close: ${lastBar.close.toFixed(0)}, Vol: ${(lastBar.volume / avgVol).toFixed(1)}x avg`);
    return;
  }

  // Attach SL/TP to every entry — NEVER send an entry without protection
  if (signal.action === 'buy' || signal.action === 'sell') {
    const { sl, tp } = calcSLTP(signal.price!, atr, signal.action, {
      stopAtr: regimeCfg.stopAtr || 1.5,
      targetAtr: regimeCfg.targetAtr || 2.0
    });
    signal.stopLoss = sl;
    signal.takeProfit = tp;
    console.log(`[ORB] [${regime.toUpperCase()}] ${signal.action.toUpperCase()} ${signal.quantity} ${signal.ticker} @ ${signal.price}`);
    console.log(`[ORB] SL: ${sl}, TP: ${tp} | ATR: ${atr.toFixed(0)}, Scale: ${positionScale}x`);

    // Track position
    _currentPosition = { ticker: 'MNQ', side: 'long', quantity: signal.quantity };
  } else if (signal.action === 'exit') {
    console.log(`[ORB] EXIT ${signal.quantity} ${signal.ticker} — back in range`);
    _currentPosition = null;
  }

  // Route signal
  await signalRouter.route(signal);
  console.log(`[ORB] Cycle complete.\n`);
}
