#!/usr/bin/env bash
# State Backup Script
# Backs up critical trading system state, credentials, and config files
# Rotates backups to keep last 14 daily archives
# Runs daily via launchd

# Note: Avoid `set -e` + pipes due to tar interaction with HDD paths with spaces

# Detect HDD or fall back to SSD
HDD_PATH="/Volumes/Seagate Expansion Drive/rumbling-hedge-cold"
SSD_FALLBACK="/Users/brain/Backups/hedge"
RETENTION_DAYS=14
SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH='' cd -- "${SCRIPT_DIR}/../../.." && pwd)"
HEDGE_STATE="${REPO_ROOT}/.rumbling-hedge"

# Choose destination
if [ -d "$HDD_PATH" ]; then
    DEST_ROOT="$HDD_PATH/state-backups"
    DEST_SOURCE="HDD"
else
    DEST_ROOT="$SSD_FALLBACK/state-backups"
    DEST_SOURCE="SSD"
fi

# Verify writable
WRITE_TEST="${DEST_ROOT}/.write-test.$$"
if ! mkdir -p "$DEST_ROOT" 2>/dev/null || ! printf 'ok\n' > "$WRITE_TEST" 2>/dev/null; then
    echo "{\"command\":\"state-backup\",\"status\":\"skipped\",\"reason\":\"destination not writable\",\"dest\":\"${DEST_ROOT}\"}"
    exit 0
fi
rm -f "$WRITE_TEST"

# Create today's archive directory
BACKUP_DATE=$(date +%Y-%m-%d)
TODAY_DIR="${DEST_ROOT}/${BACKUP_DATE}"
mkdir -p "$TODAY_DIR"

BYTES_ARCHIVED=0
SETS_ARCHIVED=0

# Backup trading system state
if [ -e "${HEDGE_STATE}/state" ]; then
    size=$(du -sb "${HEDGE_STATE}/state" 2>/dev/null | cut -f1 || echo 0)
    if [ -z "$size" ]; then size=0; fi
    if [ "$size" -lt 2000000000 ]; then
        cd "$HEDGE_STATE" || exit 1
        tar -czf "${TODAY_DIR}/rumbling-hedge-state.tar.gz" "state" 2>/dev/null
        cd - > /dev/null 2>&1 || true
        if [ -f "${TODAY_DIR}/rumbling-hedge-state.tar.gz" ]; then
            archive_sz=$(stat -f%z "${TODAY_DIR}/rumbling-hedge-state.tar.gz" 2>/dev/null || echo 0)
            BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
            SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
        fi
    fi
fi

# Backup journal
if [ -e "${HEDGE_STATE}/journal.jsonl" ]; then
    size=$(du -sb "${HEDGE_STATE}/journal.jsonl" 2>/dev/null | cut -f1 || echo 0)
    if [ -z "$size" ]; then size=0; fi
    if [ "$size" -lt 2000000000 ]; then
        cd "$HEDGE_STATE" || exit 1
        tar -czf "${TODAY_DIR}/rumbling-hedge-journal.tar.gz" "journal.jsonl" 2>/dev/null
        cd - > /dev/null 2>&1 || true
        if [ -f "${TODAY_DIR}/rumbling-hedge-journal.tar.gz" ]; then
            archive_sz=$(stat -f%z "${TODAY_DIR}/rumbling-hedge-journal.tar.gz" 2>/dev/null || echo 0)
            BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
            SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
        fi
    fi
fi

# Backup features
if [ -e "${HEDGE_STATE}/features" ]; then
    size=$(du -sb "${HEDGE_STATE}/features" 2>/dev/null | cut -f1 || echo 0)
    if [ -z "$size" ]; then size=0; fi
    if [ "$size" -lt 2000000000 ]; then
        cd "$HEDGE_STATE" || exit 1
        tar -czf "${TODAY_DIR}/rumbling-hedge-features.tar.gz" "features" 2>/dev/null
        cd - > /dev/null 2>&1 || true
        if [ -f "${TODAY_DIR}/rumbling-hedge-features.tar.gz" ]; then
            archive_sz=$(stat -f%z "${TODAY_DIR}/rumbling-hedge-features.tar.gz" 2>/dev/null || echo 0)
            BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
            SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
        fi
    fi
