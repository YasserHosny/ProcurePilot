#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/deps"
PP_PYTHON="$PWD/../../vid/bin/python"
# Source survey provides the English template image and native raw QA frames.
"$PP_PYTHON" survey_en.py
"$PP_PYTHON" mask_en.py
"$PP_PYTHON" render_fallback_en.py
# Clear only generated English segment caches to make EDL changes reproducible.
"$PP_PYTHON" - <<'PY'
from pathlib import Path
import shutil
p=Path('segments-en')
if p.exists():shutil.rmtree(p)
PY
"$PP_PYTHON" build_en.py
"$PP_PYTHON" privacy_proofs_en.py
"$PP_PYTHON" native_privacy_sheets_en.py
"$PP_PYTHON" audit_masked_en.py
"$PP_PYTHON" qa_en.py
"$PP_PYTHON" verify_en_outputs.py
"$PP_PYTHON" action_coverage_en.py
"$PP_PYTHON" source_actions_en.py
"$PP_PYTHON" report_en.py
