import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

function s(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

function findSwings(highs:number[],lows:number[],lookback:number=20):{swingHighs:number[],swingLows:number[]}{
  const sh:number[]=[],sl:number[]=[];const start=Math.max(0,highs.length-lookback);
  for(let i=start+1;i<highs.length-1;i++){
    if(highs[i]>highs[i-1]&&highs[i]>highs[i+1])sh.push(highs[i]);
    if(lows[i]<lows[i-1]&&lows[i]<lows[i+1])sl.push(lows[i]);}
  return{swingHighs:sh,swingLows:sl};}

/** Head and Shoulders: Three-peak reversal pattern. Left shoulder < Head > Right shoulder. */
export class HeadShouldersStrategy implements Strategy {
  public readonly id="head-shoulders";public readonly description="Head and shoulders top/bottom: classic reversal pattern with neckline break.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-60);if(h.length<40)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const{swingHighs,swingLows}=findSwings(h.map(b=>b.high),h.map(b=>b.low),50);
    if(swingHighs.length<3)return null;const sh=swingHighs.slice(-3);const sl=swingLows.slice(-3);
    // H&S Top: 3 peaks, middle highest
    if(sh[0]<sh[1]&&sh[2]<sh[1]&&sl.length>=2&&context.bar.close<sl[sl.length-2]){
      const stop=sh[1]+atr*0.3;const t=context.bar.close-atr*2;if(stop<=context.bar.close)return null;
      return s({context,side:"short",stop,target:t,confidence:0.65,pattern:"hs-top",id:"head-shoulders"});}
    // Inverse H&S: 3 troughs, middle lowest
    if(sl[0]>sl[1]&&sl[2]>sl[1]&&sh.length>=2&&context.bar.close>sh[sh.length-2]){
      const stop=sl[1]-atr*0.3;const t=context.bar.close+atr*2;if(stop>=context.bar.close)return null;
      return s({context,side:"long",stop,target:t,confidence:0.65,pattern:"hs-bottom",id:"head-shoulders"});}
    return null;
  }
}

/** Double Top/Bottom: Two peaks/troughs at similar level → reversal. */
export class DoubleTopBottomStrategy implements Strategy {
  public readonly id="double-top-bottom";public readonly description="Double top/bottom: two peaks/troughs at same level = exhaustion reversal.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-40);if(h.length<30)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const{swingHighs,swingLows}=findSwings(h.map(b=>b.high),h.map(b=>b.low),30);
    if(swingHighs.length<2||swingLows.length<2)return null;
    const dh=swingHighs.slice(-2);const dl=swingLows.slice(-2);
    // Double top
    if(Math.abs(dh[0]-dh[1])<atr*0.5&&context.bar.close<Math.min(dh[0],dh[1])-atr*0.3){
      const stop=Math.max(dh[0],dh[1])+atr*0.3;const t=context.bar.close-atr*1.5;if(stop<=context.bar.close)return null;
      return s({context,side:"short",stop,target:t,confidence:0.62,pattern:"double-top",id:"double-top-bottom"});}
    // Double bottom
    if(Math.abs(dl[0]-dl[1])<atr*0.5&&context.bar.close>Math.max(dl[0],dl[1])+atr*0.3){
      const stop=Math.min(dl[0],dl[1])-atr*0.3;const t=context.bar.close+atr*1.5;if(stop>=context.bar.close)return null;
      return s({context,side:"long",stop,target:t,confidence:0.62,pattern:"double-bottom",id:"double-top-bottom"});}
    return null;
  }
}

/** Flag/Pennant: Sharp move (pole) + consolidation (flag) = continuation breakout. */
export class FlagPennantStrategy implements Strategy {
  public readonly id="flag-pennant";public readonly description="Flag/pennant continuation: sharp pole move + tight consolidation = breakout continuation.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const closes=h.map(b=>b.close);const ranges=h.slice(-8).map(b=>(b.high-b.low)/b.close);
    const pole=h.slice(-20,-8);const flag=h.slice(-8);
    const poleMove=pole[pole.length-1].close-pole[0].close;
    const flagRange=Math.max(...flag.map(b=>b.high))-Math.min(...flag.map(b=>b.low));
    const squeezing=ranges.every((r,i)=>i===0||r<=ranges[i-1]*1.05);
    // Bull flag
    if(poleMove>atr*2&&flagRange<atr*1.2&&squeezing&&context.bar.close>Math.max(...flag.map(b=>b.high))){
      const stop=Math.min(...flag.map(b=>b.low));const t=context.bar.close+poleMove*0.8;
      if(stop>=context.bar.close)return null;return s({context,side:"long",stop,target:t,confidence:0.61,pattern:"bull-flag",id:"flag-pennant"});}
    // Bear flag
    if(poleMove<-atr*2&&flagRange<atr*1.2&&squeezing&&context.bar.close<Math.min(...flag.map(b=>b.low))){
      const stop=Math.max(...flag.map(b=>b.high));const t=context.bar.close+poleMove*0.8;
      if(stop<=context.bar.close)return null;return s({context,side:"short",stop,target:t,confidence:0.61,pattern:"bear-flag",id:"flag-pennant"});}
    return null;
  }
}

/** Wedge Breakout: Rising/falling wedge = exhaustion → reversal breakout. */
export class WedgeBreakoutStrategy implements Strategy {
  public readonly id="wedge-breakout";public readonly description="Rising/falling wedge exhaustion: converging trendlines → reversal breakout.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-25);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const highs=h.map(b=>b.high);const lows=h.map(b=>b.low);const closes=h.map(b=>b.close);
    const half=Math.floor(h.length/2);const firstHighs=highs.slice(0,half);const lastHighs=highs.slice(-half);
    const firstLows=lows.slice(0,half);const lastLows=lows.slice(-half);
    const highSlope=(Math.max(...lastHighs)-Math.max(...firstHighs))/half;
    const lowSlope=(Math.max(...lastLows)-Math.max(...firstLows))/half;
    // Falling wedge: highs falling faster than lows = bullish reversal
    if(highSlope<-atr*0.001&&lowSlope>highSlope*0.5&&context.bar.close>Math.max(...lastHighs)){
      const stop=Math.min(...lows.slice(-5));const t=context.bar.close+atr*2;if(stop>=context.bar.close)return null;
      return s({context,side:"long",stop,target:t,confidence:0.58,pattern:"falling-wedge",id:"wedge-breakout"});}
    // Rising wedge: lows rising faster than highs = bearish reversal
    if(lowSlope>atr*0.001&&highSlope<lowSlope*0.5&&context.bar.close<Math.min(...lastLows)){
      const stop=Math.max(...highs.slice(-5));const t=context.bar.close-atr*2;if(stop<=context.bar.close)return null;
      return s({context,side:"short",stop,target:t,confidence:0.58,pattern:"rising-wedge",id:"wedge-breakout"});}
    return null;
  }
}
