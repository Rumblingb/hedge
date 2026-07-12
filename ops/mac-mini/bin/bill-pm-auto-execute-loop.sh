#!/bin/bash
# QUARANTINED: this legacy loop patched safety gates and attempted live
# prediction execution. It is kept only as an audit artifact.
set -euo pipefail

echo "bill-pm-auto-execute-loop.sh is quarantined and will not run." >&2
echo "Reason: legacy script mutated prediction-review/promotion gates before execution." >&2
echo "Use the guarded prediction cycle and promotion review instead." >&2
exit 42
