#!/bin/bash
# Smoke test of the generic tools on the demo board (run examples/demo/run_demo.sh first). Every step must exit 0.
set -e
cd "$(dirname "$0")/../examples/demo"
K=../../kat; T=/tmp/kat_smoke; rm -rf $T; mkdir -p $T
q(){ grep -v "assert\|leak\|Debug" || true; }
for f in a b c d e f g; do cp demo.kicad_pro $T/$f.kicad_pro; done
# coordinates of two pads of net SCL on the unrouted board
read X1 Y1 X2 Y2 < <(python3 - <<'PY' 2>/dev/null
import pcbnew
b = pcbnew.LoadBoard('demo_planes.kicad_pcb')
p = [q for f in b.GetFootprints() for q in f.Pads() if q.GetNetname() == 'SCL' and f.GetReference() in ('R5', 'J1')]
p.sort(key=lambda q: q.GetParentFootprint().GetReference())
print(*['%.3f %.3f' % (q.GetPosition().x / 1e6, q.GetPosition().y / 1e6) for q in p[:2]])
PY
)
echo "== astar1 (SCL $X1,$Y1 -> $X2,$Y2)"; python3 $K/astar1.py demo_planes.kicad_pcb $T/a.kicad_pcb SCL $X1,$Y1,via $X2,$Y2,F.Cu F.Cu,B.Cu 0,0,45,32 0.2 0.2 2>&1 | q
echo "== place_free";  python3 $K/place_free.py demo_routed.kicad_pcb $T/b.kicad_pcb C3 20 27 4 F 0,90 0.2 2>&1 | q
echo "== restore_net"; python3 $K/restore_net.py demo_routed.kicad_pcb demo_planes.kicad_pcb $T/c.kicad_pcb SDA 0.2 2>&1 | q
echo "== gnd_pour";    python3 $K/gnd_pour.py demo_routed.kicad_pcb $T/d.kicad_pcb 2>&1 | q
echo "== silk_refs";   python3 $K/silk_refs.py demo_routed.kicad_pcb $T/e.kicad_pcb 2>&1 | q
read VX VY < <(python3 -c "
import pcbnew; b=pcbnew.LoadBoard('demo_routed.kicad_pcb')
v=[t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and not t.IsLocked()][0]; print('%.4f %.4f'%(v.GetPosition().x/1e6,v.GetPosition().y/1e6))" 2>/dev/null)
echo "== movevia ($VX,$VY)"; python3 $K/movevia.py demo_routed.kicad_pcb $T/f.kicad_pcb $VX,$VY 0.05,0 2>&1 | q
echo "== drc + dangle2";  $K/drc.sh demo_routed.kicad_pcb $T/drc > /dev/null; python3 $K/dangle2.py demo_routed.kicad_pcb $T/g.kicad_pcb $T/drc/out.json 2>&1 | q
echo "== cluster_link";   python3 $K/cluster_link.py $T/d.kicad_pcb $T/h.kicad_pcb GND 0.2 2>&1 | q | tail -2
echo "== layerplot / netplot"; python3 $K/layerplot.py demo_routed.kicad_pcb $T/l1.png F.Cu 2>&1 | q; python3 $K/netplot.py demo_routed.kicad_pcb $T/n.png 0,0,45,32 'SCL|SDA=red' 2>&1 | q
echo "== drc of the pour board"; $K/drc.sh $T/d.kicad_pcb $T/drc_d | head -3
ls $T/*.png >/dev/null && echo "SMOKE OK"
