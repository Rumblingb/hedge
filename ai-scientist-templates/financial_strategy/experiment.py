import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

import sys


ROOT = Path("/Users/brain/hedge")
DEFAULT_DATA_BY_TIMEFRAME = {
    "1m": ROOT / "data/free/NQ-1m-3yr.csv",
    "1m-curr": ROOT / "data/free/NQ-1m-combined.csv",
    "3m": ROOT / "data/free/NQ-1m-3yr.csv",
    "5m": ROOT / "data/free/NQ-2022-2025-5m.csv",
    "45m": ROOT / "data/free/NQ-1m-3yr.csv",
    "15m": ROOT / "data/free/NQ-2022-2025-15m.csv",
    "30m": ROOT / "data/free/NQ-2022-2025-30m.csv",
    "60m": ROOT / "data/free/NQ-2022-2025-60m.csv",
    "1m-es": ROOT / "data/free/ES-1m-20yr.csv",
    "3m-es": ROOT / "data/free/ES-1m-20yr.csv",
    "5m-es": ROOT / "data/free/ES-2000-2019-5m.csv",
    "15m-es": ROOT / "data/free/ES-2000-2019-15m.csv",
    "30m-es": ROOT / "data/free/ES-2000-2019-30m.csv",
    "60m-es": ROOT / "data/free/ES-2000-2019-60m.csv",
    # ── Vast historical data additions (2026-06-07) ──
    # Long-term multi-regime (25yr ES+NQ combined)
    "15m-long": ROOT / "data/free/ALL-2MARKETS-NQ-ES-15m-longterm.csv",
    "60m-long": ROOT / "data/free/ALL-2MARKETS-NQ-ES-15m-longterm.csv",
    # ES 20yr individual
    "5m-es-20yr": ROOT / "data/free/ES-2000-2019-5m.csv",
    "15m-es-20yr": ROOT / "data/free/ES-2000-2019-15m.csv",
    "30m-es-20yr": ROOT / "data/free/ES-2000-2019-30m.csv",
    "60m-es-20yr": ROOT / "data/free/ES-2000-2019-60m.csv",
    # NQ 3yr
    "5m-nq-3yr": ROOT / "data/free/NQ-2022-2025-5m.csv",
    "15m-nq-3yr": ROOT / "data/free/NQ-2022-2025-15m.csv",
    "30m-nq-3yr": ROOT / "data/free/NQ-2022-2025-30m.csv",
    "60m-nq-3yr": ROOT / "data/free/NQ-2022-2025-60m.csv",
    # Gold — normalized data (2026-06-08)
    "15m-gc": ROOT / "data/free/GC-15m-60d.csv",
    "1h-gc": ROOT / "data/free/GC-1h-2000-2026.csv",
    "1d-gc": ROOT / "data/free/GC-daily-2000-2026.csv",
    # Crude Oil
    "15m-cl": ROOT / "data/free/CL-15m-60d.csv",
    "60m-cl": ROOT / "data/free/CL-15m-60d.csv",
    # EUR/USD (26yr of 1min)
    "1m-6e": ROOT / "data/free/6E-1m-5d.csv",
    "15m-6e": ROOT / "data/free/6E-15m-60d.csv",
    # 30yr cross-asset (50+ symbols)
    "daily-cross": ROOT / "data/free/30yr-cross-asset-market-data.csv",
    # 24-futures daily (pre-computed features)
    "daily-futures": ROOT / "data/free/futures-daily-with-features-24tickers.csv",
    # GC/CL combined daily for ratio mean-reversion
    "daily-gc-cl": ROOT / "data/free/GC-CL-daily-2000-2025.csv",
    # 30yr cross-asset daily (8 symbols)
    "daily-xasset": Path("/tmp/cross-asset-daily-long.csv"),
}
TIMEFRAME_MINUTES = {"1m": 1, "15m": 15, "30m": 30, "3m": 3, "5m": 5, "45m": 45, "60m": 60, "1h": 60, "1d": 1440, "daily-xasset": 1440}
DERIVED_TIMEFRAME_SOURCES = {"3m": "1m", "3m-es": "1m-es", "45m": "1m"}
DEFAULT_SESSIONS = ("ny_morning", "ny_afternoon")
DEFAULT_SKIP_SESSIONS = ("london", "premarket")
DEFAULT_AGREEMENT_TIMEFRAMES = ("15m", "30m", "60m")
KNOWN_BASELINES = [
    {
        "id": "orb-breakout-15m",
        "strategy": "orb",
        "timeframe": "15m",
        "params": {"range_window_bars": 8, "volume_threshold": 1.3, "entry_offset_ticks": 8},
        "source": "Rust param sweep claim; must be revalidated with this template before use.",
    },
    {
        "id": "orb-breakout-30m",
        "strategy": "orb",
        "timeframe": "30m",
        "params": {"range_window_bars": 8, "volume_threshold": 1.3, "entry_offset_ticks": 8},
        "source": "Rust param sweep claim; must be revalidated with this template before use.",
    },
    {
        "id": "wq-trend-mom-30m",
        "strategy": "wq_trend_mom",
        "timeframe": "30m",
        "params": {"short_sma": 20, "long_sma": 60, "volume_threshold": 1.3, "entry_offset_ticks": 8},
        "source": "Rust/TS local edge claim; revalidated here with session gates and walkforward before use.",
    },
    {
        "id": "wq-vol-regime-60m",
        "strategy": "wq_vol_regime",
        "timeframe": "60m",
        "params": {"short_lookback": 10, "long_lookback": 20, "short_threshold": 1.6, "long_threshold": 0.8, "entry_offset_ticks": 8},
        "source": "Rust/TS local edge claim; revalidated here with session gates and walkforward before use.",
    },
]


