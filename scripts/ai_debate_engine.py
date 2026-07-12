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
LLM_URL = os.environ.get("BILL_AI_DEBATE_LLM_URL", "http://127.0.0.1:3001/v1/chat/completions")
LLM_KEY = os.environ.get("BILL_AI_DEBATE_LLM_KEY") or os.environ.get("FREELLM_API_KEY", "")
LLM_MODEL = os.environ.get("BILL_AI_DEBATE_LLM_MODEL", "qwen/qwen3-coder:free")

ANALYSTS = [
    "📊 Technical Analyst — candlestick patterns, trends, volume",
    "📰 News/Sentiment Analyst — news flow, fear & greed, sentiment",
    "🏢 Fundamentals Analyst — valuations, rates, macro",
    "📱 Social Media Analyst — StockTwits, Reddit, retail sentiment",
    "🕵️ Insider Analyst — SEC insider trades, institutional flows",
    "⛓️ Onchain Analyst — BTC dominance, crypto correlation, stablecoins",
    "🌍 Macro Analyst — DXY, yields, VIX, economic calendar"
]

LLM_ERRORS = []

def llm(prompt, system=""):
    """Call FreeLLM API. Never hide failures as blank analyst output."""
    msgs = []
    if system: msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    try:
        headers = {"Content-Type": "application/json"}
        if LLM_KEY:
            headers["Authorization"] = f"Bearer {LLM_KEY}"
        r = requests.post(LLM_URL, json={
            "model": LLM_MODEL, "messages": msgs, "temperature": 0.3
        }, headers=headers, timeout=60)
        if r.status_code != 200:
            msg = f"FreeLLM HTTP {r.status_code}: {r.text[:300]}"
            LLM_ERRORS.append(msg)
            return f"UNAVAILABLE: {msg}"
        data = r.json()
        content = data.get("choices", [{}])[0].get("message",{}).get("content","").strip()
        if not content:
            msg = f"FreeLLM empty response: {str(data)[:300]}"
            LLM_ERRORS.append(msg)
            return f"UNAVAILABLE: {msg}"
        return content
    except Exception as e:
        msg = f"FreeLLM request failed: {type(e).__name__}: {e}"
        LLM_ERRORS.append(msg)
        return f"UNAVAILABLE: {msg}"

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
    if not final.strip() or final.startswith("UNAVAILABLE:"):
        final = "DIRECTION: WAIT\nCONFIDENCE: 0\nBEST STRATEGY: NONE\nR:R: N/A\nREASON: AI debate engine unavailable; do not trade from blank analyst consensus."
    print("✓")
    print(f"\n{'='*60}")
    print(f"  FINAL DECISION:")
    print(f"  {final}")
    print(f"{'='*60}\n")
    
    # Save debate with both raw text and structured safe fields.
    # Downstream readers should not need to parse free-form final text.
    def _field(label, default=""):
        prefix = label.upper() + ":"
        for line in final.splitlines():
            if line.upper().startswith(prefix):
                return line[len(prefix):].strip()
        return default

    direction = _field("DIRECTION", "WAIT").upper()
    if direction not in {"LONG", "SHORT", "WAIT"}:
        direction = "WAIT"
    try:
        confidence = int(float(_field("CONFIDENCE", "0").replace("%", "")))
    except Exception:
        confidence = 0
    confidence = max(0, min(confidence, 100))

    debate_out = {
        "ts": datetime.now().isoformat(),
        "symbol": symbol,
        "analysts": opinions,
        "bull": bull,
        "bear": bear,
        "final": final,
        "final_decision": direction,
        "confidence": confidence,
        "best_strategy": _field("BEST STRATEGY", "NONE") or "NONE",
        "risk_reward": _field("R:R", "N/A") or "N/A",
        "final_reason": _field("REASON", "") or ("AI unavailable; safe WAIT" if direction == "WAIT" else ""),
        "llm_available": len(LLM_ERRORS) == 0,
        "deterministic_fallback": len(LLM_ERRORS) > 0,
        "researchOnly": True,
        "writesOrders": False,
        "touchesBroker": False,
        "readyForExecution": False,
        "llm_errors": LLM_ERRORS[-5:],
        "tradable_signal": False,
        "promoted_for_execution": False,
        "execution_role": "diagnostic_only",
    }
    
    out_file = STATE / "ai-debate.latest.json"
    out_file.write_text(json.dumps(debate_out, indent=2))
    print(f"✅ Debate saved to {out_file}")
    
    return final

if __name__ == "__main__":
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "NQ"
    debate(symbol)
