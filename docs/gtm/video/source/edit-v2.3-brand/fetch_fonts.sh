#!/usr/bin/env bash
# Readex Pro 300-700 as static TTFs (rp1..rp5) from Google Fonts.
set -euo pipefail; cd "$(dirname "$0")"; mkdir -p fonts
i=0; for u in $(curl -fsS -A "Mozilla/4.0" "https://fonts.googleapis.com/css2?family=Readex+Pro:wght@300;400;500;600;700" | grep -o "https://[^)]*"); do i=$((i+1)); curl -fsS -o fonts/rp$i.ttf "$u"; done
