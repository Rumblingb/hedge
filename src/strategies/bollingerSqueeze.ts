import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/** Bollinger Band Squeeze: Vol contraction → expansion breakout. Classic mean-reversion at bands. */
function bb(prices:number[],period:number=20,mult:number=2):{mid:number[],upper:number[],lower:number[],width:number[]}{
  const m:number[]=[],u:number[]=[],l:number[]=[],w:number[]=[];
  for(let i=period-1;i<prices.length;i++){const s=prices.slice(i-period+1,i+1);const avg=s.reduce((a,b)=>a+b,0)/period;
    const v=s.reduce((sum,x)=>sum+(x-avg)**2,0)/period;const std=Math.sqrt(v);m.push(avg);u.push(avg+mult*std);l.push(avg-mult*std);w.push((u[u.length-1]-l[l.length-1])/avg);}
  return {mid:m,upper:u,lower:l,width:w};}
function buildSignal(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:"bollinger-squeeze",side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:30,meta:{pattern}};}
export class BollingerSqueezeStrategy implements Strategy {
  public readonly id="bollinger-squeeze";public readonly description="Bollinger Band squeeze breakout: vol contraction → expansion. Fade at bands, ride breakouts.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-50);if(h.length<30)return null;const prices=h.map(b=>b.close);
    const atr=averageTrueRange(h,14);if(atr<=0)return null;const b=bb(prices,20,2);
    if(b.width.length<5)return null;const w=b.width;const squeeze=w[w.length-1]<0.02;
    const price=context.bar.close;
    // Squeeze breakout: vol expanding, break band
    if(squeeze&&price>b.upper[b.upper.length-2]){
      const stop=b.mid[b.mid.length-1];const t=price+atr*2;if(stop>=price)return null;
      return buildSignal({context,side:"long",stop,target:t,confidence:0.6,pattern:"squeeze-breakout-long"});}
    if(squeeze&&price<b.lower[b.lower.length-2]){
      const stop=b.mid[b.mid.length-1];const t=price-atr*2;if(stop<=price)return null;
      return buildSignal({context,side:"short",stop,target:t,confidence:0.6,pattern:"squeeze-breakout-short"});}
    // Band fade: touch upper band = short
    if(price>b.upper[b.upper.length-1]*1.005){
      const stop=price+atr*0.3;const t=b.mid[b.mid.length-1];if(stop<=price)return null;
      return buildSignal({context,side:"short",stop,target:t,confidence:0.55,pattern:"band-fade-short"});}
    if(price<b.lower[b.lower.length-1]*0.995){
      const stop=price-atr*0.3;const t=b.mid[b.mid.length-1];if(stop>=price)return null;
      return buildSignal({context,side:"long",stop,target:t,confidence:0.55,pattern:"band-fade-long"});}
    return null;
  }
}
