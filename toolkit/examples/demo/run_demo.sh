#!/bin/bash
# End-to-end demo: build an unrouted board, drop plane vias, autoroute, DRC, viewer.   Run from this folder.
set -e
K=../../kat
python3 make_demo.py demo.kicad_pcb
for f in demo_planes demo_routed; do cp demo.kicad_pro $f.kicad_pro; done
python3 $K/plane_via.py demo.kicad_pcb demo_planes.kicad_pcb GND,+3V3 2.0
python3 -u $K/ncroute.py cfg_demo.py demo_planes.kicad_pcb demo_routed.kicad_pcb 40
$K/drc.sh demo_routed.kicad_pcb /tmp/kat_demo_drc
python3 $K/make_viewer.py -o demo_viewer.html --name "KAT demo" demo.kicad_pcb=placed demo_routed.kicad_pcb=routed
