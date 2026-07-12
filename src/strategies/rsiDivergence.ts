import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/** RSI Divergence: Bullish/Bearish RSI divergence from price. Classic reversal signal. */
function rsi(prices:number[],period:number=14):number[]{const r:number[]=[];let g=0,l=0;
  for(let i=1;i<prices.length;i++){const d=prices[i]-prices[i-1];g+=d>0?d:0;l+=d<0?-d:0;
    if(i>=period){const ag=g/period;const al=l/period;r.push(al===0?100:100-(100/(1+ag/al))); const old=prices[i-period+1]-prices[i-period]; if(old>0)g-=old; else l-=-old;}}
  return r;}
function buildSignal(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return {symbol:context.symbol,strategyId:"rsi-divergence",side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}
export class RsiDivergenceStrategy implements Strategy {
  public readonly id="rsi-divergence";public readonly description="RSI bullish/bearish divergence: price makes new high/low but RSI doesn't confirm.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-50);if(h.length<30)return null;const prices=h.map(b=>b.close);
    const atr=averageTrueRange(h,14);if(atr<=0)return null;const r=rsi(prices,14);if(r.length<5)return null;
    const p=prices.slice(-10);const rs=r.slice(-10);const pHigh=Math.max(...p);const pLow=Math.min(...p);
    const rHigh=Math.max(...rs);const rLow=Math.min(...rs);
    // Bearish divergence: price higher high, RSI lower high
    if(p[p.length-1]>=pHigh*0.99&&rs[rs.length-1]<rHigh*0.95&&rs[rs.length-1]>60){
      const stop=context.bar.high+atr*0.5;const t=context.bar.close-atr*1.5;if(stop<=context.bar.close)return null;
      return buildSignal({context,side:"short",stop,target:t,confidence:0.62,pattern:"bearish-divergence"});}
    // Bullish divergence: price lower low, RSI higher low
    if(p[p.length-1]<=pLow*1.01&&rs[rs.length-1]>rLow*1.05&&rs[rs.length-1]<40){
      const stop=context.bar.low-atr*0.5;const t=context.bar.close+atr*1.5;if(stop>=context.bar.close)return null;
      return buildSignal({context,side:"long",stop,target:t,confidence:0.62,pattern:"bullish-divergence"});}
    return null;
  }
}
