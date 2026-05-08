import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/** ADX Trend Strength: Only trade when ADX>25 confirming strong trend. Direction from +DI/-DI. */
function adx(bars:{high:number,low:number,close:number}[],period:number=14):{adx:number,pdi:number,ndi:number}{
  if(bars.length<period+1)return{adx:0,pdi:0,ndi:0};let trSum=0,pdmSum=0,ndmSum=0;
  for(let i=bars.length-period;i<bars.length;i++){const b=bars[i],pb=bars[i-1];
    const tr=Math.max(b.high-b.low,Math.abs(b.high-pb.close),Math.abs(b.low-pb.close));
    const upMove=b.high-pb.high;const downMove=pb.low-b.low;
    trSum+=tr;pdmSum+=(upMove>downMove&&upMove>0?upMove:0);ndmSum+=(downMove>upMove&&downMove>0?downMove:0);}
  const atrVal=trSum/period;const pdi=pdmSum/atrVal*100;const ndi=ndmSum/atrVal*100;
  const dx=Math.abs(pdi-ndi)/(pdi+ndi)*100;return{adx:dx,pdi,ndi};}
function bs(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;adxVal:number;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,adxVal,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:35,meta:{pattern:"adx-trend",adx:Number(adxVal.toFixed(1))}};}
export class AdxTrendStrategy implements Strategy {
  public readonly id="adx-trend";public readonly description="ADX trend filter: only trade when ADX>25 confirms strong directional move. +DI/-DI cross.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const a=adx([...h,context.bar],14);if(a.adx<25)return null;const price=context.bar.close;
    if(a.pdi>a.ndi&&a.pdi>25){const stop=price-atr;const t=price+atr*2;
      if(stop>=price)return null;return bs({context,side:"long",stop,target:t,confidence:0.62,adxVal:a.adx,id:"adx-trend"});}
    if(a.ndi>a.pdi&&a.ndi>25){const stop=price+atr;const t=price-atr*2;
      if(stop<=price)return null;return bs({context,side:"short",stop,target:t,confidence:0.62,adxVal:a.adx,id:"adx-trend"});}
    return null;
  }
}

/** Donchian Channel Breakout: Turtle trader classic. 20-day channel breakout. */
export class DonchianBreakoutStrategy implements Strategy {
  public readonly id="donchian-breakout";public readonly description="Turtle-style Donchian channel breakout: 20-bar high/low break. Classic trend following.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-25);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const highs=h.map(b=>b.high);const lows=h.map(b=>b.low);const hh=Math.max(...highs);const ll=Math.min(...lows);const price=context.bar.close;
    if(price>hh){const stop=ll;const t=price+atr*2;if(stop>=price)return null;
      return bs({context,side:"long",stop,target:t,confidence:0.6,adxVal:0,id:"donchian-breakout"});}
    if(price<ll){const stop=hh;const t=price-atr*2;if(stop<=price)return null;
      return bs({context,side:"short",stop,target:t,confidence:0.6,adxVal:0,id:"donchian-breakout"});}
    return null;
  }
}
