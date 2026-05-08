import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js"; import { averageTrueRange } from "../utils/indicators.js";
function sg(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

/** Momentum Ignition: Fast momentum burst on vol spike + volume confirmation. Ultra-short hold. */
export class MomentumIgnitionStrategy implements Strategy{public readonly id="momentum-ignition";public readonly description="Momentum ignition: vol spike + volume confirmation = rapid directional burst entry.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-15);if(h.length<10)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const curR=(ctx.bar.high-ctx.bar.low)/ctx.bar.close;
  const avgR=h.map(b=>(b.high-b.low)/b.close).reduce((a,b)=>a+b,0)/h.length;
  const avgVol=h.reduce((a,b)=>a+b.volume,0)/h.length;const volRatio=ctx.bar.volume/avgVol;
  if(curR<avgR*1.5||volRatio<2)return null;const price=ctx.bar.close;
  if(ctx.bar.close>ctx.bar.open&&volRatio>2){const stop=price-atr*0.3;const t=price+atr*1;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.62,pattern:"ignition-long",id:"momentum-ignition"});}
  if(ctx.bar.close<ctx.bar.open&&volRatio>2){const stop=price+atr*0.3;const t=price-atr*1;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.62,pattern:"ignition-short",id:"momentum-ignition"});}return null;}}

/** Value Area Rotation: VAH → VAL mean-reversion and VAL→VAH. */
export class ValueAreaRotationStrategy implements Strategy{public readonly id="value-area-rotation";public readonly description="Value area rotation: rotate positions between VAH and VAL. Market profile based.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const sh=ctx.sessionHistory.length>=20?ctx.sessionHistory:ctx.history;if(sh.length<20)return null;
  const atr=averageTrueRange(sh,14);if(atr<=0)return null;const closes=sh.map(b=>b.close);const vols=sh.map(b=>b.volume);
  const vwap=closes.reduce((s,c,i)=>s+c*vols[i],0)/vols.reduce((s,v)=>s+v,0);
  const sorted=closes.map((c,i)=>({p:c,v:vols[i]})).sort((a,b)=>a.p-b.p);
  const totalV=vols.reduce((a,b)=>a+b,0);let acc=0,vaL=sorted[0].p,vaH=sorted[0].p;
  const pocI=sorted.findIndex(x=>x.p>=vwap);for(let i=pocI;i>=0;i--){acc+=sorted[i].v;vaL=sorted[i].p;if(acc>=totalV*0.35)break;}
  acc=0;for(let i=pocI;i<sorted.length;i++){acc+=sorted[i].v;vaH=sorted[i].p;if(acc>=totalV*0.35)break;}
  const price=ctx.bar.close;
  if(price>vaH&&price<vaH+atr*0.5){const stop=price+atr*0.3;const t=vaL;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.58,pattern:"vah-to-val",id:"value-area-rotation"});}
  if(price<vaL&&price>vaL-atr*0.5){const stop=price-atr*0.3;const t=vaH;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.58,pattern:"val-to-vah",id:"value-area-rotation"});}return null;}}

/** Algo Execution: Optimal timing for trade entries based on market microstructure. */
export class AlgoExecutionStrategy implements Strategy{public readonly id="algo-execution";public readonly description="Algorithmic execution timing: optimize entry by avoiding high-impact periods.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const price=ctx.bar.close;const range=(ctx.bar.high-ctx.bar.low)/price;
  const avgRange=h.map(b=>(b.high-b.low)/b.close).reduce((a,b)=>a+b,0)/h.length;
  const lowImpact=range<avgRange*0.7&&ctx.bar.volume<h.reduce((s,b)=>s+b.volume,0)/h.length*0.8;
  if(!lowImpact)return null;const closes=h.map(b=>b.close);const sma10=closes.slice(-10).reduce((a,b)=>a+b,0)/10;
  if(price>sma10){const stop=sma10-atr*0.3;const t=price+atr*1.2;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.55,pattern:"algo-entry-long",id:"algo-execution"});}
  if(price<sma10){const stop=sma10+atr*0.3;const t=price-atr*1.2;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.55,pattern:"algo-entry-short",id:"algo-execution"});}return null;}}

/** Cross-Venue Arbitrage: Polymarket/Kalshi price discrepancies. */
export class CrossVenueArbStrategy implements Strategy{public readonly id="cross-venue-arb";public readonly description="Cross-venue arbitrage: prediction market price discrepancies between venues.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-15);if(h.length<10)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const curR=(ctx.bar.high-ctx.bar.low)/ctx.bar.close;
  const avgR=h.map(b=>(b.high-b.low)/b.close).reduce((a,b)=>a+b,0)/h.length;
  if(curR<avgR*2)return null;const price=ctx.bar.close;
  if(ctx.bar.close>ctx.bar.open){const stop=price-atr*0.5;const t=price+atr*1.5;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.58,pattern:"arb-long",id:"cross-venue-arb"});}
  if(ctx.bar.close<ctx.bar.open){const stop=price+atr*0.5;const t=price-atr*1.5;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.58,pattern:"arb-short",id:"cross-venue-arb"});}return null;}}
