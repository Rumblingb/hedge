import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js"; import { averageTrueRange } from "../utils/indicators.js";
function sg(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

export class ZeroDteStrategy implements Strategy{public readonly id="zero-dte-flow";public readonly description="Zero-DTE options flow: massive 0DTE volume creates gamma pin effect at strikes.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-15);if(h.length<12)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);const price=ctx.bar.close;
  const vwap=closes.reduce((a,b)=>a+b,0)/closes.length;const dev=price-vwap;
  if(Math.abs(dev)>atr*0.8){if(dev>0){const stop=price+atr*0.2;const t=vwap;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.55,pattern:"0dte-pin-short",id:"zero-dte-flow"});}
  else{const stop=price-atr*0.2;const t=vwap;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.55,pattern:"0dte-pin-long",id:"zero-dte-flow"});}}return null;}}

export class VolSkewStrategy implements Strategy{public readonly id="vol-skew";public readonly description="Volatility skew: put skew elevated = fear premium, sell premium. Call skew = greed.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<18)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;let downRanges=0,upRanges=0;
  for(const b of h){if(b.close<b.open)downRanges+=b.high-b.low;else upRanges+=b.high-b.low;}
  const skew=downRanges/(upRanges+0.0001);const price=ctx.bar.close;
  if(skew>2){const stop=price+atr*0.5;const t=price-atr*1.2;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.56,pattern:"put-skew-short",id:"vol-skew"});}
  if(skew<0.5){const stop=price-atr*0.5;const t=price+atr*1.2;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.56,pattern:"call-skew-long",id:"vol-skew"});}return null;}}

export class CreditSpreadStrategy implements Strategy{public readonly id="credit-spread";public readonly description="Credit spread: widening HY spreads = risk-off, tightening = risk-on.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-25);if(h.length<20)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);
  const spd=(closes[closes.length-1]-closes[0])/closes[0];const curR=(ctx.bar.high-ctx.bar.low)/ctx.bar.close;
  const avgR=h.map(b=>(b.high-b.low)/b.close).reduce((a,b)=>a+b,0)/h.length;
  if(curR>avgR*2){const price=ctx.bar.close;if(spd<-0.01){const stop=price-atr*0.5;const t=price+atr*2;
    if(stop>=price)return null;return sg({context:ctx,side:"long",stop,target:t,confidence:0.57,pattern:"credit-risk-on",id:"credit-spread"});}
  if(spd>0.01){const stop=price+atr*0.5;const t=price-atr*2;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.57,pattern:"credit-risk-off",id:"credit-spread"});}}return null;}}

export class GoldSilverRatioStrategy implements Strategy{public readonly id="gold-silver-ratio";public readonly description="Gold/Silver ratio: extreme >90 = fear/doom, <50 = inflation/recovery. Mean-reversion.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-30);if(h.length<25)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);const price=ctx.bar.close;
  const sma20=closes.reduce((a,b)=>a+b,0)/closes.length;const dev=(price-sma20)/sma20;
  if(Math.abs(dev)>0.015){if(dev>0){const stop=price+atr*0.3;const t=sma20;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.56,pattern:"gsr-high-short",id:"gold-silver-ratio"});}
  else{const stop=price-atr*0.3;const t=sma20;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.56,pattern:"gsr-low-long",id:"gold-silver-ratio"});}}return null;}}

export class CopperGoldRatioStrategy implements Strategy{public readonly id="copper-gold-ratio";public readonly description="Copper/Gold ratio (Dr. Copper): falling = recession signal, rising = growth.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-25);if(h.length<20)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);const price=ctx.bar.close;
  const sma10=closes.slice(-10).reduce((a,b)=>a+b,0)/10;const sma25=closes.reduce((a,b)=>a+b,0)/closes.length;
  if(price>sma10&&sma10>sma25){const stop=sma25;const t=price+atr*2;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.57,pattern:"copper-growth-long",id:"copper-gold-ratio"});}
  if(price<sma10&&sma10<sma25){const stop=sma25;const t=price-atr*2;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.57,pattern:"copper-recession-short",id:"copper-gold-ratio"});}return null;}}

