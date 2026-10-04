#!/usr/bin/env python3
"""Copy the tracks / vias of the given nets from an older board (REF) into IN wherever they still fit: an item is
re-added only if it keeps CL to every foreign track / via / pad on its layer(s) and to the board edge, and does not
already exist.  The router then only has to join the restored pieces to the moved pads.
usage: restore_net.py REF IN OUT NET[,NET...] [CL] [x0,y0,x1,y1]"""
import sys
import pcbnew
from shapely.geometry import Point, LineString, box
from shapely.strtree import STRtree
MM = 1e6
ref, src, dst, nets = sys.argv[1], sys.argv[2], sys.argv[3], set(sys.argv[4].split(','))
CL = float(sys.argv[5]) if len(sys.argv) > 5 else 0.12
AREA = box(*map(float, sys.argv[6].split(','))) if len(sys.argv) > 6 else None   # x0,y0,x1,y1: only items touching it
short = lambda n: n.split('/')[-1]
R = pcbnew.LoadBoard(ref)
b = pcbnew.LoadBoard(src)
CU = list(b.GetEnabledLayers().CuStack())      # every copper layer of this board


def geo(t):
    if t.GetClass() == 'PCB_VIA':
        return Point(t.GetPosition().x / MM, t.GetPosition().y / MM).buffer(t.GetWidth(pcbnew.F_Cu) / MM / 2), None
    return LineString([(t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM)]).buffer(t.GetWidth() / MM / 2), t.GetLayer()


obs = {l: [] for l in CU}
have = set()
for t in b.GetTracks():
    g, l = geo(t)
    n = short(t.GetNetname())
    for L in (CU if l is None else [l]):
        obs[L].append((g, n))
    k = (n, t.GetClass(), t.GetLayer(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y)
    have.add(k)
for f in b.GetFootprints():
    for p in f.Pads():
        bb = p.GetBoundingBox()
        if p.GetShape(pcbnew.F_Cu) == pcbnew.PAD_SHAPE_CIRCLE:
            g = Point(p.GetPosition().x / MM, p.GetPosition().y / MM).buffer(p.GetSize(pcbnew.F_Cu).x / MM / 2)
        else:
            g = box(bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)
        for L in CU:
            if p.IsOnLayer(L):
                obs[L].append((g, short(p.GetNetname())))
TREE = {l: STRtree([g for g, n in obs[l]]) for l in CU}
NI = {short(ni.GetNetname()): ni for ni in b.GetNetsByNetcode().values()}
add, skip = [], 0
for t in R.GetTracks():
    n = short(t.GetNetname())
    if n not in nets:
        continue
    k = (n, t.GetClass(), t.GetLayer(), t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y)
    if k in have:
        continue
    g, l = geo(t)
    if AREA is not None and not g.intersects(AREA):
        continue
    gg = g.buffer(CL)
    bad = False
    for L in (CU if l is None else [l]):
        for i in TREE[L].query(gg):
            if obs[L][i][1] != n and gg.intersects(obs[L][i][0]):
                bad = True; break
        if bad:
            break
    if bad:
        skip += 1; continue
    add.append(t)
for t in add:
    if t.GetClass() == 'PCB_VIA':
        c = pcbnew.PCB_VIA(b); c.SetPosition(t.GetPosition()); c.SetWidth(t.GetWidth(pcbnew.F_Cu)); c.SetDrill(t.GetDrillValue())
        c.SetViaType(t.GetViaType())
    else:
        c = pcbnew.PCB_TRACK(b); c.SetStart(t.GetStart()); c.SetEnd(t.GetEnd()); c.SetWidth(t.GetWidth()); c.SetLayer(t.GetLayer())
    c.SetNet(NI[short(t.GetNetname())]); c.SetLocked(t.IsLocked()); b.Add(c)
b.Save(dst)
print('restored', len(add), 'skipped', skip)
