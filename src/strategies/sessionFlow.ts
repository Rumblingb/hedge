import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js"; import { averageTrueRange } from "../utils/indicators.js";
function sg(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

/** Overnight drift: capture predictable overnight price drift patterns. */
export class OvernightDriftStrategy implements Strategy {
  public readonly id="overnight-drift";public readonly description="Overnight drift: capture predictable overnight price drift patterns.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const d=new Date(ctx.bar.ts);const hour=d.getUTCHours();if(hour<13||hour>14)return null;
    const prevDayClose=h[0].close;const drift=(ctx.bar.close-prevDayClose)/prevDayClose;
    if(drift>0.003){const stop=ctx.bar.close-atr*0.5;const t=ctx.bar.close+atr*1;if(stop>=ctx.bar.close)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.53,pattern:"drift-long",id:"overnight-drift"});}
    if(drift<-0.003){const stop=ctx.bar.close+atr*0.5;const t=ctx.bar.close-atr*1;if(stop<=ctx.bar.close)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.53,pattern:"drift-short",id:"overnight-drift"});}return null;}}

/** Pre-market reversal: pre-market moves often reverse at open. */
export class PreMarketReversalStrategy implements Strategy {
  public readonly id="pre-market-reversal";public readonly description="Pre-market reversal: pre-market extended moves often reverse at regular session open.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-15);if(h.length<10)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const sessionH=ctx.sessionHistory;if(sessionH.length<1)return null;const preMove=(ctx.bar.close-sessionH[0].close)/sessionH[0].close;
    if(Math.abs(preMove)<0.002)return null;const price=ctx.bar.close;
    if(preMove>0.004&&ctx.bar.close<ctx.bar.open){const stop=price+atr*0.3;const t=sessionH[0].close;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.57,pattern:"pre-rev-short",id:"pre-market-reversal"});}
    if(preMove<-0.004&&ctx.bar.close>ctx.bar.open){const stop=price-atr*0.3;const t=sessionH[0].close;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.57,pattern:"pre-rev-long",id:"pre-market-reversal"});}return null;}}

/** Initial Balance: First 60-min range. Trade breakouts and failures. */
export class InitialBalanceStrategy implements Strategy {
  public readonly id="initial-balance";public readonly description="Initial balance (first 60 min range): break IB high = long, break IB low = short.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.sessionHistory;if(h.length<8)return null;const atr=averageTrueRange([...ctx.history.slice(-20),ctx.bar],14);if(atr<=0)return null;
    const ibBars=h.slice(0,Math.min(12,h.length));const ibH=Math.max(...ibBars.map(b=>b.high));const ibL=Math.min(...ibBars.map(b=>b.low));
    if(ctx.bar.close>ibH+atr*0.1){const stop=ibL;const t=ctx.bar.close+atr*2;if(stop>=ctx.bar.close)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.6,pattern:"ib-breakout-long",id:"initial-balance"});}
    if(ctx.bar.close<ibL-atr*0.1){const stop=ibH;const t=ctx.bar.close-atr*2;if(stop<=ctx.bar.close)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.6,pattern:"ib-breakout-short",id:"initial-balance"});}return null;}}

/** Economic Surprise: Trade economic data surprise direction. */
export class EconSurpriseStrategy implements Strategy {
  public readonly id="econ-surprise";public readonly description="Economic surprise: trade direction of economic data beats/misses.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const curRange=(ctx.bar.high-ctx.bar.low)/ctx.bar.close;const avgR=h.map(b=>(b.high-b.low)/b.close).reduce((a,b)=>a+b,0)/h.length;
    if(curRange<avgR*2.5)return null;const price=ctx.bar.close;
    if(ctx.bar.close>ctx.bar.open&&curRange>avgR*2.5){const stop=price-atr*0.5;const t=price+atr*1;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.58,pattern:"surprise-long",id:"econ-surprise"});}
    if(ctx.bar.close<ctx.bar.open&&curRange>avgR*2.5){const stop=price+atr*0.5;const t=price-atr*1;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.58,pattern:"surprise-short",id:"econ-surprise"});}return null;}}

/** Put/Call ratio signal: High PCR = fear (buy), low PCR = greed (sell). Contrarian. */
export class PutCallSignalStrategy implements Strategy {
  public readonly id="put-call-signal";public readonly description="Put/call ratio: high PCR = contrarian buy signal (fear), low PCR = sell (greed).";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // PCR proxy: consecutive down days = high put activity
    let downDays=0;const closes=h.map(b=>b.close);for(let i=1;i<closes.length;i++)if(closes[i]<closes[i-1])downDays++;
    const pcrSignal=downDays/14;const price=ctx.bar.close;
    if(pcrSignal>0.7){const stop=price-atr*0.5;const t=price+atr*1;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.57,pattern:"pcr-fear-long",id:"put-call-signal"});}
    if(pcrSignal<0.2){const stop=price+atr*0.5;const t=price-atr*1;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.57,pattern:"pcr-greed-short",id:"put-call-signal"});}return null;}}
