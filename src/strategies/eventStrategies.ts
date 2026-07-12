import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js"; import { averageTrueRange } from "../utils/indicators.js";
function sg(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

/** Opening Auction: Trade opening auction range breakout. First 2 min. */
export class OpeningAuctionStrategy implements Strategy{public readonly id="opening-auction";public readonly description="Opening auction range breakout: trade the opening 2-min auction range.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const sh=ctx.sessionHistory;if(sh.length<3)return null;
  const atr=averageTrueRange([...ctx.history.slice(-20),ctx.bar],14);if(atr<=0)return null;const d=new Date(ctx.bar.ts);const m=d.getUTCHours()*60+d.getUTCMinutes();
  if(m<14*60+32||m>14*60+35)return null;const auH=Math.max(sh[0].high,sh[1].high);const auL=Math.min(sh[0].low,sh[1].low);
  if(ctx.bar.close>auH){const stop=auL;const t=ctx.bar.close+atr*1.5;if(stop>=ctx.bar.close)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.58,pattern:"open-auction-long",id:"opening-auction"});}
  if(ctx.bar.close<auL){const stop=auH;const t=ctx.bar.close-atr*1.5;if(stop<=ctx.bar.close)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.58,pattern:"open-auction-short",id:"opening-auction"});}return null;}}

/** Closing Auction: Last 5-min order flow predicts next day. */
export class ClosingAuctionStrategy implements Strategy{public readonly id="closing-auction";public readonly description="Closing auction momentum: last 5-min imbalance → next-day direction.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-5);if(h.length<3)return null;
  const atr=averageTrueRange(ctx.history.slice(-20),14);if(atr<=0)return null;const d=new Date(ctx.bar.ts);
  if(d.getUTCHours()!==20||d.getUTCMinutes()>3)return null;const net=ctx.bar.close>ctx.bar.open?ctx.bar.volume:-ctx.bar.volume;
  if(net>0){const stop=ctx.bar.close-atr*0.3;const t=ctx.bar.close+atr*2;if(stop>=ctx.bar.close)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.53,pattern:"close-auction-long",id:"closing-auction"});}
  if(net<0){const stop=ctx.bar.close+atr*0.3;const t=ctx.bar.close-atr*2;if(stop<=ctx.bar.close)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.53,pattern:"close-auction-short",id:"closing-auction"});}return null;}}

/** Pre-FOMC drift: Markets drift into FOMC → trade the drift then exit before announcement. */
export class PreFomcDriftStrategy implements Strategy{public readonly id="pre-fomc-drift";public readonly description="Pre-FOMC drift: markets drift into FOMC → trade drift, exit before 2pm.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-30);if(h.length<25)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);
  const trend=closes.slice(-10).reduce((a,b)=>a+b,0)/10-closes.slice(0,10).reduce((a,b)=>a+b,0)/10;
  const d=new Date(ctx.bar.ts);if(d.getUTCHours()>=17)return null;const range=ctx.bar.high-ctx.bar.low;
  if(trend>atr*1.5&&range<atr*2){const stop=ctx.bar.close-atr*0.5;const t=ctx.bar.close+atr*1;if(stop>=ctx.bar.close)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.52,pattern:"fomc-drift-long",id:"pre-fomc-drift"});}
  if(trend<-atr*1.5&&range<atr*2){const stop=ctx.bar.close+atr*0.5;const t=ctx.bar.close-atr*1;if(stop<=ctx.bar.close)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.52,pattern:"fomc-drift-short",id:"pre-fomc-drift"});}return null;}}

/** Post-FOMC fade: Initial FOMC spike usually fades. */
export class PostFomcFadeStrategy implements Strategy{public readonly id="post-fomc-fade";public readonly description="Post-FOMC fade: initial FOMC move fades within 30 min. Fade the spike.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-10);if(h.length<8)return null;
  const atr=averageTrueRange(ctx.history.slice(-20),14);if(atr<=0)return null;const curR=(ctx.bar.high-ctx.bar.low)/ctx.bar.close;
  const avgR=h.map(b=>(b.high-b.low)/b.close).reduce((a,b)=>a+b,0)/h.length;
  if(curR<avgR*3)return null;const price=ctx.bar.close;const isUp=ctx.bar.close>h[h.length-1].close;
  if(isUp&&ctx.bar.close<ctx.bar.high-(ctx.bar.high-ctx.bar.low)*0.3){const stop=ctx.bar.high;const t=price-atr*1;
    if(stop<=price)return null;return sg({context:ctx,side:"short",stop,target:t,confidence:0.56,pattern:"post-fomc-fade-short",id:"post-fomc-fade"});}
  if(!isUp&&ctx.bar.close>ctx.bar.low+(ctx.bar.high-ctx.bar.low)*0.3){const stop=ctx.bar.low;const t=price+atr*1;
    if(stop>=price)return null;return sg({context:ctx,side:"long",stop,target:t,confidence:0.56,pattern:"post-fomc-fade-long",id:"post-fomc-fade"});}return null;}}

/** NFP Reaction: Non-farm payrolls → initial spike direction = trade. */
export class NfpReactionStrategy implements Strategy{public readonly id="nfp-reaction";public readonly description="NFP reaction: trade first 5-min move direction on payroll day.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-10);if(h.length<8)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const curR=(ctx.bar.high-ctx.bar.low)/ctx.bar.close;
  const avgR=h.map(b=>(b.high-b.low)/b.close).reduce((a,b)=>a+b,0)/h.length;
  if(curR<avgR*3)return null;const price=ctx.bar.close;
  if(ctx.bar.close>ctx.bar.open&&curR>avgR*2.5){const stop=price-atr*0.5;const t=price+atr*1.5;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.6,pattern:"nfp-long",id:"nfp-reaction"});}
  if(ctx.bar.close<ctx.bar.open&&curR>avgR*2.5){const stop=price+atr*0.5;const t=price-atr*1.5;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.6,pattern:"nfp-short",id:"nfp-reaction"});}return null;}}
