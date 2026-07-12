import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/** MACD Crossover: Classic moving average convergence divergence. Signal line cross. */
function ema(prices:number[],period:number):number{const k=2/(period+1);let e=prices[0];for(let i=1;i<prices.length;i++)e=prices[i]*k+e*(1-k);return e;}
function buildSignal(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;macd:number}):StrategySignal|null{
  const{context,side,stop,target,confidence,macd}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:"macd-crossover",side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:30,meta:{pattern:"macd-cross",macd:Number(macd.toFixed(4))}};}
export class MacdCrossoverStrategy implements Strategy {
  public readonly id="macd-crossover";public readonly description="MACD signal line crossover: 12/26/9 classic. Bullish cross above zero = strong.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-40);if(h.length<35)return null;const closes=h.map(b=>b.close);
    const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // MACD = EMA12 - EMA26, Signal = EMA9 of MACD
    const ema12=ema(closes,12);const ema26=ema(closes,26);const macd=ema12-ema26;
    // Approximate signal line
    const prevCloses=closes.slice(0,-1);const pEma12=prevCloses.length>0?ema(prevCloses,12):ema12;
    const pEma26=prevCloses.length>0?ema(prevCloses,26):ema26;const pMacd=pEma12-pEma26;
    const signal=macd*0.2+pMacd*0.8;const prevSignal=pMacd*0.2+(pEma12-pEma26)*0.8;
    const price=context.bar.close;
    if(macd>signal&&macd>0&&pMacd<=prevSignal){const stop=price-atr*0.8;const t=price+atr*2;
      if(stop>=price)return null;return buildSignal({context,side:"long",stop,target:t,confidence:0.58,macd});}
    if(macd<signal&&macd<0&&pMacd>=prevSignal){const stop=price+atr*0.8;const t=price-atr*2;
      if(stop<=price)return null;return buildSignal({context,side:"short",stop,target:t,confidence:0.58,macd});}
    // Zero line cross
    if(macd>0&&pMacd<0){const stop=price-atr;const t=price+atr*1.5;
      if(stop>=price)return null;return buildSignal({context,side:"long",stop,target:t,confidence:0.6,macd});}
    if(macd<0&&pMacd>0){const stop=price+atr;const t=price-atr*1.5;
      if(stop<=price)return null;return buildSignal({context,side:"short",stop,target:t,confidence:0.6,macd});}
    return null;
  }
}

/** Keltner Channel: ATR-based envelope. Breakout = momentum, touch band = mean reversion. */
export class KeltnerChannelStrategy implements Strategy {
  public readonly id="keltner-channel";public readonly description="Keltner Channel (EMA+ATR envelope): band touch fade, breakout continuation.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<25)return null;const closes=h.map(b=>b.close);
    const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const ema20=ema(closes,20);const upper=ema20+atr*2;const lower=ema20-atr*2;const price=context.bar.close;
    function bs(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string}):StrategySignal|null{
      const{context,side,stop,target,confidence,pattern}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
      return{symbol:context.symbol,strategyId:"keltner-channel",side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}
    if(price>upper){const stop=price+atr*0.3;const t=ema20;if(stop<=price)return null;
      return bs({context,side:"short",stop,target:t,confidence:0.55,pattern:"upper-fade"});}
    if(price<lower){const stop=price-atr*0.3;const t=ema20;if(stop>=price)return null;
      return bs({context,side:"long",stop,target:t,confidence:0.55,pattern:"lower-fade"});}
    if(price>ema20&&price<upper&&closes[closes.length-2]<=ema20){const stop=ema20-atr*0.5;const t=price+atr*1.5;
      if(stop>=price)return null;return bs({context,side:"long",stop,target:t,confidence:0.56,pattern:"ema-bounce-long"});}
    if(price<ema20&&price>lower&&closes[closes.length-2]>=ema20){const stop=ema20+atr*0.5;const t=price-atr*1.5;
      if(stop<=price)return null;return bs({context,side:"short",stop,target:t,confidence:0.56,pattern:"ema-bounce-short"});}
    return null;
  }
}
