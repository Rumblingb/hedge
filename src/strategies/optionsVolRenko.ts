import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

function s(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

/** Options Gamma Scalp: Delta-hedge gamma scalping signal from options flow. Buy dips, sell rips. */
export class GammaScalpStrategy implements Strategy {
  public readonly id="gamma-scalp";public readonly description="Gamma scalping proxy: buy pullbacks, sell rips. Derived from options market-maker behavior.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-15);if(h.length<10)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const price=context.bar.close;const closes=h.map(b=>b.close);const vwap=closes.reduce((a,b)=>a+b,0)/closes.length;
    const prev2=h[h.length-2]?.close;const prev=closes[closes.length-1];
    // Momentum burst: 3-bar acceleration
    const mom=(price-prev2)/prev2;const priceAbove=price>vwap;
    // Scalp long on pullback to VWAP in uptrend
    if(mom>0.001&&price>vwap*0.998&&price<vwap*1.005&&price<prev){
      const stop=price-atr*0.4;const t=price+atr*0.8;if(stop>=price)return null;
      return s({context,side:"long",stop,target:t,confidence:0.55,pattern:"gamma-scalp-long",id:"gamma-scalp"});}
    if(mom<-0.001&&price<vwap*1.002&&price>vwap*0.995&&price>prev){
      const stop=price+atr*0.4;const t=price-atr*0.8;if(stop<=price)return null;
      return s({context,side:"short",stop,target:t,confidence:0.55,pattern:"gamma-scalp-short",id:"gamma-scalp"});}
    return null;
  }
}

/** Volatility Risk Premium: Sell vol when IV>RV. Long vol when IV<RV. */
export class VolPremiumStrategy implements Strategy {
  public readonly id="vol-premium";public readonly description="Volatility risk premium: sell when implied vol > realized vol, buy when inverted.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<25)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // RV = 14-bar ATR as % of price; IV proxy = current bar range vs average
    const ranges=h.map(b=>(b.high-b.low)/b.close);const avgRange=ranges.reduce((a,b)=>a+b,0)/ranges.length;
    const curRange=(context.bar.high-context.bar.low)/context.bar.close;
    const ivRvRatio=curRange/(avgRange+0.0001);const price=context.bar.close;
    // High IV/RV: sell premium (mean reversion / short vol)
    if(ivRvRatio>2.5){const stop=price+atr*0.5;const t=price-atr*1;if(stop<=price)return null;
      return s({context,side:"short",stop,target:t,confidence:0.57,pattern:"sell-premium",id:"vol-premium"});}
    // Low IV/RV: buy premium (breakout / long vol)
    if(ivRvRatio<0.6&&curRange>avgRange*0.8){const stop=price-atr*0.5;const t=price+atr*1.5;
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.57,pattern:"buy-premium",id:"vol-premium"});}
    return null;
  }
}

/** Renko Brick Momentum: Simplified price action - trade brick direction with volume. */
export class RenkoStrategy implements Strategy {
  public readonly id="renko-momentum";public readonly description="Renko-style brick momentum: consecutive bricks in same direction = trend continuation.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-15);if(h.length<8)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const brickSize=atr*0.5;const price=context.bar.close;
    // Count consecutive moves
    let upBricks=0,downBricks=0;let lastPrice=h[0].close;
    for(let i=1;i<h.length;i++){const move=h[i].close-lastPrice;
      if(move>0)upBricks++;else if(move<0)downBricks++;lastPrice=h[i].close;}
    if(upBricks>=4&&context.bar.close>h[h.length-1].close){const stop=price-atr*0.5;const t=price+atr*1.5;
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.56,pattern:"renko-long",id:"renko-momentum"});}
    if(downBricks>=4&&context.bar.close<h[h.length-1].close){const stop=price+atr*0.5;const t=price-atr*1.5;
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.56,pattern:"renko-short",id:"renko-momentum"});}
    return null;
  }
}
