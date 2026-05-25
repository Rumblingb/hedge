#!/usr/bin/env python3
"""
AI DEBATE ENGINE — TradingAgents-inspired analyst loop
=======================================================
7 AI analysts debate market conditions. Bull/Bear/Neutral arbiter settles.
FreeLLM API powers all agents. Bill TS quant engine verifies.

Usage:
  python3 ai_debate_engine.py         # Full debate cycle
  python3 ai_debate_engine.py NQ      # Debate one symbol
"""
import sys, json, os, subprocess, requests
from pathlib import Path
from datetime import datetime

HOME = Path.home()
HEDGE = HOME / "hedge"
STATE = HEDGE / ".rumbling-hedge" / "state"
LLM_URL = "http://127.0.0.1:3001/v1/chat/completions"
LLM_KEY = "freellmapi-b6d2f544ee792a0c7e32ce9a835fb52970151103fdf31c00"
LLM_MODEL = "qwen/qwen3-coder:free"

ANALYSTS = [
    "📊 Technical Analyst — candlestick patterns, trends, volume",
    "📰 News/Sentiment Analyst — news flow, fear & greed, sentiment",
    "🏢 Fundamentals Analyst — valuations, rates, macro",
    "📱 Social Media Analyst — StockTwits, Reddit, retail sentiment",
    "🕵️ Insider Analyst — SEC insider trades, institutional flows",
    "⛓️ Onchain Analyst — BTC dominance, crypto correlation, stablecoins",
    "🌍 Macro Analyst — DXY, yields, VIX, economic calendar"
]

def llm(prompt, system=""):
    """Call FreeLLM API"""
    msgs = []
    if system: msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    try:
        r = requests.post(LLM_URL, json={
            "model": LLM_MODEL, "messages": msgs, "temperature": 0.3
        }, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_KEY}"
        }, timeout=60)
        return r.json().get("choices", [{}])[0].get("message",{}).get("content","")
    except:
        return ""

def load_context():
    """Load all signal states for context"""
    ctx = {}
    for f in STATE.glob("*.latest.json"):
        try: ctx[f.stem.replace(".latest","")] = json.loads(f.read_text())
        except: pass
    return ctx

def run_analyst(name, symbol, context):
    """Run one AI analyst and get their opinion"""
    system_prompt = f"You are a {name}. Analyze {symbol} for trading."
    
    data = json.dumps({
        k: str(v)[:500] for k,v in context.items()
        if symbol.upper() in str(v) or k in ['manipulation_4h','noise-analysis','cot','vwap','heiken_ashi','opening_candle']
    }, indent=2)[:3000]
    
    prompt = f"""Data available for {symbol}:
{data}

Give EXACTLY:
1. BIAS: (bullish/bearish/neutral)
2. CONFIDENCE: (0-100)
3. REASON: One sentence
4. KEY LEVEL: One price level to watch

Keep it to 3 lines max. Be decisive."""
    
    return llm(prompt, system_prompt)

def debate(symbol="NQ"):
    """Run full analyst debate"""
    print(f"\n{'='*60}")
    print(f"  AI DEBATE ENGINE — Analyzing {symbol}")
    print(f"  {datetime.now().isoformat()}")
    print(f"{'='*60}\n")
    
    context = load_context()
    
    # Phase 1: Run all analysts
    opinions = {}
    for analyst in ANALYSTS:
        name = analyst.split(" — ")[0].strip()
        print(f"  {analyst}... ", end="", flush=True)
        opinion = run_analyst(name, symbol, context)
        opinions[name] = opinion
        print("✓")
        if opinion:
            print(f"    {opinion[:200]}\n")
    
    # Phase 2: Bull/Bear/Neutral debate
    session = "\n\n".join([f"{a}:\n{opinions.get(a,'no opinion')}" for a in ANALYSTS])
    
    bull_prompt = f"""You are a BULL trader reviewing analyst opinions for {symbol}.

Analyst Session:
{session[:4000]}

Build the BULL case: what's the strongest bullish argument?
Rate confidence 0-100 and give a price target. 3 lines max."""
    
    bear_prompt = f"""You are a BEAR trader reviewing analyst opinions for {symbol}.

Analyst Session:
{session[:4000]}

Build the BEAR case: what's the strongest bearish argument?
Rate confidence 0-100 and give a price target. 3 lines max."""
    
    print("  🔴 BULL case... ", end="", flush=True)
    bull = llm(bull_prompt)
    print("✓")
    print(f"  {bull}\n")
    
    print("  🟢 BEAR case... ", end="", flush=True)
    bear = llm(bear_prompt)
    print("✓")
    print(f"  {bear}\n")
    
    # Phase 3: Neutral arbiter (final decision)
    arbiter_prompt = f"""You are the NEUTRAL ARBITER for {symbol}. Review both sides.

BULL:
{bull[:1000]}

BEAR:
{bear[:1000]}

Make the FINAL decision:
1. DIRECTION: (LONG/SHORT/WAIT)
2. CONFIDENCE: (0-100)
3. BEST STRATEGY: Which strategy fits?
4. R:R: X:Y
5. REASON: One sentence

If confidence < 60, recommend WAIT."""
    
    print("  ⚪ NEUTRAL ARBITER deciding... ", end="", flush=True)
    final = llm(arbiter_prompt)
    print("✓")
    print(f"\n{'='*60}")
    print(f"  FINAL DECISION:")
    print(f"  {final}")
    print(f"{'='*60}\n")
    
    # Save debate
    debate_out = {
        "ts": datetime.now().isoformat(),
        "symbol": symbol,
        "analysts": opinions,
        "bull": bull,
        "bear": bear,
        "final": final
    }
    
    out_file = STATE / "ai-debate.latest.json"
    out_file.write_text(json.dumps(debate_out, indent=2))
    print(f"✅ Debate saved to {out_file}")
    
    return final

if __name__ == "__main__":
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "NQ"
    debate(symbol)
