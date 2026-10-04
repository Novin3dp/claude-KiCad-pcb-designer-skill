#!/usr/bin/env python3
"""v5 ECO step: re-place the VCC_DRAM buck block (U5 rotated so SW faces L4, input cap at VIN) and turn the microSD
socket J10 so its card slot faces the board edge.  Copper hanging on the moved parts' old pads is deleted, and so is
every foreign track / via that the new pads would hit (the nets are re-routed afterwards).
usage: v5_move.py IN OUT   (prints the nets that need routing)"""
import sys
import pcbnew
from shapely.geometry import Point, LineString, box
MM = 1e6
src, dst = sys.argv[1:3]
b = pcbnew.LoadBoard(src)
short = lambda n: n.split('/')[-1]
F = {r: b.FindFootprintByReference(r) for r in ('U5', 'L4', 'C23', 'C26', 'J10')}
MOVES = {'U5': (60.5, 10.6, 180.0), 'L4': (64.5, 10.9, None), 'C23': (62.1, 8.0, 0.0), 'C26': (68.18, 12.2, 0.0),
         'J10': (76.875, 15.5, 270.0)}
TR = list(b.GetTracks())


def geom(t):
    if t.GetClass() == 'PCB_VIA':
        return Point(t.GetPosition().x / MM, t.GetPosition().y / MM).buffer(t.GetWidth(pcbnew.F_Cu) / MM / 2), None
    return LineString([(t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM)]).buffer(t.GetWidth() / MM / 2), t.GetLayer()


def padgeo(p, grow=0.0):
    bb = p.GetBoundingBox()
    return box(bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM).buffer(grow)


G = [geom(t) for t in TR]
kill = set()
# 1. copper on the old pads
for r, f in F.items():
    lay = pcbnew.B_Cu if f.IsFlipped() else pcbnew.F_Cu
    for p in f.Pads():
        pg = padgeo(p, 0.01)
        for i, t in enumerate(TR):
            g, l = G[i]
            if t.GetNetCode() == p.GetNetCode() and p.GetNetCode() > 0 and (l is None or l == lay) and g.intersects(pg):
                kill.add(i)
# 2. move
for r, (x, y, rot) in MOVES.items():
    f = F[r]
    if rot is not None:
        f.SetOrientationDegrees(rot)
    f.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(y * MM)))
# L4: rot 0 puts pad 1 (SW) on the left, facing U5
F['L4'].SetOrientationDegrees(0.0)
L4 = F['L4']
print('L4 rot', L4.GetOrientationDegrees(), [(p.GetNumber(), p.GetPosition().x / MM, p.GetPosition().y / MM) for p in L4.Pads()])
for r in ('U5', 'C23', 'C26', 'J10'):
    print(r, [(p.GetNumber(), round(p.GetPosition().x / MM, 3), round(p.GetPosition().y / MM, 3), short(p.GetNetname())) for p in F[r].Pads()])
# 3. foreign copper the new pads hit (0.12 mm clearance)
nets = set()
for r, f in F.items():
    lay = pcbnew.B_Cu if f.IsFlipped() else pcbnew.F_Cu
    for p in f.Pads():
        pg = padgeo(p, 0.13)
        for i, t in enumerate(TR):
            g, l = G[i]
            if (l is None or l == lay or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH) and g.intersects(pg) and \
                    (t.GetNetCode() != p.GetNetCode() or p.GetNetCode() == 0):
                kill.add(i)
RIPALL = {'DRAM_SW', 'DRAM_BST', 'SD_D0', 'SD_D1', 'SD_D2', 'SD_D3', 'SD_CMD', 'SD_CLK', 'SD_DET', 'SD_VDD'}
for i, t in enumerate(TR):
    if short(t.GetNetname()) in RIPALL and not t.IsLocked():
        kill.add(i)
for i in kill:
    nets.add(short(TR[i].GetNetname()))
print('removing %d tracks/vias; nets: %s' % (len(kill), ' '.join(sorted(nets))))
for i in sorted(kill):
    b.Remove(TR[i])
b.Save(dst)
