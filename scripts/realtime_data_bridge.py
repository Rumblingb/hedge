#!/usr/bin/env python3
"""
realtime_data_bridge.py — Real-time NQ/ES futures data bridge.
Writes quote state for futures research and execution gates.

Data sources (priority order):
  1. TopstepX/ProjectX SignalR — execution-grade real-time quotes (PRIMARY)
  2. TradingView WebSocket — execution-grade only if update_mode is not delayed
  3. Yahoo Finance (2-10min delay) — FALLBACK

Usage:
  python3 scripts/realtime_data_bridge.py [--quiet]

Cron-ready: call every 30s. Writes state file, the master bridge
checks freshness to be < 60s before allowing any trades.

Output: ~/hedge/.rumbling-hedge/state/realtime-quote.latest.json
Format: { timestamp, price_nq, price_es, source, latency_ms, execution_grade, error }
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
STATE_DIR = HOME / "hedge" / ".rumbling-hedge" / "state"
LEGACY_STATE_DIR = HOME / ".rumbling-hedge" / "state"
STATE_FILE = STATE_DIR / "realtime-quote.latest.json"
LEGACY_STATE_FILE = LEGACY_STATE_DIR / "realtime-quote.latest.json"
HEDGE_DIR = HOME / "hedge"

# Node.js fetcher script location
TV_FETCHER = HEDGE_DIR / "scripts" / "tv_quote_fetcher.cjs"

# Freshness thresholds
MAX_DATA_AGE_SECONDS = 60  # Must be < 60s for trading
FALLBACK_MAX_AGE_SECONDS = 300  # Allow fallback data up to 5 minutes old

# Bill env file for TV session credentials
BILL_ENV = HOME / "Library" / "Application Support" / "AgentPay" / "bill" / "bill.env"

EXECUTION_GRADE_SOURCES = {"tradingview_pro", "tradingview_ws", "broker_realtime", "topstep_realtime", "databento_realtime"}
DATABENTO_SYMBOLS = {"nq": "NQ.v.0", "es": "ES.v.0"}
DATABENTO_DATASET = "GLBX.MDP3"
DATABENTO_SCHEMA = "mbp-1"
DATABENTO_TIMEOUT_SECONDS = 8
FIXED_PRICE_SCALE = 1_000_000_000
LAST_DATABENTO_DIAGNOSTIC = {}


def quote_block_reason(data):
    source = str(data.get("source") or "unknown")
    modes = [
        str(data.get("update_mode_nq") or "unknown").lower(),
        str(data.get("update_mode_es") or "unknown").lower(),
    ]
    if source in {"yahoo", "yahoo_fallback"}:
        return "fallback quote is delayed/research-only, not execution-grade realtime data"
    if source.startswith("tradingview_public"):
        return "public TradingView quote is delayed/research-only, not execution-grade realtime data"
    delayed_modes = [mode for mode in modes if "delayed" in mode]
    if delayed_modes:
        return f"quote update mode is delayed/research-only: {', '.join(sorted(set(delayed_modes)))}"
    if source not in EXECUTION_GRADE_SOURCES:
        return f"quote source={source} is not in the execution-grade source allowlist"
    return None


def annotate_quote_quality(data):
    """Attach execution-grade metadata without hiding the raw upstream source."""
    out = dict(data)
    original_source = str(out.get("source") or "unknown")
    reason = quote_block_reason(out)
    out["original_source"] = original_source
    out["execution_grade"] = reason is None
    out["execution_block_reason"] = reason
    if reason:
        if original_source.startswith("tradingview_pro") and "delayed" in reason:
            out["source"] = "tradingview_pro_delayed"
        elif original_source.startswith("tradingview_public"):
            out["source"] = "tradingview_public_delayed"
    return out


def load_bill_env(keys):
    """Load selected keys from bill.env."""
    env = {}
    if BILL_ENV.exists():
        for line in BILL_ENV.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip("'\"")
                if k in keys:
                    env[k] = v
    return env


def load_tv_env():
    """Load TV_SESSION and TV_SESSION_SIGN from bill.env."""
    return load_bill_env(("TV_SESSION", "TV_SESSION_SIGN", "TV_ECUID", "TV_DEVICE", "TV_BACKEND", "TV_BACKEND_SIGN"))


def load_databento_env():
    """Load retired Databento config from process env plus bill.env.

    Databento is no longer part of the normal bridge path. These helpers remain
    only so older audit/test commands fail closed instead of crashing.
    """
    env = load_bill_env((
        "DATABENTO_API_KEY",
        "BILL_DATABENTO_REALTIME_ENABLED",
        "BILL_DATABENTO_DATASET",
        "BILL_DATABENTO_SCHEMA",
    ))
    env.update(os.environ)
    return env


def databento_realtime_enabled(env=None):
    env = env or os.environ
    return str(env.get("BILL_DATABENTO_REALTIME_ENABLED") or "").lower() == "true"


def fixed_price_to_float(value):
    if value is None:
        return None
    try:
        return float(value) / FIXED_PRICE_SCALE
    except (TypeError, ValueError):
        return None


def databento_symbol_text(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = databento_symbol_text(item)
            if text:
                return text
        return None
    if isinstance(value, dict):
        for key in ("symbol", "raw_symbol", "stype_in_symbol", "stype_out_symbol"):
            text = databento_symbol_text(value.get(key))
            if text:
                return text
        return None
    for attr in ("symbol", "raw_symbol", "stype_in_symbol", "stype_out_symbol"):
        text = getattr(value, attr, None)
        if text:
            return str(text)
    return str(value)


def normalized_databento_symbol(value):
    symbol = str(databento_symbol_text(value) or "").upper()
    if symbol.startswith("NQ"):
        return "nq"
    if symbol.startswith("ES"):
        return "es"
    return None


def databento_record_instrument_id(record):
    value = getattr(record, "instrument_id", None)
    if value is not None:
        return value
    header = getattr(record, "hd", None)
    return getattr(header, "instrument_id", None)


def databento_record_raw_symbol(record, client):
    candidates = [
        getattr(record, "symbol", None),
        getattr(record, "raw_symbol", None),
        getattr(record, "stype_in_symbol", None),
        getattr(record, "stype_out_symbol", None),
    ]
    instrument_id = databento_record_instrument_id(record)
    sym_map = getattr(client, "symbology_map", {}) if client is not None else {}
    if instrument_id is not None and hasattr(sym_map, "get"):
        candidates.append(sym_map.get(instrument_id))
        candidates.append(sym_map.get(str(instrument_id)))
    for candidate in candidates:
        text = databento_symbol_text(candidate)
        if text:
            return text
    return None


def databento_record_ts_event(record):
    value = getattr(record, "ts_event", None)
    if value is not None:
        return value
    header = getattr(record, "hd", None)
    return getattr(header, "ts_event", None)


def databento_record_price(record):
    levels = getattr(record, "levels", None)
    if levels:
        first = levels[0]
        bid = fixed_price_to_float(getattr(first, "bid_px", None))
        ask = fixed_price_to_float(getattr(first, "ask_px", None))
        bid_size = getattr(first, "bid_sz", None)
        ask_size = getattr(first, "ask_sz", None)
        if bid and ask and bid > 0 and ask > 0:
            return round((bid + ask) / 2, 4), bid, ask, bid_size, ask_size
        if bid and bid > 0:
            return bid, bid, None, bid_size, ask_size
        if ask and ask > 0:
            return ask, None, ask, bid_size, ask_size
    price = fixed_price_to_float(getattr(record, "price", None))
    return price, None, None, None, None


def fetch_databento_realtime(quiet=False, client_factory=None, timeout_seconds=DATABENTO_TIMEOUT_SECONDS):
    """Retired Databento compatibility path.

    The production bridge no longer calls this. It remains for legacy audit
    commands and tests, and it only attempts a fetch when explicitly enabled.
    """
    global LAST_DATABENTO_DIAGNOSTIC
    env = load_databento_env()
    dataset = env.get("BILL_DATABENTO_DATASET") or DATABENTO_DATASET
    schema = env.get("BILL_DATABENTO_SCHEMA") or DATABENTO_SCHEMA
    diagnostic = {
        "dataset": dataset,
        "schema": schema,
        "symbols": list(DATABENTO_SYMBOLS.values()),
        "stype_in": "continuous",
        "timeout_seconds": timeout_seconds,
        "records_seen": 0,
        "records_with_symbol": 0,
        "records_with_price": 0,
        "seen_symbols": [],
        "seen_record_types": {},
        "errors": [],
        "retired": True,
    }
    LAST_DATABENTO_DIAGNOSTIC = diagnostic
    if not databento_realtime_enabled(env):
        if not quiet:
            print("[bridge] Databento realtime is retired/disabled; TopstepX is the primary realtime path", file=sys.stderr)
        diagnostic["blocked_reason"] = "databento realtime retired/disabled"
        return None

    api_key = env.get("DATABENTO_API_KEY")
    if not api_key:
        if not quiet:
            print("[bridge] Databento realtime enabled but DATABENTO_API_KEY is missing", file=sys.stderr)
        diagnostic["blocked_reason"] = "missing DATABENTO_API_KEY"
        return None

    if client_factory is None:
        try:
            import databento as db
        except ImportError:
            if not quiet:
                print("[bridge] Databento module not installed in bridge runtime", file=sys.stderr)
            diagnostic["blocked_reason"] = "databento module not installed"
            return None
        client_factory = db.Live

    done = threading.Event()
    quotes = {}
    errors = []
    client = None
    t0 = time.time()

    def on_record(record):
        try:
            diagnostic["records_seen"] += 1
            record_type = type(record).__name__
            diagnostic["seen_record_types"][record_type] = diagnostic["seen_record_types"].get(record_type, 0) + 1
            raw_symbol = databento_record_raw_symbol(record, client)
            symbol = normalized_databento_symbol(raw_symbol)
            if not symbol:
                return
            diagnostic["records_with_symbol"] += 1
            if raw_symbol not in diagnostic["seen_symbols"]:
                diagnostic["seen_symbols"].append(raw_symbol)
            price, bid, ask, bid_size, ask_size = databento_record_price(record)
            if price is None:
                return
            diagnostic["records_with_price"] += 1
            ts_event = databento_record_ts_event(record)
            event_dt = datetime.now(timezone.utc)
            if isinstance(ts_event, int) and ts_event > 0:
                event_dt = datetime.fromtimestamp(ts_event / 1_000_000_000, tz=timezone.utc)
            quotes[symbol] = {
                "price": price,
                "bid": bid,
                "ask": ask,
                "bid_size": bid_size,
                "ask_size": ask_size,
                "event_ts": event_dt.isoformat(),
            }
            if all(key in quotes for key in ("nq", "es")):
                done.set()
        except Exception as exc:
            errors.append(str(exc))
            diagnostic["errors"].append(str(exc))

    try:
        client = client_factory(key=api_key)
        client.add_callback(on_record)
        client.subscribe(
            dataset=dataset,
            schema=schema,
            symbols=list(DATABENTO_SYMBOLS.values()),
            stype_in="continuous",
        )
        client.start()
        done.wait(timeout_seconds)
    except Exception as exc:
        errors.append(str(exc))
        diagnostic["errors"].append(str(exc))
    finally:
        if client is not None:
            for method_name in ("stop", "terminate"):
                method = getattr(client, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break

    if not all(key in quotes for key in ("nq", "es")):
        diagnostic["quotes_seen"] = sorted(quotes)
        diagnostic["blocked_reason"] = f"missing required quotes: {', '.join(sorted(set(('nq', 'es')) - set(quotes)))}"
        return None

    latency = round((time.time() - t0) * 1000)
    diagnostic["quotes_seen"] = sorted(quotes)
    diagnostic["blocked_reason"] = None
    return annotate_quote_quality({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price_nq": quotes["nq"]["price"],
        "price_es": quotes["es"]["price"],
        "bid_nq": quotes["nq"]["bid"],
        "ask_nq": quotes["nq"]["ask"],
        "bid_size_nq": quotes["nq"]["bid_size"],
        "ask_size_nq": quotes["nq"]["ask_size"],
        "bid_es": quotes["es"]["bid"],
        "ask_es": quotes["es"]["ask"],
        "bid_size_es": quotes["es"]["bid_size"],
        "ask_size_es": quotes["es"]["ask_size"],
        "event_ts_nq": quotes["nq"]["event_ts"],
        "event_ts_es": quotes["es"]["event_ts"],
        "source": "databento_realtime",
        "latency_ms": latency,
        "session_nq": None,
        "session_es": None,
        "update_mode_nq": "realtime",
        "update_mode_es": "realtime",
        "databento_dataset": dataset,
        "databento_schema": schema,
        "databento_diagnostic": diagnostic,
        "error": "; ".join(errors) if errors else None,
    })


def get_last_databento_diagnostic():
    return dict(LAST_DATABENTO_DIAGNOSTIC)


def fetch_tv_websocket(quiet=False):
    """
    Fetch real-time NQ/ES quotes via TradingView WebSocket (Node.js).
    Returns dict or None on failure.
    """
    if not TV_FETCHER.exists():
        if not quiet:
            print(f"[bridge] TV fetcher not found: {TV_FETCHER}", file=sys.stderr)
        return None

    try:
        env = os.environ.copy()
        env.update(load_tv_env())

        if not env.get("TV_SESSION"):
            if not quiet:
                print("[bridge] No TV_SESSION in env — will run in public mode", file=sys.stderr)

        t0 = time.time()
        proc = subprocess.run(
            ["node", str(TV_FETCHER), "--json"],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(HEDGE_DIR),
            env=env,
        )

        if proc.returncode != 0:
            if not quiet:
                print(f"[bridge] TV fetcher exit code {proc.returncode}: {proc.stderr.strip()[:200]}", file=sys.stderr)
            return None

        data = json.loads(proc.stdout.strip())
        elapsed = time.time() - t0

        # Validate the response
        if data.get("price_nq") is None or data.get("price_es") is None:
            if not quiet:
                print(f"[bridge] TV returned incomplete data: {data.get('error', 'unknown')}", file=sys.stderr)
            return None

        data["_fetch_elapsed_ms"] = round(elapsed * 1000)
        return annotate_quote_quality(data)

    except subprocess.TimeoutExpired:
        if not quiet:
            print("[bridge] TV fetcher timed out after 20s", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        if not quiet:
            print(f"[bridge] TV fetcher invalid JSON: {e}", file=sys.stderr)
        return None
    except Exception as e:
        if not quiet:
            print(f"[bridge] TV fetcher error: {e}", file=sys.stderr)
        return None


def fetch_yahoo_fallback():
    """
    Fallback: fetch NQ and ES prices from Yahoo Finance.
    Much slower (~2-10min delay) but always available.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None

    t0 = time.time()
    prices = {}
    errors = []

    for symbol, yahoo_sym in [("nq", "NQ=F"), ("es", "ES=F")]:
        try:
            ticker = yf.Ticker(yahoo_sym)
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                prices[symbol] = float(hist.iloc[-1]["Close"])
            else:
                errors.append(f"{symbol}: no data from Yahoo")
        except Exception as e:
            errors.append(f"{symbol}: {e}")

    latency = round((time.time() - t0) * 1000)

    if not prices:
        return None

    return annotate_quote_quality({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price_nq": prices.get("nq"),
        "price_es": prices.get("es"),
        "bid_nq": None,
        "ask_nq": None,
        "bid_es": None,
        "ask_es": None,
        "source": "yahoo_fallback",
        "latency_ms": latency,
        "session_nq": None,
        "session_es": None,
        "update_mode_nq": "delayed_120s",
        "update_mode_es": "delayed_120s",
        "error": "; ".join(errors) if errors else None,
    })


