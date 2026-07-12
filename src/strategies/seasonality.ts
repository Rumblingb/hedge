import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/** Seasonality + Day-of-Week: Time-based edge. Monday/Friday effects, month-end rebalancing. */
const DAY_NAMES=["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
function buildSignal(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:"seasonality",side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:60,meta:{pattern}};}
export class SeasonalityStrategy implements Strategy {
  public readonly id="seasonality";public readonly description="Time-based edge: Monday reversal, Friday profit-taking, month-end rebalancing flows, FOMC drift.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-20);if(h.length<10)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const d=new Date(context.bar.ts);const day=d.getUTCDay();const date=d.getUTCDate();const month=d.getUTCMonth();
    const hour=d.getUTCHours();const price=context.bar.close;
    // Monday AM: gap fade (retail panic selling creates buying opportunity)
    if(day===1&&hour>=14&&hour<=16){const sessionH=context.sessionHistory;if(sessionH.length<5)return null;
      const open=sessionH[0].close;const move=(price-open)/open;
      if(move<-0.003){const stop=price-atr*0.5;const t=open;if(stop>=price)return null;
        return buildSignal({context,side:"long",stop,target:t,confidence:0.55,pattern:"monday-gap-fade"});}}
    // Friday PM: profit-taking reversal
    if(day===5&&hour>=20){const sessionH=context.sessionHistory.slice(-10);
      if(sessionH.length<5)return null;const netMove=(price-sessionH[0].close)/sessionH[0].close;
      if(netMove>0.005){const stop=price+atr*0.3;const t=price-atr*1;if(stop<=price)return null;
        return buildSignal({context,side:"short",stop,target:t,confidence:0.53,pattern:"friday-profit-taking"});}}
    // Month-end rebalancing: last 2 trading days, buy equities
    const lastDay=new Date(d.getUTCFullYear(),month+1,0).getUTCDate();
    if(date>=lastDay-1&&day<=5&&hour===14){const stop=price-atr*0.5;const t=price+atr*1.5;
      if(stop>=price)return null;return buildSignal({context,side:"long",stop,target:t,confidence:0.52,pattern:"month-end-rebalance"});}
    return null;
  }
}
