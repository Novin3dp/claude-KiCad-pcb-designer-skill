#!/usr/bin/env python3
"""Connect orphan plane pads: for every pad of the given nets that has no copper of its own net attached, drop a
0.40/0.20 via (or 0.31/0.15 when space is tight) within R of the pad, on a spot that keeps DRC clearance to all
foreign copper on every layer and lies inside a filled zone of that net on some inner layer, plus a stub on the
pad layer.   usage: plane_via.py IN OUT NET[,NET...] [R]"""
import sys, math, os
import pcbnew
from shapely.geometry import Point, LineString, Polygon, box
from shapely.strtree import STRtree
MM = 1e6
src, dst, nets = sys.argv[1], sys.argv[2], set(sys.argv[3].split(','))
R = float(sys.argv[4]) if len(sys.argv) > 4 else 1.6
CLR = 0.13
b = pcbnew.LoadBoard(src)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
CU = list(b.GetEnabledLayers().CuStack())      # every copper layer of this board
INNER = [l for l in CU if l not in (pcbnew.F_Cu, pcbnew.B_Cu)]
short = lambda n: n.split('/')[-1]
geo, gnet = [], []          # foreign-copper obstacles (all layers merged: a through via hits them all)
plane = {}                  # net -> filled zone shapes on inner layers
for z in b.Zones():
    if z.GetIsRuleArea():
        continue
    for l in z.GetLayerSet().Seq():
        ps = z.GetFilledPolysList(l)
        for i in range(ps.OutlineCount()):
            ol = ps.Outline(i)
            g = Polygon([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())]).buffer(0)
            if l in INNER:
                plane.setdefault(short(z.GetNetname()), []).append(g)
for f in b.GetFootprints():
    for p in f.Pads():
        ps = pcbnew.SHAPE_POLY_SET()
        p.TransformShapeToPolygon(ps, pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
        for i in range(ps.OutlineCount()):
            ol = ps.Outline(i)
            geo.append(Polygon([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())])); gnet.append(p.GetNetCode())
        if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            geo.append(Point(p.GetPosition().x / MM, p.GetPosition().y / MM).buffer(max(p.GetSize().x, p.GetSize().y) / MM / 2)); gnet.append(p.GetNetCode())
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA':
        geo.append(Point(t.GetPosition().x / MM, t.GetPosition().y / MM).buffer(t.GetWidth(pcbnew.F_Cu) / MM / 2)); gnet.append(t.GetNetCode())
    else:
        geo.append(LineString([(t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM)]).buffer(t.GetWidth() / MM / 2)); gnet.append(t.GetNetCode())
for z in [z for f in b.GetFootprints() for z in f.Zones()] + list(b.Zones()):
    if z.GetIsRuleArea() and z.GetDoNotAllowVias():
        o = z.Outline()
        for i in range(o.OutlineCount()):
            ol = o.Outline(i)
            geo.append(Polygon([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())]).buffer(0)); gnet.append(-1)
tree = STRtree(geo)
edge = b.GetBoardEdgesBoundingBox()
BX = box(edge.GetLeft() / MM + 0.5, edge.GetTop() / MM + 0.5, edge.GetRight() / MM - 0.5, edge.GetBottom() / MM - 0.5)


ENDS = {}
for t in b.GetTracks():
    pts = [t.GetPosition()] if t.GetClass() == 'PCB_VIA' else [t.GetStart(), t.GetEnd()]
    ENDS.setdefault(t.GetNetCode(), []).extend((q.x, q.y) for q in pts)


def attached(p):
    """own-net copper touching the pad"""
    bb = p.GetBoundingBox()
    for x, y in ENDS.get(p.GetNetCode(), []):
        if bb.GetLeft() <= x <= bb.GetRight() and bb.GetTop() <= y <= bb.GetBottom() and p.HitTest(pcbnew.VECTOR2I(x, y)):
            return True
    return False


def free(g, code):
    for i in tree.query(g.buffer(CLR)):
        if gnet[i] != code and g.distance(geo[i]) < CLR:
            return False
    return True


from shapely.prepared import prep
PLB = {}
for n_, gs in plane.items():
    if n_ in nets:
        for vd_ in (0.40, 0.31):
            PLB[(n_, vd_)] = [prep(g.buffer(-vd_ / 2 - 0.05)) for g in gs if g.area > 0.5]
