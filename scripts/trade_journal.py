#!/usr/bin/env python3
"""
Trade Journal — logs completed NQ futures trades with MAE/MFE analysis.

Authenticates with TopstepX API, fetches today's fills and open positions,
matches entry/exit pairs, computes MAE/MFE via yfinance 1m bars, and appends
each closed trade to the trade journal JSONL.

Also calls failure_rag.py --log for each new trade.

CLI:
    python3 trade_journal.py            # log new trades (incremental)
    python3 trade_journal.py --dry-run  # print what would be logged
    python3 trade_journal.py --force    # re-process all today's fills
"""

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
import urllib.error
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HOME = Path.home()
STATE_DIR = HOME / ".rumbling-hedge" / "state"
ENV_PATH = HOME / "Library" / "Application Support" / "AgentPay" / "bill" / "bill.env"
API_BASE = "https://api.topstepx.com"
ACCOUNT_ID = 22983191

JOURNAL_PATH = STATE_DIR / "trade-journal.jsonl"
STATE_PATH = STATE_DIR / "trade-journal-state.json"

# Session windows in Eastern Time (UTC-5 standard, UTC-4 DST; we use ET offsets)
# We'll convert UTC timestamps to ET for session classification
ET_OFFSET = timedelta(hours=-4)  # EDT (may need adjustment for EST)

SESSION_WINDOWS = {
    "ASIA":        (timedelta(hours=0),  timedelta(hours=9, minutes=30)),
    "LONDON":      (timedelta(hours=3),  timedelta(hours=7)),
    "NY_MORNING":  (timedelta(hours=9, minutes=30), timedelta(hours=12)),
    "NY_AFTERNOON":(timedelta(hours=12), timedelta(hours=16)),
}

# MNQ point value
POINT_VALUE = 5.0  # USD per point

# ── helpers ──────────────────────────────────────────────────────────────

def read_secure(key_name: str) -> Optional[str]:
    """Read a key from the bill env file."""
    if not ENV_PATH.exists():
        return None
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and line.split("=", 1)[0].strip() == key_name:
            return line.split("=", 1)[1].strip().strip("'\"")
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_to_et(dt: datetime) -> datetime:
    """Convert UTC datetime to Eastern Time (handles DST roughly)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt + ET_OFFSET


def classify_session(utc_dt: datetime) -> str:
    """Classify a UTC datetime into a trading session (ET-based)."""
    et = utc_to_et(utc_dt)
    et_time = timedelta(hours=et.hour, minutes=et.minute, seconds=et.second)

    sessions = []
    for name, (start, end) in SESSION_WINDOWS.items():
        if start <= et_time < end:
            sessions.append(name)

    # Prefer more specific sessions
    priority = ["NY_MORNING", "NY_AFTERNOON", "LONDON", "ASIA"]
    for p in priority:
        if p in sessions:
            return p
    return "OFF_HOURS"


def api_request(url: str, body: Dict[str, Any], headers: Dict[str, str],
                timeout: int = 15) -> Dict[str, Any]:
    """Make a JSON API request and return the parsed response."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def login() -> str:
    """Authenticate with TopstepX and return a bearer token."""
    api_key = read_secure("RH_TOPSTEP_API_KEY")
    username = read_secure("RH_TOPSTEP_USERNAME") or "vishar.rumbling@gmail.com"
    if not api_key:
        raise RuntimeError("API key not found in bill.env")
    url = f"{API_BASE}/api/Auth/loginKey"
    body = {
        "apiKey": api_key,
        "userName": username,
        "applicationId": 0,
        "applicationVersion": "1.0.0",
    }
    resp = api_request(url, body,
                       {"Content-Type": "application/json"}, timeout=15)
    token = resp.get("token")
    if not token:
        raise RuntimeError(f"Login failed: {json.dumps(resp)}")
    return token


