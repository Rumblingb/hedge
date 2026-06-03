#!/usr/bin/env python3
"""
New Signal Arsenal Runner v2 — All newly implemented strategies
=================================================================
Signals:
1. PEAD Earnings Drift Scanner
2. S/R Proximity Detector (NQ + ES)
3. Donchian(50) Breakout (NQ + ES)
4. Insider Trading Scanner (SEC EDGAR)
5. Ichimoku Full System (NQ + ES)
6. Noise Area Intraday Scalp
7. QRS/RSRS Session Bias

Output: ~/hedge/.rumbling-hedge/state/new-arsenal-combined.json
"""
import json, os, sys, subprocess
from pathlib import Path
from datetime import datetime, timezone

SCRIPTS_DIR = Path("/Users/brain/hedge/scripts")
STATE_DIR = Path(os.environ.get("BILL_STATE_DIR", os.path.expanduser("~/hedge/.rumbling-hedge/state")))
STATE_DIR.mkdir(parents=True, exist_ok=True)
COMBINED_FILE = STATE_DIR / "new-arsenal-combined.json"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}")

def run_script(name: str, args: list = None) -> dict:
    """Run a signal generator script and return its output state"""
    script = SCRIPTS_DIR / name
    cmd = [sys.executable, str(script)]
    if args:
        cmd.extend(args)
    
    log(f"Running {name}...")
    env = {**os.environ, "BILL_STATE_DIR": str(STATE_DIR)}
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    
    for line in result.stdout.strip().split("\n"):
        if line.strip():
            log(f"  {line.strip()}")
    
    if result.returncode != 0:
        log(f"⚠️ {name} failed (code {result.returncode})")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-5:]:
                log(f"  ERR: {line}")
        return {"status": "failed", "exit_code": result.returncode}
    
    # Read the output state file
    signal_files = {
        "pead_earnings_scanner.py": "pead-signal.latest.json",
        "sr_proximity_detector.py": "sr-proximity-signal.latest.json",
        "donchian_breakout.py": "donchian-signal.latest.json",
        "ichimoku_full_system.py": "ichimoku-signal.latest.json",
        "insider_trading_scanner.py": "insider-signal.latest.json",
        "noise_stepforward_analysis.py": "noise-analysis.latest.json",
        "cot_signal.py": "cot-signal.latest.json",
        "vwap_agent.py": "vwap-signal.latest.json",
        "heiken_ashi_agent.py": "heiken-ashi-signal.latest.json",
        "fibonacci_agent.py": "fibonacci-signal.latest.json",
        "manipulation_4h_detector.py": "manipulation-4h-signal.latest.json",
        "noise_area_scalp.py": "noise-area-signal.latest.json",
        "qrs_session_bias.py": "qrs-bias-signal.latest.json",
    }

    # Multi-symbol generators write symbol-specific files so ES runs do not
    # overwrite the generic NQ state consumed by brain_cortex.
    if args and name in {"sr_proximity_detector.py", "donchian_breakout.py", "ichimoku_full_system.py"}:
        symbol = str(args[0]).lower()
        prefix = {
            "sr_proximity_detector.py": "sr-proximity",
            "donchian_breakout.py": "donchian",
            "ichimoku_full_system.py": "ichimoku",
        }[name]
        state_file = STATE_DIR / f"{prefix}-{symbol}-signal.latest.json"
    else:
        state_file = STATE_DIR / signal_files.get(name, "")
    if state_file.exists():
        try:
            with open(state_file) as f:
                return json.load(f)
        except:
            pass
    
    return {"status": "completed"}

