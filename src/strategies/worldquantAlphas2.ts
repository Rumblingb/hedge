import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";

/**
 * WorldQuant 101 Alphas — Batch 2 (Alphas 003-099)
 * Continuing implementation of proven institutional alpha signals.
 * Source: Kakushadze (2016) arXiv:1601.00991 "101 Formulaic Alphas"
 * Avg holding: 0.6-6.4 days. Avg correlation between alphas: 15.9% (excellent diversification).
 */

// ============================================================
// HELPERS (reused from batch 1)
// ============================================================
function rank(v: number[]): number[] { const ix=v.map((x,i)=>({v:x,i})).sort((a,b)=>a.v-b.v); const r=new Array(v.length).fill(0); for(let i=0;i<ix.length;i++)r[ix[i].i]=(i+1)/ix.length; return r }
function tsMean(v: number[], p: number): number { const s=v.slice(-p); return s.length?s.reduce((a,b)=>a+b,0)/s.length:0 }
function tsStd(v: number[], p: number): number { const m=tsMean(v,p); const s=v.slice(-p); if(s.length<2)return 0; return Math.sqrt(s.reduce((x,y)=>x+(y-m)**2,0)/s.length) }
function tsMin(v: number[], p: number): number { const s=v.slice(-p); return s.length?Math.min(...s):0 }
function tsMax(v: number[], p: number): number { const s=v.slice(-p); return s.length?Math.max(...s):0 }
function tsCorr(a: number[], b: number[], p: number): number { const sa=a.slice(-p),sb=b.slice(-p); const n=Math.min(sa.length,sb.length); if(n<3)return 0; const ma=sa.reduce((s,v)=>s+v,0)/n,mb=sb.reduce((s,v)=>s+v,0)/n; let c=0,va=0,vb=0; for(let i=0;i<n;i++){const da=sa[i]-ma,db=sb[i]-mb;c+=da*db;va+=da*da;vb+=db*db} return va>0&&vb>0?c/Math.sqrt(va*vb):0 }
function tsRank(v: number[], p: number): number { const r=rank(v.slice(-p)); return r.length?r[r.length-1]:0.5 }
function delta(v: number[], p: number): number { return v.length>p?v[v.length-1]-v[v.length-1-p]:0 }
function tsSum(v: number[], p: number): number { return v.slice(-p).reduce((a,b)=>a+b,0) }
function decayLinear(v: number[], p: number): number { const s=v.slice(-p); if(!s.length)return 0; let sum=0,wSum=0; for(let i=0;i<s.length;i++){const w=s.length-i;sum+=s[i]*w;wSum+=w} return wSum?sum/wSum:0 }
function tsArgMax(v: number[], p: number): number { const s=v.slice(-p); if(!s.length)return 0; let mx=s[0],mi=0; for(let i=1;i<s.length;i++)if(s[i]>mx){mx=s[i];mi=i} return mi/p }
function signedPower(x: number, a: number): number { return Math.sign(x)*Math.pow(Math.abs(x),a) }
function scale(v: number[], a: number=1): number { const m=tsMean(v,v.length); const s=tsStd(v,v.length); return s>0?(v[v.length-1]-m)/s*a:0 }

const LOOKBACK = 50;

function bs(ctx: StrategyContext, side: TradeSide, entry: number, stop: number, target: number, confidence: number, alphaId: string): StrategySignal | null {
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {symbol:ctx.symbol,strategyId:`wq-alpha-${alphaId}`,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:30,meta:{pattern:`worldquant-${alphaId}`}};
}

/** Alpha 003: Open-volume correlation reversal. */
export class WqAlpha003 implements Strategy { public readonly id="wq-alpha-003"; public readonly description="WQ Alpha 003: -corr(rank(open),rank(volume),10)";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<15)return null;
    const opens=h.map(b=>b.open); const vols=h.map(b=>b.volume);
    const rOpen=rank(opens.slice(-15)); const rVol=rank(vols.slice(-15));
    const corr=tsCorr(rOpen,rVol,10); const alpha=-corr;
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0)return null; const p=ctx.bar.close;
    if(alpha>0.25)return bs(ctx,"long",p,p-atr*0.8,p+atr*1.5,0.56,"003");
    if(alpha<-0.25)return bs(ctx,"short",p,p+atr*0.8,p-atr*1.5,0.56,"003");
    return null;}}

/** Alpha 007: Volume vs adv20 — momentum with vol filter. */
export class WqAlpha007 implements Strategy { public readonly id="wq-alpha-007"; public readonly description="WQ Alpha 007: Volume>adv20 momentum signal";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<25)return null;
    const vols=h.map(b=>b.volume); const closes=h.map(b=>b.close);
    const adv20=tsMean(vols,20); const curVol=vols[vols.length-1];
    if(curVol<=adv20)return null;
    const absDelta7=Math.abs(delta(closes,7));
    const rank60=tsRank(closes.map((_,i)=>i<h.length-7?Math.abs(closes[i+7]-closes[i]):absDelta7),60);
    const alpha=-rank60*Math.sign(delta(closes,7));
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0)return null; const p=ctx.bar.close;
    if(alpha>0.2)return bs(ctx,"long",p,p-atr,p+atr*1.5,0.57,"007");
    if(alpha<-0.2)return bs(ctx,"short",p,p+atr,p-atr*1.5,0.57,"007");
    return null;}}

