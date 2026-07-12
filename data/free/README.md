# Local research-data cache

CSV and Parquet files in this directory are generated or locally curated research inputs. They are not execution-grade market data and must not authorize routing.

Refresh the six-market Yahoo research snapshots with:

```bash
npm run --silent bill:refresh-futures-research-data
```

The refresh writes provenance to `.rumbling-hedge/state/futures-research-data-refresh.latest.json`. Current demo/live routing still requires independent broker-grade freshness, reconciliation, daily-plan, source, and strategy gates.

The short-window `*-1m-5d.csv` and `ALL-6MARKETS-1m-5d-normalized.csv` files are local cache outputs. They remain on the machine but are intentionally not versioned, so a normal research refresh cannot dirty the source tree.