def main():
    log("=" * 60)
    log("NEW SIGNAL ARSENAL RUNNER — Starting")
    log("=" * 60)
    
    results = {}
    
    # 1. PEAD Earnings Drift Scanner
    log("\n--- PEAD Earnings Drift ---")
    pead_result = run_script("pead_earnings_scanner.py")
    results["pead"] = pead_result
    
    # 2. S/R Proximity Detector (NQ 60m)
    log("\n--- S/R Proximity Detector (NQ 60m) ---")
    sr_nq = run_script("sr_proximity_detector.py", ["NQ", "60m"])
    results["sr_proximity_nq"] = sr_nq
    
    # 3. S/R Proximity Detector (ES 60m)
    log("\n--- S/R Proximity Detector (ES 60m) ---")
    sr_es = run_script("sr_proximity_detector.py", ["ES", "60m"])
    results["sr_proximity_es"] = sr_es
    
    # 4. Donchian(50) Breakout (NQ 60m)
    log("\n--- Donchian(50) Breakout (NQ 60m) ---")
    donchian_nq = run_script("donchian_breakout.py", ["NQ", "60m"])
    results["donchian_nq"] = donchian_nq
    
    # 5. Donchian(50) Breakout (ES 60m)
    log("\n--- Donchian(50) Breakout (ES 60m) ---")
    donchian_es = run_script("donchian_breakout.py", ["ES", "60m"])
    results["donchian_es"] = donchian_es
    
    # 5. Ichimoku Full System (NQ 60m)
    log("\n--- Ichimoku Full System (NQ 60m) ---")
    ichi_nq = run_script("ichimoku_full_system.py", ["NQ", "60m"])
    results["ichimoku_nq"] = ichi_nq
    
    # 6. Ichimoku Full System (ES 60m)
    log("\n--- Ichimoku Full System (ES 60m) ---")
    ichi_es = run_script("ichimoku_full_system.py", ["ES", "60m"])
    results["ichimoku_es"] = ichi_es
    
    # 7. Insider Trading Scanner
    log("\n--- Insider Trading Scanner (SEC EDGAR) ---")
    insider = run_script("insider_trading_scanner.py", ["--run"])
    results["insider"] = insider
    
    # 8. Noise & Step-Forward Analysis
    log("\n--- Noise & Step-Forward Analysis ---")
    noise = run_script("noise_stepforward_analysis.py")
    results["noise_analysis"] = noise
    
    # 9. COT Signal (CFTC Government Filing)
    log("\n--- COT Signal (CFTC Gov Filing) ---")
    cot = run_script("cot_signal.py")
    results["cot"] = cot
    
    # 10. VWAP Mean Reversion Agent
    log("\n--- VWAP Mean Reversion Agent ---")
    vwap_nq = run_script("vwap_agent.py")
    results["vwap"] = vwap_nq
    
    # 11. Heiken Ashi Trend Agent
    log("\n--- Heiken Ashi Trend Agent ---")
    ha_nq = run_script("heiken_ashi_agent.py")
    results["heiken_ashi"] = ha_nq
    
    # 12. Fibonacci Level Agent
    log("\n--- Fibonacci Level Agent ---")
    fib_nq = run_script("fibonacci_agent.py")
    results["fibonacci"] = fib_nq
    
    # 13. NQ 4H Manipulation Pattern Detector
    log("\n--- NQ 4H Manipulation Detector ---")
    manip = run_script("manipulation_4h_detector.py")
    results["manipulation_4h"] = manip
    
    # 14. Noise Area Intraday Scalp
    log("\n--- Noise Area Intraday Scalp ---")
    noise_scalp = run_script("noise_area_scalp.py")
    results["noise_area_scalp"] = noise_scalp
    
    # 15. QRS/RSRS Session Bias
    log("\n--- QRS/RSRS Session Bias ---")
    qrs_bias = run_script("qrs_session_bias.py")
    results["qrs_session_bias"] = qrs_bias
    
    # Combine into summary
    pead_signals = pead_result.get("active_signals", []) if isinstance(pead_result, dict) else []
    sr_signals_nq = sr_nq.get("signals", []) if isinstance(sr_nq, dict) else []
    sr_signals_es = sr_es.get("signals", []) if isinstance(sr_es, dict) else []
    donchian_nq_signal = donchian_nq.get("entry_signal", "HOLD") if isinstance(donchian_nq, dict) else "HOLD"
    donchian_es_signal = donchian_es.get("entry_signal", "HOLD") if isinstance(donchian_es, dict) else "HOLD"
    ichi_nq_trend = ichi_nq.get("trend", "neutral") if isinstance(ichi_nq, dict) else "neutral"
    ichi_es_trend = ichi_es.get("trend", "neutral") if isinstance(ichi_es, dict) else "neutral"
    insider_bias = insider.get("nq_bias", "neutral") if isinstance(insider, dict) else "neutral"
    insider_conf = insider.get("confidence", 0) if isinstance(insider, dict) else 0
    
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "arsenal_version": "1.0.0",
        "kill_switch_active": (STATE_DIR / "EMERGENCY_STOP").exists(),
        "signals_summary": {
            "pead": {
                "active": len(pead_signals),
                "nq_bias": pead_result.get("nq_bias", "neutral") if isinstance(pead_result, dict) else "neutral",
            },
            "sr_proximity": {
                "nq_signals": len(sr_signals_nq),
                "es_signals": len(sr_signals_es),
            },
            "donchian": {
                "nq": donchian_nq_signal,
                "es": donchian_es_signal,
                "nq_channel": {
                    "high": donchian_nq.get("donchian_channel", {}).get("high"),
                    "low": donchian_nq.get("donchian_channel", {}).get("low"),
                } if isinstance(donchian_nq, dict) else None,
            },
            "ichimoku": {
                "nq_trend": ichi_nq_trend,
                "es_trend": ichi_es_trend,
            },
            "insider_trading": {
                "nq_bias": insider_bias,
                "confidence": insider_conf,
            },
            "noise_area_scalp": {
                "signal": noise_scalp.get("entry_signal", noise_scalp.get("signal", "HOLD")) if isinstance(noise_scalp, dict) else "HOLD",
                "session": noise_scalp.get("session", "none") if isinstance(noise_scalp, dict) else "none",
            },
            "qrs_session_bias": {
                "bias": qrs_bias.get("signal", qrs_bias.get("bias", "neutral")) if isinstance(qrs_bias, dict) else "neutral",
                "z_score": qrs_bias.get("z_score", qrs_bias.get("z", 0)) if isinstance(qrs_bias, dict) else 0,
            },
        },
        "total_new_signals": len(pead_signals) + len(sr_signals_nq) + len(sr_signals_es) + 
                            (1 if donchian_nq_signal != "HOLD" else 0) +
                            (1 if donchian_es_signal != "HOLD" else 0),
        "details": results,
    }
    
    with open(COMBINED_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    
    log("\n" + "=" * 60)
    log("SUMMARY")
    log(f"  PEAD signals: {len(pead_signals)} active")
    log(f"  S/R proximity: {len(sr_signals_nq)} NQ + {len(sr_signals_es)} ES")
    log(f"  Donchian: {donchian_nq_signal} NQ, {donchian_es_signal} ES")
    log(f"  Ichimoku: {ichi_nq_trend} NQ, {ichi_es_trend} ES")
    log(f"  Insider bias: {insider_bias} (conf: {insider_conf})")
    
    # Extract noise summary
    noise_nq = noise.get("details", {}).get("nq_noise", {}) if isinstance(noise, dict) else {}
    noise_cl = noise.get("details", {}).get("cl_noise", {}) if isinstance(noise, dict) else {}
    log(f"  NQ noise: {noise_nq.get('regime', 'N/A')} (NSR: {noise_nq.get('current_nsr', 'N/A')})")
    log(f"  CL noise: {noise_cl.get('regime', 'N/A')} (NSR: {noise_cl.get('current_nsr', 'N/A')})")
    cot_nq = cot.get("nq_bias", "neutral") if isinstance(cot, dict) else "neutral"
    cot_es = cot.get("es_bias", "neutral") if isinstance(cot, dict) else "neutral"
    log(f"  COT: NQ={cot_nq}, ES={cot_es} (CFTC TFF)")
    
    # New TA agents
    vwap_r = isinstance(vwap_nq, dict) and vwap_nq or {}
    ha_r = isinstance(ha_nq, dict) and ha_nq or {}
    fib_r = isinstance(fib_nq, dict) and fib_nq or {}
    vwap_dir = vwap_r.get("NQ", {}).get("direction", "neutral") if isinstance(vwap_r, dict) else "neutral"
    ha_trend = ha_r.get("NQ", {}).get("trend", "neutral") if isinstance(ha_r, dict) else "neutral"
    fib_loc = fib_r.get("NQ", {}).get("signal", {}).get("nearest_level", "?") if isinstance(fib_r, dict) else "?"
    log(f"  VWAP: {vwap_dir}")
    log(f"  Heiken Ashi: {ha_trend}")
    log(f"  Fibonacci: {fib_loc}")
    
    # New signals from T3
    noise_sig = noise_scalp.get("entry_signal", noise_scalp.get("signal", "HOLD")) if isinstance(noise_scalp, dict) else "HOLD"
    noise_sess = noise_scalp.get("session", "none") if isinstance(noise_scalp, dict) else "none"
    qrs_b = qrs_bias.get("signal", qrs_bias.get("bias", "neutral")) if isinstance(qrs_bias, dict) else "neutral"
    qrs_z = qrs_bias.get("z_score", qrs_bias.get("z", 0)) if isinstance(qrs_bias, dict) else 0
    log(f"  Noise Area Scalp: {noise_sig} (session: {noise_sess})")
    log(f"  QRS Session Bias: {qrs_b} (z: {qrs_z})")
    
    log(f"  Total new signals: {summary['total_new_signals']}")
    log(f"  Kill switch: {'ACTIVE' if summary['kill_switch_active'] else 'INACTIVE'}")
    log("=" * 60)
    
    return summary

if __name__ == "__main__":
    main()
