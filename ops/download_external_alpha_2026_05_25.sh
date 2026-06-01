#!/usr/bin/env bash
set -euo pipefail
ROOT="/Volumes/Seagate Expansion Drive/hedge-data/external-alpha-2026-05-25"
LOG="$ROOT/manifests/download.log"
mkdir -p "$ROOT/hf" "$ROOT/manifests"
exec > >(tee -a "$LOG") 2>&1

echo "[$(date -u +%FT%TZ)] external alpha download start"

dl_hf() {
  local repo="$1"; shift
  local dest="$ROOT/hf/${repo//\//__}"
  mkdir -p "$dest"
  echo "[$(date -u +%FT%TZ)] HF download $repo -> $dest args=$*"
  hf download "$repo" --repo-type dataset --local-dir "$dest" "$@"
  echo "[$(date -u +%FT%TZ)] HF done $repo"
}

# 1) Full Polymarket crypto up/down dataset: directly useful for Gengar/BTC edge and orderbook/spot alignment.
dl_hf "BrockMisner/polymarket-btc-updown"

# 2) Full S&P 500 earnings transcripts: manageable size, useful for earnings/macro NLP overlays.
dl_hf "Bose345/sp500_earnings_transcripts"

# 3) SEC EDGAR full corpus is large (~295GB) but fits on external disk and is historically valuable for fundamental/NLP features.
dl_hf "TeraflopAI/SEC-EDGAR"

# 4) Equities 5m full corpus is ~478GB and cannot fit with the above on current free space.
# Pull representative high-value months for schema/feature development and backfill plan.
dl_hf "fabhaus/equities_5m_stockprices" README.md .gitattributes 2024-01.jsonl 2025-01.jsonl 2026-03.jsonl

echo "[$(date -u +%FT%TZ)] external alpha download complete"
du -sh "$ROOT"/* || true
