#!/usr/bin/env python3
"""GOLD #11 ENHANCED: Dealer Gamma + IV/RV Spread + Skew + VRP.

Professional options volatility analysis using yfinance:
- Variance Risk Premium (IV vs Realized Vol spread)
- Skew steepness (OTM put IV / ATM IV ratio)
- Put/Call ratio from CBOE
- Dealer gamma estimate from combined signals
"""

import json, os, math, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.path.expanduser("~/.rumbling-hedge"))
STATE_DIR = ROOT / "state"

try:
    import yfinance as yf
    import numpy as np
    import requests
except ImportError as e:
    print(f"  Dealer Gamma: missing dep: {e}", file=sys.stderr)
    sys.exit(1)


def _safe(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def compute_signals():
    now = datetime.now(timezone.utc)

    # ---- Fetch VIX ----
    vix_ticker = yf.Ticker("^VIX")
    vix = _safe(vix_ticker.info.get("regularMarketPrice",
              vix_ticker.info.get("previousClose")))

    # ---- Fetch SPX data ----
    spx = yf.Ticker("^SPX")
    spx_price = _safe(spx.info.get("regularMarketPrice",
                      spx.info.get("previousClose", 5000)))

    # ---- Fetch SPX options ----
    atm_iv = None
    skew_ratio = None
    try:
        expirations = spx.options
        if expirations:
            # Find nearest 30DTE (between 14-45 days)
            now_local = datetime.now()
            best_opt = None
            best_dte = 999
            for e in expirations:
                exp_date = datetime.strptime(e, "%Y-%m-%d")
                dte = (exp_date - now_local).days
                if 14 <= dte <= 45 and dte < best_dte:
                    best_dte = dte
                    best_opt = e
            if not best_opt:
                best_opt = expirations[0]

            opt = spx.option_chain(best_opt)
            calls, puts = opt.calls, opt.puts
            price = spx_price or 5000

            # ATM IV (average of ATM call and put)
            atm_call = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
            atm_put = puts.iloc[(puts["strike"] - price).abs().argsort()[:1]]
            call_iv = _safe(atm_call.iloc[0].get("impliedVolatility"))
            put_iv = _safe(atm_put.iloc[0].get("impliedVolatility"))
            if call_iv and put_iv:
                atm_iv = (call_iv + put_iv) / 2
            elif call_iv:
                atm_iv = call_iv
            elif put_iv:
                atm_iv = put_iv

            # Skew: 95% OTM put IV vs ATM IV
            otm_puts = puts[puts["strike"] < price * 0.95]
            if not otm_puts.empty and atm_iv and atm_iv > 0:
                otm_put_iv = _safe(otm_puts.iloc[-1].get("impliedVolatility"))
                if otm_put_iv:
                    skew_ratio = round(otm_put_iv / atm_iv, 3)

    except Exception as e:
        pass  # Options data not always available

    # ---- Compute realized volatility ----
    rv = None
    try:
        hist = spx.history(period="1mo")
        if len(hist) >= 10:
            closes = hist["Close"].values
            log_rets = np.log(closes[1:] / closes[:-1])
            rv = float(np.std(log_rets, ddof=1)) * math.sqrt(252)
    except Exception:
        pass

    # ---- Fetch CBOE put/call ratio ----
    pc_ratio = None
    try:
        resp = requests.get(
            "https://cdn.cboe.com/api/global/us_options/metrics/put_call_ratio.json",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if resp.ok:
            pc_data = resp.json()
            pc_ratio = _safe(pc_data.get("data", {}).get("pcRatio",
                           pc_data.get("pcRatio")))
    except Exception:
        pass

    # ---- Build output ----
    out = {
        "ts": now.isoformat(),
        "gamma_signal": 0.0,
        "vix_level": round(vix, 2) if vix else None,
        "spx_price": round(spx_price, 2) if spx_price else None,
        "atm_iv": round(atm_iv, 4) if atm_iv else None,
        "realized_vol_20d": round(rv, 4) if rv else None,
        "iv_vs_rv_spread": None,
        "skew_ratio": skew_ratio,
        "pc_ratio": round(pc_ratio, 2) if pc_ratio else None,
        "vrp_signal": None,
        "recommendation": "NEUTRAL",
        "details": {"reasons": []},
    }

    # ---- Compute IV vs RV spread (Variance Risk Premium) ----
    if atm_iv and rv and rv > 0:
        spread = round((atm_iv - rv) / rv, 3)
        out["iv_vs_rv_spread"] = spread
        if spread > 0.15:
            out["vrp_signal"] = "OVERPRICED"
        elif spread < -0.10:
            out["vrp_signal"] = "UNDERPRICED"
        else:
            out["vrp_signal"] = "FAIR"

    # ---- Fuse gamma signal from all factors ----
    gamma = 0.0
    reasons = []

    # VIX
    if vix:
        if vix < 15:
            gamma += 0.2
            reasons.append(f"VIX={vix:.1f}<15 complacent")
        elif vix > 30:
            gamma -= 0.3
            reasons.append(f"VIX={vix:.1f}>30 fear")
        elif vix > 22:
            gamma -= 0.15
            reasons.append(f"VIX={vix:.1f} elevated")
        else:
            gamma += 0.05
            reasons.append(f"VIX={vix:.1f} normal")

    # ATM IV level
    if atm_iv:
        if atm_iv > 0.25:
            gamma -= 0.15
            reasons.append(f"IV={atm_iv:.1%} elevated")
        elif atm_iv < 0.12:
            gamma += 0.1
            reasons.append(f"IV={atm_iv:.1%} low")

    # VRP spread (biggest edge signal)
    spread = out.get("iv_vs_rv_spread")
    if spread is not None:
        if spread > 0.20:
            gamma -= 0.25
            reasons.append(f"VRP+{spread:.0%} short vol edge")
        elif spread > 0.10:
            gamma -= 0.15
            reasons.append(f"VRP+{spread:.0%} moderate")
        elif spread < -0.10:
            gamma += 0.2
            reasons.append(f"VRP{spread:.0%} long vol opp")

    # Skew
    if skew_ratio:
        if skew_ratio > 1.4:
            gamma -= 0.15
            reasons.append(f"skew={skew_ratio:.2f} extreme")
        elif skew_ratio > 1.2:
            gamma -= 0.05
            reasons.append(f"skew={skew_ratio:.2f} elevated")

    # Put/Call
    if pc_ratio:
        if pc_ratio > 1.2:
            gamma -= 0.1
            reasons.append(f"P/C={pc_ratio:.2f} bearish")
        elif pc_ratio < 0.7:
            gamma += 0.1
            reasons.append(f"P/C={pc_ratio:.2f} bullish")

    gamma = max(-1.0, min(1.0, gamma))
    out["gamma_signal"] = round(gamma, 3)
    out["details"]["reasons"] = reasons

    if gamma <= -0.5:
        out["recommendation"] = "STRONG SHORT VOL"
    elif gamma <= -0.2:
        out["recommendation"] = "SHORT VOL"
    elif gamma >= 0.5:
        out["recommendation"] = "STRONG LONG VOL"
    elif gamma >= 0.2:
        out["recommendation"] = "LONG VOL"

    iv_s = f"IV={atm_iv:.1%}" if atm_iv else "IV=?"
    rv_s = f"RV={rv:.1%}" if rv else "RV=?"
    out["interpretation"] = f"VIX={vix:.1f} SPX@{spx_price:.0f} {iv_s}/{rv_s}"
    return out


def main():
    out = compute_signals()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / "dealer-gamma-signal.latest.json", "w") as f:
        json.dump(out, f, indent=2)

    sig = out["gamma_signal"]
    rec = out["recommendation"]
    iv = out.get("atm_iv")
    rv = out.get("realized_vol_20d")
    vix = out.get("vix_level")
    iv_s = f"IV={iv:.1%}" if iv else "IV=?"
    rv_s = f"RV={rv:.1%}" if rv else "RV=?"
    print(f"  Dealer Gamma: signal={sig:+.3f} [{rec}] | {iv_s}/{rv_s} | VIX={vix}")


if __name__ == "__main__":
    main()
