#!/bin/bash
set -euo pipefail

# Prevent NODE_ENV=production (set in Hermes .env) from blocking devDependency installs.
# Launchd jobs use bill.env separately; this guards cron/manual npm operations.
export NODE_ENV="development"

bill_bin_dir() {
  CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
}

bill_repo_root() {
  CDPATH='' cd -- "$(bill_bin_dir)/../../.." && pwd
}

bill_default_path() {
  printf '%s\n' "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
}

ensure_bill_path() {
  export PATH="$(bill_default_path):${PATH:-}"
}

bill_node() {
  ensure_bill_path
  if command -v node >/dev/null 2>&1; then
    command -v node
    return
  fi
  echo "Node.js is required for Bill wrappers." >&2
  exit 2
}

bill_env_file() {
  if [[ -n "${BILL_ENV_FILE:-}" ]]; then
    printf '%s\n' "$BILL_ENV_FILE"
    return
  fi
  printf '%s\n' "${HOME}/Library/Application Support/AgentPay/bill/bill.env"
}

bill_repo_env_file() {
  printf '%s\n' "$(bill_repo_root)/.env"
}

load_bill_dotenv_file() {
  local env_file line key value
  env_file="$1"
  [[ -f "$env_file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -n "$line" ]] || continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" == export\ * ]]; then
      line="${line#export }"
    fi
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "$value" == \"*\" && "${#value}" -ge 2 ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "${#value}" -ge 2 ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "$key=$value"
  done < "$env_file"
}

bill_system_access_env_candidates() {
  local candidate
  for candidate in \
    "${HOME}/Public/Drop Box/system-access.env" \
    /Users/*/Public/Drop\ Box/system-access.env
  do
    [[ -r "$candidate" ]] || continue
    printf '%s\n' "$candidate"
  done | awk '!seen[$0]++'
}

bill_cold_futures_data_dir() {
  printf '%s\n' "${BILL_FUTURES_COLD_DATA_DIR:-/Volumes/Seagate Expansion Drive/rumbling-hedge/data/free/free}"
}

bill_resolve_csv_path() {
  local csv_path="$1" root="$2" cold_dir candidate basename_path repo_relative
  [[ -n "$csv_path" ]] || return 1

  if [[ "$csv_path" == /* && -f "$csv_path" ]]; then
    printf '%s\n' "$csv_path"
    return 0
  fi

  if [[ "$csv_path" != /* && -f "$root/$csv_path" ]]; then
    printf '%s\n' "$csv_path"
    return 0
  fi

  cold_dir="$(bill_cold_futures_data_dir)"
  basename_path="$(basename -- "$csv_path")"
  repo_relative="${csv_path#"$root/"}"

  for candidate in \
    "$cold_dir/$basename_path" \
    "$cold_dir/${repo_relative#data/free/}" \
    "$cold_dir/${csv_path#data/free/}"
  do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

bill_apply_storage_fallbacks() {
  local root var current resolved
  root="$(bill_repo_root)"

  export BILL_FUTURES_COLD_DATA_DIR="${BILL_FUTURES_COLD_DATA_DIR:-/Volumes/Seagate Expansion Drive/rumbling-hedge/data/free/free}"
  export BILL_PREDICTION_MARKET_ANALYSIS_DATA_ROOT="${BILL_PREDICTION_MARKET_ANALYSIS_DATA_ROOT:-/Volumes/Seagate Expansion Drive/rumbling-hedge-cold/prediction-market-analysis}"

  for var in \
    BILL_PAPER_LOOP_CSV_PATH \
    BILL_STRATEGY_LAB_CSV_PATH \
    BILL_STRATEGY_LAB_OOS_CSV_PATH \
    BILL_TIMESFM_DEFAULT_CSV_PATH \
    BILL_OOS_CSV_PATH \
    BILL_STRATEGY_RESEARCH_CONTRACTS_CSV_PATH \
    BILL_MACRO_POLICY_CSV_PATH
  do
    current="${!var:-}"
    [[ -n "$current" ]] || continue
    if resolved="$(bill_resolve_csv_path "$current" "$root")"; then
      printf -v "$var" '%s' "$resolved"
      export "$var"
    fi
  done
}

load_bill_env() {
  local env_file

  env_file="$(bill_repo_env_file)"
  load_bill_dotenv_file "$env_file"

  while IFS= read -r env_file; do
    [[ -f "$env_file" ]] || continue
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  done < <(bill_system_access_env_candidates)

  env_file="$(bill_env_file)"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi

  # Override NODE_ENV to ensure devDependencies (tsx) are installed.
  # Hermes cron sessions inject NODE_ENV=production from ~/.hermes/.env,
  # which causes npm install to skip tsx and break bill_tsx().
  export NODE_ENV=development

  # Fail closed for futures routing. The secure env may contain real ProjectX
  # account identifiers, so scheduled demo jobs must not inherit a live-routing
  # posture unless a separate explicit override is set.
  if [[ "${BILL_ALLOW_FUTURES_LIVE_ROUTING:-false}" != "true" ]]; then
    export RH_TOPSTEP_DEMO_ONLY=true
  fi

  bill_apply_storage_fallbacks
}

bill_tsx() {
  local root
  ensure_bill_path
  root="$(bill_repo_root)"
  if [[ ! -x "$root/node_modules/.bin/tsx" ]]; then
    echo "Bill runtime is not installed. Run 'npm install' in $root first." >&2
    exit 2
  fi
  printf '%s\n' "$root/node_modules/.bin/tsx"
}

ensure_bill_runtime_dirs() {
  local root
  root="$(bill_repo_root)"
  mkdir -p "$root/.rumbling-hedge/logs" "$root/journals"
  rotate_bill_runtime_logs "$root"
}

apply_bill_process_limits() {
  local cpu_seconds open_files max_processes nice_level
  cpu_seconds="${BILL_PROCESS_CPU_LIMIT_SECONDS:-14400}"
  open_files="${BILL_PROCESS_MAX_OPEN_FILES:-4096}"
  max_processes="${BILL_PROCESS_MAX_USER_PROCESSES:-512}"
  nice_level="${BILL_PROCESS_NICE:-0}"

  if [[ "$cpu_seconds" =~ ^[0-9]+$ ]] && (( cpu_seconds > 0 )); then
    ulimit -t "$cpu_seconds" 2>/dev/null || true
  fi
  if [[ "$open_files" =~ ^[0-9]+$ ]] && (( open_files > 0 )); then
    ulimit -n "$open_files" 2>/dev/null || true
  fi
  if [[ "$max_processes" =~ ^[0-9]+$ ]] && (( max_processes > 0 )); then
    ulimit -u "$max_processes" 2>/dev/null || true
  fi
  if [[ "$nice_level" =~ ^-?[0-9]+$ ]] && (( nice_level > 0 )); then
    renice "$nice_level" "$$" >/dev/null 2>&1 || true
  fi
}

bill_kill_process_tree() {
  local pid="$1" signal="${2:-TERM}" child
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  while IFS= read -r child; do
    [[ -n "$child" ]] || continue
    bill_kill_process_tree "$child" "$signal"
  done < <(pgrep -P "$pid" 2>/dev/null || true)
  kill "-$signal" "$pid" 2>/dev/null || true
}

bill_run_with_watchdog() {
  local timeout_seconds="$1" grace_seconds="$2" command_name="$3" pid watchdog_pid status
  shift 3
  if [[ ! "$timeout_seconds" =~ ^[0-9]+$ ]] || (( timeout_seconds <= 0 )); then
    "$@"
    return $?
  fi
  if [[ ! "$grace_seconds" =~ ^[0-9]+$ ]] || (( grace_seconds <= 0 )); then
    grace_seconds="20"
  fi

  "$@" &
  pid="$!"
  (
    sleep "$timeout_seconds"
    if kill -0 "$pid" 2>/dev/null; then
      printf '{"command":"%s","status":"watchdog-timeout","pid":%s,"timeoutSeconds":%s}\n' "$command_name" "$pid" "$timeout_seconds" >&2
      bill_kill_process_tree "$pid" TERM
      sleep "$grace_seconds"
      if kill -0 "$pid" 2>/dev/null; then
        bill_kill_process_tree "$pid" KILL
      fi
    fi
  ) &
  watchdog_pid="$!"
  set +e
  wait "$pid"
  status="$?"
  set -e
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  return "$status"
}

bill_file_size_bytes() {
  local file_path="$1"
  stat -f '%z' "$file_path" 2>/dev/null || stat -c '%s' "$file_path" 2>/dev/null || printf '0\n'
}

bill_rotate_one_file() {
  local file_path="$1" max_bytes="$2" keep="${3:-3}" size index previous next
  [[ -f "$file_path" ]] || return 0
  size="$(bill_file_size_bytes "$file_path")"
  [[ "$size" =~ ^[0-9]+$ ]] || return 0
  (( size > max_bytes )) || return 0

  index="$keep"
  while (( index >= 1 )); do
    previous="${file_path}.$index"
    next="${file_path}.$(( index + 1 ))"
    if [[ -f "$previous" ]]; then
      if (( index >= keep )); then
        rm -f "$previous"
      else
        mv "$previous" "$next"
      fi
    fi
    index="$(( index - 1 ))"
  done
  mv "$file_path" "${file_path}.1"
}

rotate_bill_runtime_logs() {
  local root="$1" log_dir log_max_mb jsonl_max_mb keep log_max_bytes jsonl_max_bytes file
  log_dir="$root/.rumbling-hedge/logs"
  [[ -d "$log_dir" ]] || return 0
  log_max_mb="${BILL_LOG_MAX_MB:-16}"
  jsonl_max_mb="${BILL_JSONL_MAX_MB:-64}"
  keep="${BILL_LOG_ROTATIONS:-3}"
  log_max_bytes="$(( log_max_mb * 1024 * 1024 ))"
  jsonl_max_bytes="$(( jsonl_max_mb * 1024 * 1024 ))"

  shopt -s nullglob
  for file in "$log_dir"/*.log "$log_dir"/*.err.log; do
    bill_rotate_one_file "$file" "$log_max_bytes" "$keep"
  done
  for file in "$log_dir"/*.jsonl; do
    bill_rotate_one_file "$file" "$jsonl_max_bytes" "$keep"
  done
  shopt -u nullglob
}

run_bill_cli() {
  local root tsx timeout_seconds grace_seconds command_name
  ensure_bill_path
  root="$(bill_repo_root)"
  tsx="$(bill_tsx)"
  load_bill_env
  apply_bill_process_limits
  ensure_bill_runtime_dirs
  timeout_seconds="${BILL_PROCESS_TIMEOUT_SECONDS:-7200}"
  grace_seconds="${BILL_PROCESS_KILL_GRACE_SECONDS:-20}"
  command_name="${1:-bill-cli}"
  (
    cd "$root"
    bill_run_with_watchdog "$timeout_seconds" "$grace_seconds" "$command_name" "$tsx" src/cli.ts "$@"
  )
}

lock_mtime_epoch() {
  local lock_dir="$1"
  [[ -d "$lock_dir" ]] || return 1
  stat -f '%m' "$lock_dir" 2>/dev/null
}

lock_age_seconds() {
  local lock_dir="$1" now started
  started="$(lock_mtime_epoch "$lock_dir")" || return 1
  now="$(date +%s)"
  printf '%s\n' "$(( now - started ))"
}

clear_stale_lock_dir() {
  local lock_dir="$1" stale_after="${2:-3600}" age owner_pid
  [[ -d "$lock_dir" ]] || return 1
  age="$(lock_age_seconds "$lock_dir")" || return 1
  owner_pid="$(cat "$lock_dir/owner.pid" 2>/dev/null || true)"
  if [[ "$owner_pid" =~ ^[0-9]+$ ]] && ! kill -0 "$owner_pid" 2>/dev/null; then
    rm -rf "$lock_dir"
    return 0
  fi
  if [[ "$age" -ge "$stale_after" ]]; then
    if [[ "$owner_pid" =~ ^[0-9]+$ ]] && kill -0 "$owner_pid" 2>/dev/null; then
      return 1
    fi
    rm -rf "$lock_dir"
    return 0
  fi
  return 1
}

acquire_lock_dir() {
  local lock_dir="$1" stale_after="${2:-3600}"
  mkdir -p "$(dirname -- "$lock_dir")"
  if mkdir "$lock_dir" 2>/dev/null; then
    printf '%s\n' "$$" > "$lock_dir/owner.pid" || { rm -rf "$lock_dir"; return 1; }
    printf '%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$lock_dir/started-at.txt" || true
    printf '%s\n' "$0 $*" > "$lock_dir/owner.command" || true
    return 0
  fi
  clear_stale_lock_dir "$lock_dir" "$stale_after" >/dev/null 2>&1 || return 1
  mkdir "$lock_dir"
  printf '%s\n' "$$" > "$lock_dir/owner.pid" || { rm -rf "$lock_dir"; return 1; }
  printf '%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$lock_dir/started-at.txt" || true
  printf '%s\n' "$0 $*" > "$lock_dir/owner.command" || true
}

release_lock_dir() {
  local lock_dir="$1" owner_pid
  [[ -d "$lock_dir" ]] || return 0
  owner_pid="$(cat "$lock_dir/owner.pid" 2>/dev/null || true)"
  if [[ "$owner_pid" == "$$" ]]; then
    rm -rf "$lock_dir"
  fi
}

acquire_bill_heavy_slot() {
  local root lock_dir stale_after max_jobs
  max_jobs="${BILL_MAX_HEAVY_JOBS:-1}"
  if [[ ! "$max_jobs" =~ ^[0-9]+$ ]]; then
    max_jobs="1"
  fi
  if (( max_jobs != 1 )); then
    return 0
  fi
  root="$(bill_repo_root)"
  lock_dir="${BILL_HEAVY_JOB_LOCK_DIR:-$root/.rumbling-hedge/run/heavy-job.lock}"
  stale_after="${BILL_HEAVY_JOB_STALE_LOCK_SECONDS:-21600}"
  acquire_lock_dir "$lock_dir" "$stale_after" || return 1
  printf '%s\n' "$lock_dir"
}

bill_skip_if_low_heavy_disk() {
  local command_name="$1" root min_free_gb free_kb required_kb free_gb
  root="$(bill_repo_root)"
  min_free_gb="${BILL_HEAVY_MIN_FREE_GB:-5}"
  if [[ ! "$min_free_gb" =~ ^[0-9]+$ ]]; then
    return 0
  fi
  free_kb="$(df -Pk "$root" | awk 'NR==2 {print $4}')"
  [[ "$free_kb" =~ ^[0-9]+$ ]] || return 0
  required_kb="$((min_free_gb * 1024 * 1024))"
  if (( free_kb < required_kb )); then
    free_gb="$(awk -v kb="$free_kb" 'BEGIN { printf "%.2f", kb / 1024 / 1024 }')"
    printf '{\n  "command": "%s",\n  "status": "skipped",\n  "reason": "SSD free space below BILL_HEAVY_MIN_FREE_GB",\n  "freeGb": %s,\n  "minFreeGb": %s\n}\n' "$command_name" "$free_gb" "$min_free_gb"
    return 1
  fi
  return 0
}