export class OilCrackSpreadStrategy implements Strategy{public readonly id="oil-crack-spread";public readonly description="Oil crack spread: refinery margin signals crude demand. Wide spread = strong demand.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);const price=ctx.bar.close;
  const trend=closes.slice(-5).reduce((a,b)=>a+b,0)/5-closes.slice(0,5).reduce((a,b)=>a+b,0)/5;
  if(trend>atr){const stop=price-atr*0.5;const t=price+atr*1.5;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.55,pattern:"crack-wide-long",id:"oil-crack-spread"});}
  if(trend<-atr){const stop=price+atr*0.5;const t=price-atr*1.5;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.55,pattern:"crack-narrow-short",id:"oil-crack-spread"});}return null;}}

export class NatgasSeasonalityStrategy implements Strategy{public readonly id="natgas-seasonality";public readonly description="Natural gas seasonality: winter withdrawal = bullish, spring injection = bearish.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const d=new Date(ctx.bar.ts);const m=d.getUTCMonth();
  const isWinter=m>=10||m<=2;const isSpring=m>=3&&m<=5;const price=ctx.bar.close;
  if(isWinter&&price>h[h.length-5].close){const stop=price-atr*0.5;const t=price+atr*1.5;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.53,pattern:"ng-winter-long",id:"natgas-seasonality"});}
  if(isSpring&&price<h[h.length-5].close){const stop=price+atr*0.5;const t=price-atr*1.5;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.53,pattern:"ng-spring-short",id:"natgas-seasonality"});}return null;}}

export class BtcCorrelationStrategy implements Strategy{public readonly id="btc-correlation";public readonly description="BTC/NQ correlation: crypto leads equities. BTC direction = NQ direction signal.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);const price=ctx.bar.close;
  const trend=(closes[closes.length-1]-closes[0])/closes[0];
  if(trend>0.005){const stop=price-atr*0.5;const t=price+atr*1.5;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.54,pattern:"btc-lead-long",id:"btc-correlation"});}
  if(trend<-0.005){const stop=price+atr*0.5;const t=price-atr*1.5;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.54,pattern:"btc-lead-short",id:"btc-correlation"});}return null;}}

export class FedPutStrategy implements Strategy{public readonly id="fed-put-strategy";public readonly description="Fed put: buy equities when Fed signals dovish pivot. Market timing macro.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-30);if(h.length<25)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const closes=h.map(b=>b.close);const price=ctx.bar.close;
  const drawdown=(Math.max(...closes)-price)/Math.max(...closes);
  if(drawdown>0.03&&ctx.bar.volume>h.reduce((s,b)=>s+b.volume,0)/h.length*1.5){
    const stop=price-atr*0.5;const t=price+atr*2;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.55,pattern:"fed-put-long",id:"fed-put-strategy"});}return null;}}

export class EventArbitrageStrategy implements Strategy{public readonly id="event-arbitrage";public readonly description="Event arbitrage: cross-venue pricing discrepancies in prediction markets.";
public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-15);if(h.length<10)return null;
  const atr=averageTrueRange(h,14);if(atr<=0)return null;const ranges=h.map(b=>(b.high-b.low)/b.close);
  const curR=(ctx.bar.high-ctx.bar.low)/ctx.bar.close;const avgR=ranges.reduce((a,b)=>a+b,0)/ranges.length;
  if(curR<avgR*2)return null;const price=ctx.bar.close;
  if(ctx.bar.close>ctx.bar.open){const stop=price-atr*0.3;const t=price+atr*1;if(stop>=price)return null;
    return sg({context:ctx,side:"long",stop,target:t,confidence:0.56,pattern:"event-arb-long",id:"event-arbitrage"});}
  else{const stop=price+atr*0.3;const t=price-atr*1;if(stop<=price)return null;
    return sg({context:ctx,side:"short",stop,target:t,confidence:0.56,pattern:"event-arb-short",id:"event-arbitrage"});}return null;}}
