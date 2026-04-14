# Prediction Scanner Hedge Integration Plan

Date: 2026-04-13
Owner: Bill
Status: concrete next build step

## Why this artifact exists
The stack spec is done. The next validated step is to map that prediction-market lane into the real `hedge` repo shape that exists today.

Verified repo facts:
- `src/cli.ts` is the main command surface.
- `hedge` already uses journal and report patterns for paper/backtest work.
- Existing design bias is guarded, reviewable, and CLI-first.

## Integration decision
Do not bolt prediction work onto the Topstep futures flow.

Instead, add a parallel paper-only command family in the same repo style:
- `prediction-scan`
- `prediction-report`

That keeps Bill's prediction lane inside Hedge without contaminating the existing Topstep rehab path.

## Proposed command behavior
### `prediction-scan`
Input:
- venue catalogs
- read-only quote snapshots
- fee config
- liquidity thresholds

Output:
- JSON journal rows written to a prediction-specific journal path
- stdout summary of top candidates

### `prediction-report`
Input:
- prediction journal path

Output:
- top 10 ranked candidates
- reject/watch/paper-trade counts
- highest-confidence exact-overlap candidates
- reasons most candidates were rejected

## Proposed file/module layout
Add these modules:
- `src/prediction/types.ts`
- `src/prediction/matcher.ts`
- `src/prediction/fees.ts`
- `src/prediction/journal.ts`
- `src/prediction/report.ts`

Keep adapters behind interfaces so the first pass can run on mocked or captured snapshots before any live fetch cadence is added.

## Minimal data model
### Candidate row
- `ts`
- `candidateId`
- `venueA`
- `venueB`
- `eventTitleA`
- `eventTitleB`
- `outcomeA`
- `outcomeB`
- `expiryA`
- `expiryB`
- `matchScore`
- `settlementCompatible`
- `grossEdgePct`
- `netEdgePct`
- `displayedSizeA`
- `displayedSizeB`
- `sizeVerdict`
- `verdict`
- `reasons[]`

## Match rules for v0
Accept as `paper-trade` only if all are true:
- same event meaning
- same outcome polarity
- same expiry window
- settlement wording compatible
- net edge positive after fees and slippage
- displayed size above minimum threshold

If any of the first four checks are uncertain, downgrade to `watch` or `reject`.

## Journal path decision
Use a separate file from the futures journal, for example:
- `journals/prediction-opportunities.jsonl`

Reason:
- avoids mixing futures trade records with prediction opportunity records
- keeps report logic simple
- makes the lane reviewable on its own merits

## CLI addition point
Extend `printUsage()` and the main command switch in `src/cli.ts` with:
- `prediction-scan [inputPath]`
- `prediction-report [journalPath]`

That matches Hedge's existing operator model.

## Validation standard for first coded pass
A first coded pass is good enough if it can:
1. read a mocked snapshot file
2. rank candidates consistently
3. write a prediction-specific journal
4. print a top-10 report
5. classify candidates into `reject`, `watch`, `paper-trade`

It does not need live venue adapters yet.

## Exact blocker
No blocker inside Hedge architecture.
The only real blocker remains external truth:
- exact venue equivalence
- fee correctness
- fill realism

That means the safest next coding move is mocked-snapshot support first, not live execution.

## Recommended next move
Implement the prediction types + journal schema first, then wire a mocked `prediction-report` command before any live data adapter work.