print('planes prepared', flush=True)
made, failed = [], []
for f in b.GetFootprints():
    for p in f.Pads():
        n = short(p.GetNetname())
        if n not in nets or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH or attached(p):
            continue
        px, py = p.GetPosition().x / MM, p.GetPosition().y / MM
        lay = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
        pl = PLB.get((n, 0.40), [])
        if not pl:
            failed.append('%s.%s(%s, no plane)' % (f.GetReference(), p.GetNumber(), n)); continue
        best = None
        for vd, dr in ((0.40, 0.20), (0.31, 0.15)):
            for ring in range(3, int(R / 0.05) + 1):
                r = ring * 0.05
                for k in range(max(8, int(2 * math.pi * r / 0.05))):
                    a = 2 * math.pi * k / max(8, int(2 * math.pi * r / 0.05))
                    vx, vy = round(px + r * math.cos(a), 3), round(py + r * math.sin(a), 3)
                    vg = Point(vx, vy).buffer(vd / 2)
                    if not BX.contains(vg) or not any(z.contains(Point(vx, vy)) for z in PLB[(n, vd)]):
                        continue
                    if not free(vg, p.GetNetCode()):
                        continue
                    sg = LineString([(px, py), (vx, vy)]).buffer(0.125)
                    if not free(sg, p.GetNetCode()):
                        continue
                    best = (vx, vy, vd, dr); break
                if best: break
            if best: break
        if not best and os.environ.get('VIP', '1') == '1':
            # via in pad (epoxy filled + capped, IPC-4761 VII): pad centre, foreign copper clear on every layer
            vg = Point(px, py).buffer(0.155)
            if any(z.contains(Point(px, py)) for z in PLB[(n, 0.31)]) and free(vg, p.GetNetCode()):
                v = pcbnew.PCB_VIA(b); v.SetPosition(p.GetPosition()); v.SetWidth(int(0.31 * MM)); v.SetDrill(int(0.15 * MM))
                v.SetNet(p.GetNet()); v.SetLocked(True); v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetFrontTentingMode(pcbnew.TENTING_MODE_NOT_TENTED); v.SetBackTentingMode(pcbnew.TENTING_MODE_NOT_TENTED); b.Add(v)
                geo.append(vg); gnet.append(p.GetNetCode()); tree = STRtree(geo)
                made.append('%s.%s(vip)' % (f.GetReference(), p.GetNumber())); print('vip', made[-1], flush=True); continue
        if not best:
            # fall back: stub on the pad layer to the nearest own-net via (straight or one 45/90 bend)
            vias_ = sorted([(math.hypot(t.GetPosition().x / MM - px, t.GetPosition().y / MM - py), t) for t in b.GetTracks()
                            if t.GetClass() == 'PCB_VIA' and t.GetNetCode() == p.GetNetCode()], key=lambda q: q[0])
            done_ = False
            for dd, t in vias_[:12]:
                if dd > 3.0:
                    break
                tx_, ty_ = t.GetPosition().x / MM, t.GetPosition().y / MM
                for path in ([(px, py), (tx_, ty_)], [(px, py), (tx_, py), (tx_, ty_)], [(px, py), (px, ty_), (tx_, ty_)]):
                    for w_ in (0.20, 0.15, 0.12):
                        sg = LineString(path).buffer(w_ / 2)
                        if free(sg, p.GetNetCode()):
                            for (x0, y0), (x1, y1) in zip(path, path[1:]):
                                if math.hypot(x1 - x0, y1 - y0) < 1e-4:
                                    continue
                                tr = pcbnew.PCB_TRACK(b); tr.SetStart(pcbnew.VECTOR2I(int(x0 * MM), int(y0 * MM))); tr.SetEnd(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM)))
                                tr.SetWidth(int(w_ * MM)); tr.SetLayer(lay); tr.SetNet(p.GetNet()); tr.SetLocked(True); b.Add(tr)
                            geo.append(sg); gnet.append(p.GetNetCode()); tree = STRtree(geo)
                            done_ = True; break
                    if done_: break
                if done_: break
            if done_:
                made.append('%s.%s(stub)' % (f.GetReference(), p.GetNumber())); print('stub', made[-1], flush=True); continue
            failed.append('%s.%s(%s)' % (f.GetReference(), p.GetNumber(), n)); print('fail', failed[-1], flush=True); continue
        vx, vy, vd, dr = best
        v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(int(vx * MM), int(vy * MM))); v.SetWidth(int(vd * MM)); v.SetDrill(int(dr * MM))
        v.SetNet(p.GetNet()); v.SetLocked(True); v.SetViaType(pcbnew.VIATYPE_THROUGH); b.Add(v)
        t = pcbnew.PCB_TRACK(b); t.SetStart(p.GetPosition()); t.SetEnd(v.GetPosition()); t.SetWidth(int(0.25 * MM)); t.SetLayer(lay)
        t.SetNet(p.GetNet()); t.SetLocked(True); b.Add(t)
        geo.append(Point(vx, vy).buffer(vd / 2)); gnet.append(p.GetNetCode())
        geo.append(LineString([(px, py), (vx, vy)]).buffer(0.125)); gnet.append(p.GetNetCode())
        tree = STRtree(geo)
        made.append('%s.%s' % (f.GetReference(), p.GetNumber())); print('via', made[-1], flush=True)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(dst)
print('plane vias added', len(made), made)
print('no spot', failed)
