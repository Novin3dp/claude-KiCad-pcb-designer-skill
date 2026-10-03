#!/usr/bin/env bash
# Build distributable .skill archives (zip files containing <skill-name>/...) into ./dist
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/dist"
cd "$ROOT/skills"
for s in */; do
  name="${s%/}"
  rm -f "$ROOT/dist/$name.skill"
  zip -qr "$ROOT/dist/$name.skill" "$name" -x '*/__pycache__/*'
  echo "built dist/$name.skill"
done
