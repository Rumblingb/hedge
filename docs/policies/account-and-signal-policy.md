# Account & Signal Hygiene Policy (2026-06-12, cofounder session)

## Bot/human account separation — HARD RULE
Bots and humans never share an account. Every reconciliation ambiguity to date
(the +$1,375 mystery close on 50K-B, "no trades open" vs broker-shows-open,
journal "manual" mislabels) traces to mixed activity.

- Automated lanes: 22983191 (canonical), 23268236 (testbed-a), 23536817 (testbed-b).
- Manual/discretionary trading: ONLY 23665193 (the live account, already hard-denied to bots).
- A manual fill on a bot account invalidates that day's journal for KPI purposes
  (mark records `contaminated: true`) and must be noted in the daily plan.

## Signal registry trim (recommendation — operator approves)
21 registered signals, 1 promoted. Unverified signals are not "small edges";
they are unknowns adding arbitration noise, freshness surface, and maintenance.

KEEP (promoted or active lane candidates):
- orb-breakout (nq-orb-3m-vt16) — promoted, live
- es-orb-15m — Lane B candidate (pending exit-mode fix)
- gc-pji-signal, gc-volregime-signal — GC lane candidates (vol_regime not Topstep-tradeable; personal-account candidate)
- nq-quant-signal — V4 engine integration track
- london-orb / asia-session — ONLY while their experiment budgets live; retire on exhaustion

ARCHIVE (legacy, never promoted, no active research track): pead-signal,
sr-proximity-signal, donchian-signal, and the remaining ~9 legacy technicals.
Mechanism: mark `archived: true` in the signal registry so arbitration skips
them and signal-quality stops demanding their freshness. Producers' crons can
then be removed one at a time.

## Data integrity
- `scripts/data_manifest.py generate` after any dataset acquisition;
  `check` mode in research preflight. 5 Excel-truncation suspects flagged
  2026-06-12 — notably ALL NQ 1m research sets end 2025-12-11 (six-month
  blind spot vs today). Refresh NQ 1m coverage from the bar archive before
  the next deep research pass.

## Experiment discipline
- Anything outside blessed evidence trades only under an active budget in
  `config/experiment-budgets.json` (config-parity gate enforces once
  BILL_CONFIG_PARITY_ENFORCE=true; advisory until then).
- Budget exhausted -> experiment stops, result is written up (confirmed or
  falsified), and either promotes into evidence or retires. No zombie experiments.
