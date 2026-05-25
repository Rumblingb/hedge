#!/usr/bin/env python3
"""
AI SCREENING ENGINE — Orchestrates all tools via FreeLLM API
=============================================================
Instead of writing new code, this AI engine controls existing tools:
- MCP stock scanner (quotes, technicals, options)
- Python strategy agents (15 signal generators)
- TypeScript CLI (doctor, live-readiness, strategy-rankings)
- FreeLLM API (market analysis)

Usage:
  python3 ai_screener.py scan          # Full market sweep
  python3 ai_screener.py ask "What?"   # Ask about any market
  python3 ai_screener.py analyze NQ    # Deep dive one symbol
"""
import sys, json, subprocess, os
from pathlib import Path
from datetime import datetime
import requests

HOME = Path.home()
HEDGE = HOME / "hedge"
LLM_URL = "http://127.0.0.1:3001/v1/chat/completions"
LLM_KEY = "freellmapi-b6d2f544ee792a0c7e32ce9a835fb52970151103fdf31c00"
MCP_TOOLS = HOME / ".hermes" / "scripts"

def llm(prompt):
    """Call FreeLLM API with prompt"""
    r = requests.post(LLM_URL, json={
        "model": "qwen/qwen3-coder:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1
    }, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_KEY}"
    }, timeout=60)
    return r.json().get("choices", [{}])[0].get("message", {}).get("content", "")

def run_tool(tool, args=None):
    """Run a Python script or shell command"""
    script = MCP_TOOLS / tool
    if script.exists():
        r = subprocess.run(["python3", str(script), *(args or [])],
                          capture_output=True, text=True, timeout=120, cwd=HEDGE)
        return r.stdout[-2000:] if r.stdout else r.stderr[-2000:]
    else:
        r = subprocess.run(tool.split() + (args or []),
                          capture_output=True, text=True, timeout=120, cwd=HEDGE)
        return r.stdout[-2000:] if r.stdout else r.stderr[-2000:]

def scan():
    """Full market sweep using all tools"""
    print("\n=== AI SCREENING ENGINE — Full Market Sweep ===")
    print(f"Time: {datetime.now().isoformat()}\n")
    
    # Gather data from all tools
    data = {}
    
    # 1. Strategy signals
    print("Reading strategy signals...")
    state = HEDGE / ".rumbling-hedge" / "state"
    signals = {}
    for f in state.glob("*.latest.json"):
        try:
            signals[f.stem.replace(".latest","")] = json.loads(f.read_text())
        except: pass
    
    # 2. MCP tools - stock scanner for current markets
    print("Checking market indices...")
    tsx = subprocess.run(["npx", "tsx", "src/cli.ts", "doctor"],
                        capture_output=True, text=True, timeout=30, cwd=HEDGE)
    data['doctor'] = tsx.stdout[-1000:].split('\n')[:15]
    
    # 3. Candlestick patterns
    print("Running candlestick analysis...")
    data['candles'] = run_tool("candlestick_multitf_analyzer.py")[:1500]
    
    # 4. Compile into AI prompt
    prompt = f"""You are an AI trading screening engine. Analyze this data and answer:

DATA:
- Signals from {len(signals)} generators
- Doctor output: {json.dumps(data.get('doctor',[]))[:500]}
- Candlestick patterns: {data.get('candles','')[:500]}
- Gengar state: {json.dumps(signals.get('gengar-monitor',{}), indent=2)[:300]}

INSTRUCTIONS:
1. Which instruments have the strongest edge RIGHT NOW?
2. What's the bias (bullish/bearish/neutral)?
3. Which patterns are forming?
4. What would you trade if you had to pick ONE?
5. Risk level?

Be concise. Use numbers."""
    
    print("\nAnalyzing with AI...")
    try:
        result = llm(prompt)
    except:
        result = ""
    if not result:
        # Fallback: show raw data
        print("(LLM unavailable — showing raw data)\n")
        for sig_name, sig_data in list(signals.items())[:10]:
            print(f"  • {sig_name}: {str(sig_data)[:100]}")
        result = f"Raw scan: {len(signals)} signals, see ai-sweep.latest.json for details"
    
    print(result)
    
    # Save sweep
    out = HEDGE / ".rumbling-hedge" / "state" / "ai-sweep.latest.json"
    out.write_text(json.dumps({
        "ts": datetime.now().isoformat(),
        "result": result,
        "signal_count": len(signals)
    }, indent=2))
    print(f"\n✅ Sweep saved to {out}")

def ask(question):
    """Ask AI about any market topic using all available data"""
    state = HEDGE / ".rumbling-hedge" / "state"
    signals = {}
    for f in state.glob("*.latest.json"):
        try: signals[f.stem.replace(".latest","")] = json.loads(f.read_text())[:2000]
        except: pass
    
    prompt = f"""You are an AI trading system with access to {len(signals)} real-time data sources.
    
Available data:
{json.dumps({k: str(v)[:300] for k,v in signals.items()}, indent=2)[:3000]}

Question: {question}

Answer based on the available data. If data is insufficient, say so."""
    
    result = llm(prompt)
    print(f"\n=== AI Answer ===\n{result}")

def analyze(symbol):
    """Deep dive on one symbol using all tools"""
    print(f"\n=== AI Deep Dive: {symbol} ===")
    
    # Gather data
    data = {"symbol": symbol}
    
    # Read signal state files
    state = HEDGE / ".rumbling-hedge" / "state"
    for f in state.glob(f"*{symbol}*.latest.json"):
        try: data[f.stem] = json.loads(f.read_text())
        except: pass
    for f in state.glob("*.latest.json"):
        try:
            d = json.loads(f.read_text())
            if symbol.upper() in str(d):
                data[f.stem.replace(".latest","")] = d
        except: pass
    
    prompt = f"""Analyze {symbol} for trading right now.

Data available:
{json.dumps({k: str(v)[:500] for k,v in data.items()}, indent=2)[:3000]}

Give me:
1. Current bias (bullish/bearish/neutral)
2. Key levels
3. R:R for a trade
4. Which strategy fits best
5. Confidence (0-100%)

Keep it actionable. Use numbers."""
    
    result = llm(prompt)
    print(result)
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 ai_screener.py <scan|ask '?'|analyze SYMBOL>")
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "scan":
        scan()
    elif cmd == "ask":
        ask(" ".join(sys.argv[2:]) if len(sys.argv) > 2 else "What's the market doing?")
    elif cmd == "analyze":
        analyze(sys.argv[2].upper() if len(sys.argv) > 2 else "NQ")
    else:
        print(f"Unknown: {cmd}")
