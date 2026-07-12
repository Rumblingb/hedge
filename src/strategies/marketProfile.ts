import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/** Market Profile / TPO Value Area: Trade value area high/low bounces and breakouts */
function buildSignal(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:"market-profile",side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:30,meta:{pattern}};}
export class MarketProfileStrategy implements Strategy {
  public readonly id="market-profile";public readonly description="TPO/Volume Profile value area trading: bounce at VAH/VAL, breakout from value area.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.sessionHistory.length>=30?context.sessionHistory:context.history;if(h.length<30)return null;
    const closes=h.map(b=>b.close);const volumes=h.map(b=>b.volume);
    // Compute POC (point of control) and value area
    const sorted=closes.map((c,i)=>({price:c,vol:volumes[i]})).sort((a,b)=>a.price-b.price);
    let totalVol=volumes.reduce((a,b)=>a+b,0);const vaTarget=totalVol*0.7;let vaLow=sorted[0].price,vaHigh=sorted[0].price,accVol=0;
    let poc=sorted[0].price,pocVol=0;
    for(const s of sorted){accVol+=s.vol;if(s.vol>pocVol){pocVol=s.vol;poc=s.price;}}
    accVol=0;const pocIdx=sorted.findIndex(s=>s.price===poc);
    for(let i=pocIdx;i>=0;i--){accVol+=sorted[i].vol;vaLow=sorted[i].price;if(accVol>=vaTarget/2)break;}
    accVol=0;for(let i=pocIdx;i<sorted.length;i++){accVol+=sorted[i].vol;vaHigh=sorted[i].price;if(accVol>=vaTarget/2)break;}
    const atr=averageTrueRange(h,14);if(atr<=0)return null;const price=context.bar.close;
    // VAH reversal short
    if(price>vaHigh&&price<vaHigh+atr*0.5){const stop=price+atr*0.3;const t=vaHigh-atr*0.5;
      if(stop<=price)return null;return buildSignal({context,side:"short",stop,target:t,confidence:0.56,pattern:"vah-reversal"});}
    // VAL reversal long
    if(price<vaLow&&price>vaLow-atr*0.5){const stop=price-atr*0.3;const t=vaLow+atr*0.5;
      if(stop>=price)return null;return buildSignal({context,side:"long",stop,target:t,confidence:0.56,pattern:"val-reversal"});}
    // Value area breakout long
    if(price>vaHigh+atr*0.5&&context.bar.volume>volumes.reduce((a,b)=>a+b,0)/volumes.length*1.3){
      const stop=vaHigh;const t=price+atr*1.5;if(stop>=price)return null;
      return buildSignal({context,side:"long",stop,target:t,confidence:0.6,pattern:"va-breakout-long"});}
    // Value area breakout short
    if(price<vaLow-atr*0.5&&context.bar.volume>volumes.reduce((a,b)=>a+b,0)/volumes.length*1.3){
      const stop=vaLow;const t=price-atr*1.5;if(stop<=price)return null;
      return buildSignal({context,side:"short",stop,target:t,confidence:0.6,pattern:"va-breakout-short"});}
    return null;
  }
}
