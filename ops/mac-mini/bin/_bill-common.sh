#!/bin/bash
set -euo pipefail

bill_bin_dir() {
  CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd
}

bill_repo_root() {
  CDPATH='' cd -- "$(bill_bin_dir)/../../.." && pwd
}

bill_default_path() {
  printf '%s\n' "/opt/homebrew/opt/node/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
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

load_bill_env() {
  local env_file
  env_file="$(bill_env_file)"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
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
}

run_bill_cli() {
  local root tsx
  ensure_bill_path
  root="$(bill_repo_root)"
  tsx="$(bill_tsx)"
  ensure_bill_runtime_dirs
  load_bill_env
  (
    cd "$root"
    "$tsx" src/cli.ts "$@"
  )
}
