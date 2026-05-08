import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js"; import { averageTrueRange } from "../utils/indicators.js";

function sg(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

/** Vol-of-Vol: Trade when volatility of volatility spikes = regime change incoming. */
export class VolOfVolStrategy implements Strategy {
  public readonly id="volatility-of-vol";public readonly description="Vol-of-vol: trade VVIX-like vol of vol spikes as regime change signals.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-30);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const ranges=h.map(b=>(b.high-b.low)/b.close);const rangeChanges=[];for(let i=1;i<ranges.length;i++)rangeChanges.push(Math.abs(ranges[i]-ranges[i-1])/ranges[i-1]);
    const volOfVol=rangeChanges.reduce((a,b)=>a+b,0)/rangeChanges.length;const price=ctx.bar.close;
    if(volOfVol>0.5&&ctx.bar.close>ctx.bar.open){const stop=price-atr;const t=price+atr*1.5;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.55,pattern:"vov-spike-long",id:"volatility-of-vol"});}
    if(volOfVol>0.5&&ctx.bar.close<ctx.bar.open){const stop=price+atr;const t=price-atr*1.5;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.55,pattern:"vov-spike-short",id:"volatility-of-vol"});}return null;}}

/** Correlation Switch: When ES/NQ correlation breaks = opportunity. */
export class CorrelationSwitchStrategy implements Strategy {
  public readonly id="correlation-switch";public readonly description="Correlation regime switch: when ES/NQ decouple, trade the divergence.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<18)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const closes=h.map(b=>b.close);const firstHalf=closes.slice(0,10);const secondHalf=closes.slice(-10);
    const trend1=(firstHalf[firstHalf.length-1]-firstHalf[0])/firstHalf[0];const trend2=(secondHalf[secondHalf.length-1]-secondHalf[0])/secondHalf[0];
    if(trend1>0.001&&trend2<-0.001){const stop=ctx.bar.close+atr*0.5;const t=ctx.bar.close-atr*1.5;if(stop<=ctx.bar.close)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.56,pattern:"corr-switch-short",id:"correlation-switch"});}
    if(trend1<-0.001&&trend2>0.001){const stop=ctx.bar.close-atr*0.5;const t=ctx.bar.close+atr*1.5;if(stop>=ctx.bar.close)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.56,pattern:"corr-switch-long",id:"correlation-switch"});}return null;}}

/** Momentum Crash: Detect momentum strategy crashes (sharp reversals) → fade or exit. */
export class MomentumCrashStrategy implements Strategy {
  public readonly id="momentum-crash";public readonly description="Momentum crash detection: sharp reversal after extended trend = exit/fade signal.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-25);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const closes=h.map(b=>b.close);let upDays=0;for(let i=1;i<Math.min(15,closes.length);i++)if(closes[i]>closes[i-1])upDays++;
    const extended=upDays>=12||upDays<=3;const curRet=(ctx.bar.close-closes[closes.length-1])/closes[closes.length-1];
    if(extended&&upDays>=12&&curRet<-0.002){const stop=ctx.bar.close+atr*0.5;const t=ctx.bar.close-atr*2;if(stop<=ctx.bar.close)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.6,pattern:"mom-crash-short",id:"momentum-crash"});}
    if(extended&&upDays<=3&&curRet>0.002){const stop=ctx.bar.close-atr*0.5;const t=ctx.bar.close+atr*2;if(stop>=ctx.bar.close)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.6,pattern:"mom-crash-long",id:"momentum-crash"});}return null;}}

/** Liquidity Cascade: Sequential stop-loss triggering = cascade. Trade the cascade exhaustion. */
export class LiquidityCascadeStrategy implements Strategy {
  public readonly id="liquidity-cascade";public readonly description="Liquidity cascade: sequential stop runs → exhaustion. Fade the cascade.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-15);if(h.length<10)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    let consecutiveDown=0,consecutiveUp=0;const closes=h.map(b=>b.close);
    for(let i=closes.length-1;i>0;i--){if(closes[i]<closes[i-1])consecutiveDown++;else break;}
    for(let i=closes.length-1;i>0;i--){if(closes[i]>closes[i-1])consecutiveUp++;else break;}
    if(consecutiveDown>=5&&ctx.bar.close>ctx.bar.open){const stop=ctx.bar.low-atr*0.3;const t=ctx.bar.close+atr*1.5;
      if(stop>=ctx.bar.close)return null;return sg({context:ctx,side:"long",stop,target:t,confidence:0.62,pattern:"cascade-long",id:"liquidity-cascade"});}
    if(consecutiveUp>=5&&ctx.bar.close<ctx.bar.open){const stop=ctx.bar.high+atr*0.3;const t=ctx.bar.close-atr*1.5;
      if(stop<=ctx.bar.close)return null;return sg({context:ctx,side:"short",stop,target:t,confidence:0.62,pattern:"cascade-short",id:"liquidity-cascade"});}return null;}}
