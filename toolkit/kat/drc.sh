#!/bin/bash
# drc.sh BOARD.kicad_pcb [OUTDIR] [--parity]
# Refill the zones on a COPY (with the board's own .kicad_pro / .kicad_dru next to it), run kicad-cli DRC, summarise.
# kicad-cli checks the SAVED fills, so a board edited by script must be refilled first or zone results are stale.
set -e
B=$(readlink -f "$1"); O=${2:-/tmp/kat_drc_$(basename "$B" .kicad_pcb)}; PAR=""
[ "$3" = "--parity" ] && PAR="--schematic-parity"
HERE=$(dirname "$(readlink -f "$0")")
rm -rf "$O"; mkdir -p "$O"; base="${B%.kicad_pcb}"
cp "$B" "$O/b.kicad_pcb"
for e in kicad_pro kicad_dru; do [ -f "$base.$e" ] && cp "$base.$e" "$O/b.$e"; done
python3 - "$O/b.kicad_pcb" <<'PY' 2>&1 | grep -v "assert\|leak\|Debug" || true
import sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1]); pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save(sys.argv[1])
PY
kicad-cli pcb drc $PAR --format json --severity-all -o "$O/out.json" "$O/b.kicad_pcb" >/dev/null 2>&1 || true
python3 "$HERE/drcsum.py" "$O/out.json"
