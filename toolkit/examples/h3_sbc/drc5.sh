#!/bin/bash
# drc5.sh BOARD TAG : refill zones on a copy, run kicad-cli DRC (with parity vs schematic), summarise
cd /home/claude/h3-two-board/pcb
B=$1; T=$2; O=out/sbc/drc_$T; rm -rf $O; mkdir -p $O
cp $B $O/b.kicad_pcb; cp out/sbc2/v5/e0.kicad_pro $O/b.kicad_pro; cp out/sbc2/v5/e0.kicad_dru $O/b.kicad_dru
python3 - <<PY 2>&1 | grep -v "assert\|leak\|Debug"
import pcbnew
b=pcbnew.LoadBoard('$O/b.kicad_pcb'); pcbnew.ZONE_FILLER(b).Fill(b.Zones()); b.Save('$O/b.kicad_pcb')
PY
kicad-cli pcb drc --format json --severity-all -o $O/out.json $O/b.kicad_pcb >/dev/null 2>&1
python3 drcfull.py $T
