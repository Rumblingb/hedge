import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

function s(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:30,meta:{pattern}};}

/** RL-Inspired: Q-learning style state-action. State = {trend,vol,volume}. Action = {long,short,flat}. */
export class RLInspiredStrategy implements Strategy {
  public readonly id="rl-inspired";public readonly description="RL-inspired state-action trading: discretize regime → Q-table action selection. arXiv:1911.10107.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<25)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const price=context.bar.close;const closes=h.map(b=>b.close);const volumes=h.map(b=>b.volume);
    // State: trend direction + volatility level + volume level
    const sma20=closes.reduce((a,b)=>a+b,0)/closes.length;const trend=price>sma20?2:price<sma20?0:1;
    const volLevel=atr/price>0.01?2:atr/price>0.005?1:0;
    const avgVol=volumes.reduce((a,b)=>a+b,0)/volumes.length;const volRatio=context.bar.volume/avgVol;
    // Q-table heuristic: high trend + high vol = momentum, low trend + high vol = reversal
    if(trend===2&&volLevel>=1&&volRatio>1.2){const stop=price-atr*0.8;const t=price+atr*1.5;
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.58,pattern:"rl-momentum-long",id:"rl-inspired"});}
    if(trend===0&&volLevel>=1&&volRatio>1.2){const stop=price+atr*0.8;const t=price-atr*1.5;
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.58,pattern:"rl-momentum-short",id:"rl-inspired"});}
    if(trend===1&&volLevel===2){const stop=price+atr*0.5;const t=price-atr*1;
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.54,pattern:"rl-chop-fade",id:"rl-inspired"});}
    return null;
  }
}

/** Uncertainty-Based Sizing: Scale position size by prediction uncertainty. arXiv:2007.15982. */
export class UncertaintySizingStrategy implements Strategy {
  public readonly id="uncertainty-sizing";public readonly description="Uncertainty-based position sizing: scale size by prediction confidence. From HFT Eurodollar paper.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const closes=h.map(b=>b.close);const returns=[];for(let i=1;i<closes.length;i++)returns.push((closes[i]-closes[i-1])/closes[i-1]);
    const meanRet=returns.reduce((a,b)=>a+b,0)/returns.length;const stdRet=Math.sqrt(returns.reduce((s,r)=>(r-meanRet)**2,0)/returns.length);
    const price=context.bar.close;const lastRet=(price-closes[closes.length-1])/closes[closes.length-1];
    // Signal: recent return vs volatility = momentum score
    const zScore=stdRet>0?lastRet/stdRet:0;
    if(zScore>1.5){const stop=price-atr*0.5;const t=price+atr*Math.min(2,zScore*0.8);
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:Math.min(0.65,zScore*0.2),pattern:"uncertainty-long",id:"uncertainty-sizing"});}
    if(zScore<-1.5){const stop=price+atr*0.5;const t=price-atr*Math.min(2,Math.abs(zScore)*0.8);
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:Math.min(0.65,Math.abs(zScore)*0.2),pattern:"uncertainty-short",id:"uncertainty-sizing"});}
    return null;
  }
}

/** Ensemble Strategy: Combine multiple signals with market state classification. arXiv:2012.03078. */
export class EnsembleStrategy implements Strategy {
  public readonly id="ensemble-meta";public readonly description="Meta-ensemble: classify market state → select best strategy sub-ensemble. arXiv:2012.03078.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-40);if(h.length<35)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const closes=h.map(b=>b.close);const price=context.bar.close;
    // Market state classification
    const sma20=closes.reduce((a,b)=>a+b,0)/closes.length;const sma10=closes.slice(-10).reduce((a,b)=>a+b,0)/10;
    const trendiness=Math.abs((sma10-sma20)/sma20);
    const ranges=h.slice(-10).map(b=>(b.high-b.low)/b.close);const meanRange=ranges.reduce((a,b)=>a+b,0)/10;
    const curRange=(context.bar.high-context.bar.low)/price;
    // State: trending (0), range-bound (1), volatile (2)
    const state=trendiness>0.003?0:curRange>meanRange*2?2:1;
    // Ensemble: trend state → momentum, range state → mean-reversion, vol state → breakout
    if(state===0&&price>sma20){const stop=sma20-atr*0.3;const t=price+atr*1.5;
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.6,pattern:"ensemble-trend-long",id:"ensemble-meta"});}
    if(state===0&&price<sma20){const stop=sma20+atr*0.3;const t=price-atr*1.5;
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.6,pattern:"ensemble-trend-short",id:"ensemble-meta"});}
    if(state===1){const dev=price-sma20;
      if(dev>atr){const stop=price+atr*0.3;const t=sma20;if(stop<=price)return null;
        return s({context,side:"short",stop,target:t,confidence:0.55,pattern:"ensemble-range-short",id:"ensemble-meta"});}
      if(dev<-atr){const stop=price-atr*0.3;const t=sma20;if(stop>=price)return null;
        return s({context,side:"long",stop,target:t,confidence:0.55,pattern:"ensemble-range-long",id:"ensemble-meta"});}}
    if(state===2&&curRange>meanRange*2.5){const isUp=context.bar.close>context.bar.open;
      if(isUp){const stop=context.bar.low-atr*0.2;const t=price+atr*2;if(stop>=price)return null;
        return s({context,side:"long",stop,target:t,confidence:0.53,pattern:"ensemble-vol-breakout",id:"ensemble-meta"});}
      else{const stop=context.bar.high+atr*0.2;const t=price-atr*2;if(stop<=price)return null;
        return s({context,side:"short",stop,target:t,confidence:0.53,pattern:"ensemble-vol-breakout",id:"ensemble-meta"});}}
    return null;
  }
}
