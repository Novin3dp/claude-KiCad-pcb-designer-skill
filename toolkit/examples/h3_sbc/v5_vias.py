#!/usr/bin/env python3
"""v5 review fixes that only add vias (all clearance-checked by viatool):
  * RTL8189FTV exposed pad: GND via array (epoxy filled + capped)
  * GND stitching on both sides of the Wi-Fi RF feed (WL_RF / WL_RF_A / WL_RF_B) at ~1.2 mm pitch
  * extra GND vias next to the buck GND pins and their input-cap GND pads (shorter hot loops through L2)
  * extra VMOD_5V vias where the D4 anode pad overlaps the MP1584 OUT+ pad
usage: v5_vias.py IN OUT"""
import sys, math
import pcbnew
from shapely.geometry import Point, LineString, box
from viatool import Tool, short
MM = 1e6
src, dst = sys.argv[1:3]
b = pcbnew.LoadBoard(src)
T = Tool(b, cl=0.12, hole_gap=0.25)
FP = {f.GetReference(): f for f in b.GetFootprints()}


def pad(ref, num):
    return [p for p in FP[ref].Pads() if p.GetNumber() == num][0]


def pbox(p):
    bb = p.GetBoundingBox()
    return box(bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)


log = []
# 1. U8 exposed pad
ep = pad('U8', '25'); cx, cy = ep.GetPosition().x / MM, ep.GetPosition().y / MM
_epb = pbox(ep)
T.obst = [o for o in T.obst if not (o[2] == '' and o[0].intersects(_epb))]   # paste-only sub-pads of the EP
n = 0
for dx in (-0.6, 0.0, 0.6):
    for dy in (-0.6, 0.0, 0.6):
        n += T.via(cx + dx, cy + dy, 'GND', 0.31, 0.15)
log.append('U8 EP: %d GND vias' % n)
# 2. RF stitching
rf = [t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK' and short(t.GetNetname()) in ('WL_RF', 'WL_RF_A', 'WL_RF_B')]
n = 0
for t in rf:
    ax, ay, bx, by = t.GetStart().x / MM, t.GetStart().y / MM, t.GetEnd().x / MM, t.GetEnd().y / MM
    L = math.hypot(bx - ax, by - ay)
    if L < 0.3:
        continue
    ux, uy = (bx - ax) / L, (by - ay) / L
    k = max(1, int(L / 1.2) + 1)
    for i in range(k + 1):
        s = L * i / k
        for side in (1, -1):
            for off in (0.70, 0.80, 0.95):
                x, y = ax + ux * s - uy * off * side, ay + uy * s + ux * off * side
                if T.via(x, y, 'GND', 0.31, 0.15):
                    n += 1; break
log.append('RF stitching: %d GND vias' % n)
# 3. buck GND pins + input-cap GND pads
n = 0
for ref, num in (('U2', '1'), ('U3', '1'), ('U4', '1'), ('U5', '1'), ('C2', '2'), ('C4', '2'), ('C9', '2'), ('C11', '2'),
                 ('C17', '2'), ('C18', '2'), ('C23', '2'), ('C24', '2')):
    p = pad(ref, num)
    if short(p.GetNetname()) != 'GND':
        log.append('  skip %s.%s (%s)' % (ref, num, p.GetNetname())); continue
    px, py = p.GetPosition().x / MM, p.GetPosition().y / MM
    got = 0
    cands = sorted(((px + r * math.cos(a), py + r * math.sin(a)) for r in (0.55, 0.7, 0.85, 1.0, 1.2) for a in [k * math.pi / 8 for k in range(16)]),
                   key=lambda q: math.hypot(q[0] - px, q[1] - py))
    for x, y in cands:
        if got >= 2:
            break
        lay = pcbnew.B_Cu if FP[ref].IsFlipped() else pcbnew.F_Cu
        if T.via_ok(x, y, 'GND', 0.4, 0.2) and T.track_ok([(px, py), (x, y)], 'GND', 0.3, lay):
            T.via(x, y, 'GND', 0.4, 0.2, check=False)
            T.track([(px, py), (x, y)], 'GND', 0.3, lay, check=False)
            got += 1
    n += got
log.append('buck GND: %d vias' % n)
# 4. VMOD_5V: D4 anode pad x U9 OUT+ pad
got = []
if T.track([(63.1, 44.7), (62.6, 46.85)], 'VMOD_5V', 1.0, pcbnew.F_Cu):
    got = T.vias_in(box(61.75, 45.6, 63.5, 47.2), 'VMOD_5V', 4, pitch=0.85, d=0.6, dr=0.3)
log.append('VMOD_5V: top strap D4 -> OUT+ pad + %d vias %s' % (len(got), got))
T.commit(fill=False)
b.Save(dst)
print('\n'.join(log))
