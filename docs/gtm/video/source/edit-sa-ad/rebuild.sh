#!/bin/bash
# Saudi ad cut: voice timing -> assets -> frames (4 Chrome workers) -> sound -> mp4. usage: ./rebuild.sh [h] [v]
# Needs: ffmpeg, python3 (numpy, pillow), node with playwright + Chromium, ../../fetch-assets.sh run once (music),
# fonts/ReadexPro.ttf (see README). vo/*.mp3 are committed (align_vo.py cuts them from vo/elevenlabs-full.mp3).
set -euo pipefail
cd "$(dirname "$0")"
export NODE_PATH=${NODE_PATH:-$(npm root -g)}
mkdir -p build
python3 prep_vo.py
[ -f build/assets.js ] || python3 make_assets.py
python3 audio.py
N=$(python3 -c "import json;print(round(json.load(open('timeline.json'))['duration']*30))")
OUT=../../cuts/gcc-sa-ad-v1; mkdir -p "$OUT"
for fmt in "${@:-h v}"; do for f in $fmt; do
  d=build/frames-$f; rm -rf $d; W=4; pids=()
  for i in $(seq 0 $((W-1))); do node render.cjs $f $d $((N*i/W)) $((N*(i+1)/W)) & pids+=($!); done
  for p in "${pids[@]}"; do wait $p; done
  [ "$(ls $d | wc -l)" = "$N" ] || { echo "frame count mismatch"; exit 1; }
  name=procurepilot-ad-sa-ar-$([ $f = h ] && echo 16x9 || echo 9x16).mp4
  ffmpeg -v error -y -framerate 30 -i $d/%05d.jpg -i build/mix.wav -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p \
    -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a aac -b:a 256k -movflags +faststart -shortest "$OUT/$name"
  echo "built $OUT/$name"
done; done
cp build/captions.srt "$OUT/procurepilot-ad-sa-ar.srt"
