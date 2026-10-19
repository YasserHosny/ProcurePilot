#!/usr/bin/env bash
# Download the licensed third-party media used by the demo video and verify it byte for byte.
# These files are NOT committed: Pixabay's licence forbids distributing content on a standalone
# basis and Pexels forbids redistributing unaltered copies, and this repository is public.
set -euo pipefail
cd "$(dirname "$0")"
fetch() { # url referer dest sha256
  mkdir -p "$(dirname "$3")"
  [ -f "$3" ] || curl -fsSL -A "Mozilla/5.0" -e "$2" -o "$3" "$1"
  echo "$4  $3" | sha256sum -c -
}
fetch "https://cdn.pixabay.com/audio/2022/09/03/audio_d444c2f0d2.mp3" \
  "https://pixabay.com/music/soft-house-antalya-beaches-119047/" \
  music/dayfox-antalya-beaches-119047.mp3 b7d4d3f8a6454b5456e91b1117c44521ffac4a0b093d72ffc246672cd3b62878
fetch "https://www.pexels.com/download/video/4253325/?fps=25&h=1080&w=2048" \
  "https://www.pexels.com/video/two-men-in-aprons-are-working-in-a-kitchen-4253325/" \
  source/stock/pexels-4253325-kitchen-2048x1080.mp4 d592ccaf173821c9b75d00bf53215db5f82403fb572bc0a7bcbad2223841bfd6
fetch "https://www.pexels.com/download/video/31735802/" \
  "https://www.pexels.com/video/chef-grilling-meat-in-a-busy-kitchen-31735802/" \
  source/stock/pexels-31735802-chef-grill-2160x3840.mp4 013025ea54abcefd47ff78d01dbef34b6b3ef3d97e7e7ad75730ac6f24e973a2
