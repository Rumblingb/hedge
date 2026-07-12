#!/usr/bin/env python3
"""Build offline BTC Polymarket up/down feature bars from BrockMisner HF dataset.

Outputs one parquet with market/probability/orderbook/tick/spot features for research.
Keep this as an offline feature builder; it does not place trades.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

DEFAULT_ROOT = Path("/Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25")


def q(path: Path) -> str:
    return str(path).replace("'", "''")


def bucket_seconds(timeframe: str) -> int:
    return {
        "5-minute": 300,
        "15-minute": 900,
        "1-hour": 3600,
        "4-hour": 14400,
    }[timeframe]


def build(args: argparse.Namespace) -> None:
    root = Path(args.root).expanduser()
    data = root / "hf/BrockMisner__polymarket-btc-updown/data"
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    tf = args.timeframe
    bucket = bucket_seconds(tf)
    markets = data / "markets.parquet"
    prices = data / f"prices/crypto=BTC/timeframe={tf}/part-0.parquet"
    orderbook = data / f"orderbook/crypto=BTC/timeframe={tf}/part-0.parquet"
    ticks = data / f"ticks/crypto=BTC/timeframe={tf}/part-0.parquet"
    spot = data / "spot_prices/part-0.parquet"

    for p in [markets, prices, orderbook, ticks, spot]:
        if not p.exists():
            raise FileNotFoundError(p)

    limit_clause = f"LIMIT {int(args.market_limit)}" if args.market_limit else ""
    resolution_clause = "" if args.include_unresolved else "AND resolution IN (0, 1)"
    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA threads={int(args.threads)}")
    con.execute("PRAGMA preserve_insertion_order=false")

    sql = f"""
    CREATE OR REPLACE TEMP TABLE selected_markets AS
    SELECT market_id, question, volume, resolution, start_ts, end_ts,
           up_token_id, down_token_id,
           TRY_CAST(regexp_extract(question, '\\$([0-9][0-9,]*(?:\\.[0-9]+)?)', 1) AS DOUBLE) AS parsed_strike
    FROM read_parquet('{q(markets)}')
    WHERE crypto = 'BTC' AND timeframe = '{tf}' {resolution_clause}
    ORDER BY volume DESC NULLS LAST
    {limit_clause};

    CREATE OR REPLACE TEMP TABLE price_bars AS
    SELECT p.market_id,
           p.timestamp AS ts,
           p.up_price,
           p.down_price,
           p.up_price - lag(p.up_price) OVER (PARTITION BY p.market_id ORDER BY p.timestamp) AS up_price_delta,
           p.down_price - lag(p.down_price) OVER (PARTITION BY p.market_id ORDER BY p.timestamp) AS down_price_delta
    FROM read_parquet('{q(prices)}') p
    INNER JOIN selected_markets m USING (market_id);

    CREATE OR REPLACE TEMP TABLE ob_features AS
    SELECT o.market_id,
           CAST(floor((o.ts_ms / 1000) / {bucket}) * {bucket} AS BIGINT) AS ts,
           avg(o.best_ask - o.best_bid) AS avg_spread,
           avg(CASE WHEN lower(o.outcome) LIKE 'up%' THEN (o.best_bid + o.best_ask) / 2 END) AS up_ob_mid,
           avg(CASE WHEN lower(o.outcome) LIKE 'down%' THEN (o.best_bid + o.best_ask) / 2 END) AS down_ob_mid,
           sum(CASE WHEN lower(o.outcome) LIKE 'up%' THEN coalesce(o.best_bid_size,0) ELSE 0 END) AS up_bid_depth,
           sum(CASE WHEN lower(o.outcome) LIKE 'up%' THEN coalesce(o.best_ask_size,0) ELSE 0 END) AS up_ask_depth,
           sum(CASE WHEN lower(o.outcome) LIKE 'down%' THEN coalesce(o.best_bid_size,0) ELSE 0 END) AS down_bid_depth,
           sum(CASE WHEN lower(o.outcome) LIKE 'down%' THEN coalesce(o.best_ask_size,0) ELSE 0 END) AS down_ask_depth,
           count(*) AS ob_rows
    FROM read_parquet('{q(orderbook)}') o
    INNER JOIN selected_markets m USING (market_id)
    GROUP BY 1,2;

    CREATE OR REPLACE TEMP TABLE tick_features AS
    SELECT t.market_id,
           CAST(floor((t.timestamp_ms / 1000) / {bucket}) * {bucket} AS BIGINT) AS ts,
           count(*) AS trade_count,
           sum(coalesce(t.size_usdc,0)) AS trade_usdc,
           sum(CASE WHEN lower(t.side)='buy' THEN coalesce(t.size_usdc,0) ELSE 0 END) AS buy_usdc,
           sum(CASE WHEN lower(t.side)='sell' THEN coalesce(t.size_usdc,0) ELSE 0 END) AS sell_usdc,
           avg(t.price) AS avg_trade_price,
           avg(t.spot_price_usdt) AS avg_tick_spot
    FROM read_parquet('{q(ticks)}') t
    INNER JOIN selected_markets m USING (market_id)
    GROUP BY 1,2;

    CREATE OR REPLACE TEMP TABLE spot_features AS
    SELECT CAST(floor((ts_ms / 1000) / {bucket}) * {bucket} AS BIGINT) AS ts,
           avg(price) AS spot_price,
           avg(price) - lag(avg(price)) OVER (ORDER BY CAST(floor((ts_ms / 1000) / {bucket}) * {bucket} AS BIGINT)) AS spot_delta,
           (avg(price) / nullif(lag(avg(price)) OVER (ORDER BY CAST(floor((ts_ms / 1000) / {bucket}) * {bucket} AS BIGINT)),0) - 1.0) AS spot_ret_1bar
    FROM read_parquet('{q(spot)}')
    WHERE upper(symbol) IN ('BTC/USDT', 'BTCUSDT', 'BTC/USD') OR upper(symbol) LIKE '%BTC%'
    GROUP BY 1;

    CREATE OR REPLACE TEMP TABLE spot_features_rolling AS
    SELECT *,
           avg(spot_ret_1bar) OVER (ORDER BY ts ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS spot_mom_3bar,
           avg(spot_ret_1bar) OVER (ORDER BY ts ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING) AS spot_mom_12bar,
           stddev_samp(spot_ret_1bar) OVER (ORDER BY ts ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING) AS spot_vol_12bar,
           stddev_samp(spot_ret_1bar) OVER (ORDER BY ts ROWS BETWEEN 48 PRECEDING AND 1 PRECEDING) AS spot_vol_48bar
    FROM spot_features;

    COPY (
      SELECT p.*, m.question, m.volume, m.resolution, m.start_ts, m.end_ts,
             CASE WHEN m.resolution = 1 THEN 1 ELSE 0 END AS target_up_win,
             CASE WHEN m.resolution = 0 THEN 1 ELSE 0 END AS target_down_win,
             m.parsed_strike,
             (s.spot_price - m.parsed_strike) AS spot_distance_to_strike,
             (s.spot_price / nullif(m.parsed_strike,0) - 1.0) AS spot_distance_to_strike_pct,
             ({bucket} * floor((m.end_ts - p.ts) / {bucket})) AS seconds_to_expiry_bucket,
             ob.avg_spread,
             ob.up_ob_mid,
             ob.down_ob_mid,
             ob.up_bid_depth,
             ob.up_ask_depth,
             ob.down_bid_depth,
             ob.down_ask_depth,
             (ob.up_bid_depth - ob.up_ask_depth) / nullif(ob.up_bid_depth + ob.up_ask_depth, 0) AS up_depth_imbalance,
             (ob.down_bid_depth - ob.down_ask_depth) / nullif(ob.down_bid_depth + ob.down_ask_depth, 0) AS down_depth_imbalance,
             ob.ob_rows,
             tk.trade_count,
             tk.trade_usdc,
             tk.buy_usdc,
             tk.sell_usdc,
             (tk.buy_usdc - tk.sell_usdc) / nullif(tk.buy_usdc + tk.sell_usdc, 0) AS trade_flow_imbalance,
             tk.avg_trade_price,
             s.spot_price,
             s.spot_delta,
             s.spot_ret_1bar,
             s.spot_mom_3bar,
             s.spot_mom_12bar,
             s.spot_vol_12bar,
             s.spot_vol_48bar
      FROM price_bars p
      INNER JOIN selected_markets m USING (market_id)
      LEFT JOIN ob_features ob USING (market_id, ts)
      LEFT JOIN tick_features tk USING (market_id, ts)
      LEFT JOIN spot_features_rolling s USING (ts)
      ORDER BY p.market_id, p.ts
    ) TO '{q(out)}' (FORMAT PARQUET);
    """
    con.execute(sql)
    row = con.execute(f"SELECT count(*) FROM read_parquet('{q(out)}')").fetchone()
    n = int(row[0]) if row is not None else 0
    print(f"wrote {n:,} rows -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--timeframe", default="15-minute", choices=["5-minute", "15-minute", "1-hour", "4-hour"])
    ap.add_argument("--market-limit", type=int, default=25, help="Top markets by volume; set 0 for all markets.")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--include-unresolved", action="store_true", help="Include markets with resolution=-1. Default excludes unresolved markets for label-ready research.")
    ap.add_argument("--output", default="/Volumes/Seagate Expansion Drive/hedge-data/features/polymarket_btc_updown/btc_15m_features.parquet")
    args = ap.parse_args()
    if args.market_limit == 0:
        args.market_limit = None
    build(args)


if __name__ == "__main__":
    main()
