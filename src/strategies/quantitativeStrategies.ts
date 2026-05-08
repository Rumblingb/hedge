import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

function sg(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

/** Dispersion Trading: Long index vol, short single-stock vol proxy. Use NQ vs individual tech proxy. */
export class DispersionTradingStrategy implements Strategy {
  public readonly id="dispersion-trading";public readonly description="Dispersion: trade correlation breakdown. Long index vol proxy, short individual vol proxy.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<25)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const ranges=h.map(b=>(b.high-b.low)/b.close);const curRange=(context.bar.high-context.bar.low)/context.bar.close;
    const avgRange=ranges.reduce((a,b)=>a+b,0)/ranges.length;
    const price=context.bar.close;
    // When NQ vol > ES vol (dispersion) → individual names moving differently from index
    if(curRange>avgRange*2&&context.bar.volume>h.reduce((s,b)=>s+b.volume,0)/h.length*1.5){
      if(context.bar.close>context.bar.open){const stop=price-atr;const t=price+atr*1.5;
        if(stop>=price)return null;return sg({context,side:"long",stop,target:t,confidence:0.55,pattern:"dispersion-long",id:"dispersion-trading"});}
      else{const stop=price+atr;const t=price-atr*1.5;
        if(stop<=price)return null;return sg({context,side:"short",stop,target:t,confidence:0.55,pattern:"dispersion-short",id:"dispersion-trading"});}}
    return null;
  }
}

/** Pairs Convergence: Z-score based mean reversion on NQ/ES spread. Classic stat arb. */
export class PairsConvergenceStrategy implements Strategy {
  public readonly id="pairs-convergence";public readonly description="NQ/ES spread convergence: z-score >2 = short spread, z-score <-2 = long spread.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    if(context.symbol!=="NQ"&&context.symbol!=="ES")return null;
    const h=context.history.slice(-40);if(h.length<30)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const closes=h.map(b=>b.close);const sma=closes.reduce((a,b)=>a+b,0)/closes.length;
    const std=Math.sqrt(closes.reduce((s,c)=>(c-sma)**2,0)/closes.length);
    const price=context.bar.close;const z=(price-sma)/(std+0.0001);
    if(z>2&&context.symbol==="NQ"){const stop=price+atr*0.3;const t=sma;if(stop<=price)return null;
      return sg({context,side:"short",stop,target:t,confidence:0.6,pattern:"pairs-z-short",id:"pairs-convergence"});}
    if(z<-2&&context.symbol==="ES"){const stop=price-atr*0.3;const t=sma;if(stop>=price)return null;
      return sg({context,side:"long",stop,target:t,confidence:0.6,pattern:"pairs-z-long",id:"pairs-convergence"});}
    return null;
  }
}

/** Implied Correlation: VIX/equity correlation regime. High corr = systemic risk, reduce size. */
export class ImpliedCorrelationStrategy implements Strategy {
  public readonly id="implied-correlation";public readonly description="Implied correlation proxy: when all assets move together = systemic, fade breakouts.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-25);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // Correlation proxy: consecutive bars in same direction = high correlation
    const closes=h.map(b=>b.close);let sameDir=0;
    for(let i=1;i<Math.min(15,closes.length);i++)if((closes[i]-closes[i-1])*(closes[i-1]-closes[i-2]||0)>0)sameDir++;
    const corrHigh=sameDir>10;const price=context.bar.close;
    if(corrHigh){const sma10=closes.slice(-10).reduce((a,b)=>a+b,0)/10;
      if(price>sma10+atr){const stop=price+atr*0.3;const t=sma10;if(stop<=price)return null;
        return sg({context,side:"short",stop,target:t,confidence:0.55,pattern:"high-corr-fade",id:"implied-correlation"});}
      if(price<sma10-atr){const stop=price-atr*0.3;const t=sma10;if(stop>=price)return null;
        return sg({context,side:"long",stop,target:t,confidence:0.55,pattern:"high-corr-fade",id:"implied-correlation"});}}
    return null;
  }
}