def fetch_fills(token: str, start: str, end: str) -> List[Dict[str, Any]]:
    """Fetch all fills for today."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    url = f"{API_BASE}/api/Order/search"
    body = {
        "accountId": ACCOUNT_ID,
        "startTimestamp": start,
        "endTimestamp": end,
    }
    data = api_request(url, body, headers, timeout=15)
    orders = data.get("orders", [])
    if not orders and isinstance(data, dict):
        for k in ("orders", "data", "result"):
            v = data.get(k)
            if isinstance(v, list):
                orders = v
                break
        # Sometimes orders is inside data.orders
        if isinstance(data.get("data"), dict):
            inner = data["data"].get("orders")
            if isinstance(inner, list):
                orders = inner
    return orders if isinstance(orders, list) else []


def fetch_positions(token: str) -> List[Dict[str, Any]]:
    """Fetch currently open positions."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    url = f"{API_BASE}/api/Position/searchOpen"
    body = {"accountId": ACCOUNT_ID}
    try:
        data = api_request(url, body, headers, timeout=15)
    except Exception:
        return []

    pos_list = data.get("positions", data.get("data", {}).get("positions", []))
    if not pos_list and isinstance(data, dict):
        for k in ("positions", "data", "result"):
            v = data.get(k)
            if isinstance(v, list):
                pos_list = v
                break
    return pos_list if isinstance(pos_list, list) else []


def parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp to datetime."""
    if not ts_str:
        return None
    try:
        # Handle Z suffix
        s = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ── yfinance helpers ────────────────────────────────────────────────────

def fetch_bars(symbol: str, start: datetime, end: datetime,
               max_retries: int = 3) -> Optional[List[Dict[str, float]]]:
    """Fetch 1-minute bars from yfinance. Returns list of {o,h,l,c} dicts."""
    import yfinance as yf

    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start, end=end, interval="1m")
            if df.empty:
                # Try extending window slightly
                ticker2 = yf.Ticker(symbol)
                df = ticker2.history(
                    start=start - timedelta(minutes=5),
                    end=end + timedelta(minutes=5),
                    interval="1m"
                )
            if df.empty:
                return None

            bars = []
            for idx, row in df.iterrows():
                bars.append({
                    "t": idx,
                    "o": float(row["Open"]),
                    "h": float(row["High"]),
                    "l": float(row["Low"]),
                    "c": float(row["Close"]),
                })
            return bars
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
            else:
                return None
    return None


def compute_mae_mfe(bars: List[Dict[str, float]], direction: str,
                    entry_price: float) -> Tuple[float, float, float]:
    """
    Compute MAE and MFE from 1m bars and entry price.

    Returns (mae_pts, mfe_pts, atr_at_entry).

    For LONG: MAE = entry - min_low, MFE = max_high - entry
    For SHORT: MAE = max_high - entry, MFE = entry - min_low
    """
    if not bars or len(bars) < 1:
        return 0.0, 0.0, 0.0

    high_prices = [b["h"] for b in bars]
    low_prices = [b["l"] for b in bars]
    close_prices = [b["c"] for b in bars]

    if direction.upper() == "LONG":
        mae = max(0.0, entry_price - min(low_prices))
        mfe = max(0.0, max(high_prices) - entry_price)
    else:
        mae = max(0.0, max(high_prices) - entry_price)
        mfe = max(0.0, entry_price - min(low_prices))

    # Compute ATR from the bars (first 14 bars or all if fewer)
    atr = compute_atr(bars)

    return round(mae, 4), round(mfe, 4), round(atr, 4)


def compute_atr(bars: List[Dict[str, float]], period: int = 14) -> float:
    """Compute ATR from 1m bars using Wilder's smoothing."""
    if len(bars) < 2:
        return 0.0

    true_ranges = []
    for i in range(1, len(bars)):
        high = bars[i]["h"]
        low = bars[i]["l"]
        prev_close = bars[i-1]["c"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    if not true_ranges:
        return 0.0

    # Simple average of available TRs
    return sum(true_ranges) / len(true_ranges)


# ── trade matching ──────────────────────────────────────────────────────

def match_trades(fills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Match filled orders into completed trades (entry + exit pairs).

    Uses simple FIFO matching per symbol.
    Returns list of trade dicts with entry_ts, exit_ts, direction, etc.
    """
    # Filter to only filled orders (status == 2)
    filled = [o for o in fills if o.get("status") == 2]

    if not filled:
        return []

    # Group by contract and sort by timestamp
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for o in filled:
        symbol = o.get("contractId", o.get("symbol", "UNKNOWN"))
        by_symbol.setdefault(symbol, []).append(o)

    trades = []

    for symbol, orders in by_symbol.items():
        # Sort by timestamp
        orders.sort(key=lambda o: o.get("creationTimestamp", o.get("updateTimestamp", "")))

        # FIFO matching: track remaining buys and sells
        buy_queue: List[Dict[str, Any]] = []
        sell_queue: List[Dict[str, Any]] = []

        for o in orders:
            side = o.get("side")
            volume = float(o.get("fillVolume", o.get("size", 0)))

            if side == 0:  # BUY
                buy_queue.append(o)
            elif side == 1:  # SELL
                sell_queue.append(o)

            # Try to match
            while buy_queue and sell_queue:
                buy = buy_queue[0]
                sell = sell_queue[0]

                buy_vol = float(buy.get("fillVolume", buy.get("size", 0)))
                sell_vol = float(sell.get("fillVolume", sell.get("size", 0)))

                buy_ts = parse_ts(buy.get("creationTimestamp") or buy.get("updateTimestamp", ""))
                sell_ts = parse_ts(sell.get("creationTimestamp") or sell.get("updateTimestamp", ""))

                if buy_ts and sell_ts and buy_ts < sell_ts:
                    # Long trade: buy then sell
                    match_size = min(buy_vol, sell_vol)
                    entry_price = float(buy.get("filledPrice", buy.get("price", 0)))
                    exit_price = float(sell.get("filledPrice", sell.get("price", 0)))

                    trades.append({
                        "entry_ts": buy_ts,
                        "exit_ts": sell_ts,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "direction": "LONG",
                        "size": int(match_size),
                        "symbol": symbol,
                        "entry_order": buy,
                        "exit_order": sell,
                    })

                    # Reduce volumes
                    if buy_vol == match_size:
                        buy_queue.pop(0)
                    else:
                        buy["fillVolume"] = buy_vol - match_size
                    if sell_vol == match_size:
                        sell_queue.pop(0)
                    else:
                        sell["fillVolume"] = sell_vol - match_size
                else:
                    # Short trade: sell then buy
                    match_size = min(sell_vol, buy_vol)
                    entry_price = float(sell.get("filledPrice", sell.get("price", 0)))
                    exit_price = float(buy.get("filledPrice", buy.get("price", 0)))

                    trades.append({
                        "entry_ts": sell_ts,
                        "exit_ts": buy_ts,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "direction": "SHORT",
                        "size": int(match_size),
                        "symbol": symbol,
                        "entry_order": sell,
                        "exit_order": buy,
                    })

                    if sell_vol == match_size:
                        sell_queue.pop(0)
                    else:
                        sell["fillVolume"] = sell_vol - match_size
                    if buy_vol == match_size:
                        buy_queue.pop(0)
                    else:
                        buy["fillVolume"] = buy_vol - match_size

        # Don't match partials — these are still open or unmatched

    # Sort by entry time
    trades.sort(key=lambda t: (t["entry_ts"], t["exit_ts"]))
    return trades


# ── trade_id generation ─────────────────────────────────────────────────

def make_trade_id(trade: Dict[str, Any]) -> str:
    """Generate a unique trade ID based on entry/exit timestamps and prices."""
    entry_str = trade["entry_ts"].strftime("%Y%m%d-%H%M%S")
    exit_str = trade["exit_ts"].strftime("%Y%m%d-%H%M%S")
    return f"{trade['direction']}-{trade['symbol']}-{entry_str}-{exit_str}"


# ── SL/TP detection ─────────────────────────────────────────────────────

def detect_sl_tp(trade: Dict[str, Any]) -> Tuple[bool, bool]:
    """
    Heuristic detection of stop-loss and take-profit hits.

    If the exit order has a customTag or related metadata suggesting SL/TP.
    Also checks: if MAE is very close to the actual loss, it's likely an SL hit.
    """
    # Check order tags
    exit_order = trade.get("exit_order", {})
    tag = exit_order.get("customTag", "").lower()

    sl_hit = "sl" in tag or "stop" in tag or "stoploss" in tag
    tp_hit = "tp" in tag or "target" in tag or "takeprofit" in tag

    # Heuristic: if the loss is > 0.8 * MAE, it's likely an SL hit
    # This will be refined after MAE/MFE computation
    return sl_hit, tp_hit


# ── main journal logic ───────────────────────────────────────────────────

def load_state() -> Dict[str, Any]:
    """Load the journal state (last-seen timestamp)."""
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_seen": None}


def save_state(state: Dict[str, Any]) -> None:
    """Save the journal state."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def load_existing_trade_ids() -> set:
    """Load all existing trade IDs from the journal to avoid duplicates."""
    ids = set()
    if JOURNAL_PATH.exists():
        for line in JOURNAL_PATH.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                tid = record.get("trade_id")
                if tid:
                    ids.add(tid)
            except json.JSONDecodeError:
                pass
    return ids


def run(dry_run: bool = False, force: bool = False) -> List[Dict[str, Any]]:
    """Main journaling logic. Returns list of logged trade records."""
    token = login()
    today = date.today()
    today_start = today.strftime("%Y-%m-%dT00:00:00Z")
    check_ts = now_iso()

    # Fetch fills and positions
    fills = fetch_fills(token, today_start, check_ts)
    positions = fetch_positions(token)

    if force:
        print(f"Force mode: processing all {len(fills)} fills from today")
    else:
        print(f"Fetched {len(fills)} fills, {len(positions)} open positions")

    # Load state
    state = load_state()
    last_seen = state.get("last_seen")
    existing_ids = load_existing_trade_ids()

    # Filter to new fills if not in force mode
    if not force and last_seen:
        fills = [o for o in fills
                 if (o.get("creationTimestamp") or o.get("updateTimestamp", "")) > last_seen]

    if not fills:
        print("No new fills to process.")
        save_state({"last_seen": check_ts if not last_seen else last_seen,
                     "last_check": check_ts})
        return []

    # Match trades
    raw_trades = match_trades(fills)

    if not raw_trades:
        print("No completed trades to log (unmatched fills may indicate open positions).")
        # Still update last_seen
        latest_ts = max(
            [o.get("creationTimestamp") or o.get("updateTimestamp", "")
             for o in fills] or [check_ts]
        )
        save_state({"last_seen": latest_ts, "last_check": check_ts})
        return []

    # Process each trade
    logged = []
    for trade in raw_trades:
        trade_id = make_trade_id(trade)

        # Skip if already logged (unless force mode)
        if trade_id in existing_ids and not force:
            continue

        entry_ts = trade["entry_ts"]
        exit_ts = trade["exit_ts"]
        direction = trade["direction"]
        entry_price = trade["entry_price"]
        exit_price = trade["exit_price"]
        size = trade["size"]
        symbol = trade.get("symbol", "NQ")

        # PnL
        if direction == "LONG":
            pnl_pts = exit_price - entry_price
        else:
            pnl_pts = entry_price - exit_price
        pnl_pts = round(pnl_pts, 4)
        pnl_dollars = round(pnl_pts * POINT_VALUE * size, 2)

        # Duration
        duration_minutes = round((exit_ts - entry_ts).total_seconds() / 60, 1)

        # Session
        session = classify_session(entry_ts)

        # Day of week
        day_of_week = entry_ts.strftime("%A")

        # Fetch bars for MAE/MFE
        print(f"  Fetching bars for {trade_id} ({symbol} {direction})...")
        bars = fetch_bars("NQ=F", entry_ts, exit_ts)
        mae_pts, mfe_pts, atr = compute_mae_mfe(bars, direction, entry_price) if bars else (0.0, 0.0, 0.0)

        if not bars:
            print(f"    Warning: No bars available for {trade_id}, MAE/MFE set to 0")

        # SL/TP detection
        sl_hit, tp_hit = detect_sl_tp(trade)
        # Heuristic refinement
        if not sl_hit and mae_pts > 0 and pnl_pts < 0:
            # If loss is within 1.2x of MAE, likely SL was hit
            if abs(pnl_pts) >= mae_pts * 0.7:
                sl_hit = True

        # Ratios
        mae_ratio = round(mae_pts / atr, 4) if atr > 0 else 0.0
        mfe_ratio = round(mfe_pts / atr, 4) if atr > 0 else 0.0

        record = {
            "trade_id": trade_id,
            "entry_ts": entry_ts.isoformat(),
            "exit_ts": exit_ts.isoformat(),
            "direction": direction,
            "size": size,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_pts": pnl_pts,
            "pnl_dollars": pnl_dollars,
            "duration_minutes": duration_minutes,
            "session": session,
            "day_of_week": day_of_week,
            "mae_pts": mae_pts,
            "mfe_pts": mfe_pts,
            "sl_hit": sl_hit,
            "tp_hit": tp_hit,
            "mae_ratio": mae_ratio,
            "mfe_ratio": mfe_ratio,
            "atr_at_entry": atr,
            "regime": "normal",
            "signal_source": "manual",
            "notes": "",
            "logged_at": now_iso(),
        }

        if dry_run:
            print(f"  [DRY RUN] Would log: {json.dumps(record, indent=2)}")
            logged.append(record)
        else:
            # Append to journal
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            with open(JOURNAL_PATH, "a") as f:
                f.write(json.dumps(record) + "\n")
            print(f"  Logged: {trade_id} ({direction}) PnL=${pnl_dollars:.2f} MAE={mae_pts} MFE={mfe_pts}")

            # Call failure_rag.py
            try:
                rag_script = str(HOME / "hedge" / "scripts" / "failure_rag.py")
                win_loss = "win" if pnl_dollars >= 0 else "loss"
                rag_args = [
                    sys.executable, rag_script, "log",
                    "--timestamp", entry_ts.isoformat(),
                    "--session", "NQ",
                    "--regime", "normal",
                    "--direction", direction,
                    "--entry-price", str(entry_price),
                    "--exit-price", str(exit_price),
                    "--pnl-pts", str(pnl_pts),
                    "--win-loss", win_loss,
                    "--atr-at-entry", str(atr),
                    "--day-of-week", day_of_week,
                    "--reason", f"trade_journal auto-log: {direction} {symbol}",
                ]
                subprocess.run(rag_args, capture_output=True, timeout=15)
            except Exception as e:
                print(f"    Warning: failure_rag call failed: {e}")

            logged.append(record)

    # Update state with latest fill timestamp
    all_fills = fills + [t["entry_order"] for t in raw_trades] + [t["exit_order"] for t in raw_trades]
    timestamps = []
    for o in all_fills:
        ts = o.get("creationTimestamp") or o.get("updateTimestamp", "")
        if ts:
            timestamps.append(ts)
    latest_ts = max(timestamps) if timestamps else check_ts

    save_state({"last_seen": latest_ts, "last_check": check_ts})

    if not dry_run:
        print(f"\nDone. Logged {len(logged)} trades. Journal: {JOURNAL_PATH}")
    else:
        print(f"\nDry run complete. Would have logged {len(logged)} trades.")

    return logged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trade Journal — log closed NQ futures trades with MAE/MFE"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be logged without writing")
    parser.add_argument("--force", action="store_true",
                        help="Re-process all fills from today (ignore last-seen)")

    args = parser.parse_args()
    run(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
