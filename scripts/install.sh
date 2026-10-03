#!/usr/bin/env bash
# Install the skills into a Claude Code skills directory.
#   ./scripts/install.sh            -> ~/.claude/skills   (personal, all projects)
#   ./scripts/install.sh --project  -> ./.claude/skills   (current project only)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$HOME/.claude/skills"
[ "${1:-}" = "--project" ] && DEST="$PWD/.claude/skills"
mkdir -p "$DEST"
for s in "$ROOT"/skills/*/; do
  name="$(basename "$s")"
  rm -rf "$DEST/$name"
  cp -r "$s" "$DEST/$name"
  echo "installed $name -> $DEST/$name"
done
