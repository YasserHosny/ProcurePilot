#!/bin/bash
# v2.5 build for every market: data, textures, frames (3 Chrome workers per cut), audio, final cuts.
# usage: ./rebuild.sh [job ...]   jobs look like eg-ar-h or sa-en-en-v; default all. Needs the plates-<market> links.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-/home/yasserhosny/Work/pp-video-env/bin/python}
export NODE_PATH=${NODE_PATH:-/home/yasserhosny/Work/Projects/ProcurePilot/apps/web/node_modules}
export PP_CHROME=${PP_CHROME:-/usr/bin/google-chrome}
export TMPDIR=$(mktemp -d /tmp/pp-r-XXXX)
$PY make_data.py
[ -d tex/ie ] || $PY make_textures.py
JOBS=("$@"); [ ${#JOBS[@]} -gt 0 ] || mapfile -t JOBS < <($PY -c "import json;from paths import jobs;print('\n'.join('-'.join(j) for j in jobs(json.load(open('timeline.json')))))")
for job in "${JOBS[@]}"; do
  fmt=${job##*-}; rest=${job%-*}; lang=${rest##*-}; market=${rest%-*}
  n=$($PY -c "import json;print(round(json.load(open('timeline.json'))['$market']['$fmt']['body']*30))")
  out=frames-$job; have=$( [ -d $out ] && ls $out | wc -l || echo 0)
  if [ "$have" != "$n" ] || [ -n "${FORCE:-}" ]; then
    a=$((n/3)); b=$((2*n/3))
    node render.cjs $market $fmt $lang $out 0 $a & p1=$!
    node render.cjs $market $fmt $lang $out $a $b & p2=$!
    node render.cjs $market $fmt $lang $out $b $n & p3=$!
    wait $p1 && wait $p2 && wait $p3
  fi
  [ "$(ls $out | wc -l)" = "$n" ] || { echo "frame count mismatch for $job"; exit 1; }
  echo "rendered $job ($n frames)"
done
ONLY=$(IFS=,; echo "${JOBS[*]}")
$PY audio.py --only "$ONLY" > proof/audio-run.log
$PY finish.py --only "$ONLY" > proof/finish-run.log
echo DONE
