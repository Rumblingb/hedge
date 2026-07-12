
## LSE WATCH data refresh (2026-07-12 ~15:28Z)

- **NAS100/USD 5m → CPI:** Pulled to Seagate `nq-proxy-5m-to-cpi-window.json` (252 rows; 2026-07-10T00:00Z–2026-07-10T20:55Z). Canonical longer slice `nq-proxy-5m-jul-to-cpi.json` unchanged at 2136 rows, same last bar. LSE API has **no** Jul 11–14 5m bars yet (~87.6 h / ~1051 bars gap to 2026-07-14T12:30Z CPI).
- **QQQ IV:** Snapshot `qqq-puts-30-45dte-20260712T1528Z.json` — 45 delta-band puts (−0.30…−0.15), median IV **0.2707**.
- **Pull:** `npm run bill:lse-research-pull` PASS (11/11); machine state `lse-watch-data-readiness.latest.json`.
- **Repo:** Symlinks under `.rumbling-hedge/research/lse/` for `nq-proxy-5m-to-cpi-window.json` and `qqq-iv-snapshots/`. Execution locked.