def topstep_broker_touch_paused(quiet=False):
    """True when env or session-safety forbids opening new TopstepX/ProjectX sessions."""
    if os.environ.get("BILL_TOPSTEP_BROKER_TOUCH_PAUSED", "").strip().lower() in {"1", "true", "yes"}:
        if not quiet:
            print("[bridge] TopstepX fetch skipped: BILL_TOPSTEP_BROKER_TOUCH_PAUSED=true", file=sys.stderr)
        return True
    try:
        sys.path.insert(0, str(HEDGE_DIR / "scripts"))
        import topstep_market_data_smoke as md  # noqa: WPS433

        blockers = md.safety_blockers()
        if blockers:
            if not quiet:
                print(f"[bridge] TopstepX fetch skipped: {'; '.join(blockers)}", file=sys.stderr)
            return True
    except Exception as exc:
        if not quiet:
            print(f"[bridge] TopstepX safety check failed: {exc}", file=sys.stderr)
    return False


def fetch_topstepx_realtime(quiet=False):
    """
    Fetch real-time NQ/ES quotes from TopstepX/ProjectX SignalR hub.
    Uses the topstepx_quote_fetcher.py script. Returns dict or None.
    """
    if topstep_broker_touch_paused(quiet=quiet):
        return None

    fetcher = HEDGE_DIR / "scripts" / "topstepx_quote_fetcher.py"
    if not fetcher.exists():
        if not quiet:
            print(f"[bridge] TopstepX fetcher not found: {fetcher}", file=sys.stderr)
        return None

    try:
        result = subprocess.run(
            [sys.executable, str(fetcher), "--quiet"],
            capture_output=True,
            text=True,
            timeout=25,
            cwd=str(HEDGE_DIR),
        )
        if result.returncode != 0:
            if not quiet:
                stderr = result.stderr.strip()[:200] if result.stderr else "exit code non-zero"
                print(f"[bridge] TopstepX fetcher failed: {stderr}", file=sys.stderr)
            return None

        data = json.loads(result.stdout.strip())
        if data.get("price_nq") is None:
            if not quiet:
                print(f"[bridge] TopstepX returned no NQ price: {data.get('error', 'unknown')}", file=sys.stderr)
            return None

        return annotate_quote_quality(data)

    except json.JSONDecodeError:
        if not quiet:
            print(f"[bridge] TopstepX fetcher returned invalid JSON", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        if not quiet:
            print("[bridge] TopstepX fetcher timed out after 25s", file=sys.stderr)
        return None
    except Exception as e:
        if not quiet:
            print(f"[bridge] TopstepX fetcher error: {e}", file=sys.stderr)
        return None


def fetch_existing_topstep_realtime(quiet=False):
    """Preserve a fresh canonical TopstepX quote instead of downgrading to fallback."""
    state_file = STATE_FILE if STATE_FILE.exists() else LEGACY_STATE_FILE
    if not state_file.exists():
        return None
    try:
        data = json.loads(state_file.read_text())
    except Exception as exc:
        if not quiet:
            print(f"[bridge] Could not read existing realtime state: {exc}", file=sys.stderr)
        return None

    if data.get("source") != "topstep_realtime":
        return None
    if not data.get("price_nq") or not data.get("price_es"):
        return None
    ts_str = data.get("timestamp") or data.get("bridge_generated_at")
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except ValueError:
        return None
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    if age >= MAX_DATA_AGE_SECONDS:
        return None

    annotated = annotate_quote_quality(data)
    if annotated.get("execution_grade") is not True:
        return None
    annotated["preserved_existing_state"] = True
    annotated["existing_state_age_seconds"] = round(age, 1)
    annotated["latency_ms"] = annotated.get("latency_ms") or 0
    if not quiet:
        print(f"[bridge] Preserving fresh TopstepX realtime state ({age:.1f}s old)", file=sys.stderr)
    return annotated


def write_state(data, quiet=False):
    """Write quote data to state file."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Add bridge metadata
    output = {
        **data,
        "bridge_generated_at": datetime.now(timezone.utc).isoformat(),
        "bridge_version": "1.0.0",
        "canonical_state_path": str(STATE_FILE),
    }

    STATE_FILE.write_text(json.dumps(output, indent=2))
    LEGACY_STATE_FILE.write_text(json.dumps(output, indent=2))

    if not quiet:
        nq_str = f"${data['price_nq']:.2f}" if data.get("price_nq") else "N/A"
        es_str = f"${data['price_es']:.2f}" if data.get("price_es") else "N/A"
        src = data.get("source", "unknown")
        lat = data.get("latency_ms", "?")
        print(f"[bridge] {nq_str} / {es_str} | source={src} | latency={lat}ms | {STATE_FILE}")


def check_state_freshness():
    """Check if existing state file data is fresh enough for trading."""
    state_file = STATE_FILE if STATE_FILE.exists() else LEGACY_STATE_FILE

    if not state_file.exists():
        return {"fresh": False, "age_seconds": None, "reason": "no_state_file"}

    try:
        data = json.loads(state_file.read_text())
        ts_str = data.get("timestamp") or data.get("bridge_generated_at")
        if not ts_str:
            return {"fresh": False, "age_seconds": None, "reason": "no_timestamp"}

        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        block_reason = data.get("execution_block_reason") or quote_block_reason(data)
        fresh = age < MAX_DATA_AGE_SECONDS and not block_reason

        return {
            "fresh": fresh,
            "age_seconds": round(age, 1),
            "source": data.get("source", "unknown"),
            "state_path": str(state_file),
            "price_nq": data.get("price_nq"),
            "price_es": data.get("price_es"),
            "execution_grade": not block_reason,
            "execution_block_reason": block_reason,
            "reason": block_reason or ("ok" if age < MAX_DATA_AGE_SECONDS else f"stale ({age:.0f}s > {MAX_DATA_AGE_SECONDS}s max)"),
        }
    except Exception as e:
        return {"fresh": False, "age_seconds": None, "reason": f"error: {e}"}


def fetch_tsxapi_v2(quiet=False):
    """Fetch quotes via the tsxapipy-based v2 fetcher (topstepx_quote_fetcher_v2.py).

    Uses tsxapipy DataStream for SignalR connections instead of raw websockets.
    Reads credentials from bill.env and creates its own auth session
    (does NOT share the token cache used by the original fetcher).
    Returns dict or None on failure.
    """

    fetcher = HEDGE_DIR / "scripts" / "topstepx_quote_fetcher_v2.py"
    if not fetcher.exists():
        if not quiet:
            print(f"[bridge] tsxapi v2 fetcher not found: {fetcher}", file=sys.stderr)
        return None

    try:
        result = subprocess.run(
            [sys.executable, str(fetcher), "--quiet"],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(HEDGE_DIR),
            env={**os.environ, "TRADING_ENVIRONMENT": "LIVE"},
        )
        if result.returncode != 0:
            if not quiet:
                stderr = result.stderr.strip()[:200] if result.stderr else "exit code non-zero"
                print(f"[bridge] tsxapi v2 fetcher failed: {stderr}", file=sys.stderr)
            return None

        data = json.loads(result.stdout.strip())
        if data.get("price_nq") is None:
            if not quiet:
                print(f"[bridge] tsxapi v2 returned no NQ price: {data.get('error', 'unknown')}", file=sys.stderr)
            return None

        return annotate_quote_quality(data)

    except json.JSONDecodeError:
        if not quiet:
            print(f"[bridge] tsxapi v2 fetcher returned invalid JSON", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        if not quiet:
            print("[bridge] tsxapi v2 fetcher timed out after 20s", file=sys.stderr)
        return None
    except Exception as e:
        if not quiet:
            print(f"[bridge] tsxapi v2 fetcher error: {e}", file=sys.stderr)
        return None



def main():
    quiet = "--quiet" in sys.argv or "-q" in sys.argv

    if "--check" in sys.argv:
        freshness = check_state_freshness()
        print(json.dumps(freshness, indent=2))
        return 0 if freshness["fresh"] else 1

    if "--databento-only" in sys.argv:
        data = fetch_databento_realtime(quiet=quiet)
        if data is None:
            return 1
        write_state(data, quiet=quiet)
        return 0 if data.get("price_nq") and data.get("price_es") else 1

    # Step 1: Reuse fresh canonical TopstepX state before opening a new
    # ProjectX SignalR session. This reduces avoidable broker-session churn.
    data = fetch_existing_topstep_realtime(quiet=quiet)

    # Step 2: Try tsxapipy v2 fetcher (DataStream-based). DEFAULT OFF: the v2
    # fetcher opens its own auth session instead of the shared machine-wide
    # token cache, which is exactly what trips Topstep's multiple-session
    # warning (session safety re-paused 2026-07-06). Do not enable until the
    # v2 fetcher reuses topstep_auth_cache.
    if data is None and os.environ.get("BILL_TSXAPI_V2_ENABLED", "").lower() == "true":
        data = fetch_tsxapi_v2(quiet=quiet)

    # Step 3: Fallback to original raw-websocket fetcher
    if data is None:
        data = fetch_topstepx_realtime(quiet=quiet)

    # Step 4: Try TradingView WebSocket.
    if data is None:
        if not quiet:
            print("[bridge] Fetching real-time quotes via TradingView WebSocket...", file=sys.stderr)
        data = fetch_tv_websocket(quiet=quiet)

    # Step 5: Fall back to Yahoo if higher-quality sources fail.
    if data is None:
        if not quiet:
            print("[bridge] TopstepX/TV failed, falling back to Yahoo...", file=sys.stderr)
        data = fetch_yahoo_fallback()

    # Step 6: If everything failed
    if data is None:
        error_output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price_nq": None,
            "price_es": None,
            "source": "none",
            "latency_ms": None,
            "error": "All data sources failed",
            "bridge_generated_at": datetime.now(timezone.utc).isoformat(),
            "bridge_version": "1.0.0",
        }
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LEGACY_STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(error_output, indent=2))
        LEGACY_STATE_FILE.write_text(json.dumps(error_output, indent=2))
        print("[bridge] ALL SOURCES FAILED — wrote error state", file=sys.stderr)
        return 2

    # Step 7: Write state file
    write_state(data, quiet=quiet)

    if data.get("price_nq") and data.get("price_es"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
