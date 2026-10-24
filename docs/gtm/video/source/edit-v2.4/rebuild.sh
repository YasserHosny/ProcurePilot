#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PY=/home/yasserhosny/Work/pp-video-env/bin/python
export NODE_PATH=/home/yasserhosny/Work/Projects/ProcurePilot/apps/web/node_modules
export PP_CHROME=/usr/bin/google-chrome
mkdir -p proof tmp
export TMPDIR="$PWD/tmp"
case "${1:-render}" in
 privacy)
  "$PY" privacy.py before | tee proof/before-native.log
  "$PY" privacy.py mask | tee proof/mask.log
  "$PY" privacy.py after | tee proof/after-native.log
  "$PY" privacy.py control | tee proof/control-native.log
  ;;
 prepare)
  "$PY" extract.py
  "$PY" make_data.py
  "$PY" make_textures.py
  node check_timeline.cjs
  "$PY" audio.py
  ;;
 render)
  # Chrome's singleton socket path must stay under ~107 bytes: render with a short temp dir.
  export TMPDIR="$(mktemp -d /tmp/pp-render-XXXX)"
  for lang in ar en; do
   node render.cjs h "$lang" "frames-$lang-h" 0 3030
   node render.cjs v "$lang" "frames-$lang-v" 0 1530
  done
  "$PY" finish.py
  ;;
 *) echo 'usage: bash rebuild.sh privacy|prepare|render' >&2; exit 2 ;;
esac
