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
from datetime import datetime, timezone
import requests

HOME = Path.home()
HEDGE = HOME / "hedge"
LLM_URL = "http://127.0.0.1:3001/v1/chat/completions"
LLM_KEY = os.environ.get("BILL_AI_SCREENER_LLM_KEY") or os.environ.get("FREELLM_API_KEY", "")
MCP_TOOLS = HOME / ".hermes" / "scripts"

def llm(prompt):
    """Call FreeLLM API with prompt"""
    headers = {"Content-Type": "application/json"}
    if LLM_KEY:
        headers["Authorization"] = f"Bearer {LLM_KEY}"
    r = requests.post(LLM_URL, json={
        "model": "qwen/qwen3-coder:free",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1
    }, headers=headers, timeout=60)
    return r.json().get("choices", [{}])[0].get("message", {}).get("content", "")

def as_number(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default

def deterministic_signal_rows(signals):
    """No-agent fallback when LLM is unavailable."""
    rows = []
    excluded = []
    for name, payload in signals.items():
        if not isinstance(payload, dict):
            continue
        lowered_name = name.lower()
        signal_like = (
            lowered_name.endswith("-signal")
            or "-signal-" in lowered_name
            or lowered_name in {"arbitration", "master-signal", "signal-quality-advisor", "brain-state"}
        )
        excluded_hint = any(token in lowered_name for token in (
            "replay",
            "backtest",
            "submission",
            "reconciliation",
            "alpha-lab",
            "edge-matrix",
            "clearance",
            "audit",
            "requirements",
            "handoff",
        ))
        if not signal_like or excluded_hint:
            excluded.append(name)
            continue
        direction = 0.0
        confidence = 0.0
        text = json.dumps(payload, default=str).lower()[:4000]
        if any(token in text for token in ['"bullish"', '"long"', '"buy"', '"enter_long"']):
            direction += 1.0
        if any(token in text for token in ['"bearish"', '"short"', '"sell"', '"enter_short"']):
            direction -= 1.0
        for key in ("confidence", "conviction", "score"):
            if key in payload:
                confidence = max(confidence, abs(as_number(payload.get(key))))
        if confidence == 0.0 and direction != 0.0:
            confidence = 0.3
        if direction or confidence:
            rows.append({
                "source": name,
                "direction": max(-1.0, min(1.0, direction)),
                "confidence": max(0.0, min(1.0, confidence)),
                "promotedLikeExecution": any(payload.get(key) is True for key in (
                    "promoted_for_execution",
                    "promotedForExecution",
                    "tradable_signal",
                    "tradableSignal",
                    "ready_for_execution",
                    "readyForExecution",
                )),
            })
    return rows, excluded

def deterministic_summary(signals):
    rows, excluded = deterministic_signal_rows(signals)
    active = [row for row in rows if row["confidence"] > 0]
    weighted = sum(row["direction"] * row["confidence"] for row in active)
    total = sum(row["confidence"] for row in active)
    fused = weighted / total if total else 0.0
    promoted = [row for row in rows if row["promotedLikeExecution"]]
    blockers = []
    blockers.append("diagnostic-only-no-execution-authority")
    if abs(fused) < 0.15:
        blockers.append("no-consensus")
    if promoted:
        blockers.append("some-inputs-look-promoted-but-screener-is-diagnostic-only")
    decision = "diagnostic-no-trade"
    if fused > 0.3:
        bias = "bullish-watch"
    elif fused < -0.3:
        bias = "bearish-watch"
    else:
        bias = "neutral"
    return {
        "mode": "deterministic-no-agent-fallback",
        "activeSignalRows": len(active),
        "fusedDirection": round(fused, 3),
        "bias": bias,
        "decision": decision,
        "blockers": blockers,
        "excludedNonSignalArtifactCount": len(excluded),
        "excludedNonSignalArtifactSample": sorted(excluded)[:16],
        "topRows": sorted(active, key=lambda row: abs(row["direction"] * row["confidence"]), reverse=True)[:12],
    }

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
    fallback = None
    if not result:
        fallback = deterministic_summary(signals)
        print("(LLM unavailable — using deterministic no-agent analysis)\n")
        print(json.dumps(fallback, indent=2))
        result = (
            f"Deterministic scan: {fallback['bias']}, fusedDirection={fallback['fusedDirection']}, "
            f"activeRows={fallback['activeSignalRows']}, decision={fallback['decision']}"
        )
    
    print(result)
    
    # Save sweep
    out = HEDGE / ".rumbling-hedge" / "state" / "ai-sweep.latest.json"
    out.write_text(json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "deterministic_fallback": fallback,
        "signal_count": len(signals),
        "research_only": True,
        "writes_orders": False,
        "touches_broker": False,
        "moves_funds": False,
        "ready_for_execution": False,
        "tradable_signal": False,
        "promoted_for_execution": False,
        "execution_role": "diagnostic_only"
    }, indent=2))
    print(f"\n✅ Sweep saved to {out}")

def ask(question):
    """Ask AI about any market topic using all available data"""
    state = HEDGE / ".rumbling-hedge" / "state"
    signals = {}
    for f in state.glob("*.latest.json"):
        try: signals[f.stem.replace(".latest","")] = json.loads(f.read_text())
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
