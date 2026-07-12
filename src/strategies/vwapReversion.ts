import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

/** VWAP Reversion: Mean-reversion to VWAP. Price stretched 2+ ATR → fade back. */
function buildSignal(args: {context: StrategyContext; side: TradeSide; stop: number; target: number; confidence: number; vwap: number}): StrategySignal|null {
  const {context,side,stop,target,confidence,vwap}=args; const entry=context.bar.close; const rr=calculateRr(entry,stop,target,side); if(rr<=0)return null;
  return {symbol:context.symbol,strategyId:"vwap-reversion",side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:20,meta:{pattern:"vwap-reversion",vwap:Number(vwap.toFixed(4))}};
}
export class VwapReversionStrategy implements Strategy {
  public readonly id="vwap-reversion"; public readonly description="Mean-reversion to VWAP when price stretches 2+ ATR away.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.sessionHistory.length>=20?context.sessionHistory:context.history; if(h.length<20)return null;
    const c=h.map(b=>b.close); const v=h.map(b=>b.volume); const vw=c.reduce((s,p,i)=>s+p*v[i],0)/v.reduce((s,x)=>s+x,0);
    const atr=averageTrueRange(h,14);    if(atr<=0)return null; const _hmm=context.macro?.hmmRegime; const _rm=_hmm&&_hmm!=="range-chop"?0.7:1.0; const dev=context.bar.close-vw;
    if(Math.abs(dev)>atr*2) {
      if(dev>0){const stop=context.bar.high+atr*0.3; const t=vw; if(stop<=context.bar.close)return null; const _c=0.6*_rm; if(_c<0.35)return null; return buildSignal({context,side:"short",stop,target:t,confidence:_c,vwap:vw});}
      if(dev<0){const stop=context.bar.low-atr*0.3; const t=vw; if(stop>=context.bar.close)return null; const _c2=0.6*_rm; if(_c2<0.35)return null; return buildSignal({context,side:"long",stop,target:t,confidence:_c2,vwap:vw});}
    } return null;
  }
}
