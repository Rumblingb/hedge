import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/** Order Flow Delta Divergence: Cumulative delta diverging from price = reversal signal */
function cumulativeDelta(bars:{close:number,open:number,high:number,low:number,volume:number}[],period:number):number{
  let d=0; const s=bars.slice(-period);
  for(const b of s){const buyVol=b.volume*(b.close>b.open?1:b.close<b.open?0:0.5);const sellVol=b.volume-buyVol;d+=buyVol-sellVol;}
  return d;}
function buildSignal(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:"delta-divergence",side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:20,meta:{pattern}};}
export class DeltaDivergenceStrategy implements Strategy {
  public readonly id="delta-divergence";public readonly description="Cumulative delta vs price divergence: buying/selling absorption signals.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-50);if(h.length<30)return null;
    const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const cd5=cumulativeDelta(h,5);const cd20=cumulativeDelta(h,20);
    const price=context.bar.close;const prevPrices=h.slice(-5).map(b=>b.close);
    const priceUp=prevPrices[prevPrices.length-1]>prevPrices[0];
    // Bearish divergence: price rising but delta falling
    if(priceUp&&cd5<cd20*0.3&&cd20>0){const stop=price+atr*0.5;const t=price-atr*1.5;
      if(stop<=price)return null;return buildSignal({context,side:"short",stop,target:t,confidence:0.58,pattern:"delta-bearish-div"});}
    // Bullish divergence: price falling but delta rising
    if(!priceUp&&cd5>cd20*0.3&&cd20<0){const stop=price-atr*0.5;const t=price+atr*1.5;
      if(stop>=price)return null;return buildSignal({context,side:"long",stop,target:t,confidence:0.58,pattern:"delta-bullish-div"});}
    return null;
  }
}
