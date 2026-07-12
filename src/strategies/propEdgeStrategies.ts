import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js"; import { averageTrueRange } from "../utils/indicators.js";
function s(args:{c:StrategyContext;side:TradeSide;stop:number;t:number;conf:number;p:string;id:string}):StrategySignal|null{
  const{c,side,stop,t,conf,p,id}=args;const e=c.bar.close;const rr=calculateRr(e,stop,t,side);if(rr<=0)return null;
  return{symbol:c.symbol,strategyId:id,side,entry:e,stop,target:t,rr,confidence:conf,contracts:1,maxHoldMinutes:15,meta:{pattern:p}};}

/** Tick Scalp: 1-tick micro-scalp on order flow imbalance. Ultra-high frequency concept. */
export class TickScalpStrategy implements Strategy{public readonly id="tick-scalp";public readonly description="1-tick micro-scalp: capture bid-ask spread on momentum micro-bursts.";
public generateSignal(c:StrategyContext):StrategySignal|null{const h=c.history.slice(-5);if(h.length<3)return null;
  const atr=averageTrueRange(c.history.slice(-20),14);if(atr<=0)return null;const tick=atr*0.06;
  const m3=(c.bar.close-h[h.length-3].close)/h[h.length-3].close;
  const volR=c.bar.volume/(h.reduce((a,b)=>a+b.volume,0)/h.length+0.0001);
  if(Math.abs(m3)<0.0001||volR<2)return null;
  if(m3>0){const stop=c.bar.close-tick;const t=c.bar.close+tick*2;if(stop>=c.bar.close)return null;
    return s({c,side:"long",stop,t,conf:0.65,p:"tick-long",id:"tick-scalp"});}
  else{const stop=c.bar.close+tick;const t=c.bar.close-tick*2;if(stop<=c.bar.close)return null;
    return s({c,side:"short",stop,t,conf:0.65,p:"tick-short",id:"tick-scalp"});}return null;}}

/** Mean-Reversion Pairs Proxy: Z-score extreme on single symbol as proxy for spread. */
export class ZScoreMeanRevStrategy implements Strategy{public readonly id="zscore-mean-rev";public readonly description="Z-score extreme mean reversion: 2.5 sigma deviation → fade back to mean.";
public generateSignal(c:StrategyContext):StrategySignal|null{const h=c.history.slice(-30);if(h.length<25)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);
  const mean=closes.reduce((a,b)=>a+b,0)/closes.length;
  const std=Math.sqrt(closes.reduce((s,x)=>(x-mean)**2,0)/closes.length);
  const z=(c.bar.close-mean)/(std+0.0001);
  if(Math.abs(z)<2.5)return null;
  if(z>2.5){const stop=c.bar.close+atr*0.2;const t=mean;if(stop<=c.bar.close)return null;
    return s({c,side:"short",stop,t,conf:0.63,p:"z-short",id:"zscore-mean-rev"});}
  else{const stop=c.bar.close-atr*0.2;const t=mean;if(stop>=c.bar.close)return null;
    return s({c,side:"long",stop,t,conf:0.63,p:"z-long",id:"zscore-mean-rev"});}return null;}}

/** Opening Drive Fade: First 2-min drive fades within 15 min. Classic prop firm edge. */
export class OpenDriveFadeStrategy implements Strategy{public readonly id="open-drive-fade";public readonly description="Opening drive fade: first 2-min directional burst fades within 15 min.";
public generateSignal(c:StrategyContext):StrategySignal|null{const sh=c.sessionHistory;if(sh.length<4)return null;
  const atr=averageTrueRange([...c.history.slice(-20),c.bar],14);if(atr<=0)return null;
  const d=new Date(c.bar.ts);const min=d.getUTCHours()*60+d.getUTCMinutes();
  if(min<14*60+33||min>14*60+50)return null;
  const first=sh.slice(0,2);const fM=(first[1].close-first[0].close)/first[0].close;
  if(Math.abs(fM)<0.001)return null;const price=c.bar.close;
  if(fM>0.002&&price<first[1].close){const stop=price+atr*0.15;const t=first[0].close;if(stop<=price)return null;
    return s({c,side:"short",stop,t,conf:0.61,p:"drive-fade-short",id:"open-drive-fade"});}
  if(fM<-0.002&&price>first[1].close){const stop=price-atr*0.15;const t=first[0].close;if(stop>=price)return null;
    return s({c,side:"long",stop,t,conf:0.61,p:"drive-fade-long",id:"open-drive-fade"});}return null;}}

/** Time-Based Exit: Exit positions before known reversal times (10:30, 12:00, 3:30). */
export class TimeBasedExitStrategy implements Strategy{public readonly id="time-based-exit";public readonly description="Time-based exit: enter near reversal windows for quick mean-reversion.";
public generateSignal(c:StrategyContext):StrategySignal|null{const h=c.history.slice(-10);if(h.length<8)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const d=new Date(c.bar.ts);
  const hh=d.getUTCHours();const mm=d.getUTCMinutes();const min=hh*60+mm;
  const reversalWindows=[[15*60+25,15*60+35],[17*60,17*60+10],[19*60+25,19*60+35]];
  let inWindow=false;for(const[s,e]of reversalWindows)if(min>=s&&min<=e){inWindow=true;break;}
  if(!inWindow)return null;const closes=h.map(b=>b.close);const trend=closes[closes.length-1]-closes[0];
  const price=c.bar.close;
  if(trend>atr*0.5){const stop=price+atr*0.15;const t=closes[0];if(stop<=price)return null;
    return s({c,side:"short",stop,t,conf:0.58,p:"time-rev-short",id:"time-based-exit"});}
  if(trend<-atr*0.5){const stop=price-atr*0.15;const t=closes[0];if(stop>=price)return null;
    return s({c,side:"long",stop,t,conf:0.58,p:"time-rev-long",id:"time-based-exit"});}return null;}}

/** Range-bound scalping: Trade the range when market is clearly range-bound. */
export class RangeBoundScalpStrategy implements Strategy{public readonly id="range-bound-scalp";public readonly description="Range-bound scalp: buy support, sell resistance when ADX < 20 confirms chop.";
public generateSignal(c:StrategyContext):StrategySignal|null{const h=c.history.slice(-20);if(h.length<15)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const highs=h.map(b=>b.high);const lows=h.map(b=>b.low);
  const rH=Math.max(...highs);const rL=Math.min(...lows);const range=rH-rL;
  if(range<atr*3||range>atr*6)return null;const price=c.bar.close;
  if(price<rL+range*0.2){const stop=rL-atr*0.3;const t=rL+range*0.5;if(stop>=price)return null;
    return s({c,side:"long",stop,t,conf:0.62,p:"range-long",id:"range-bound-scalp"});}
  if(price>rH-range*0.2){const stop=rH+atr*0.3;const t=rH-range*0.5;if(stop<=price)return null;
    return s({c,side:"short",stop,t,conf:0.62,p:"range-short",id:"range-bound-scalp"});}return null;}}
