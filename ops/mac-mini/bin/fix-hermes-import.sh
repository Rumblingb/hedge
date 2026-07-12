#!/bin/bash
set -euo pipefail

# Create symlink from src to dist for hermesSupervisor
script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$(CDPATH='' cd -- "$script_dir/../../.." && pwd)"
mkdir -p src/engine
ln -sf ../../dist/src/engine/hermesSupervisor.js src/engine/hermesSupervisor.js 2>/dev/null || true

echo "Symlink created: $(ls -la src/engine/hermesSupervisor.js)"
echo "Testing import..."
node -e "import('./dist/src/engine/hermesSupervisor.js').then(() => console.log('✅ dist import works')).catch(e => console.error('❌', e.message))"