fi

# Backup research
if [ -e "${HEDGE_STATE}/research" ]; then
    size=$(du -sb "${HEDGE_STATE}/research" 2>/dev/null | cut -f1 || echo 0)
    if [ -z "$size" ]; then size=0; fi
    if [ "$size" -lt 2000000000 ]; then
        cd "$HEDGE_STATE" || exit 1
        tar -czf "${TODAY_DIR}/rumbling-hedge-research.tar.gz" "research" 2>/dev/null
        cd - > /dev/null 2>&1 || true
        if [ -f "${TODAY_DIR}/rumbling-hedge-research.tar.gz" ]; then
            archive_sz=$(stat -f%z "${TODAY_DIR}/rumbling-hedge-research.tar.gz" 2>/dev/null || echo 0)
            BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
            SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
        fi
    fi
fi

# Backup AgentPay credentials
if [ -f "/Users/brain/Library/Application Support/AgentPay/bill/bill.env" ]; then
    cd "/Users/brain/Library/Application Support/AgentPay/bill" || exit 1
    tar -czf "${TODAY_DIR}/agentpay-bill.env.tar.gz" "bill.env" 2>/dev/null
    cd - > /dev/null 2>&1 || true
    if [ -f "${TODAY_DIR}/agentpay-bill.env.tar.gz" ]; then
        chmod 600 "${TODAY_DIR}/agentpay-bill.env.tar.gz"
        cred_sz=$(stat -f%z "${TODAY_DIR}/agentpay-bill.env.tar.gz" 2>/dev/null || echo 0)
        BYTES_ARCHIVED=$((BYTES_ARCHIVED + cred_sz))
        SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
    fi
fi

# Backup Hermes config and scripts
if [ -f "/Users/brain/.hermes/config.yaml" ]; then
    cd "/Users/brain/.hermes" || exit 1
    tar -czf "${TODAY_DIR}/hermes-config.tar.gz" "config.yaml" 2>/dev/null
    cd - > /dev/null 2>&1 || true
    if [ -f "${TODAY_DIR}/hermes-config.tar.gz" ]; then
        archive_sz=$(stat -f%z "${TODAY_DIR}/hermes-config.tar.gz" 2>/dev/null || echo 0)
        BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
        SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
    fi
fi

if [ -f "/Users/brain/.hermes/.env" ]; then
    cd "/Users/brain/.hermes" || exit 1
    tar -czf "${TODAY_DIR}/hermes-env.tar.gz" ".env" 2>/dev/null
    cd - > /dev/null 2>&1 || true
    if [ -f "${TODAY_DIR}/hermes-env.tar.gz" ]; then
        archive_sz=$(stat -f%z "${TODAY_DIR}/hermes-env.tar.gz" 2>/dev/null || echo 0)
        BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
        SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
    fi
fi

if [ -f "/Users/brain/.hermes/cron/jobs.json" ]; then
    cd "/Users/brain/.hermes" || exit 1
    tar -czf "${TODAY_DIR}/hermes-cron-jobs.tar.gz" "cron/jobs.json" 2>/dev/null
    cd - > /dev/null 2>&1 || true
    if [ -f "${TODAY_DIR}/hermes-cron-jobs.tar.gz" ]; then
        archive_sz=$(stat -f%z "${TODAY_DIR}/hermes-cron-jobs.tar.gz" 2>/dev/null || echo 0)
        BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
        SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
    fi
fi

