#!/usr/bin/env python3
"""Bounded local importer for jon-becker/prediction-market-analysis parquet data.

This script is intentionally local-only:
- no network calls
- no upstream setup execution
- no writes outside --out-dir

It reads an already extracted data directory and emits compact JSON artifacts
that Bill/Hermes can use for calibration and maker/taker research.
"""

from __future__ import annotations

import argparse
import json
import sys
import math
from pathlib import Path
from typing import Any

TABLES = {
    "kalshi_markets": "kalshi/markets",
    "kalshi_trades": "kalshi/trades",
    "polymarket_markets": "polymarket/markets",
    "polymarket_trades": "polymarket/trades",
    "polymarket_legacy_trades": "polymarket/legacy_trades",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a bounded slice of prediction-market-analysis parquet data."
    )
    parser.add_argument(
        "--data-root", required=True, help="Extracted upstream data root containing kalshi/ and polymarket/."
    )
    parser.add_argument(
        "--out-dir", required=True, help="Directory for compact Bill/Hermes artifacts."
    )
    parser.add_argument(
        "--max-files-per-table",
        type=int,
        default=25,
        help="Max parquet files per table; 0 means all files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only scan paths and write a manifest.",
    )
    parser.add_argument(
        "--skip-kalshi",
        action="store_true",
        help="Skip Kalshi aggregate reports.",
    )
    parser.add_argument(
        "--skip-polymarket",
        action="store_true",
        help="Skip Polymarket aggregate reports.",
    )
    return parser.parse_args()


def collect_parquets(root: Path, relative: str, max_files: int) -> list[Path]:
    table_root = root / relative
    if not table_root.exists():
        return []
    files = sorted(table_root.rglob("*.parquet"))
    if max_files > 0:
        return files[:max_files]
    return files


def file_manifest(root: Path, max_files: int) -> dict[str, Any]:
    tables = {}
    for key, relative in TABLES.items():
        files = collect_parquets(root, relative, max_files)
        tables[key] = {
            "relativePath": relative,
            "files": len(files),
            "bytes": sum(path.stat().st_size for path in files),
            "sample": [str(path) for path in files[:3]],
        }
    return {"dataRoot": str(root), "maxFilesPerTable": max_files, "tables": tables}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def duckdb_list(paths: list[Path]) -> str:
    quoted = []
    for path in paths:
        quoted.append("'" + str(path).replace("'", "''") + "'")
    return "[" + ", ".join(quoted) + "]"


def rows_from_duckdb_relation(con: Any, query: str) -> list[dict[str, Any]]:
    columns = [col[0] for col in con.execute(query).description]
    rows = con.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def calibration_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(int(row.get("total_trades", 0)) for row in rows)
    if total <= 0:
        return {"totalTrades": 0, "brierScore": 0, "logLoss": 0, "ece": 0}

    brier_sum = 0.0
    log_loss_sum = 0.0
    ece_sum = 0.0
    epsilon = 1e-6
    for row in rows:
        price = float(row["price"])
        predicted = max(min(price / 100.0, 1 - epsilon), epsilon)
        wins = float(row.get("wins", 0))
        count = float(row.get("total_trades", 0))
        losses = count - wins
        actual = wins / count if count > 0 else 0.0
        brier_sum += wins * (predicted - 1) ** 2 + losses * predicted**2
        log_loss_sum += wins * (-math.log(predicted)) + losses * (-math.log(1 - predicted))
        ece_sum += count * abs(actual - predicted)

    return {
        "totalTrades": int(total),
        "brierScore": round(brier_sum / total, 6),
        "logLoss": round(log_loss_sum / total, 6),
        "ece": round(ece_sum / total, 6),
    }