/** Alpha 008: Open*returns cross momentum decay. */
export class WqAlpha008 implements Strategy { public readonly id="wq-alpha-008"; public readonly description="WQ Alpha 008: -(sum(open,5)*sum(returns,5) - lagged)";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<20)return null;
    const opens=h.map(b=>b.open); const closes=h.map(b=>b.close);
    const rets=closes.map((c,i)=>i>0?(c-closes[i-1])/closes[i-1]:0);
    const sumOpen5=tsSum(opens,5); const sumRet5=tsSum(rets,5);
    const lagged=(()=>{const o2=opens.slice(0,-10);const r2=rets.slice(0,-10);return tsSum(o2,5)*tsSum(r2,5)})();
    const alpha=-(sumOpen5*sumRet5-lagged);
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0||Math.abs(alpha)<atr*0.05)return null; const p=ctx.bar.close;
    if(alpha>0)return bs(ctx,"long",p,p-atr*0.8,p+atr*1.5,0.55,"008");
    return bs(ctx,"short",p,p+atr*0.8,p-atr*1.5,0.55,"008");
}}

/** Alpha 021: Mean return over 8 days — trend continuation. */
export class WqAlpha021 implements Strategy { public readonly id="wq-alpha-021"; public readonly description="WQ Alpha 021: Mean(returns,8) trend signal";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<15)return null;
    const closes=h.map(b=>b.close); const rets=closes.map((c,i)=>i>0?(c-closes[i-1])/closes[i-1]:0);
    const alpha=tsMean(rets,8);
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0||Math.abs(alpha)<0.0003)return null; const p=ctx.bar.close;
    if(alpha>0)return bs(ctx,"long",p,p-atr,p+atr*1.5,0.58,"021");
    return bs(ctx,"short",p,p+atr,p-atr*1.5,0.58,"021");
}}

/** Alpha 033: Rank(1/open) * volume — liquidity-weighted reversal. */
export class WqAlpha033 implements Strategy { public readonly id="wq-alpha-033"; public readonly description="WQ Alpha 033: rank(1/open)*volume reversal";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<15)return null;
    const opens=h.map(b=>b.open); const vols=h.map(b=>b.volume);
    const invOpen=opens.map(o=>1/Math.max(o,0.0001));
    const rInv=rank(invOpen.slice(-15)); const rVol=rank(vols.slice(-15));
    const alpha=rInv[rInv.length-1]*vols[vols.length-1];
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0)return null; const p=ctx.bar.close;
    const med=alpha/(vols.reduce((a,b)=>a+b,0)/vols.length+0.0001);
    if(med>1.5)return bs(ctx,"long",p,p-atr*0.8,p+atr*1.5,0.54,"033");
    if(med<0.5)return bs(ctx,"short",p,p+atr*0.8,p-atr*1.5,0.54,"033");
    return null;}}

/** Alpha 049: (open-close) × volume correlation × delta momentum. */
export class WqAlpha049 implements Strategy { public readonly id="wq-alpha-049"; public readonly description="WQ Alpha 049: corr(open-close,volume,10)*delta(close,5)";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<20)return null;
    const opens=h.map(b=>b.open); const closes=h.map(b=>b.close); const vols=h.map(b=>b.volume);
    const spreads=opens.map((o,i)=>o-closes[i]);
    const corr=tsCorr(spreads,vols,10); const d5=delta(closes,5);
    const alpha=corr*d5;
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0||Math.abs(alpha)<atr*0.02)return null; const p=ctx.bar.close;
    if(alpha>0)return bs(ctx,"long",p,p-atr*0.8,p+atr*1.5,0.56,"049");
    return bs(ctx,"short",p,p+atr*0.8,p-atr*1.5,0.56,"049");
}}

/** Alpha 053: Reversal from 9-day low with return normalization. */
export class WqAlpha053 implements Strategy { public readonly id="wq-alpha-053"; public readonly description="WQ Alpha 053: -(delta(close-min(low,9),5))/sum(returns,10)";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<20)return null;
    const closes=h.map(b=>b.close); const lows=h.map(b=>b.low);
    const minLow9=tsMin(lows,9); const diff=closes[closes.length-1]-minLow9;
    const rets=closes.map((c,i)=>i>0?(c-closes[i-1])/closes[i-1]:0);
    const sumRet10=tsSum(rets,10);
    if(Math.abs(sumRet10)<0.0001)return null;
    const alpha=-(delta([diff],1))/sumRet10;
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0||Math.abs(alpha)<0.1)return null; const p=ctx.bar.close;
    if(alpha>0)return bs(ctx,"long",p,p-atr*0.6,p+atr*1.5,0.57,"053");
    return bs(ctx,"short",p,p+atr*0.6,p-atr*1.5,0.57,"053");
}}