if [ -e "/Users/brain/.hermes/scripts" ]; then
    size=$(du -sb "/Users/brain/.hermes/scripts" 2>/dev/null | cut -f1 || echo 0)
    if [ -z "$size" ]; then size=0; fi
    if [ "$size" -lt 2000000000 ]; then
        cd "/Users/brain/.hermes" || exit 1
        tar -czf "${TODAY_DIR}/hermes-scripts.tar.gz" "scripts" 2>/dev/null
        cd - > /dev/null 2>&1 || true
        if [ -f "${TODAY_DIR}/hermes-scripts.tar.gz" ]; then
            archive_sz=$(stat -f%z "${TODAY_DIR}/hermes-scripts.tar.gz" 2>/dev/null || echo 0)
            BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
            SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
        fi
    fi
fi

# Backup Obsidian vault subfolders if not synced
if [ -d "/Users/brain/Documents/memorybrain" ] && [ ! -d "/Users/brain/Documents/memorybrain/.git" ]; then
    if [ -d "/Users/brain/Documents/memorybrain/Agent-Hermes" ]; then
        size=$(du -sb "/Users/brain/Documents/memorybrain/Agent-Hermes" 2>/dev/null | cut -f1 || echo 0)
        if [ -z "$size" ]; then size=0; fi
        if [ "$size" -lt 2000000000 ]; then
            cd "/Users/brain/Documents/memorybrain" || exit 1
            tar -czf "${TODAY_DIR}/memorybrain-Agent-Hermes.tar.gz" "Agent-Hermes" 2>/dev/null
            cd - > /dev/null 2>&1 || true
            if [ -f "${TODAY_DIR}/memorybrain-Agent-Hermes.tar.gz" ]; then
                archive_sz=$(stat -f%z "${TODAY_DIR}/memorybrain-Agent-Hermes.tar.gz" 2>/dev/null || echo 0)
                BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
                SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
            fi
        fi
    fi
    if [ -d "/Users/brain/Documents/memorybrain/Trading" ]; then
        size=$(du -sb "/Users/brain/Documents/memorybrain/Trading" 2>/dev/null | cut -f1 || echo 0)
        if [ -z "$size" ]; then size=0; fi
        if [ "$size" -lt 2000000000 ]; then
            cd "/Users/brain/Documents/memorybrain" || exit 1
            tar -czf "${TODAY_DIR}/memorybrain-Trading.tar.gz" "Trading" 2>/dev/null
            cd - > /dev/null 2>&1 || true
            if [ -f "${TODAY_DIR}/memorybrain-Trading.tar.gz" ]; then
                archive_sz=$(stat -f%z "${TODAY_DIR}/memorybrain-Trading.tar.gz" 2>/dev/null || echo 0)
                BYTES_ARCHIVED=$((BYTES_ARCHIVED + archive_sz))
                SETS_ARCHIVED=$((SETS_ARCHIVED + 1))
            fi
        fi
    fi
fi

# Rotation: delete backups older than RETENTION_DAYS
find "$DEST_ROOT" -maxdepth 1 -type d -name "????-??-??" 2>/dev/null | while read old_dir; do
    old_date=$(basename "$old_dir")
    old_epoch=$(date -jf %Y-%m-%d "$old_date" +%s 2>/dev/null || echo 0)
    now_epoch=$(date +%s)
    age_days=$(( (now_epoch - old_epoch) / 86400 ))
    if [ "$age_days" -gt "$RETENTION_DAYS" ]; then
        rm -rf "$old_dir"
    fi
done

# Report
BYTES_MB=$((BYTES_ARCHIVED / 1048576))
echo "{\"command\":\"state-backup\",\"status\":\"ok\",\"dest\":\"${DEST_ROOT}\",\"dest_source\":\"${DEST_SOURCE}\",\"date\":\"${BACKUP_DATE}\",\"bytes\":${BYTES_ARCHIVED},\"bytes_mb\":${BYTES_MB},\"sets\":${SETS_ARCHIVED},\"retention_days\":${RETENTION_DAYS}}"
