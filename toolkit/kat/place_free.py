#!/usr/bin/env python3
"""place one footprint at the free spot closest to a target point.
usage: place_free.py IN OUT REF X Y RADIUS SIDE(F|B) [ROTS=0,90] [CL=0.15]
Free = its pads keep CL from foreign copper (tracks / vias / pads) on its copper layer and from every via / PTH,
and its courtyard does not overlap another courtyard on the same side.  Zones are ignored (refilled later)."""
import sys, math
import pcbnew
from shapely.geometry import Point, LineString, box, Polygon
from shapely.ops import unary_union
MM = 1e6
src, dst, ref = sys.argv[1:4]
X, Y, RAD = map(float, sys.argv[4:7]); side = sys.argv[7]
ROTS = [float(r) for r in (sys.argv[8] if len(sys.argv) > 8 else '0,90').split(',')]
CL = float(sys.argv[9]) if len(sys.argv) > 9 else 0.15
b = pcbnew.LoadBoard(src)
f = b.FindFootprintByReference(ref)
lay = pcbnew.B_Cu if side == 'B' else pcbnew.F_Cu
if (side == 'B') != f.IsFlipped():
    f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
cy_layer = pcbnew.B_CrtYd if side == 'B' else pcbnew.F_CrtYd
obst = []
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA':
        c = t.GetPosition(); obst.append((Point(c.x / MM, c.y / MM).buffer(t.GetWidth(pcbnew.F_Cu) / MM / 2), t.GetNetCode()))
    elif t.GetLayer() == lay:
        obst.append((LineString([(t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM)]).buffer(t.GetWidth() / MM / 2), t.GetNetCode()))
crt = []
for g in b.GetFootprints():
    if g.GetReference() == ref:
        continue
    for p in g.Pads():
        if p.IsOnLayer(lay) or p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            bb = p.GetBoundingBox()
            obst.append((box(bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM), p.GetNetCode() if p.GetNetCode() else -1))
    if g.IsFlipped() == (side == 'B'):
        cy = g.GetCourtyard(cy_layer)
        if cy.OutlineCount():
            o = cy.Outline(0)
            crt.append(Polygon([(o.CPoint(i).x / MM, o.CPoint(i).y / MM) for i in range(o.PointCount())]))
_win = box(X - RAD - 4, Y - RAD - 4, X + RAD + 4, Y + RAD + 4)
obst = [(g, n) for g, n in obst if g.intersects(_win)]
crt = [c for c in crt if c.intersects(_win)]
from shapely.strtree import STRtree
edge = b.GetBoardEdgesBoundingBox()
ex0, ey0, ex1, ey1 = edge.GetLeft() / MM + 0.5, edge.GetTop() / MM + 0.5, edge.GetRight() / MM - 0.5, edge.GetBottom() / MM - 0.5
crt_u = unary_union(crt)
TREE = STRtree([g for g, n in obst])


def ok():
    for p in f.Pads():
        bb = p.GetBoundingBox()
        g = box(bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)
        if not (ex0 < g.bounds[0] and g.bounds[2] < ex1 and ey0 < g.bounds[1] and g.bounds[3] < ey1):
            return False
        gg = g.buffer(CL)
        for k in TREE.query(gg):
            og, nc = obst[k]
            if (nc != p.GetNetCode() or nc <= 0) and gg.intersects(og):
                return False
    cy = f.GetCourtyard(cy_layer)
    if cy.OutlineCount():
        o = cy.Outline(0)
        poly = Polygon([(o.CPoint(i).x / MM, o.CPoint(i).y / MM) for i in range(o.PointCount())])
        if poly.intersection(crt_u).area > 1e-4:
            return False
    return True


best = None
st = 0.1
n = int(RAD / st)
cands = sorted(((i * st, j * st) for i in range(-n, n + 1) for j in range(-n, n + 1) if math.hypot(i, j) * st <= RAD), key=lambda d: math.hypot(*d))
for dx, dy in cands:
    for r in ROTS:
        f.SetOrientationDegrees(r)
        f.SetPosition(pcbnew.VECTOR2I(int((X + dx) * MM), int((Y + dy) * MM)))
        if ok():
            best = (X + dx, Y + dy, r); break
    if best:
        break
if not best:
    print('NO SPOT'); sys.exit(1)
f.SetOrientationDegrees(best[2]); f.SetPosition(pcbnew.VECTOR2I(int(best[0] * MM), int(best[1] * MM)))
b.Save(dst)
print('%s at %.2f %.2f rot %g (%.2f mm from target)' % (ref, best[0], best[1], best[2], math.hypot(best[0] - X, best[1] - Y)))
