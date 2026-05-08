import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

function s(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:20,meta:{pattern}};}

/** Stochastic Oscillator: Overbought>80 short, oversold<20 long with divergence confirmation. */
export class StochasticStrategy implements Strategy {
  public readonly id="stochastic";public readonly description="Stochastic oscillator: overbought/oversold with divergence. Classic Wilder system.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-25);if(h.length<20)return null;
    const atr=averageTrueRange(h,14);if(atr<=0)return null;const price=context.bar.close;
    // Fast stochastic %K
    const period=14;const slice=h.slice(-period);const hh=Math.max(...slice.map(b=>b.high));
    const ll=Math.min(...slice.map(b=>b.low));const k=((price-ll)/(hh-ll+0.0001))*100;
    if(k>80){const stop=price+atr*0.5;const t=price-atr*1.2;
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.55,pattern:"overbought",id:"stochastic"});}
    if(k<20){const stop=price-atr*0.5;const t=price+atr*1.2;
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.55,pattern:"oversold",id:"stochastic"});}
    return null;
  }
}

/** Heikin-Ashi Reversal: Smoothed candles show trend change before regular candles. */
function heikinAshi(b:{o:number,h:number,l:number,c:number},prev:{o:number,c:number}):{o:number,h:number,l:number,c:number}{
  const o=(prev.o+prev.c)/2;const c=(b.o+b.h+b.l+b.c)/4;const h=Math.max(b.h,o,c);const l=Math.min(b.l,o,c);return{o,h,l,c};}
export class HeikinAshiStrategy implements Strategy {
  public readonly id="heikin-ashi";public readonly description="Heikin-Ashi smoothed candles: trend continuation on green/red sequence, reversal on doji.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // Build HA series
    const ha:{o:number,c:number}[]=[{o:h[0].open,c:h[0].close}];
    for(let i=1;i<h.length;i++)ha.push({o:(ha[i-1].o+ha[i-1].c)/2,c:(h[i].open+h[i].high+h[i].low+h[i].close)/4});
    // Current HA
    const curHa={o:(ha[ha.length-1].o+ha[ha.length-1].c)/2,c:(context.bar.open+context.bar.high+context.bar.low+context.bar.close)/4};
    const last5=ha.slice(-5).map(x=>x.c>x.o?1:x.c<x.o?-1:0);
    const greenStreak=last5.filter(x=>x===1).length;const redStreak=last5.filter(x=>x===-1).length;
    // 5+ green bars, first red = sell
    if(greenStreak>=5&&curHa.c<curHa.o&&ha[ha.length-1].c>ha[ha.length-1].o){
      const stop=context.bar.high+atr*0.3;const t=context.bar.close-atr*1.5;if(stop<=context.bar.close)return null;
      return s({context,side:"short",stop,target:t,confidence:0.6,pattern:"ha-reversal-short",id:"heikin-ashi"});}
    if(redStreak>=5&&curHa.c>curHa.o&&ha[ha.length-1].c<ha[ha.length-1].o){
      const stop=context.bar.low-atr*0.3;const t=context.bar.close+atr*1.5;if(stop>=context.bar.close)return null;
      return s({context,side:"long",stop,target:t,confidence:0.6,pattern:"ha-reversal-long",id:"heikin-ashi"});}
    return null;
  }
}

/** False Breakout: Break above resistance then reverse = trap. Fade the breakout. */
export class FalseBreakoutStrategy implements Strategy {
  public readonly id="false-breakout";public readonly description="False breakout fade: break level → fail to hold → reverse. Classic stop-hunt pattern.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history;if(h.length<10)return null;const atr=averageTrueRange(h.slice(-20),14);if(atr<=0)return null;
    const recent=h.slice(-10);const rHigh=Math.max(...recent.map(b=>b.high));const rLow=Math.min(...recent.map(b=>b.low));
    const cur=context.bar;const prev=h[h.length-1];
    // False break above: bar goes above resistance then closes back below
    if(cur.high>rHigh+atr*0.3&&cur.close<rHigh&&prev.close>rHigh){
      const stop=cur.high+atr*0.3;const t=rLow;if(stop<=cur.close)return null;
      return s({context,side:"short",stop,target:t,confidence:0.63,pattern:"false-break-short",id:"false-breakout"});}
    // False break below: bar goes below support then closes back above
    if(cur.low<rLow-atr*0.3&&cur.close>rLow&&prev.close<rLow){
      const stop=cur.low-atr*0.3;const t=rHigh;if(stop>=cur.close)return null;
      return s({context,side:"long",stop,target:t,confidence:0.63,pattern:"false-break-long",id:"false-breakout"});}
    return null;
  }
}