def import_kalshi(con: Any, files: dict[str, list[Path]], out_dir: Path) -> dict[str, Any]:
    markets = files["kalshi_markets"]
    trades = files["kalshi_trades"]
    if not markets or not trades:
        print(
            "[prediction-market-analysis-import] skipped due to missing Kalshi market or trade parquet files",
            file=sys.stderr,
        )
        return {"status": "skipped", "reason": "missing Kalshi market or trade parquet files"}

    market_expr = duckdb_list(markets)
    trade_expr = duckdb_list(trades)

    win_rate_rows = rows_from_duckdb_relation(
        con,
        f\"\"\"
        WITH resolved_markets AS (
          SELECT ticker, result
          FROM read_parquet({market_expr})
          WHERE status = 'finalized' AND result IN ('yes', 'no')
        ), 
        all_positions AS (
          SELECT
            CASE WHEN t.taker_side = 'yes' THEN t.yes_price ELSE t.no_price END AS price,
            CASE WHEN t.taker_side = m.result THEN 1 ELSE 0 END AS won
          FROM read_parquet({trade_expr}) t
          INNER JOIN resolved_markets m ON t.ticker = m.ticker
          UNION ALL
          SELECT
            CASE WHEN t.taker_side = 'yes' THEN t.no_price ELSE t.yes_price END AS price,
            CASE WHEN t.taker_side != m.result THEN 1 ELSE 0 END AS won
          FROM read_parquet({trade_expr}) t
          INNER JOIN resolved_markets m ON t.ticker = m.ticker
        )
        SELECT
          CAST(price AS INTEGER) AS price,
          COUNT(*) AS total_trades,
          SUM(won) AS wins,
          ROUND(100.0 * SUM(won) / COUNT(*), 4) AS win_rate
        FROM all_positions
        WHERE price BETWEEN 1 AND 99
        GROUP BY price
        ORDER BY price
        \"\"\"
    )

    maker_taker_rows = rows_from_duckdb_relation(
        con,
        f\"\"\"
        WITH resolved_markets AS (
          SELECT ticker, result
          FROM read_parquet({market_expr})
          WHERE status = 'finalized' AND result IN ('yes', 'no')
        ), 
        positions AS (
          SELECT
            'taker' AS role,
            CASE WHEN t.taker_side = 'yes' THEN t.yes_price ELSE t.no_price END AS price,
            CASE WHEN t.taker_side = m.result THEN 1.0 ELSE 0.0 END AS won,
            t.count AS contracts
          FROM read_parquet({trade_expr}) t
          INNER JOIN resolved_markets m ON t.ticker = m.ticker
          UNION ALL
          SELECT
            'maker' AS role,
            CASE WHEN t.taker_side != 'yes' THEN 1.0 ELSE 0.0 END AS won,
            t.count AS contracts
          FROM read_parquet({trade_expr}) t
          INNER JOIN resolved_markets m ON t.ticker = m.ticker
        )
        SELECT
          role,
          CAST(FLOOR(price / 10) * 10 AS INTEGER) AS price_bucket,
          COUNT(*) AS trades,
          SUM(contracts) AS contracts,
          ROUND(AVG(won), 6) AS win_rate,
          ROUND(AVG(price / 100.0), 6) AS implied_rate,
          ROUND(AVG(won - price / 100.0), 6) AS excess_return
        FROM positions
        WHERE price BETWEEN 1 AND 99
        GROUP BY role, FLOOR(price / 10) * 10
        ORDER BY role, price_bucket
        \"\"\"
    )

    result = {
        "status": "ok",
        "source": "kalshi",
        "files": {"markets": len(markets), "trades": len(trades)},
        "metrics": calibration_metrics(win_rate_rows),
        "artifacts": {
            "winRateByPrice": str(out_dir / "kalshi-win-rate-by-price.json"),
            "makerTakerReturns": str(out_dir / "kalshi-maker-taker-returns.json"),
        },
    }
    write_json(out_dir / "kalshi-win-rate-by-price.json", {"source": "kalshi", "rows": win_rate_rows, "metrics": result["metrics"]})
    write_json(out_dir / "kalshi-maker-taker-returns.json", {"source": "kalshi", "rows": maker_taker_rows})
    return result


