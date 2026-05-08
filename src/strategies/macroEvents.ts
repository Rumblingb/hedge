import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js"; import { averageTrueRange } from "../utils/indicators.js";
function sg(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

export class CpiReactionStrategy implements Strategy{public readonly id="cpi-reaction";public readonly description="CPI reaction: inflation surprise → trade initial direction with tight stop.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-10);if(h.length<8)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const curR=(ctx.bar.high-ctx.bar.low)/ctx.bar.close;
  const avgR=h.map(b=>(b.high-b.low)/b.close).reduce((a,b)=>a+b,0)/h.length;
  if(curR<avgR*2.5)return null;const price=ctx.bar.close;
  if(ctx.bar.close>ctx.bar.open){const stop=price-atr*0.4;const t=price+atr*1.5;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.59,pattern:"cpi-long",id:"cpi-reaction"});}
  else{const stop=price+atr*0.4;const t=price-atr*1.5;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.59,pattern:"cpi-short",id:"cpi-reaction"});}}}

export class OpecFadeStrategy implements Strategy{public readonly id="opec-fade";public readonly description="OPEC meeting fade: initial crude spike usually fades within hours.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-10);if(h.length<8)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const curR=(ctx.bar.high-ctx.bar.low)/ctx.bar.close;
  if(curR<0.02)return null;const isUp=ctx.bar.close>h[h.length-1].close;const price=ctx.bar.close;
  if(isUp&&ctx.bar.close<ctx.bar.high-curR*0.3*ctx.bar.close){const stop=ctx.bar.high;const t=price-atr*0.8;
    if(stop<=price)return null;return sg({context:ctx,side:"short",stop,target:t,confidence:0.57,pattern:"opec-fade",id:"opec-fade"});}
  return null;}}

export class EiaInventoryStrategy implements Strategy{public readonly id="eia-inventory";public readonly description="EIA inventory: crude draw = long, build = short. Weekly Wednesday data.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-10);if(h.length<8)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const d=new Date(ctx.bar.ts);
  if(d.getUTCDay()!==3||d.getUTCHours()!==14)return null;const price=ctx.bar.close;const sessionH=ctx.sessionHistory;
  if(sessionH.length<3)return null;const trend=price>sessionH[0].close?1:-1;
  if(trend===1){const stop=price-atr*0.5;const t=price+atr*1;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.55,pattern:"eia-draw-long",id:"eia-inventory"});}
  if(trend===-1){const stop=price+atr*0.5;const t=price-atr*1;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.55,pattern:"eia-build-short",id:"eia-inventory"});}return null;}}

export class CotPositioningStrategy implements Strategy{public readonly id="cot-positioning";public readonly description="COT report: extreme speculative positioning = contrarian signal.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-25);if(h.length<20)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);
  let upDays=0;for(let i=1;i<closes.length;i++)if(closes[i]>closes[i-1])upDays++;
  const extreme=upDays>=18||upDays<=2;const price=ctx.bar.close;
  if(extreme&&upDays>=18){const stop=price+atr*0.5;const t=price-atr*1.5;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.58,pattern:"cot-contrarian-short",id:"cot-positioning"});}
  if(extreme&&upDays<=2){const stop=price-atr*0.5;const t=price+atr*1.5;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.58,pattern:"cot-contrarian-long",id:"cot-positioning"});}return null;}}

export class VixTermStructureStrategy implements Strategy{public readonly id="vix-term-structure";public readonly description="VIX term structure: contango = sell vol, backwardation = buy vol.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-30);if(h.length<25)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const ranges=h.map(b=>(b.high-b.low)/b.close);
  const shortVol=ranges.slice(-5).reduce((a,b)=>a+b,0)/5;const longVol=ranges.slice(-20).reduce((a,b)=>a+b,0)/20;
  const contango=shortVol<longVol*0.7;const backwardation=shortVol>longVol*1.3;const price=ctx.bar.close;
  if(contango){const stop=price+atr*0.3;const t=price-atr*0.8;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.54,pattern:"vix-contango-short",id:"vix-term-structure"});}
  if(backwardation){const stop=price-atr*0.3;const t=price+atr*0.8;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.54,pattern:"vix-backward-long",id:"vix-term-structure"});}return null;}}

export class GammaPinStrategy implements Strategy{public readonly id="gamma-pin";public readonly description="Gamma pin: OPEX Friday markets pin to max pain / high gamma strike.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-15);if(h.length<12)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);
  const vwap=closes.reduce((a,b)=>a+b,0)/closes.length;const price=ctx.bar.close;const dev=price-vwap;
  if(Math.abs(dev)<atr*0.3)return null;const d=new Date(ctx.bar.ts);
  if(d.getUTCDay()!==5)return null;
  if(dev>atr*0.5){const stop=price+atr*0.3;const t=vwap;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.56,pattern:"gamma-pin-short",id:"gamma-pin"});}
  if(dev<-atr*0.5){const stop=price-atr*0.3;const t=vwap;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.56,pattern:"gamma-pin-long",id:"gamma-pin"});}return null;}}
