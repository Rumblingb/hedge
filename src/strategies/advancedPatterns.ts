import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

function s(args:{context:StrategyContext;side:TradeSide;stop:number;target:number;confidence:number;pattern:string;id:string}):StrategySignal|null{
  const{context,side,stop,target,confidence,pattern,id}=args;const entry=context.bar.close;const rr=calculateRr(entry,stop,target,side);if(rr<=0)return null;
  return{symbol:context.symbol,strategyId:id,side,entry,stop,target,rr,confidence,contracts:1,maxHoldMinutes:25,meta:{pattern}};}

/** Breakout Retest: Break level → pullback retest → continuation. */
export class BreakoutRetestStrategy implements Strategy {
  public readonly id="breakout-retest";public readonly description="Breakout retest: break key level, pullback to retest, continuation entry.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const highs=h.map(b=>b.high);const lows=h.map(b=>b.low);const rHigh=Math.max(...highs.slice(-20,-5));const rLow=Math.min(...lows.slice(-20,-5));
    const price=context.bar.close;
    if(price>rHigh+atr*0.3&&price<rHigh+atr*1.5){const stop=rHigh-atr*0.5;const t=price+atr*2;
      if(stop>=price)return null;return s({context,side:"long",stop,target:t,confidence:0.59,pattern:"retest-long",id:"breakout-retest"});}
    if(price<rLow-atr*0.3&&price>rLow-atr*1.5){const stop=rLow+atr*0.5;const t=price-atr*2;
      if(stop<=price)return null;return s({context,side:"short",stop,target:t,confidence:0.59,pattern:"retest-short",id:"breakout-retest"});}
    return null;
  }
}

/** Volume Spike: Unusual volume = institutional activity. Trade in direction of volume bar. */
export class VolumeSpikeStrategy implements Strategy {
  public readonly id="volume-spike";public readonly description="Volume spike detection: 3x normal volume = institutional activity. Follow the volume.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const avgVol=h.slice(0,-1).reduce((a,b)=>a+b.volume,0)/(h.length-1);
    const volRatio=context.bar.volume/(avgVol+0.0001);
    if(volRatio<3)return null;const isUpBar=context.bar.close>context.bar.open;const range=context.bar.high-context.bar.low;
    if(isUpBar&&context.bar.close>context.bar.high-range*0.3){const stop=context.bar.low-atr*0.3;const t=context.bar.close+atr*1.5;
      if(stop>=context.bar.close)return null;return s({context,side:"long",stop,target:t,confidence:0.6,pattern:"vol-spike-long",id:"volume-spike"});}
    if(!isUpBar&&context.bar.close<context.bar.low+range*0.3){const stop=context.bar.high+atr*0.3;const t=context.bar.close-atr*1.5;
      if(stop<=context.bar.close)return null;return s({context,side:"short",stop,target:t,confidence:0.6,pattern:"vol-spike-short",id:"volume-spike"});}
    return null;
  }
}

/** Market Structure Shift: Break of structure (BOS) / Change of character (CHoCH). ICT Smart Money. */
export class MarketStructureStrategy implements Strategy {
  public readonly id="market-structure";public readonly description="Market structure shift: BOS/CHoCH. Higher high→lower low break = bearish, vice versa.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-30);if(h.length<20)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const highs=h.map(b=>b.high);const lows=h.map(b=>b.low);
    const lastHH=Math.max(...highs.slice(-15,-5));const lastHL=Math.min(...lows.slice(-15,-5));
    const recentLow=Math.min(...lows.slice(-5));const recentHigh=Math.max(...highs.slice(-5));
    // Bearish CHoCH: broke below last higher low
    if(recentLow<lastHL-atr*0.3&&context.bar.close<lastHL){const stop=lastHH+atr*0.3;const t=context.bar.close-atr*1.5;
      if(stop<=context.bar.close)return null;return s({context,side:"short",stop,target:t,confidence:0.61,pattern:"bearish-choch",id:"market-structure"});}
    // Bullish CHoCH: broke above last lower high
    if(recentHigh>lastHH+atr*0.3&&context.bar.close>lastHH){const stop=lastHL-atr*0.3;const t=context.bar.close+atr*1.5;
      if(stop>=context.bar.close)return null;return s({context,side:"long",stop,target:t,confidence:0.61,pattern:"bullish-choch",id:"market-structure"});}
    return null;
  }
}