def import_polymarket(con: Any, files: dict[str, list[Path]], out_dir: Path) -> dict[str, Any]:
    markets = files["polymarket_markets"]
    trades = files["polymarket_trades"]
    legacy_trades = files["polymarket_legacy_trades"]
    if not markets or not trades:
        print(
            "[prediction-market-analysis-import] skipped due to missing Polymarket market or trade parquet files",
            file=sys.stderr,
        )
        return {"status": "skipped", "reason": "missing Polymarket market or trade parquet files"}

    markets_df = con.execute(
        f\"\"\"
        SELECT id, clob_token_ids, outcome_prices, market_maker_address
        FROM read_parquet({duckdb_list(markets)})
        WHERE closed = true
        \"\"\"
    ).fetchall()

    token_won: dict[str, bool] = {}
    fpmm_resolution: dict[str, int] = {}
    for _, clob_token_ids, outcome_prices, market_maker_address in markets_df:
        try:
            prices = json.loads(outcome_prices) if outcome_prices else None
            if not prices or len(prices) != 2:
                continue
            p0 = float(prices[0])
            p1 = float(prices[1])
            winning_outcome = None
            if p0 > 0.99 and p1 < 0.01:
                winning_outcome = 0
            elif p0 < 0.01 and p1 > 0.99:
                winning_outcome = 1
            if winning_outcome is None:
                continue

            token_ids = json.loads(clob_token_ids) if clob_token_ids else None
            if token_ids and len(token_ids) == 2:
                token_won[str(token_ids[0])] = winning_outcome == 0
                token_won[str(token_ids[1])] = winning_outcome == 1
            if isinstance(market_maker_address, str) and market_maker_address:
                fpmm_resolution[market_maker_address.lower()] = winning_outcome
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    if not token_won and not fpmm_resolution:
        return {"status": "skipped", "reason": "no resolved Polymarket token mapping found"}

    con.execute("CREATE OR REPLACE TABLE token_resolution (token_id VARCHAR, won BOOLEAN)")
    if token_won:
        con.executemany("INSERT INTO token_resolution VALUES (?, ?)", list(token_won.items()))
    con.execute("CREATE OR REPLACE TABLE fpmm_resolution (fpmm_address VARCHAR, winning_outcome BIGINT)")
    if fpmm_resolution:
        con.executemany("INSERT INTO fpmm_resolution VALUES (?, ?)", list(fpmm_resolution.items()))

    ctf_query = f\"\"\"
      SELECT
        CASE
          WHEN CAST(t.maker_asset_id AS VARCHAR) = '0' THEN ROUND(100.0 * t.maker_amount / t.taker_amount)
          ELSE ROUND(100.0 * t.taker_amount / t.maker_amount)
        END AS price,
        tr.won AS won
      FROM read_parquet({duckdb_list(trades)}) t
      INNER JOIN token_resolution tr ON (
        CASE
          WHEN CAST(t.maker_asset_id AS VARCHAR) = '0' THEN CAST(t.taker_asset_id AS VARCHAR)
          ELSE CAST(t.maker_asset_id AS VARCHAR)
        END = tr.token_id
      )
      WHERE t.taker_amount > 0 AND t.maker_amount > 0
      UNION ALL
      SELECT
        CASE
          WHEN CAST(t.maker_asset_id AS VARCHAR) = '0' THEN ROUND(100.0 - 100.0 * t.maker_amount / t.taker_amount)
          ELSE ROUND(100.0 - 100.0 * t.taker_amount / t.maker_amount)
        END AS price,
        NOT tr.won AS won
      FROM read_parquet({duckdb_list(trades)}) t
      INNER JOIN token_resolution tr ON (
        CASE
          WHEN CAST(t.maker_asset_id AS VARCHAR) = '0' THEN CAST(t.taker_asset_id AS VARCHAR)
          ELSE CAST(t.taker_asset_id AS VARCHAR)
        END = tr.token_id
      )
      WHERE t.taker_amount > 0 AND t.maker_amount > 0
    \"\"\"

    legacy_query = \"\"
    if legacy_trades and fpmm_resolution:
        legacy_query = f\"\"\"
          UNION ALL
          SELECT
            ROUND(100.0 * CAST(t.amount AS DOUBLE) / CAST(t.outcome_tokens AS DOUBLE)) AS price,
            (t.outcome_index = r.winning_outcome) AS won
          FROM read_parquet({duckdb_list(legacy_trades)}) t
          INNER JOIN fpmm_resolution r ON LOWER(t.fpmm_address) = r.fpmm_address
          WHERE CAST(t.outcome_tokens AS DOUBLE) > 0
          UNION ALL
          SELECT
            ROUND(100.0 - 100.0 * CAST(t.amount AS DOUBLE) / CAST(t.outcome_tokens AS DOUBLE)) AS price,
            (t.outcome_index != r.winning_outcome) AS won
          FROM read_parquet({duckdb_list(legacy_trades)}) t
          INNER JOIN fpmm_resolution r ON LOWER(t.fpmm_address) = r.fpmm_address
          WHERE CAST(t.outcome_tokens AS DOUBLE) > 0
        \"\"\"

    rows = rows_from_duckdb_relation(
        con,
        f\"\"\"
        WITH trade_positions AS (
          {ctf_query}
          {legacy_query}
        )
        SELECT
          CAST(price AS INTEGER) AS price,
          COUNT(*) AS total_trades,
          SUM(CASE WHEN won THEN 1 ELSE 0 END) AS wins,
          ROUND(100.0 * SUM(CASE WHEN won THEN 1 ELSE 0 END) / COUNT(*), 4) AS win_rate
        FROM trade_positions
        WHERE price BETWEEN 1 AND 99
        GROUP BY price
        ORDER BY price
        \"\"\"
    )

    result = {
        "status": "ok",
        "source": "polymarket",
        "files": {"markets": len(markets), "trades": len(trades), "legacyTrades": len(legacy_trades)},
        "resolvedTokens": len(token_won),
        "resolvedLegacyMarkets": len(fpmm_resolution),
        "metrics": calibration_metrics(rows),
        "artifacts": {"winRateByPrice": str(out_dir / "polymarket-win-rate-by-price.json")},
    }
    write_json(out_dir / "polymarket-win-rate-by-price.json", {"source": "polymarket", "rows": rows, "metrics": result["metrics"]})
    return result


def main() -> int:
    args = parse_args()
    data_root = Path(args.data_root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = file_manifest(data_root, args.max_files_per_table)
    write_json(out_dir / "manifest.json", manifest)

    if args.dry_run:
        summary = {
            "status": "dry-run",
            "manifestPath": str(out_dir / "manifest.json"),
            "manifest": manifest,
        }
        write_json(out_dir / "summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 0

    try:
        import duckdb
    except ModuleNotFoundError:
        summary = {
            "status": "blocked",
            "reason": "python duckdb is not installed",
            "installCommand": "python3 -m pip install --user duckdb",
            "manifestPath": str(out_dir / "manifest.json"),
        }
        write_json(out_dir / "summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 2

    files = {
        key: collect_parquets(data_root, relative, args.max_files_per_table)
        for key, relative in TABLES.items()
    }
    con = duckdb.connect()
    imports = []
    if not args.skip_kalshi:
        imports.append(import_kalshi(con, files, out_dir))
    if not args.skip_polymarket:
        imports.append(import_polymarket(con, files, out_dir))

    summary = {
        "status": "ok" if any(item.get("status") == "ok" for item in imports) else "blocked",
        "manifestPath": str(out_dir / "manifest.json"),
        "imports": imports,
    }
    write_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())