# Real Data Playbook

This lab is demo-first, but it is ready for real minute-bar futures CSVs when the file shape is clean and the symbols are normalized.

## Expected CSV shape

Recommended header:

```text
ts,symbol,open,high,low,close,volume
2026-04-01T13:30:00.000Z,NQM26,18250,18253,18248,18252,1320
2026-04-01T13:31:00.000Z,NQM26,18252,18255,18249,18250,1184
```

The loader also accepts the legacy 7-column order without a header row, but headered files are safer and easier to inspect.

## Column rules

- `ts` must be a single ISO 8601 timestamp string.
- Use UTC timestamps if you can. That keeps session logic and replay consistent.
- `symbol` may be either a root symbol or a contract code.
- `open`, `high`, `low`, `close`, and `volume` must be numeric.
- Extra columns are ignored.

Accepted symbol aliases in the header:

- `ts`: `ts`, `timestamp`, `datetime`, `date_time`, `time_stamp`
- `symbol`: `symbol`, `root`, `ticker`, `contract`, `instrument`
- `open`: `open`, `o`
- `high`: `high`, `h`
- `low`: `low`, `l`
- `close`: `close`, `c`
- `volume`: `volume`, `vol`, `v`

## Symbol handling

The ingest layer normalizes common futures contract codes to the root symbol before the bar enters the research engine.

Examples:

- `NQM26` -> `NQ`
- `ESM26` -> `ES`
- `CLM26` -> `CL`
- `6EH26` -> `6E`

That means the lab can research root-based strategies without being tied to a specific expiry file.

## Workflow

1. Export a minute-bar CSV from your vendor or internal feed.
2. Make sure the file is ordered chronologically.
3. Keep one root universe per file if you want a clean backtest or walk-forward pass.
4. Inspect the CSV before you trust it:

```bash
npm run inspect-csv -- ./data/nq-minute-bars.csv
```

5. Run a single-strategy backtest:

```bash
npm run backtest -- ./data/nq-minute-bars.csv
```

6. Run the profile comparison pass:

```bash
npm run research -- ./data/nq-minute-bars.csv
```

7. Read the JSON summary and compare total `R`, win rate, profit factor, drawdown, and family budget recommendation.
8. Only then consider a new iteration or a tighter guardrail.

## Recommended real-data universe

Start with the liquid contracts Topstep traders actually care about:

- `NQ`
- `ES`
- `CL`
- `GC`
- `6E`

Add anything else only after the first pass proves that the lab is stable on these names.

## Failure modes to avoid

- Mixing multiple expiries in the same file without normalizing the symbol first.
- Using local timestamps without knowing whether they are CT, ET, or UTC.
- Feeding sparse or gappy data into a minute-bar strategy and expecting clean fills.
- Treating a synthetic win rate as evidence that the real feed will behave the same.

## Good operating rule

If the CSV is not obvious to a new engineer in 30 seconds, it is not ready yet.