/** Alpha 083: VWAP distance from close — overnight gap signal. */
export class WqAlpha083 implements Strategy { public readonly id="wq-alpha-083"; public readonly description="WQ Alpha 083: rank(delay(vwap,1)-close)/rank(delay(vwap,1)+close)";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<20)return null;
    const closes=h.map(b=>b.close); const vols=h.map(b=>b.volume);
    const vwaps:number[]=[]; let cumV=0,cumPV=0;
    for(let i=0;i<closes.length;i++){cumV+=vols[i];cumPV+=closes[i]*vols[i];vwaps.push(cumV>0?cumPV/cumV:closes[i])}
    const prevVwap=vwaps.length>1?vwaps[vwaps.length-2]:vwaps[vwaps.length-1];
    const num=prevVwap-closes[closes.length-1];
    const den=prevVwap+closes[closes.length-1];
    if(Math.abs(den)<0.0001)return null;
    const alpha=num/den;
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0||Math.abs(alpha)<0.003)return null; const p=ctx.bar.close;
    if(alpha>0)return bs(ctx,"long",p,p-atr*0.5,p+atr*1.2,0.55,"083");
    return bs(ctx,"short",p,p+atr*0.5,p-atr*1.2,0.55,"083");
}}

/** Alpha 024: Correlation(high, rank(volume), 5) — volume-weighted resistance. */
export class WqAlpha024 implements Strategy { public readonly id="wq-alpha-024"; public readonly description="WQ Alpha 024: corr(high,rank(volume),5) resistance signal";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<15)return null;
    const highs=h.map(b=>b.high); const vols=h.map(b=>b.volume);
    const rVol=rank(vols.slice(-10));
    const corr=tsCorr(highs.slice(-10),rVol,5);
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0)return null; const p=ctx.bar.close;
    if(corr>0.3)return bs(ctx,"short",p,p+atr*0.5,p-atr*1.2,0.55,"024");
    if(corr<-0.3)return bs(ctx,"long",p,p-atr*0.5,p+atr*1.2,0.55,"024");
    return null;}}

/** Alpha 044: Correlation(high, rank(volume), 5) — continuation signal reversed. */
export class WqAlpha044 implements Strategy { public readonly id="wq-alpha-044"; public readonly description="WQ Alpha 044: -corr(high,rank(volume),5) continuation";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<15)return null;
    const highs=h.map(b=>b.high); const vols=h.map(b=>b.volume);
    const rVol=rank(vols.slice(-10));
    const corr=tsCorr(highs.slice(-10),rVol,5);
    const alpha=-corr;
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0)return null; const p=ctx.bar.close;
    if(alpha>0.3)return bs(ctx,"long",p,p-atr*0.6,p+atr*1.2,0.54,"044");
    if(alpha<-0.3)return bs(ctx,"short",p,p+atr*0.6,p-atr*1.2,0.54,"044");
    return null;}}

/** Alpha 057: VWAP-close distance with rank decay — mean-reversion magnitude. */
export class WqAlpha057 implements Strategy { public readonly id="wq-alpha-057"; public readonly description="WQ Alpha 057: (close-vwap)/decayLinear(rank(tsArgMax(close,30)),2)";
  public generateSignal(ctx: StrategyContext): StrategySignal | null { const h=ctx.history.slice(-LOOKBACK); if(h.length<35)return null;
    const closes=h.map(b=>b.close); const vols=h.map(b=>b.volume);
    let cumV=0,cumPV=0; const vwaps:number[]=[];
    for(let i=0;i<closes.length;i++){cumV+=vols[i];cumPV+=closes[i]*vols[i];vwaps.push(cumV>0?cumPV/cumV:closes[i])}
    const vwap=vwaps[vwaps.length-1]; const diff=closes[closes.length-1]-vwap;
    const argMaxRank=Array.from({length:30},(_,i)=>tsArgMax(closes.slice(0,closes.length-30+i+1),30));
    const r=rank(argMaxRank); const dl=decayLinear(r,2);
    if(Math.abs(dl)<0.01)return null;
    const alpha=diff/dl;
    const atr=tsStd(h.map(b=>b.high-b.low),14); if(atr<=0||Math.abs(alpha)<atr*0.5)return null; const p=ctx.bar.close;
    if(alpha<0)return bs(ctx,"long",p,p-atr*0.5,p+atr*1.5,0.56,"057");
    return bs(ctx,"short",p,p+atr*0.5,p-atr*1.5,0.56,"057");
}}