def parse_csv_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research-only alpha strategy experiment")
    parser.add_argument("--out_dir", type=str, default="run_0", help="Output directory")
    parser.add_argument("--data", type=str, default=None, help="Local OHLCV CSV only")
    parser.add_argument("--timeframe", choices=sorted(DEFAULT_DATA_BY_TIMEFRAME), default="5m")
    parser.add_argument("--strategy", choices=["orb", "wq_trend_mom", "wq_vol_regime", "known_baselines", "pji", "vwap", "ratio_mean_reversion"], default="orb")
    parser.add_argument("--symbol", type=str, default="NQ")
    parser.add_argument("--sessions", type=str, default=",".join(DEFAULT_SESSIONS))
    parser.add_argument("--skip_sessions", type=str, default=",".join(DEFAULT_SKIP_SESSIONS))
    parser.add_argument("--opening_minutes", type=int, default=30)
    parser.add_argument("--range_window_bars", type=int, default=None)
    parser.add_argument("--hold_bars", type=int, default=6)
    parser.add_argument("--cost_points", type=float, default=1.5)
    parser.add_argument("--volume_threshold", type=float, default=1.0)
    parser.add_argument("--entry_offset_ticks", type=int, default=0)
    parser.add_argument("--tick_size", type=float, default=0.25)
    parser.add_argument("--short_sma", type=int, default=20)
    parser.add_argument("--long_sma", type=int, default=60)
    parser.add_argument("--short_lookback", type=int, default=10)
    parser.add_argument("--long_lookback", type=int, default=20)
    parser.add_argument("--short_threshold", type=float, default=1.6)
    parser.add_argument("--long_threshold", type=float, default=0.8)
    parser.add_argument("--pji_lookback", type=int, default=8, help="PJI rolling window (default: 8)")
    parser.add_argument("--pji_threshold", type=float, default=0.005, help="PJI cross threshold (default: 0.005)")
    parser.add_argument("--vwap_threshold", type=float, default=1.5, help="VWAP deviation threshold in ATR units (default: 1.5)")
    parser.add_argument("--ratio_pair", type=str, default="GC/CL", help="Ratio pair for mean reversion (default: GC/CL)")
    parser.add_argument("--ratio_lookback", type=int, default=20, help="Lookback for ratio z-score (default: 20)")
    parser.add_argument("--ratio_entry_z", type=float, default=2.0, help="Z-score threshold for entry (default: 2.0)")
    parser.add_argument("--max_trades_per_session", type=int, default=3)
    parser.add_argument("--min_timeframe_agreement", type=int, default=2)
    parser.add_argument("--stop_loss_atr", type=float, default=0.0,
        help="ATR multiplier for stop loss. 0 = no stop. 1.0 = 1x ATR below entry for longs, above for shorts.")
    parser.add_argument("--take_profit_rr", type=float, default=0.0,
        help="Take profit as risk-reward ratio. 0 = no take profit. 1.0 = 1:1 RR, 2.0 = 1:2 RR, etc.")
    parser.add_argument("--rth_only", type=lambda x: x.lower() == "true", default=True,
        help="Only trade during RTH (True for NQ/ES, False for 24h instruments like GC, CL, 6E)")
    parser.add_argument("--force_session_close_exit", type=lambda x: x.lower() == "true", default=False,
        help="Force exit at 21:00 UTC (Topstep flat-by-3:10pm-CT rule). Truncates holds that would cross the session close.")
    parser.add_argument("--agreement_timeframes", type=str, default=",".join(DEFAULT_AGREEMENT_TIMEFRAMES))
    parser.add_argument("--agreement_sma_window", type=int, default=20)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--shuffle_splits", type=int, default=5)
    parser.add_argument("--min_train_trades", type=int, default=20)
    parser.add_argument("--min_oos_trades", type=int, default=30)
    return parser.parse_args()


def resolve_data_path(args: argparse.Namespace) -> Path:
    if args.data:
        return Path(args.data).resolve()
    return DEFAULT_DATA_BY_TIMEFRAME[args.timeframe].resolve()


def base_timeframe(timeframe: str) -> str:
    return DERIVED_TIMEFRAME_SOURCES.get(timeframe, timeframe)


def timeframe_key(timeframe: str) -> str:
    if '-' in timeframe:
        return timeframe.split('-')[0]
    return timeframe


def classify_session(hour_float_et: float) -> str:
    if 3 <= hour_float_et < 7:
        return "london"
    if 7 <= hour_float_et < 9.5:
        return "premarket"
    if 9.5 <= hour_float_et < 12:
        return "ny_morning"
    if 12 <= hour_float_et < 16:
        return "ny_afternoon"
    return "unknown"


