import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

function s(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:20,meta:{pattern}};}

/** Inside Bar Breakout: Inside bar → break high/low = continuation/reversal. */
export class InsideBarStrategy implements Strategy {
  public readonly id="inside-bar";public readonly description="Inside bar breakout: mother bar engulfs inside bar, break direction = trade direction.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history;if(h.length<3)return null;const atr=averageTrueRange(h.slice(-20),14);if(atr<=0)return null;
    const prev=h[h.length-1];const cur=context.bar;
    if(cur.high<prev.high&&cur.low>prev.low){return null;} // Still inside, wait for break
    if(prev.high<h[h.length-2].high&&prev.low>h[h.length-2].low){ // Previous bar was inside
      if(cur.close>h[h.length-2].high){const stop=h[h.length-2].low;const t=cur.close+atr*1.5;
        if(stop>=cur.close)return null;return s({context,side:"long",stop,target:t,confidence:0.58,pattern:"inside-break-long",id:"inside-bar"});}
      if(cur.close<h[h.length-2].low){const stop=h[h.length-2].high;const t=cur.close-atr*1.5;
        if(stop<=cur.close)return null;return s({context,side:"short",stop,target:t,confidence:0.58,pattern:"inside-break-short",id:"inside-bar"});}
    }return null;
  }
}

/** Pin Bar Reversal: Long wick, small body at extreme = rejection/reversal. */
export class PinBarStrategy implements Strategy {
  public readonly id="pin-bar";public readonly description="Pin bar / hammer / shooting star: long wick rejection at swing high/low.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-20);if(h.length<10)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const cur=context.bar;const body=Math.abs(cur.close-cur.open);const range=cur.high-cur.low;
    const upperWick=cur.high-Math.max(cur.open,cur.close);const lowerWick=Math.min(cur.open,cur.close)-cur.low;
    if(range<atr*0.5)return null;
    // Bullish pin: long lower wick, small body, close near high
    if(lowerWick>body*3&&lowerWick>upperWick*2&&cur.close>cur.open&&body<range*0.35){
      const stop=cur.low-atr*0.2;const t=cur.close+atr*1.5;if(stop>=cur.close)return null;
      return s({context,side:"long",stop,target:t,confidence:0.6,pattern:"bullish-pin-bar",id:"pin-bar"});}
    // Bearish pin: long upper wick, small body, close near low
    if(upperWick>body*3&&upperWick>lowerWick*2&&cur.close<cur.open&&body<range*0.35){
      const stop=cur.high+atr*0.2;const t=cur.close-atr*1.5;if(stop<=cur.close)return null;
      return s({context,side:"short",stop,target:t,confidence:0.6,pattern:"bearish-pin-bar",id:"pin-bar"});}
    return null;
  }
}

/** Engulfing Pattern: Bullish/bearish engulfing candlestick pattern. */
export class EngulfingStrategy implements Strategy {
  public readonly id="engulfing-pattern";public readonly description="Candlestick engulfing: bullish engulfing at support, bearish engulfing at resistance.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history;if(h.length<20)return null;const atr=averageTrueRange(h.slice(-20),14);if(atr<=0)return null;
    const prev=h[h.length-1];const cur=context.bar;
    // Bullish engulfing
    if(cur.close>cur.open&&prev.close<prev.open&&cur.open<prev.close&&cur.close>prev.open&&Math.abs(cur.close-cur.open)>atr*0.5){
      const stop=Math.min(cur.low,prev.low);const t=cur.close+atr*1.5;if(stop>=cur.close)return null;
      return s({context,side:"long",stop,target:t,confidence:0.62,pattern:"bullish-engulfing",id:"engulfing-pattern"});}
    // Bearish engulfing
    if(cur.close<cur.open&&prev.close>prev.open&&cur.open>prev.close&&cur.close<prev.open&&Math.abs(cur.close-cur.open)>atr*0.5){
      const stop=Math.max(cur.high,prev.high);const t=cur.close-atr*1.5;if(stop<=cur.close)return null;
      return s({context,side:"short",stop,target:t,confidence:0.62,pattern:"bearish-engulfing",id:"engulfing-pattern"});}
    return null;
  }
}
