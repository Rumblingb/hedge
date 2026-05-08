import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/** Ichimoku Cloud: Kumo breakout + Tenkan/Kijun cross. Classic Japanese system by Goichi Hosoda. */
function buildSignal(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:"ichimoku",side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:45,meta:{pattern}};}
function donchian(h:number[],l:number[],p:number):{h:number,l:number}{const s=Math.max(0,h.length-p);return{h:Math.max(...h.slice(s)),l:Math.min(...l.slice(s))};}
export class IchimokuStrategy implements Strategy {
  public readonly id="ichimoku";public readonly description="Ichimoku Kinko Hyo: cloud breakout, Tenkan/Kijun cross. Full Japanese system.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-60);if(h.length<52)return null;
    const highs=h.map(b=>b.high);const lows=h.map(b=>b.low);const closes=h.map(b=>b.close);
    const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // Tenkan-sen (9), Kijun-sen (26)
    const t9hi=donchian(highs,lows,9);const t9=(t9hi.h+t9hi.l)/2;
    const t26hi=donchian(highs,lows,26);const t26=(t26hi.h+t26hi.l)/2;
    // Senkou Span A (leading 1) = (Tenkan+Kijun)/2 shifted 26 forward - approximated as current
    const ssa=(t9+t26)/2;
    // Senkou Span B (leading 2) = 52-period midpoint shifted 26 forward
    const t52hi=donchian(highs,lows,52);const ssb=(t52hi.h+t52hi.l)/2;
    const price=context.bar.close;
    // Kumo breakout: price above cloud = long
    if(price>Math.max(ssa,ssb)&&price>t9&&t9>t26){
      const stop=Math.min(ssa,ssb);const t=price+atr*2;if(stop>=price)return null;
      return buildSignal({context,side:"long",stop,target:t,confidence:0.62,pattern:"kumo-breakout-long"});}
    if(price<Math.min(ssa,ssb)&&price<t9&&t9<t26){
      const stop=Math.max(ssa,ssb);const t=price-atr*2;if(stop<=price)return null;
      return buildSignal({context,side:"short",stop,target:t,confidence:0.62,pattern:"kumo-breakout-short"});}
    // Tenkan/Kijun cross
    if(t9>t26&&closes[closes.length-2]<=closes[closes.length-2]&&price>ssa){
      const stop=t26;const t=price+atr*1.5;if(stop>=price)return null;
      return buildSignal({context,side:"long",stop,target:t,confidence:0.55,pattern:"tk-cross-long"});}
    if(t9<t26&&price<ssb){
      const stop=t26;const t=price-atr*1.5;if(stop<=price)return null;
      return buildSignal({context,side:"short",stop,target:t,confidence:0.55,pattern:"tk-cross-short"});}
    return null;
  }
}