def load_bars(path: Path, symbol: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing local research CSV: {path}")
    frame = pd.read_csv(path)
    required = {"ts", "open", "high", "low", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    frame = frame.copy()
    # Only filter by symbol if not __ALL__ (for multi-symbol strategies)
    if "symbol" in frame.columns and symbol != "__ALL__":
        frame = frame[frame["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["ts", "open", "high", "low", "close"]).sort_values("ts")
    frame["ts_et"] = frame["ts"].dt.tz_convert("America/New_York")
    hour_float = frame["ts_et"].dt.hour + frame["ts_et"].dt.minute / 60.0
    frame["hour_et"] = hour_float
    frame["session"] = hour_float.map(classify_session)
    frame["date"] = frame["ts_et"].dt.date
    frame["weekday"] = frame["ts_et"].dt.day_name()
    frame["minutes_from_session_open"] = (
        frame["ts_et"].dt.hour * 60 + frame["ts_et"].dt.minute - (9 * 60 + 30)
    )
    return frame


def resample_bars(frame: pd.DataFrame, timeframe: str, symbol: str) -> pd.DataFrame:
    minutes = timeframe_minutes(timeframe)
    if minutes == 1:
        return frame.copy()

    source = frame.copy().sort_values("ts")
    source["_bar_count"] = 1
    source = source.set_index("ts")
    aggregations: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in source.columns:
        aggregations["volume"] = "sum"
    if "symbol" in source.columns:
        aggregations["symbol"] = "last"
    aggregations["_bar_count"] = "sum"
    resampled = (
        source.resample(f"{minutes}min", label="right", closed="right")
        .agg(aggregations)
        .reset_index()
    )
    resampled = resampled[resampled["_bar_count"] >= minutes].drop(columns=["_bar_count"])
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])
    if "symbol" not in resampled.columns:
        resampled["symbol"] = symbol
    return load_bars_from_frame(resampled, symbol)


def load_bars_from_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    frame = frame.copy()
    if "symbol" in frame.columns:
        frame = frame[frame["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["ts", "open", "high", "low", "close"]).sort_values("ts")
    frame["ts_et"] = frame["ts"].dt.tz_convert("America/New_York")
    hour_float = frame["ts_et"].dt.hour + frame["ts_et"].dt.minute / 60.0
    frame["hour_et"] = hour_float
    frame["session"] = hour_float.map(classify_session)
    frame["date"] = frame["ts_et"].dt.date
    frame["weekday"] = frame["ts_et"].dt.day_name()
    frame["minutes_from_session_open"] = (
        frame["ts_et"].dt.hour * 60 + frame["ts_et"].dt.minute - (9 * 60 + 30)
    )
    return frame


def timeframe_minutes(timeframe: str) -> int:
    key = timeframe_key(timeframe)
    if key not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return TIMEFRAME_MINUTES[key]


def load_bars_for_timeframe(path: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    frame = load_bars(path, symbol)
    if timeframe in DERIVED_TIMEFRAME_SOURCES:
        return resample_bars(frame, timeframe, symbol)
    return frame


def agreement_timeframes_for_args(args: argparse.Namespace) -> list[str]:
    raw = getattr(args, "agreement_timeframes", ",".join(DEFAULT_AGREEMENT_TIMEFRAMES))
    return [
        timeframe
        for timeframe in parse_csv_list(raw)
        if timeframe in DEFAULT_DATA_BY_TIMEFRAME and timeframe != args.timeframe
    ]


def prepare_agreement_frame(frame: pd.DataFrame, timeframe: str, sma_window: int) -> pd.DataFrame:
    prepared = frame[["ts", "close"]].copy().sort_values("ts")
    prepared["sma"] = prepared["close"].rolling(sma_window, min_periods=sma_window).mean()
    prepared["prior_close"] = prepared["close"].shift(1)
    prepared["bar_end"] = prepared["ts"] + pd.to_timedelta(timeframe_minutes(timeframe), unit="m")
    prepared["trend_direction"] = 0
    prepared.loc[
        (prepared["close"] > prepared["sma"]) & (prepared["close"] > prepared["prior_close"]),
        "trend_direction",
    ] = 1
    prepared.loc[
        (prepared["close"] < prepared["sma"]) & (prepared["close"] < prepared["prior_close"]),
        "trend_direction",
    ] = -1
    return prepared.dropna(subset=["sma", "prior_close"])


def load_agreement_frames(args: argparse.Namespace, base_data_path: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    sma_window = int(getattr(args, "agreement_sma_window", 20))
    if sma_window < 2:
        return frames
    for timeframe in agreement_timeframes_for_args(args):
        path = DEFAULT_DATA_BY_TIMEFRAME[timeframe].resolve()
        if path == base_data_path.resolve():
            continue
        if not path.exists():
            continue
        try:
            frames[timeframe] = prepare_agreement_frame(load_bars_for_timeframe(path, args.symbol, timeframe), timeframe, sma_window)
        except Exception:
            continue
    return frames


def annotate_timeframe_agreement(
    trades: list[dict],
    agreement_frames: dict[str, pd.DataFrame],
) -> tuple[list[dict], dict[str, Any]]:
    if not agreement_frames:
        return trades, {
            "available": False,
            "frames": [],
            "mode": "not-available",
            "coverage": {},
        }

    annotated: list[dict] = []
    coverage = {timeframe: {"checked": 0, "matched": 0, "opposed": 0, "neutral": 0, "missing": 0} for timeframe in agreement_frames}
    for trade in trades:
        direction = 1 if trade.get("direction") == "long" else -1
        entry_ts = pd.Timestamp(trade["entryTs"])
        agreement = 1
        evidence: list[dict[str, Any]] = [{"timeframe": "base", "signal": trade.get("direction"), "counts": True}]
        for timeframe, frame in agreement_frames.items():
            eligible = frame[frame["bar_end"] <= entry_ts]
            coverage[timeframe]["checked"] += 1
            if eligible.empty:
                coverage[timeframe]["missing"] += 1
                evidence.append({"timeframe": timeframe, "signal": "missing-complete-bar", "counts": False})
                continue
            row = eligible.iloc[-1]
            signal = int(row["trend_direction"])
            if signal == direction:
                agreement += 1
                coverage[timeframe]["matched"] += 1
                label = "long" if signal > 0 else "short"
                counts = True
            elif signal == -direction:
                coverage[timeframe]["opposed"] += 1
                label = "short" if signal < 0 else "long"
                counts = False
            else:
                coverage[timeframe]["neutral"] += 1
                label = "neutral"
                counts = False
            evidence.append({
                "timeframe": timeframe,
                "signal": label,
                "counts": counts,
                "barEnd": str(row["bar_end"]),
                "close": float(row["close"]),
                "sma": float(row["sma"]),
            })
        updated = dict(trade)
        updated["timeframeAgreement"] = agreement
        updated["timeframeAgreementEvidence"] = evidence
        annotated.append(updated)

    return annotated, {
        "available": True,
        "frames": sorted(agreement_frames),
        "mode": "complete-bars-only-no-lookahead-close-vs-sma-plus-momentum",
        "coverage": coverage,
    }


def session_distribution(trades: list[dict]) -> dict:
    counts = Counter(str(trade.get("session", "unknown")) for trade in trades)
    return dict(sorted(counts.items()))


def date_range(trades: list[dict]) -> dict:
    if not trades:
        return {"start": None, "end": None}
    entries = sorted(str(trade["entryTs"]) for trade in trades)
    return {"start": entries[0], "end": entries[-1]}


def orb_trades(
    frame: pd.DataFrame,
    opening_minutes: int,
    hold_bars: int,
    cost_points: float,
    volume_threshold: float,
    entry_offset_ticks: int,
    tick_size: float,
    stop_loss_atr: float = 0.0,
    take_profit_rr: float = 0.0,
    rth_only: bool = True,
    weekday_size_multiplier: float = 1.0,
) -> list[dict]:
    trades: list[dict] = []
    entry_offset = entry_offset_ticks * tick_size
    # Precompute ATR for stop loss (14-period)
    atr: pd.Series | None = None
    if stop_loss_atr > 0:
        tr = pd.concat([
            abs(frame["high"] - frame["low"]),
            abs(frame["high"] - frame["close"].shift(1)),
            abs(frame["low"] - frame["close"].shift(1)),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14, min_periods=7).mean()
    for day, group in frame.groupby("date", sort=True):
        if rth_only:
            rth = group[(group["minutes_from_session_open"] >= 0) & (group["minutes_from_session_open"] < 390)].copy()
        else:
            rth = group.copy()
        opening = rth[rth["minutes_from_session_open"] < opening_minutes]
        after_open = rth[rth["minutes_from_session_open"] >= opening_minutes]
        if opening.empty or after_open.empty:
            continue
        high = float(opening["high"].max())
        low = float(opening["low"].min())
        width = high - low
        if width <= 0:
            continue

        volume_floor = 0.0
        if "volume" in rth.columns and volume_threshold > 1:
            # Compute volume floor from opening bars only (no forward-look into after_open)
            volume_mean_opening = rth.iloc[:len(opening)]["volume"].rolling(20, min_periods=5).mean()
            volume_floor = float(volume_mean_opening.median()) * volume_threshold if not volume_mean_opening.empty else 0.0
        long_break = after_open[after_open["high"] > high + entry_offset]
        short_break = after_open[after_open["low"] < low - entry_offset]
        if volume_floor > 0:
            long_break = long_break[long_break["volume"] >= volume_floor]
            short_break = short_break[short_break["volume"] >= volume_floor]
        long_break = long_break.head(1)
        short_break = short_break.head(1)
        if long_break.empty and short_break.empty:
            continue
        if short_break.empty or (not long_break.empty and long_break.index[0] < short_break.index[0]):
            entry_idx = long_break.index[0]
            direction = 1
            entry = high + entry_offset
        else:
            entry_idx = short_break.index[0]
            direction = -1
            entry = low - entry_offset
        entry_pos = rth.index.get_loc(entry_idx)
        # Determine exit with optional stop loss and take profit
        exit_pos = min(entry_pos + hold_bars, len(rth) - 1)
        exit_price = float(rth.iloc[exit_pos]["close"])
        exit_reason = "time"
        if stop_loss_atr > 0 and atr is not None:
            atr_val = float(atr.iloc[entry_pos]) if entry_pos < len(atr) else 0.0
            if atr_val > 0:
                stop_distance = atr_val * stop_loss_atr
                take_profit_distance = stop_distance * take_profit_rr if take_profit_rr > 0 else 0.0
                if direction > 0:  # long
                    stop_price = entry - stop_distance
                    take_profit_price = entry + take_profit_distance
                    for scan_pos in range(entry_pos + 1, exit_pos + 1):
                        low_bar = float(rth.iloc[scan_pos]["low"])
                        high_bar = float(rth.iloc[scan_pos]["high"])
                        if low_bar <= stop_price:
                            exit_pos = scan_pos
                            exit_price = stop_price
                            exit_reason = "stop"
                            break
                        if take_profit_price > 0 and high_bar >= take_profit_price:
                            exit_pos = scan_pos
                            exit_price = take_profit_price
                            exit_reason = "take_profit"
                            break
                else:  # short
                    stop_price = entry + stop_distance
                    take_profit_price = entry - take_profit_distance
                    for scan_pos in range(entry_pos + 1, exit_pos + 1):
                        low_bar = float(rth.iloc[scan_pos]["low"])
                        high_bar = float(rth.iloc[scan_pos]["high"])
                        if high_bar >= stop_price:
                            exit_pos = scan_pos
                            exit_price = stop_price
                            exit_reason = "stop"
                            break
                        if take_profit_price > 0 and low_bar <= take_profit_price:
                            exit_pos = scan_pos
                            exit_price = take_profit_price
                            exit_reason = "take_profit"
                            break
        gross = direction * (exit_price - entry)
        net = gross - cost_points
        entry_row = rth.loc[entry_idx]
        weekday = str(entry_row["weekday"])
        size_multiplier = weekday_size_multiplier
        trades.append({
            "date": str(day),
            "weekday": weekday,
            "session": str(entry_row["session"]),
            "direction": "long" if direction > 0 else "short",
            "entryTs": str(entry_row["ts"]),
            "exitTs": str(rth.iloc[exit_pos]["ts"]),
            "minutesFromOpen": int(entry_row["minutes_from_session_open"]),
            "openingRangePoints": width,
            "grossPoints": gross,
            "netPoints": net,
            "exitReason": exit_reason,
            "sizeMultiplier": size_multiplier,
            "timeframeAgreement": None,
        })
    return trades


def exit_trade_from_bar(
    frame: pd.DataFrame,
    entry_pos: int,
    hold_bars: int,
    direction: int,
    entry_price: float,
    cost_points: float,
    pattern: str,
    extra: dict | None = None,
    force_session_close_exit: bool = False,
) -> dict:
    exit_pos = min(entry_pos + hold_bars, len(frame) - 1)
    entry_row = frame.iloc[entry_pos]
    
    # Apply Topstep session-close rule: cap exit at 21:00 UTC if flag is set
    if force_session_close_exit and "ts" in frame.columns:
        entry_date = entry_row["ts"].date()
        # Find the last bar on entry date with hour < 21 UTC
        entry_frame = frame[(frame["ts"].dt.date == entry_date) & (frame["ts"].dt.hour < 21)]
        if not entry_frame.empty:
            last_valid_idx = entry_frame.index[-1]
            # Get position in current frame
            if last_valid_idx in frame.index:
                last_valid_pos = frame.index.get_loc(last_valid_idx)
                exit_pos = min(exit_pos, last_valid_pos)
    
    exit_row = frame.iloc[exit_pos]
    exit_price = float(exit_row["close"])
    gross = direction * (exit_price - entry_price)
    weekday = str(entry_row["weekday"])
    trade = {
        "date": str(entry_row["date"]),
        "weekday": weekday,
        "session": str(entry_row["session"]),
        "direction": "long" if direction > 0 else "short",
        "entryTs": str(entry_row["ts"]),
        "exitTs": str(exit_row["ts"]),
        "minutesFromOpen": int(entry_row["minutes_from_session_open"]),
        "grossPoints": gross,
        "netPoints": gross - cost_points,
        "sizeMultiplier": 1.0,
        "timeframeAgreement": None,
        "pattern": pattern,
    }
    if extra:
        trade.update(extra)
    return trade


def wq_trend_mom_trades(
    frame: pd.DataFrame,
    short_sma: int,
    long_sma: int,
    hold_bars: int,
    cost_points: float,
    volume_threshold: float,
    entry_offset_ticks: int,
    tick_size: float,
    rth_only: bool = True,
) -> list[dict]:
    if long_sma <= short_sma or short_sma <= 1:
        raise ValueError("wq_trend_mom requires 1 < short_sma < long_sma")
    if rth_only:
        rth = frame[(frame["minutes_from_session_open"] >= 0) & (frame["minutes_from_session_open"] < 390)].copy()
    else:
        rth = frame.copy()
    if rth.empty:
        return []
    rth["short_sma"] = rth["close"].rolling(short_sma, min_periods=short_sma).mean()
    rth["long_sma"] = rth["close"].rolling(long_sma, min_periods=long_sma).mean()
    if "volume" in rth.columns:
        rth["avg_volume"] = rth["volume"].rolling(20, min_periods=5).mean()
    else:
        rth["avg_volume"] = 0.0

    trades: list[dict] = []
    entry_offset = entry_offset_ticks * tick_size
    for pos in range(long_sma, len(rth)):
        row = rth.iloc[pos]
        prev = rth.iloc[pos - 1]
        if pd.isna(row["short_sma"]) or pd.isna(row["long_sma"]) or pd.isna(prev["short_sma"]) or pd.isna(prev["long_sma"]):
            continue
        if volume_threshold > 1 and row.get("avg_volume", 0.0) > 0 and row.get("volume", 0.0) < row["avg_volume"] * volume_threshold:
            continue
        crossed_up = prev["short_sma"] <= prev["long_sma"] and row["short_sma"] > row["long_sma"] and row["close"] > row["long_sma"]
        crossed_down = prev["short_sma"] >= prev["long_sma"] and row["short_sma"] < row["long_sma"] and row["close"] < row["long_sma"]
        if not crossed_up and not crossed_down:
            continue
        direction = 1 if crossed_up else -1
        entry = float(row["close"]) + direction * entry_offset
        trades.append(exit_trade_from_bar(
            rth,
            pos,
            hold_bars,
            direction,
            entry,
            cost_points,
            "wq-trend-mom-cross",
            {
                "shortSma": float(row["short_sma"]),
                "longSma": float(row["long_sma"]),
                "volumeRatio": float(row["volume"] / row["avg_volume"]) if row.get("avg_volume", 0.0) else None,
            },
        ))
    return trades


def bb_width(close: pd.Series, index: int, lookback: int, stddev_mult: float) -> tuple[float, float, float, float] | None:
    if index < lookback - 1:
        return None
    window = close.iloc[index - lookback + 1:index + 1]
    sma = float(window.mean())
    stddev = float(window.std(ddof=0))
    if sma <= 0 or stddev <= 0:
        return None
    upper = sma + stddev_mult * stddev
    lower = sma - stddev_mult * stddev
    return (upper - lower) / sma, upper, lower, sma


def wq_vol_regime_trades(
    frame: pd.DataFrame,
    short_lookback: int,
    long_lookback: int,
    short_threshold: float,
    long_threshold: float,
    hold_bars: int,
    cost_points: float,
    entry_offset_ticks: int,
    tick_size: float,
    rth_only: bool = True,
) -> list[dict]:
    if short_lookback <= 1 or long_lookback <= 1:
        raise ValueError("wq_vol_regime lookbacks must be greater than 1")
    if rth_only:
        rth = frame[(frame["minutes_from_session_open"] >= 0) & (frame["minutes_from_session_open"] < 390)].copy()
    else:
        rth = frame.copy()
    if rth.empty:
        return []
    closes = rth["close"].reset_index(drop=True)
    rth = rth.reset_index(drop=True)
    warmup = long_lookback + short_lookback
    trades: list[dict] = []
    entry_offset = entry_offset_ticks * tick_size

    for pos in range(warmup, len(rth)):
        current = bb_width(closes, pos, long_lookback, short_threshold)
        if current is None:
            continue
        current_width, upper, lower, _sma = current
        prior_widths = [
            value[0]
            for j in range(1, short_lookback + 1)
            if (value := bb_width(closes, pos - j, long_lookback, short_threshold)) is not None
        ]
        if not prior_widths:
            continue
        avg_width = float(np.mean(prior_widths))
        if avg_width <= 0 or current_width >= avg_width * long_threshold:
            continue
        row = rth.iloc[pos]
        if row["close"] > upper:
            direction = 1
        elif row["close"] < lower:
            direction = -1
        else:
            continue
        entry = float(row["close"]) + direction * entry_offset
        trades.append(exit_trade_from_bar(
            rth,
            pos,
            hold_bars,
            direction,
            entry,
            cost_points,
            "wq-vol-regime-squeeze-expansion",
            {
                "bbWidth": float(current_width),
                "avgBbWidth": avg_width,
                "widthRatio": float(current_width / avg_width),
            },
        ))
    return trades


def vwap_trades(
    frame: pd.DataFrame,
    vwap_threshold: float,
    hold_bars: int,
    cost_points: float,
    entry_offset_ticks: int,
    tick_size: float,
    rth_only: bool = True,
) -> list[dict]:
    """
    VWAP Mean-Reversion Strategy.
    Uses cumulative VWAP from session open.
    
    Signal:
      - Price > VWAP + threshold * ATR → SHORT (overextended above)
      - Price < VWAP - threshold * ATR → LONG (oversold below)
    """
    trades: list[dict] = []
    entry_offset = entry_offset_ticks * tick_size

    for day, group in frame.groupby("date", sort=True):
        if rth_only:
            rth = group[(group["minutes_from_session_open"] >= 0) & (group["minutes_from_session_open"] < 390)].copy()
        else:
            rth = group.copy()
        if rth.empty:
            continue

        # Compute cumulative VWAP
        rth["cum_pv"] = (rth["close"] * rth["volume"]).cumsum()
        rth["cum_vol"] = rth["volume"].cumsum()
        rth["vwap"] = rth["cum_pv"] / rth["cum_vol"].where(rth["cum_vol"] > 0, np.nan)
        
        # ATR for threshold scaling
        tr = pd.concat([
            abs(rth["high"] - rth["low"]),
            abs(rth["high"] - rth["close"].shift(1)),
            abs(rth["low"] - rth["close"].shift(1)),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14, min_periods=7).mean()

        for pos in range(1, len(rth)):  # Need at least 1 bar for VWAP
            row = rth.iloc[pos]
            vwap_val = float(row["vwap"])
            atr_val = float(atr.iloc[pos]) if pos < len(atr) and not np.isnan(atr.iloc[pos]) else 0.0
            if np.isnan(vwap_val) or atr_val <= 0:
                continue
            
            price = float(row["close"])
            deviation = (price - vwap_val) / atr_val
            
            direction = 0
            if deviation > vwap_threshold:
                direction = 1   # Price above VWAP → long (trend following)
            elif deviation < -vwap_threshold:
                direction = -1  # Price below VWAP → short
            
            if direction != 0:
                entry = price + direction * entry_offset
                trades.append(exit_trade_from_bar(
                    rth, pos, hold_bars, direction, entry, cost_points,
                    "vwap-reversion",
                    {"vwap": vwap_val, "deviation": deviation, "atr": atr_val},
                ))
    return trades


def ratio_mean_reversion_trades(
    frame: pd.DataFrame,
    ratio_pair: str,
    ratio_lookback: int,
    ratio_entry_z: float,
    hold_bars: int,
    cost_points: float,
    entry_offset_ticks: int,
    tick_size: float,
) -> list[dict]:
    """
    Ratio mean-reversion strategy.
    
    Computes the ratio of two symbols' prices (e.g., GC/CL).
    When ratio deviates > z-score threshold, bet on reversion.
    
    ratio_pair format: 'GC/CL' (first/second)
    
    Data format: single CSV with BOTH symbols, filtered by symbol column.
    The function processes the ratio bar-by-bar by aligning timestamps.
    """
    if ratio_lookback < 5:
        raise ValueError("ratio_lookback must be >= 5")
    
    symbols = ratio_pair.split('/')
    if len(symbols) != 2:
        raise ValueError(f"ratio_pair must be SYM1/SYM2, got {ratio_pair}")
    
    sym1, sym2 = symbols
    entry_offset = entry_offset_ticks * tick_size
    
    # Filter to each symbol separately
    s1 = frame[frame['symbol'].astype(str).str.upper() == sym1.upper()].copy()
    s2 = frame[frame['symbol'].astype(str).str.upper() == sym2.upper()].copy()
    
    if s1.empty or s2.empty:
        raise ValueError(f"Symbols {sym1} ({len(s1)} rows) or {sym2} ({len(s2)} rows) not found in data")
    
    # Align on DATE (not exact timestamp — daily data has different bar times)
    s1 = s1[['ts', 'close']].copy()
    s2 = s2[['ts', 'close']].copy()
    s1['date'] = s1['ts'].dt.date
    s2['date'] = s2['ts'].dt.date
    s1 = s1.rename(columns={'close': f'{sym1}_close', 'ts': f'{sym1}_ts'})
    s2 = s2.rename(columns={'close': f'{sym2}_close', 'ts': f'{sym2}_ts'})
    merged = pd.merge(s1, s2, on='date', how='inner').sort_values(f'{sym1}_ts')
    
    if merged.empty:
        raise ValueError(f"No overlapping timestamps found for {sym1} and {sym2}")
    
    # Compute ratio
    merged['ratio'] = merged[f'{sym1}_close'] / merged[f'{sym2}_close']
    merged['ratio_z'] = (merged['ratio'] - merged['ratio'].rolling(ratio_lookback, min_periods=ratio_lookback).mean()) / merged['ratio'].rolling(ratio_lookback, min_periods=ratio_lookback).std()
    
    # Generate trades  
    trades = []
    for idx, row in merged.iterrows():
        z = float(row['ratio_z'])
        if np.isnan(z):
            continue
        
        direction = 0
        if z > ratio_entry_z:
            direction = -1
        elif z < -ratio_entry_z:
            direction = 1
        
        if direction != 0:
            # Simple bar-based approach: assume hold_bars = trading days
            pos = merged.index.get_loc(idx)
            exit_pos = min(pos + hold_bars, len(merged) - 1)
            entry_price = float(row[f'{sym1}_close'])  # Use first symbol's price
            exit_price = float(merged.iloc[exit_pos][f'{sym1}_close'])
            gross = direction * (exit_price - entry_price)
            net = gross - cost_points
            
            trades.append({
                "date": str(row['date']),
                "weekday": str(pd.Timestamp(row['date']).day_name()),
                "session": "daily",
                "direction": "long" if direction > 0 else "short",
                "entryTs": str(row.get(f'{sym1}_ts', row['date'])),
                "exitTs": str(merged.iloc[exit_pos].get(f'{sym1}_ts', merged.iloc[exit_pos]['date'])),
                "minutesFromOpen": 0,
                "grossPoints": float(gross),
                "netPoints": float(net),
                "sizeMultiplier": 1.0,
                "timeframeAgreement": None,
                "pattern": f"ratio-reversion-{ratio_pair}",
                "ratio": float(row['ratio']),
                "zScore": float(z),
            })
    
    return trades


def pji_trades(
    frame: pd.DataFrame,
    pji_lookback: int,
    pji_threshold: float,
    hold_bars: int,
    cost_points: float,
    entry_offset_ticks: int,
    tick_size: float,
    rth_only: bool = True,
) -> list[dict]:
    """
    Price Jerk Indicator (PJI) strategy.
    Based on SSRN 6487618 — third derivative of price for reversal detection.

    Jerk[i] = P[i] - 3*P[i-1] + 3*P[i-2] - P[i-3]
    PJI = rolling mean of jerk over pji_lookback (smoothing)

    Signal rules:
      - PJI crosses below -threshold (from above): LONG  (decelerating decline → reversal up)
      - PJI crosses above +threshold (from below): SHORT (decelerating rise → reversal down)
    """
    if pji_lookback < 4:
        raise ValueError("pji requires lookback >= 4")
    if rth_only:
        rth = frame[(frame["minutes_from_session_open"] >= 0) & (frame["minutes_from_session_open"] < 390)].copy()
    else:
        rth = frame.copy()
    if rth.empty:
        return []

    closes = rth["close"].reset_index(drop=True)
    rth = rth.reset_index(drop=True)
    trades: list[dict] = []
    entry_offset = entry_offset_ticks * tick_size

    # Compute jerk and PJI
    jerk = closes.diff(3) - 3 * closes.diff(2) + 3 * closes.diff(1)
    jerk = jerk / (closes.shift(3).abs() + 1e-10)  # normalize by price level
    pji = jerk.rolling(pji_lookback, min_periods=pji_lookback).mean()

    warmup = pji_lookback + 4  # enough history for PJI
    prev_pji = None

    for pos in range(warmup, len(rth)):
        row = rth.iloc[pos]
        curr_pji = float(pji.iloc[pos])
        if np.isnan(curr_pji):
            continue
        if prev_pji is None:
            prev_pji = curr_pji
            continue

        direction = 0
        # Cross below -threshold (from above) = LONG reversal signal
        if prev_pji > -pji_threshold and curr_pji <= -pji_threshold:
            direction = 1
        # Cross above +threshold (from below) = SHORT reversal signal
        elif prev_pji < pji_threshold and curr_pji >= pji_threshold:
            direction = -1

        if direction != 0:
            entry = float(row["close"]) + direction * entry_offset
            trades.append(exit_trade_from_bar(
                rth, pos, hold_bars, direction, entry, cost_points,
                "pji-reversal",
                {"pji": float(curr_pji), "prevPji": float(prev_pji), "jerk": float(jerk.iloc[pos])},
            ))
        prev_pji = curr_pji

    return trades


def trade_session_gate(
    trades: list[dict],
    max_per_session: int = 3,
    skip_sessions: list[str] | None = None,
    allowed_sessions: list[str] | None = None,
    min_timeframe_agreement: int = 2,
    rth_only: bool = True,
) -> tuple[list[dict], dict]:
    skip = set(skip_sessions or DEFAULT_SKIP_SESSIONS)
    allowed = set(allowed_sessions or DEFAULT_SESSIONS)
    kept: list[dict] = []
    dropped = Counter()
    counts: dict[tuple[str, str], int] = defaultdict(int)
    agreement_values = [trade.get("timeframeAgreement") for trade in trades]
    agreement_available = any(value is not None for value in agreement_values)

    for trade in trades:
        session = str(trade.get("session", "unknown"))
        minutes_from_open = int(trade.get("minutesFromOpen", -999))
        key = (str(trade.get("date")), session)
        if session in skip:
            dropped[f"skip-session-{session}"] += 1
            continue
        if session not in allowed:
            dropped[f"not-allowed-session-{session}"] += 1
            continue
        if rth_only and minutes_from_open < 5:
            dropped["first-five-minutes"] += 1
            continue
        if rth_only and minutes_from_open >= 270:
            dropped["after-14-et"] += 1
            continue
        if counts[key] >= max_per_session:
            dropped["max-trades-per-session"] += 1
            continue
        if agreement_available and int(trade.get("timeframeAgreement") or 0) < min_timeframe_agreement:
            dropped["timeframe-agreement-below-min"] += 1
            continue
        counts[key] += 1
        kept.append(trade)

    return kept, {
        "max_per_session": max_per_session,
        "skip_sessions": sorted(skip),
        "allowed_sessions": sorted(allowed),
        "min_timeframe_agreement": min_timeframe_agreement,
        "timeframe_agreement_available": agreement_available,
        "dropped": dict(sorted(dropped.items())),
        "kept": len(kept),
    }


def metrics(trades: list[dict]) -> dict:
    if not trades:
        return {
            "trade_count": 0,
            "total_net_points": 0.0,
            "avg_net_points": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "profit_factor_lossless": False,
            "max_drawdown_points": 0.0,
            "session_distribution": {},
            "date_range": {"start": None, "end": None},
        }
    pnl = np.array([float(t["netPoints"]) for t in trades], dtype=float)
    equity = np.cumsum(pnl)
    peaks = np.maximum.accumulate(equity)
    drawdowns = peaks - equity
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    lossless_profit = gross_loss == 0 and gross_win > 0
    profit_factor = float(gross_win / gross_loss) if gross_loss else (None if lossless_profit else 0.0)
    return {
        "trade_count": int(len(pnl)),
        "total_net_points": float(pnl.sum()),
        "avg_net_points": float(pnl.mean()),
        "win_rate": float((pnl > 0).mean()),
        "profit_factor": profit_factor,
        "profit_factor_lossless": lossless_profit,
        "max_drawdown_points": float(drawdowns.max()) if len(drawdowns) else 0.0,
        "session_distribution": session_distribution(trades),
        "date_range": date_range(trades),
    }


def split_train_oos(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    split = int(len(trades) * 0.7)
    return trades[:split], trades[split:]


def rolling_walkforward(trades: list[dict], folds: int = 5) -> list[dict]:
    if folds <= 0 or len(trades) < folds + 1:
        return []
    results: list[dict] = []
    fold_size = len(trades) // (folds + 1)
    if fold_size <= 0:
        return []
    for i in range(1, folds + 1):
        split = i * fold_size
        train = trades[:split]
        oos = trades[split:split + fold_size]
        # Skip fold if OOS has fewer than 5 trades
        if len(oos) < 5:
            continue
        oos_metrics = metrics(oos)
        results.append({
            "fold": i,
            "train": metrics(train),
            "oos": oos_metrics,
            "oos_positive": oos_metrics["total_net_points"] > 0,
        })
    return results


def random_shuffle_robustness(trades: list[dict], runs: int = 5, train_ratio: float = 0.7) -> dict:
    if not trades or runs <= 0:
        return {"runs": [], "oos_total_net_points": {"min": None, "median": None, "max": None}}
    results = []
    for seed in range(runs):
        rng = np.random.default_rng(seed)
        indices = np.arange(len(trades))
        rng.shuffle(indices)
        split = int(len(indices) * train_ratio)
        oos = [trades[int(index)] for index in indices[split:]]
        oos_metrics = metrics(oos)
        results.append({
            "seed": seed,
            "oos_total_net_points": oos_metrics["total_net_points"],
            "oos_profit_factor": oos_metrics["profit_factor"],
            "oos_trade_count": oos_metrics["trade_count"],
            "oos_session_distribution": oos_metrics["session_distribution"],
        })
    values = [item["oos_total_net_points"] for item in results]
    return {
        "runs": results,
        "oos_total_net_points": {
            "min": float(min(values)),
            "median": float(median(values)),
            "max": float(max(values)),
        },
    }


def walkforward_blockers(folds: list[dict]) -> list[str]:
    if not folds:
        return ["walkforward-not-enough-trades"]
    positive = sum(1 for fold in folds if fold["oos_positive"])
    positive_share = positive / len(folds)
    aggregate_oos = [fold["oos"] for fold in folds]
    if positive_share <= 0.5:
        return ["walkforward-positive-fold-share-too-low"]
    if any(item["total_net_points"] <= 0 for item in aggregate_oos):
        return ["walkforward-has-negative-oos-fold"]
    if any(not item.get("profit_factor_lossless") and (item["profit_factor"] is None or item["profit_factor"] < 1.2) for item in aggregate_oos):
        return ["walkforward-oos-profit-factor-too-low"]
    return []


def opening_minutes_for_args(args: argparse.Namespace) -> int:
    opening_minutes = args.opening_minutes
    if args.range_window_bars is not None:
        opening_minutes = args.range_window_bars * timeframe_minutes(args.timeframe)
    return opening_minutes


def raw_trades_for_args(frame: pd.DataFrame, args: argparse.Namespace, opening_minutes: int, force_session_close_exit: bool = False) -> list[dict]:
    if args.strategy == "orb":
        return orb_trades(
            frame,
            opening_minutes,
            args.hold_bars,
            args.cost_points,
            args.volume_threshold,
            args.entry_offset_ticks,
            args.tick_size,
            stop_loss_atr=args.stop_loss_atr,
            take_profit_rr=args.take_profit_rr,
            rth_only=args.rth_only,
        )
    if args.strategy == "wq_trend_mom":
        return wq_trend_mom_trades(
            frame,
            args.short_sma,
            args.long_sma,
            args.hold_bars,
            args.cost_points,
            args.volume_threshold,
            args.entry_offset_ticks,
            args.tick_size,
            rth_only=args.rth_only,
        )
    if args.strategy == "wq_vol_regime":
        return wq_vol_regime_trades(
            frame,
            args.short_lookback,
            args.long_lookback,
            args.short_threshold,
            args.long_threshold,
            args.hold_bars,
            args.cost_points,
            args.entry_offset_ticks,
            args.tick_size,
            rth_only=args.rth_only,
        )
    if args.strategy == "pji":
        return pji_trades(
            frame,
            args.pji_lookback,
            args.pji_threshold,
            args.hold_bars,
            args.cost_points,
            args.entry_offset_ticks,
            args.tick_size,
            rth_only=args.rth_only,
        )
    if args.strategy == "vwap":
        return vwap_trades(
            frame,
            args.vwap_threshold,
            args.hold_bars,
            args.cost_points,
            args.entry_offset_ticks,
            args.tick_size,
            rth_only=args.rth_only,
        )
    if args.strategy == "ratio_mean_reversion":
        return ratio_mean_reversion_trades(
            frame,
            args.ratio_pair,
            args.ratio_lookback,
            args.ratio_entry_z,
            args.hold_bars,
            args.cost_points,
            args.entry_offset_ticks,
            args.tick_size,
        )
    raise ValueError(f"Unsupported strategy for direct run: {args.strategy}")


def strategy_params(args: argparse.Namespace, opening_minutes: int) -> dict:
    params = {
        "opening_minutes": opening_minutes,
        "range_window_bars": args.range_window_bars,
        "hold_bars": args.hold_bars,
        "cost_points": args.cost_points,
        "volume_threshold": args.volume_threshold,
        "entry_offset_ticks": args.entry_offset_ticks,
        "stop_loss_atr": args.stop_loss_atr,
        "take_profit_rr": args.take_profit_rr,
    }
    if args.strategy == "wq_trend_mom":
        params.update({"short_sma": args.short_sma, "long_sma": args.long_sma})
    if args.strategy == "wq_vol_regime":
        params.update({
            "short_lookback": args.short_lookback,
            "long_lookback": args.long_lookback,
            "short_threshold": args.short_threshold,
            "long_threshold": args.long_threshold,
        })
    if args.strategy == "pji":
        params.update({
            "pji_lookback": args.pji_lookback,
            "pji_threshold": args.pji_threshold,
        })
    if args.strategy == "vwap":
        params.update({"vwap_threshold": args.vwap_threshold})
    if args.strategy == "ratio_mean_reversion":
        params.update({
            "ratio_pair": args.ratio_pair,
            "ratio_lookback": args.ratio_lookback,
            "ratio_entry_z": args.ratio_entry_z,
        })
    return params


def evaluate_run(args: argparse.Namespace, data_path: Path, sessions: list[str], skip_sessions: list[str]) -> dict:
    opening_minutes = opening_minutes_for_args(args)
    frame = load_bars_for_timeframe(data_path, args.symbol, args.timeframe)
    raw_trades = raw_trades_for_args(frame, args, opening_minutes)
    raw_trades, agreement_report = annotate_timeframe_agreement(
        raw_trades,
        load_agreement_frames(args, data_path),
    )
    trades, gate_report = trade_session_gate(
        raw_trades,
        max_per_session=args.max_trades_per_session,
        skip_sessions=skip_sessions,
        allowed_sessions=sessions,
        min_timeframe_agreement=args.min_timeframe_agreement,
        rth_only=args.rth_only,
    )
    train, oos = split_train_oos(trades)
    train_metrics = metrics(train)
    oos_metrics = metrics(oos)
    walkforward_folds = rolling_walkforward(trades, args.folds)
    shuffle_report = random_shuffle_robustness(trades, args.shuffle_splits)

    metric_blockers: list[str] = []
    if train_metrics["trade_count"] < args.min_train_trades:
        metric_blockers.append("too-few-train-trades")
    if oos_metrics["trade_count"] < args.min_oos_trades:
        metric_blockers.append("too-few-oos-trades")
    if oos_metrics["total_net_points"] <= 0:
        metric_blockers.append("oos-net-not-positive-after-costs")
    if not oos_metrics.get("profit_factor_lossless") and (
        oos_metrics["profit_factor"] is None or oos_metrics["profit_factor"] < 1.2
    ):
        metric_blockers.append("oos-profit-factor-too-low")
    metric_blockers.extend(walkforward_blockers(walkforward_folds))
    if raw_trades and not gate_report["timeframe_agreement_available"] and args.min_timeframe_agreement > 1:
        metric_blockers.append("timeframe-agreement-not-available-in-single-csv-template")

    research_candidate = not metric_blockers
    promotion_blockers = [
        "template-output-is-not-paper-demo-or-execution-promotion",
        *metric_blockers,
    ]

    return {
        "means": {
            "train_total_net_points": train_metrics["total_net_points"],
            "oos_total_net_points": oos_metrics["total_net_points"],
            "oos_profit_factor": oos_metrics["profit_factor"],
            "oos_win_rate": oos_metrics["win_rate"],
            "oos_trade_count": oos_metrics["trade_count"],
            "walkforward_positive_fold_share": (
                sum(1 for fold in walkforward_folds if fold["oos_positive"]) / len(walkforward_folds)
                if walkforward_folds else 0.0
            ),
            "ready_for_paper": False,
            "ready_for_execution": False,
        },
        "experiment": {
            "data": str(data_path),
            "timeframe": args.timeframe,
            "strategy": args.strategy,
            "symbol": args.symbol,
            "sessions": sessions,
            "skip_sessions": skip_sessions,
            "params": strategy_params(args, opening_minutes),
            "max_trades_per_session": args.max_trades_per_session,
            "known_baselines": KNOWN_BASELINES,
            "raw_trade_count": len(raw_trades),
            "timeframe_agreement": agreement_report,
            "gate": gate_report,
            "train": train_metrics,
            "oos": oos_metrics,
            "walkforward_folds": walkforward_folds,
            "random_shuffle_robustness": shuffle_report,
            "metric_blockers": metric_blockers,
            "research_candidate": research_candidate,
            "promotion_blockers": promotion_blockers,
            "decision": "research-only-template-candidate" if research_candidate else "research-only-template-blocked",
            "oos_suspicion_checks": {
                "train_oos_date_ranges": {"train": train_metrics["date_range"], "oos": oos_metrics["date_range"]},
                "train_oos_session_distribution": {
                    "train": train_metrics["session_distribution"],
                    "oos": oos_metrics["session_distribution"],
                },
                "oos_beats_train": oos_metrics["total_net_points"] > train_metrics["total_net_points"],
            },
        },
        "trades": trades[-20:],
    }


def baseline_args(base_args: argparse.Namespace, baseline: dict) -> argparse.Namespace:
    values = vars(base_args).copy()
    values.update({
        "data": None,
        "timeframe": baseline["timeframe"],
        "strategy": baseline["strategy"],
        "range_window_bars": None,
        "volume_threshold": base_args.volume_threshold,
        "entry_offset_ticks": base_args.entry_offset_ticks,
        "short_sma": base_args.short_sma,
        "long_sma": base_args.long_sma,
        "short_lookback": base_args.short_lookback,
        "long_lookback": base_args.long_lookback,
        "short_threshold": base_args.short_threshold,
        "long_threshold": base_args.long_threshold,
        "agreement_timeframes": getattr(base_args, "agreement_timeframes", ",".join(DEFAULT_AGREEMENT_TIMEFRAMES)),
        "agreement_sma_window": getattr(base_args, "agreement_sma_window", 20),
    })
    values.update(baseline["params"])
    return argparse.Namespace(**values)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = parse_csv_list(args.sessions)
    skip_sessions = parse_csv_list(args.skip_sessions)
    safety = {
        "research_only": True,
        "writes_orders": False,
        "touches_broker": False,
        "moves_funds": False,
        "operator_approval_required_before_execution": True,
    }

    if args.strategy == "known_baselines":
        baseline_results = []
        for baseline in KNOWN_BASELINES:
            run_args = baseline_args(args, baseline)
            result = evaluate_run(run_args, resolve_data_path(run_args), sessions, skip_sessions)
            result["baseline"] = baseline
            baseline_results.append(result)
        final_info = {
            "AlphaStrategyTemplate": {
                "means": {
                    "baseline_count": len(baseline_results),
                    "candidate_count": sum(1 for item in baseline_results if item["experiment"]["research_candidate"]),
                    "ready_for_paper": False,
                    "ready_for_execution": False,
                },
                "safety": safety,
                "experiment": {
                    "strategy": "known_baselines",
                    "symbol": args.symbol,
                    "sessions": sessions,
                    "skip_sessions": skip_sessions,
                    "known_baselines": KNOWN_BASELINES,
                    "baseline_results": baseline_results,
                    "decision": "research-only-baseline-review",
                    "promotion_blockers": ["template-output-is-not-paper-demo-or-execution-promotion"],
                },
            }
        }
    else:
        data_path = resolve_data_path(args)
        result = evaluate_run(args, data_path, sessions, skip_sessions)
        final_info = {
            "AlphaStrategyTemplate": {
                "means": result["means"],
                "safety": safety,
                "experiment": result["experiment"],
                "trades": result["trades"],
            }
        }

    final_info["argv"] = sys.argv
    final_info["args"] = vars(args)
    with (out_dir / "final_info.json").open("w") as f:
        json.dump(final_info, f, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
