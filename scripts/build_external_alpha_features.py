#!/usr/bin/env python3
"""Build offline feature artifacts from externally supplied alpha datasets.

This is research/offline only. It writes parquet feature tables under the external
hedge-data volume and never places trades.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

DEFAULT_ROOT = Path("/Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25")
DEFAULT_FEATURE_ROOT = Path("/Volumes/Seagate Expansion Drive/hedge-data/features")


def q(path: Path) -> str:
    return str(path).replace("'", "''")


def connect(threads: int) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA threads={int(threads)}")
    con.execute("PRAGMA preserve_insertion_order=false")
    return con


def normalize_nq(args: argparse.Namespace) -> None:
    """Convert Kaggle NQ CSV bars to canonical parquet tables."""
    root = Path(args.root).expanduser()
    src = root / "kaggle/youneseloiarm__nasdaq-cme-future-nq"
    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        raise FileNotFoundError(src)

    con = connect(args.threads)
    written = []
    for csv in sorted(src.glob("NQ_in_*.csv")):
        timeframe = csv.stem.replace("NQ_in_", "")
        out = out_dir / f"nq_{timeframe}.parquet"
        con.execute(
            f"""
            COPY (
              SELECT
                CAST(datetime AS TIMESTAMP) AS ts,
                'NQ' AS symbol,
                '{timeframe}' AS source_timeframe,
                CAST(open AS DOUBLE) AS open,
                CAST(high AS DOUBLE) AS high,
                CAST(low AS DOUBLE) AS low,
                CAST(close AS DOUBLE) AS close,
                CAST(volume AS DOUBLE) AS volume,
                close - lag(close) OVER (ORDER BY CAST(datetime AS TIMESTAMP)) AS close_delta,
                (close / nullif(lag(close) OVER (ORDER BY CAST(datetime AS TIMESTAMP)),0) - 1.0) AS close_ret,
                high - low AS range_points,
                abs(close - open) AS body_points
              FROM read_csv_auto('{q(csv)}')
              ORDER BY ts
            ) TO '{q(out)}' (FORMAT PARQUET);
            """
        )
        row_count = con.execute(f"SELECT count(*) FROM read_parquet('{q(out)}')").fetchone()
        minmax = con.execute(f"SELECT min(ts), max(ts) FROM read_parquet('{q(out)}')").fetchone()
        if row_count is None or minmax is None:
            raise RuntimeError(f"Failed to verify output {out}")
        n = int(row_count[0])
        written.append((out, n, minmax[0], minmax[1]))

    manifest = out_dir / "manifest.txt"
    manifest.write_text("\n".join(f"{p.name}\trows={n}\tmin_ts={a}\tmax_ts={b}" for p, n, a, b in written) + "\n")
    for p, n, a, b in written:
        print(f"wrote {n:,} rows {a} -> {b}: {p}")
    print(f"manifest: {manifest}")


def equities_breadth(args: argparse.Namespace) -> None:
    """Aggregate selected fabhaus 5m equity JSONL months into market-breadth bars.

    The full fabhaus corpus is ~478GB, so this command is designed to work month
    by month and append/partition later. It creates cross-sectional breadth and
    mega-cap lead/lag features that can be joined to NQ/SPY bars.
    """
    root = Path(args.root).expanduser()
    src = root / f"hf/fabhaus__equities_5m_stockprices/{args.month}.jsonl"
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        raise FileNotFoundError(src)
    con = connect(args.threads)
    mega = "'AAPL','MSFT','NVDA','AMZN','META','GOOGL','GOOG','TSLA','AVGO','AMD','NFLX','COST'"
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE raw AS
        SELECT
          CAST(datetime AS TIMESTAMP) AS ts,
          upper(symbol) AS symbol,
          CAST(open AS DOUBLE) AS open,
          CAST(high AS DOUBLE) AS high,
          CAST(low AS DOUBLE) AS low,
          CAST(close AS DOUBLE) AS close,
          CAST(volume AS DOUBLE) AS volume,
          CAST(vwap AS DOUBLE) AS vwap,
          CAST(ti_rsi_14 AS DOUBLE) AS rsi_14,
          CAST(ti_atr_14 AS DOUBLE) AS atr_14,
          CAST(cv_valuation_gap_pct AS DOUBLE) AS valuation_gap_pct,
          CAST(cf_revenue_growth_yoy AS DOUBLE) AS revenue_growth_yoy,
          CAST(cf_net_margin AS DOUBLE) AS net_margin
        FROM read_json_auto('{q(src)}', format='newline_delimited', maximum_object_size=16777216);

        CREATE OR REPLACE TEMP TABLE bars AS
        SELECT *,
          close / nullif(lag(close) OVER (PARTITION BY symbol ORDER BY ts), 0) - 1.0 AS ret_5m,
          volume / nullif(avg(volume) OVER (PARTITION BY symbol ORDER BY ts ROWS BETWEEN 78 PRECEDING AND 1 PRECEDING), 0) AS volume_rel_1d
        FROM raw;

        COPY (
          SELECT
            ts,
            count(*) AS symbol_count,
            avg(ret_5m) AS avg_ret_5m,
            median(ret_5m) AS median_ret_5m,
            sum(CASE WHEN ret_5m > 0 THEN 1 ELSE 0 END)::DOUBLE / nullif(count(ret_5m),0) AS advancer_ratio,
            sum(CASE WHEN ret_5m < 0 THEN 1 ELSE 0 END)::DOUBLE / nullif(count(ret_5m),0) AS decliner_ratio,
            avg(CASE WHEN volume_rel_1d >= 2 THEN 1.0 ELSE 0.0 END) AS unusual_volume_ratio,
            avg(CASE WHEN rsi_14 >= 70 THEN 1.0 ELSE 0.0 END) AS overbought_ratio,
            avg(CASE WHEN rsi_14 <= 30 THEN 1.0 ELSE 0.0 END) AS oversold_ratio,
            avg(valuation_gap_pct) AS avg_valuation_gap_pct,
            avg(revenue_growth_yoy) AS avg_revenue_growth_yoy,
            avg(net_margin) AS avg_net_margin,
            avg(CASE WHEN symbol IN ({mega}) THEN ret_5m END) AS mega_avg_ret_5m,
            sum(CASE WHEN symbol IN ({mega}) THEN volume ELSE 0 END) AS mega_volume,
            avg(CASE WHEN symbol IN ({mega}) THEN volume_rel_1d END) AS mega_volume_rel_1d,
            avg(CASE WHEN symbol IN ({mega}) THEN rsi_14 END) AS mega_avg_rsi_14,
            avg(CASE WHEN symbol IN ({mega}) THEN valuation_gap_pct END) AS mega_avg_valuation_gap_pct
          FROM bars
          GROUP BY ts
          ORDER BY ts
        ) TO '{q(out)}' (FORMAT PARQUET);
        """
    )
    row_count = con.execute(f"SELECT count(*) FROM read_parquet('{q(out)}')").fetchone()
    minmax = con.execute(f"SELECT min(ts), max(ts) FROM read_parquet('{q(out)}')").fetchone()
    if row_count is None or minmax is None:
        raise RuntimeError(f"Failed to verify output {out}")
    n = int(row_count[0])
    print(f"wrote {n:,} breadth bars {minmax[0]} -> {minmax[1]}: {out}")



