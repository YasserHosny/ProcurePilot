#!/usr/bin/env bash
set -euo pipefail
V2=$(cd -- "$(dirname -- "$0")" && pwd)
SCRATCH=$(cd -- "$V2/../.." && pwd)
export TMPDIR="$V2/tmp" XDG_CACHE_HOME="$V2/tmp" PYTHONPYCACHEPREFIX="$V2/tmp/pycache"
mkdir -p "$TMPDIR"
# This sandbox needs the Raqm fallback; the original requested renderer is retained.
if ! node "$V2/render_cards_v2.cjs" > "$V2/graphics.log" 2>&1; then
  "$SCRATCH/vid/bin/python" "$V2/render_fallback.py"
fi
"$SCRATCH/vid/bin/python" "$V2/audit.py" > "$V2/analysis/audit-pts.log" 2>&1
"$SCRATCH/vid/bin/python" "$V2/audit_phone_list.py"
"$SCRATCH/vid/bin/python" "$V2/audit_extra.py"
"$SCRATCH/vid/bin/python" "$V2/verify_masks.py"
"$SCRATCH/vid/bin/python" "$V2/build_v2.py" > "$V2/build.log" 2>&1
"$SCRATCH/vid/bin/python" "$V2/qa.py" > "$V2/qa.log" 2>&1

"$SCRATCH/vid/bin/python" "$V2/verify_output_masks.py" > "$V2/output-mask-check.log" 2>&1
"$SCRATCH/vid/bin/python" "$V2/report.py"
