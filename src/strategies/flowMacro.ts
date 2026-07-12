import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js"; import { averageTrueRange } from "../utils/indicators.js";
function sg(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

/** Dark Pool Print: Large off-exchange prints at support/resistance = institutional positioning. */
export class DarkPoolPrintStrategy implements Strategy {
  public readonly id="dark-pool-print";public readonly description="Dark pool print proxy: large volume at extremes = institutional positioning signal.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const vols=h.map(b=>b.volume);const avgVol=vols.reduce((a,b)=>a+b,0)/vols.length;
    const curVol=ctx.bar.volume;const volRatio=curVol/(avgVol+0.0001);
    if(volRatio<4)return null;const closeLoc=(ctx.bar.close-ctx.bar.low)/(ctx.bar.high-ctx.bar.low+0.0001);const price=ctx.bar.close;
    if(closeLoc<0.2){const stop=ctx.bar.low-atr*0.3;const t=price+atr*1.5;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.6,pattern:"dark-pool-long",id:"dark-pool-print"});}
    if(closeLoc>0.8){const stop=ctx.bar.high+atr*0.3;const t=price-atr*1.5;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.6,pattern:"dark-pool-short",id:"dark-pool-print"});}return null;}}

/** Block Trade Fade: Large blocks often exhaust the move → fade. */
export class BlockTradeFadeStrategy implements Strategy {
  public readonly id="block-trade-fade";public readonly description="Block trade fade: unusually large volume spikes = exhaustion → fade the move.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const vols=h.map(b=>b.volume);const avgVol=vols.slice(0,-1).reduce((a,b)=>a+b,0)/(vols.length-1);
    const curVol=ctx.bar.volume;if(curVol<avgVol*5)return null;const price=ctx.bar.close;
    if(ctx.bar.close>ctx.bar.open&&price>h[h.length-2].high){const stop=price+atr*0.3;const t=price-atr*1;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.61,pattern:"block-fade-short",id:"block-trade-fade"});}
    if(ctx.bar.close<ctx.bar.open&&price<h[h.length-2].low){const stop=price-atr*0.3;const t=price+atr*1;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.61,pattern:"block-fade-long",id:"block-trade-fade"});}return null;}}

/** Auction Imbalance: Closing auction order flow imbalance → next day direction. */
export class AuctionImbalanceStrategy implements Strategy {
  public readonly id="auction-imbalance";public readonly description="Closing auction imbalance: end-of-day order flow predicts next day direction.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-10);if(h.length<8)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const d=new Date(ctx.bar.ts);const hour=d.getUTCHours();const minute=d.getUTCMinutes();
    if(hour!==20||minute>5)return null;const last5=h.slice(-5);const netVol=last5.reduce((s,b)=>s+(b.close>b.open?b.volume:-b.volume),0);
    if(netVol>0){const stop=ctx.bar.close-atr*0.3;const t=ctx.bar.close+atr*2;if(stop>=ctx.bar.close)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.55,pattern:"auction-long",id:"auction-imbalance"});}
    if(netVol<0){const stop=ctx.bar.close+atr*0.3;const t=ctx.bar.close-atr*2;if(stop<=ctx.bar.close)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.55,pattern:"auction-short",id:"auction-imbalance"});}return null;}}

/** Yield Curve Steepener: 2s10s spread widening/narrowing signals. */
export class YieldCurveSteepenStrategy implements Strategy {
  public readonly id="yield-curve-steepen";public readonly description="Yield curve steepener/flattener: curve moves signal macro regime shifts.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-25);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const price=ctx.bar.close;const closes=h.map(b=>b.close);const sma20=closes.reduce((a,b)=>a+b,0)/20;
    const curveSlope=(price-sma20)/sma20*100;
    if(curveSlope>0.5){const stop=price-atr*0.5;const t=price+atr*1.5;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.54,pattern:"steepen-long",id:"yield-curve-steepen"});}
    if(curveSlope<-0.5){const stop=price+atr*0.5;const t=price-atr*1.5;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.54,pattern:"flatten-short",id:"yield-curve-steepen"});}return null;}}

/** Inflation Breakeven: Inflation expectations drive commodity/rates divergence. */
export class InflationBreakevenStrategy implements Strategy {
  public readonly id="inflation-breakeven";public readonly description="Inflation breakeven: rising breakevens = long commodities, short bonds.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const price=ctx.bar.close;const closes=h.map(b=>b.close);const sma10=closes.slice(-10).reduce((a,b)=>a+b,0)/10;
    const trend=price-sma10;const volRatio=ctx.bar.volume/(h.reduce((s,b)=>s+b.volume,0)/h.length);
    if(trend>atr*1.5&&volRatio>1.5){const stop=sma10;const t=price+atr*2;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.56,pattern:"inflation-long",id:"inflation-breakeven"});}
    if(trend<-atr*1.5&&volRatio>1.5){const stop=sma10;const t=price-atr*2;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.56,pattern:"disinflation-short",id:"inflation-breakeven"});}return null;}}

/** Dollar Smile: USD strength/weakness regimes → trade ES/NQ/GC accordingly. */
export class DollarSmileStrategy implements Strategy {
  public readonly id="dollar-smile";public readonly description="Dollar smile theory: USD extreme weakness or strength = risk-on/off signal.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const closes=h.map(b=>b.close);const sma20=closes.reduce((a,b)=>a+b,0)/closes.length;
    const dollarMove=(ctx.bar.close-sma20)/sma20;const price=ctx.bar.close;
    if(dollarMove<-0.005){const stop=price-atr*0.5;const t=price+atr*1.5;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.55,pattern:"dollar-weak-long",id:"dollar-smile"});}
    if(dollarMove>0.005){const stop=price+atr*0.5;const t=price-atr*1.5;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.55,pattern:"dollar-strong-short",id:"dollar-smile"});}return null;}}

/** Risk Parity Rebalance: End-of-period rebalancing creates predictable flows. */
export class RiskParityRebalanceStrategy implements Strategy {
  public readonly id="risk-parity-rebalance";public readonly description="Risk parity rebalancing: month-end rebalancing flows = predictable directional moves.";
  public generateSignal(ctx:StrategyContext):StrategySignal|null{const h=ctx.history.slice(-20);if(h.length<15)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const d=new Date(ctx.bar.ts);const date=d.getUTCDate();const month=d.getUTCMonth();
    const lastDay=new Date(d.getUTCFullYear(),month+1,0).getUTCDate();
    if(date<lastDay-2||date>lastDay)return null;const price=ctx.bar.close;const closes=h.map(b=>b.close);const sma5=closes.slice(-5).reduce((a,b)=>a+b,0)/5;
    if(price>sma5){const stop=sma5-atr*0.3;const t=price+atr*1;if(stop>=price)return null;
      return sg({context:ctx,side:"long",stop,target:t,confidence:0.52,pattern:"rp-rebalance-long",id:"risk-parity-rebalance"});}
    if(price<sma5){const stop=sma5+atr*0.3;const t=price-atr*1;if(stop<=price)return null;
      return sg({context:ctx,side:"short",stop,target:t,confidence:0.52,pattern:"rp-rebalance-short",id:"risk-parity-rebalance"});}return null;}}