/** Trendline Break: Trendline from swing points → break = reversal signal. */
export class TrendlineBreakStrategy implements Strategy {
  public readonly id="trendline-break";public readonly description="Trendline break: connect swing points, break trendline = reversal entry.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-40);if(h.length<30)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    const highs=h.map(b=>b.high);const lows=h.map(b=>b.low);const closes=h.map(b=>b.close);
    // Find swing lows for uptrend line
    let sl:{idx:number,val:number}[]=[];for(let i=2;i<highs.length-2;i++)if(lows[i]<lows[i-1]&&lows[i]<lows[i+1])sl.push({idx:i,val:lows[i]});
    if(sl.length<2)return null;const lastTwo=sl.slice(-2);
    const tlSlope=(lastTwo[1].val-lastTwo[0].val)/(lastTwo[1].idx-lastTwo[0].idx);
    const tlNow=lastTwo[1].val+tlSlope*(h.length-lastTwo[1].idx);
    // Find swing highs for downtrend line
    let sh:{idx:number,val:number}[]=[];for(let i=2;i<highs.length-2;i++)if(highs[i]>highs[i-1]&&highs[i]>highs[i+1])sh.push({idx:i,val:highs[i]});
    // Uptrend line break = bearish
    if(sl.length>=2&&tlSlope>0&&context.bar.close<tlNow-atr*0.3){
      const stop=tlNow+atr*0.5;const t=context.bar.close-atr*1.5;if(stop<=context.bar.close)return null;
      return s({context,side:"short",stop,target:t,confidence:0.57,pattern:"tl-break-short",id:"trendline-break"});}
    // Downtrend line break = bullish
    if(sh.length>=2){const dt=sh.slice(-2);const dtSlope=(dt[1].val-dt[0].val)/(dt[1].idx-dt[0].idx);const dtNow=dt[1].val+dtSlope*(h.length-dt[1].idx);
      if(dtSlope<0&&context.bar.close>dtNow+atr*0.3){const stop=dtNow-atr*0.5;const t=context.bar.close+atr*1.5;
        if(stop>=context.bar.close)return null;return s({context,side:"long",stop,target:t,confidence:0.57,pattern:"tl-break-long",id:"trendline-break"});}}
    return null;
  }
}

/** Multi-Timeframe Confirmation: 1m/5m/15m alignment for higher probability entries. */
export class MultiTimeframeStrategy implements Strategy {
  public readonly id="multi-timeframe";public readonly description="Multi-timeframe confirmation: 1m/5m/15m directional alignment for high-conviction entries.";
  public generateSignal(context:StrategyContext):StrategySignal|null {
    const h=context.history.slice(-60);if(h.length<50)return null;const atr=averageTrueRange(h,14);if(atr<=0)return null;
    // 5m proxy: 5-bar aggregate
    const m5=[];for(let i=0;i<h.length;i+=5){const s=h.slice(i,Math.min(i+5,h.length));if(s.length>0)m5.push({o:s[0].open,c:s[s.length-1].close,h:Math.max(...s.map(b=>b.high)),l:Math.min(...s.map(b=>b.low))});}
    // 15m proxy: 15-bar aggregate
    const m15=[];for(let i=0;i<h.length;i+=15){const s=h.slice(i,Math.min(i+15,h.length));if(s.length>0)m15.push({o:s[0].open,c:s[s.length-1].close,h:Math.max(...s.map(b=>b.high)),l:Math.min(...s.map(b=>b.low))});}
    // Check alignment
    const m1Up=context.bar.close>h[h.length-5].close;const m5Up=m5.length>=2&&m5[m5.length-1].c>m5[m5.length-2].c;
    const m15Up=m15.length>=2&&m15[m15.length-1].c>m15[m15.length-2].c;
    if(m1Up&&m5Up&&m15Up){const stop=h[h.length-10].low;const t=context.bar.close+atr*2;
      if(stop>=context.bar.close)return null;return s({context,side:"long",stop,target:t,confidence:0.7,pattern:"mtf-long",id:"multi-timeframe"});}
    if(!m1Up&&!m5Up&&!m15Up){const stop=h[h.length-10].high;const t=context.bar.close-atr*2;
      if(stop<=context.bar.close)return null;return s({context,side:"short",stop,target:t,confidence:0.7,pattern:"mtf-short",id:"multi-timeframe"});}
    return null;
  }
}