def sp500_options_daily(args: argparse.Namespace) -> None:
    """Aggregate Kaggle S&P 500 daily options into regime/risk features."""
    root = Path(args.root).expanduser()
    src = root / "kaggle/shubhamcodez__s-and-p-500-daily-options-data-2010-2023/combined_options_data.csv"
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        raise FileNotFoundError(src)
    con = connect(args.threads)

    # Dataset has volumes/greeks/IV but no explicit open interest. Use volume walls,
    # ATM IV and 25-delta skew proxies as daily risk-regime inputs.
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE opt AS
        SELECT * FROM read_csv_auto('{q(src)}', sample_size=200000);

        CREATE OR REPLACE TEMP TABLE base AS
        SELECT
          QUOTE_DATE::DATE AS quote_date,
          CAST(UNDERLYING_LAST AS DOUBLE) AS underlying_last,
          CAST(EXPIRE_DATE AS DATE) AS expire_date,
          CAST(DTE AS DOUBLE) AS dte,
          CAST(STRIKE AS DOUBLE) AS strike,
          CAST(STRIKE_DISTANCE AS DOUBLE) AS strike_distance,
          CAST(C_VOLUME AS DOUBLE) AS c_volume,
          CAST(P_VOLUME AS DOUBLE) AS p_volume,
          CAST(C_IV AS DOUBLE) AS c_iv,
          CAST(P_IV AS DOUBLE) AS p_iv,
          CAST(C_DELTA AS DOUBLE) AS c_delta,
          CAST(P_DELTA AS DOUBLE) AS p_delta,
          CAST(C_GAMMA AS DOUBLE) AS c_gamma,
          CAST(P_GAMMA AS DOUBLE) AS p_gamma
        FROM opt;

        CREATE OR REPLACE TEMP TABLE daily AS
        SELECT
          quote_date,
          avg(underlying_last) AS underlying_last,
          count(*) AS option_rows,
          sum(coalesce(c_volume,0)) AS call_volume,
          sum(coalesce(p_volume,0)) AS put_volume,
          sum(coalesce(p_volume,0)) / nullif(sum(coalesce(c_volume,0)),0) AS put_call_volume_ratio,
          avg(CASE WHEN dte BETWEEN 5 AND 45 AND strike_distance <= 25 THEN c_iv END) AS near_atm_call_iv_5_45d,
          avg(CASE WHEN dte BETWEEN 5 AND 45 AND strike_distance <= 25 THEN p_iv END) AS near_atm_put_iv_5_45d,
          avg(CASE WHEN dte BETWEEN 5 AND 45 AND abs(c_delta - 0.25) <= 0.05 THEN c_iv END) AS call_25d_iv,
          avg(CASE WHEN dte BETWEEN 5 AND 45 AND abs(p_delta + 0.25) <= 0.05 THEN p_iv END) AS put_25d_iv,
          avg(CASE WHEN dte <= 7 AND strike_distance <= 25 THEN (coalesce(c_gamma,0)+coalesce(p_gamma,0)) END) AS front_atm_gamma_proxy
        FROM base
        GROUP BY 1;

        CREATE OR REPLACE TEMP TABLE call_walls AS
        SELECT quote_date, strike AS call_wall_strike, c_volume AS call_wall_volume
        FROM (
          SELECT quote_date, strike, c_volume,
                 row_number() OVER (PARTITION BY quote_date ORDER BY c_volume DESC NULLS LAST) AS rn
          FROM base WHERE coalesce(c_volume,0) > 0
        ) WHERE rn=1;

        CREATE OR REPLACE TEMP TABLE put_walls AS
        SELECT quote_date, strike AS put_wall_strike, p_volume AS put_wall_volume
        FROM (
          SELECT quote_date, strike, p_volume,
                 row_number() OVER (PARTITION BY quote_date ORDER BY p_volume DESC NULLS LAST) AS rn
          FROM base WHERE coalesce(p_volume,0) > 0
        ) WHERE rn=1;

        COPY (
          SELECT
            d.*,
            (d.put_25d_iv - d.call_25d_iv) AS skew_25d_put_minus_call,
            c.call_wall_strike,
            c.call_wall_volume,
            p.put_wall_strike,
            p.put_wall_volume,
            (c.call_wall_strike - d.underlying_last) AS call_wall_distance_points,
            (d.underlying_last - p.put_wall_strike) AS put_wall_distance_points
          FROM daily d
          LEFT JOIN call_walls c USING (quote_date)
          LEFT JOIN put_walls p USING (quote_date)
          ORDER BY quote_date
        ) TO '{q(out)}' (FORMAT PARQUET);
        """
    )
    row_count = con.execute(f"SELECT count(*) FROM read_parquet('{q(out)}')").fetchone()
    minmax = con.execute(f"SELECT min(quote_date), max(quote_date) FROM read_parquet('{q(out)}')").fetchone()
    if row_count is None or minmax is None:
        raise RuntimeError(f"Failed to verify output {out}")
    n = int(row_count[0])
    print(f"wrote {n:,} daily rows {minmax[0]} -> {minmax[1]}: {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    nq = sub.add_parser("normalize-nq")
    nq.add_argument("--root", default=str(DEFAULT_ROOT))
    nq.add_argument("--output-dir", default=str(DEFAULT_FEATURE_ROOT / "nq_futures"))
    nq.add_argument("--threads", type=int, default=4)
    nq.set_defaults(func=normalize_nq)

    opt = sub.add_parser("sp500-options-daily")
    opt.add_argument("--root", default=str(DEFAULT_ROOT))
    opt.add_argument("--output", default=str(DEFAULT_FEATURE_ROOT / "sp500_options/daily_regime_features.parquet"))
    opt.add_argument("--threads", type=int, default=4)
    opt.set_defaults(func=sp500_options_daily)

    eq = sub.add_parser("equities-breadth")
    eq.add_argument("--root", default=str(DEFAULT_ROOT))
    eq.add_argument("--month", default="2026-03", help="fabhaus JSONL month, e.g. 2026-03")
    eq.add_argument("--output", default=str(DEFAULT_FEATURE_ROOT / "equities_breadth/equities_5m_breadth_2026-03.parquet"))
    eq.add_argument("--threads", type=int, default=4)
    eq.set_defaults(func=equities_breadth)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
