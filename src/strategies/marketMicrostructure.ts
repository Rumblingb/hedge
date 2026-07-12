import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

function s(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

/** Order Flow Imbalance: Multi-level OFI from limit order book proxy. arXiv:1907.06230. */
export class OrderFlowImbalanceStrategy implements Strategy {
  public readonly id="order-flow-imbalance";public readonly description="Multi-level OFI: buy/sell pressure from bar-level order flow proxy. arXiv:1907.06230.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-20);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // OFI proxy: buy pressure = close>open volume weighted, sell = close<open weighted
    let buyPressure=0,sellPressure=0;
    for(const b of h){if(b.close>b.open)buyPressure+=b.volume*(b.close-b.open)/(b.high-b.low+0.0001);
      else sellPressure+=b.volume*(b.open-b.close)/(b.high-b.low+0.0001);}
    const curBuy=context.bar.close>context.bar.open?context.bar.volume*(context.bar.close-context.bar.open)/(context.bar.high-context.bar.low+0.0001):0;
    const curSell=context.bar.close<context.bar.open?context.bar.volume*(context.bar.open-context.bar.close)/(context.bar.high-context.bar.low+0.0001):0;
    const totalBuy=buyPressure+curBuy;const totalSell=sellPressure+curSell;
    const ofi=totalBuy-totalSell;const price=context.bar.close;
    if(ofi>0&&curBuy>curSell*2&&price>h[h.length-5].close){const stop=price-atr*0.5;const t=price+atr*1.5;
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.59,pattern:"ofi-long",id:"order-flow-imbalance"});}
    if(ofi<0&&curSell>curBuy*2&&price<h[h.length-5].close){const stop=price+atr*0.5;const t=price-atr*1.5;
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.59,pattern:"ofi-short",id:"order-flow-imbalance"});}
    return null;
  }
}

/** Hawkes Process: Self-exciting point process for order flow clustering. arXiv:1602.03944. */
export class HawkesProcessStrategy implements Strategy {
  public readonly id="hawkes-process";public readonly description="Hawkes process order flow: self-exciting clustering detects momentum bursts. arXiv:1602.03944.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<25)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // Hawkes intensity proxy: consecutive bars in same direction with increasing volume
    const closes=h.map(b=>b.close);const volumes=h.map(b=>b.volume);
    let streak=0;let prevDir=0;for(let i=h.length-10;i<h.length;i++){
      const dir=h[i].close>h[i].open?1:h[i].close<h[i].open?-1:0;
      if(dir===prevDir&&dir!==0)streak++;else{if(dir!==0)streak=1;prevDir=dir;}
    }
    const price=context.bar.close;const curDir=context.bar.close>context.bar.open?1:-1;
    // Self-exciting: streak + vol increasing = cluster
    const recentVol=volumes.slice(-5);const volIncreasing=recentVol[4]>recentVol[0]*1.2;
    if(streak>=3&&volIncreasing&&curDir===prevDir){
      if(curDir===1){const stop=price-atr*0.5;const t=price+atr*2;
        if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.6,pattern:"hawkes-long",id:"hawkes-process"});}
      if(curDir===-1){const stop=price+atr*0.5;const t=price-atr*2;
        if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.6,pattern:"hawkes-short",id:"hawkes-process"});}}
    return null;
  }
}

/** HARNet Vol Forecasting: Predict vol regime for sizing. arXiv:2205.07719. Neural net approximated. */
export class HARNetVolStrategy implements Strategy {
  public readonly id="harnet-vol";public readonly description="HARNet volatility forecasting: predict vol expansion/contraction for pre-positioning. arXiv:2205.07719.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const ranges=h.map(b=>(b.high-b.low)/b.close);const closes=h.map(b=>b.close);
    // HAR model approximation: daily/weekly/monthly vol components
    const dailyRV=ranges.slice(-5).reduce((a,b)=>a+b,0)/5;
    const weeklyRV=ranges.slice(-20).reduce((a,b)=>a+b,0)/Math.min(20,ranges.length);
    const monthlyRV=ranges.reduce((a,b)=>a+b,0)/ranges.length;
    // HARNet: if daily RV > weekly, vol expanding → trade breakout
    const curRV=(context.bar.high-context.bar.low)/context.bar.close;
    const volExpanding=dailyRV>weeklyRV*1.2&&curRV>dailyRV;
    const volContracting=dailyRV<weeklyRV*0.7&&curRV<dailyRV;
    const price=context.bar.close;const direction=price>closes[closes.length-5];
    if(volExpanding&&direction){const stop=price-atr*0.6;const t=price+atr*1.8;
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.58,pattern:"harnet-expand",id:"harnet-vol"});}
    if(volExpanding&&!direction){const stop=price+atr*0.6;const t=price-atr*1.8;
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.58,pattern:"harnet-expand",id:"harnet-vol"});}
    if(volContracting){const dev=price-closes[closes.length-5];
      if(dev>0){const stop=price-atr*0.3;const t=price+atr*0.8;if(stop>=price)return null;
        return s({context,side:"long",stop,target:t,confidence:0.52,pattern:"harnet-contract",id:"harnet-vol"});}}
    return null;
  }
}

/** Optimal Execution: Use market impact model for entry timing. arXiv:1412.4839. */
export class OptimalExecutionStrategy implements Strategy {
  public readonly id="optimal-execution";public readonly description="Optimal execution with market impact: time entries when impact minimal. arXiv:1412.4839.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-15);if(h.length<10)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // Market impact proxy: price moves against trade direction = impact
    const curBar=context.bar;const prevBar=h[h.length-1];const price=curBar.close;
    const spread=(curBar.high-curBar.low)/price;
    const volume=curBar.volume;const prevVol=h.slice(-5).reduce((s,b)=>s+b.volume,0)/5;
    // Low impact entry: tight spread + normal volume + near VWAP
    const closes=h.map(b=>b.close);const vols=h.map(b=>b.volume);
    const vwap=closes.reduce((s,c,i)=>s+c*vols[i],0)/vols.reduce((s,v)=>s+v,0);
    const lowImpact=spread<atr/price*0.8&&volume<prevVol*1.5&&Math.abs(price-vwap)<atr*0.5;
    if(!lowImpact)return null;
    const direction=price>closes[closes.length-5]?1:price<closes[closes.length-5]?-1:0;
    if(direction===1){const stop=price-atr*0.5;const t=price+atr*1.2;
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.56,pattern:"opt-exec-long",id:"optimal-execution"});}
    if(direction===-1){const stop=price+atr*0.5;const t=price-atr*1.2;
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.56,pattern:"opt-exec-short",id:"optimal-execution"});}
    return null;
  }
}