/** Tail Risk Hedge: Detect extreme moves → position for reversal or continuation. */
export class TailRiskStrategy implements Strategy {
  public readonly id="tail-risk";public readonly description="Tail risk detection: 4+ sigma moves → fade extreme moves, ride momentum on 3-sigma.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-50);if(h.length<40)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const returns=[];for(let i=1;i<h.length;i++)returns.push((h[i].close-h[i-1].close)/h[i-1].close);
    const meanRet=returns.reduce((a,b)=>a+b,0)/returns.length;
    const stdRet=Math.sqrt(returns.reduce((s,r)=>(r-meanRet)**2,0)/returns.length);
    const curRet=(context.bar.close-h[h.length-1].close)/h[h.length-1].close;
    const sigmas=stdRet>0?Math.abs(curRet)/stdRet:0;const price=context.bar.close;
    if(sigmas>4){if(curRet>0){const stop=price-atr*0.3;const t=price+atr*0.8;if(stop>=price)return null;
        return sg({context,side:"long",stop,target:t,confidence:0.6,pattern:"tail-reversal-long",id:"tail-risk"});}
      else{const stop=price+atr*0.3;const t=price-atr*0.8;if(stop<=price)return null;
        return sg({context,side:"short",stop,target:t,confidence:0.6,pattern:"tail-reversal-short",id:"tail-risk"});}}
    if(sigmas>3&&sigmas<=4){if(curRet>0){const stop=price-atr*0.5;const t=price+atr*1.2;if(stop>=price)return null;
        return sg({context,side:"long",stop,target:t,confidence:0.58,pattern:"tail-momentum-long",id:"tail-risk"});}
      else{const stop=price+atr*0.5;const t=price-atr*1.2;if(stop<=price)return null;
        return sg({context,side:"short",stop,target:t,confidence:0.58,pattern:"tail-momentum-short",id:"tail-risk"});}}
    return null;
  }
}

/** Regime Probability: Bayesian regime probability update. Most likely regime → trade accordingly. */
export class RegimeProbabilityStrategy implements Strategy {
  public readonly id="regime-probability";public readonly description="Bayesian regime probability: update regime belief, trade most likely regime direction.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<25)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // Simple regime detection: trend, chop, vol
    const closes=h.map(b=>b.close);const returns=[];for(let i=1;i<closes.length;i++)returns.push(closes[i]-closes[i-1]);
    const trendScore=Math.abs(returns.reduce((a,b)=>a+b,0))/returns.length;
    const volScore=returns.reduce((s,r)=>s+r*r,0)/returns.length;
    const price=context.bar.close;const sma10=closes.slice(-10).reduce((a,b)=>a+b,0)/10;
    // Trend probability high → trade direction
    if(trendScore>volScore*0.5&&price>sma10){const stop=sma10-atr*0.3;const t=price+atr*1.5;
      if(stop>=price)return null;return sg({context,side:"long",stop,target:t,confidence:0.58,pattern:"regime-trend-long",id:"regime-probability"});}
    if(trendScore>volScore*0.5&&price<sma10){const stop=sma10+atr*0.3;const t=price-atr*1.5;
      if(stop<=price)return null;return sg({context,side:"short",stop,target:t,confidence:0.58,pattern:"regime-trend-short",id:"regime-probability"});}
    if(trendScore<volScore*0.3){const dev=price-sma10;
      if(dev>atr){const stop=price+atr*0.3;const t=sma10;if(stop<=price)return null;
        return sg({context,side:"short",stop,target:t,confidence:0.53,pattern:"regime-chop-fade",id:"regime-probability"});}
      if(dev<-atr){const stop=price-atr*0.3;const t=sma10;if(stop>=price)return null;
        return sg({context,side:"long",stop,target:t,confidence:0.53,pattern:"regime-chop-fade",id:"regime-probability"});}}
    return null;
  }
}
