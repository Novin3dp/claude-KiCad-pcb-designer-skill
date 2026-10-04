#!/usr/bin/env python3
"""Join the copper clusters of one net (plane-fill islands, stranded pads / vias / tracks) to its main cluster with a
routed bridge.  Clusters come from KiCad's own item connectivity plus via / pad-in-fill tests per filled zone piece.
Grid Dijkstra (0.025 mm) over L1 / L3 / L6: starts on the copper of a stranded cluster (or at a via-legal spot inside
one of its fill pieces), ends on the copper of the main cluster (or a via-legal spot inside a main fill piece); a layer
change costs an extra via.  New vias clear foreign copper on all six layers (and drills hole-to-hole), tracks clear
foreign copper on their layer, both by max(CLR, the foreign item's own clearance).
usage: cluster_link.py IN OUT NET [W] [WIN]        env BOX=x0,y0,x1,y1 limits which stranded clusters are handled"""
import sys, math, heapq, os
import numpy as np
import pcbnew
from PIL import Image, ImageDraw
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import unary_union
MM = 1e6
src, dst, NET = sys.argv[1], sys.argv[2], sys.argv[3]
TW = float(sys.argv[4]) if len(sys.argv) > 4 else 0.15
WIN = float(sys.argv[5]) if len(sys.argv) > 5 else 6.0
CLR = float(os.environ.get('CLR', 0.12))
VD, VDR = 0.31, 0.15
RES = 0.025
b = pcbnew.LoadBoard(src)
ALL = list(b.GetEnabledLayers().CuStack())      # every copper layer of this board
# layers the bridge may run on: env SIG_LAYERS='F.Cu,In2.Cu,B.Cu' (default: outer layers + inner layers typed 'signal')
SIG = [b.GetLayerID(n) for n in os.environ['SIG_LAYERS'].split(',')] if os.environ.get('SIG_LAYERS') else \
    [l for l in ALL if l in (pcbnew.F_Cu, pcbnew.B_Cu) or b.GetLayerType(l) == pcbnew.LT_SIGNAL]
net = b.FindNet(NET)
code = net.GetNetCode()


def poly(ol):
    return Polygon([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())]).buffer(0)


BGA = []
for z in [z for f in b.GetFootprints() for z in f.Zones()] + list(b.Zones()):
    if z.GetIsRuleArea() and z.GetZoneName() == 'BGA_U1':
        o = z.Outline()
        for i in range(o.OutlineCount()):
            BGA.append(poly(o.Outline(i)))
BGA = unary_union(BGA) if BGA else None
BGA_CLR = float(os.environ.get('BGA_CLR', 0.10))


def clr_of(it, g=None):
    if BGA is not None and g is not None and g.intersects(BGA):
        return BGA_CLR        # DRU 'BGA escape' rule: 0.10 mm for every pair touching the ball field
    try:
        return max(CLR, it.GetOwnClearance(pcbnew.F_Cu) / MM)
    except Exception:
        return CLR


def item_geom(it, l):
    if it.GetClass() == 'PCB_VIA':
        return Point(it.GetPosition().x / MM, it.GetPosition().y / MM).buffer(it.GetWidth(l) / MM / 2)
    if it.GetClass() in ('PCB_TRACK', 'PCB_ARC'):
        return LineString([(it.GetStart().x / MM, it.GetStart().y / MM), (it.GetEnd().x / MM, it.GetEnd().y / MM)]).buffer(it.GetWidth() / MM / 2)
    ps = pcbnew.SHAPE_POLY_SET()
    it.TransformShapeToPolygon(ps, l, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    return unary_union([poly(ps.Outline(i)) for i in range(ps.OutlineCount())])


def layers_of(it):
    if it.GetClass() == 'PCB_VIA':
        return list(ALL)
    if it.GetClass() == 'PAD':
        if it.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
            return list(ALL)
        return [l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if it.IsOnLayer(l)]
    return [it.GetLayer()]


def clusters():
    """-> list of clusters; each = dict(items=[...], fills=[(layer, poly)])"""
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.BuildConnectivity()
    con = b.GetConnectivity()
    items = [p for f in b.GetFootprints() for p in f.Pads() if p.GetNetCode() == code] + \
            [t for t in b.GetTracks() if t.GetNetCode() == code]
    idx = {it.m_Uuid.AsString(): i for i, it in enumerate(items)}
    fills = []
    for z in b.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() != code:
            continue
        for l in z.GetLayerSet().Seq():
            ps = z.GetFilledPolysList(l)
            for i in range(ps.OutlineCount()):
                fills.append((l, poly(ps.Outline(i))))
    n = len(items) + len(fills)
    par = list(range(n))

    def fnd(a):
        while par[a] != a:
            par[a] = par[par[a]]; a = par[a]
        return a

    def uni(a, c):
        a, c = fnd(a), fnd(c)
        if a != c:
            par[a] = c
    for i, it in enumerate(items):
        for o in con.GetConnectedItems(it):
            j = idx.get(o.m_Uuid.AsString())
            if j is not None:
                uni(i, j)
    for k, (l, g) in enumerate(fills):
        for i, it in enumerate(items):
            if l not in layers_of(it):
                continue
            if it.GetClass() == 'PCB_VIA':
                if g.contains(Point(it.GetPosition().x / MM, it.GetPosition().y / MM)):
                    uni(i, len(items) + k)
            elif it.GetClass() == 'PAD':
                if g.intersects(item_geom(it, l).buffer(-0.01)):
                    uni(i, len(items) + k)
            else:
                if g.intersects(item_geom(it, l).buffer(-0.01)):
                    uni(i, len(items) + k)
    groups = {}
    for i in range(n):
        groups.setdefault(fnd(i), []).append(i)
    out = []
    for g in groups.values():
        out.append(dict(items=[items[i] for i in g if i < len(items)], fills=[fills[i - len(items)] for i in g if i >= len(items)]))
    # main = largest fill area, else most items
    out.sort(key=lambda c: (-sum(f[1].area for f in c['fills']), -len(c['items'])))
    return out


def collect():
    per = {l: [] for l in ALL}
    drills = []
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                drills.append((p.GetPosition().x / MM, p.GetPosition().y / MM, p.GetDrillSize().x / MM / 2))
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                for l in ALL:
                    per[l].append((Point(p.GetPosition().x / MM, p.GetPosition().y / MM).buffer(p.GetDrillSize().x / MM / 2), 0.2))
                continue
            if p.GetNetCode() == code:
                continue
            for l in layers_of(p):
                g_ = item_geom(p, l); per[l].append((g_, clr_of(p, g_)))
    for t in b.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            drills.append((t.GetPosition().x / MM, t.GetPosition().y / MM, t.GetDrillValue() / MM / 2))
        if t.GetNetCode() == code:
            continue
        for l in layers_of(t):
            if l in per:
                g_ = item_geom(t, l); per[l].append((g_, clr_of(t, g_)))
    for z in b.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() == code:
            continue
        for l in z.GetLayerSet().Seq():
            if l in SIG:
                ps = z.GetFilledPolysList(l)
                for i in range(ps.OutlineCount()):
                    per[l].append((poly(ps.Outline(i)), CLR))
    keep = []
    for z in [z for f in b.GetFootprints() for z in f.Zones()] + list(b.Zones()):
        if z.GetIsRuleArea() and (z.GetDoNotAllowVias() or z.GetDoNotAllowTracks()):
            o = z.Outline()
            for i in range(o.OutlineCount()):
                keep.append((poly(o.Outline(i)), z.GetDoNotAllowVias(), z.GetDoNotAllowTracks(), list(z.GetLayerSet().Seq())))
    return per, drills, keep


def raster(geoms, x0, y0, nx, ny):
    im = Image.new('1', (nx, ny), 0)
    dr = ImageDraw.Draw(im)
    for g in geoms:
        if g is None or g.is_empty:
            continue
        for pg in (g.geoms if g.geom_type in ('MultiPolygon', 'GeometryCollection') else [g]):
            if pg.geom_type != 'Polygon' or pg.is_empty:
                continue
            dr.polygon([((x - x0) / RES, (y - y0) / RES) for x, y in pg.exterior.coords], fill=1)
            for h in pg.interiors:
                dr.polygon([((x - x0) / RES, (y - y0) / RES) for x, y in h.coords], fill=0)
    return np.array(im, dtype=bool)


def cl_bounds(c):
    gs = [item_geom(it, layers_of(it)[0]) for it in c['items']] + [f[1] for f in c['fills']]
    return unary_union(gs)


made, failed = [], []
tried = set()
while True:
    CL = clusters()
    if len(CL) < 2:
        break
    main = CL[0]
    rest = []
    for c in CL[1:]:
        g = cl_bounds(c)
        key = '%.2f,%.2f' % (g.centroid.x, g.centroid.y)
        if key in tried:
            continue
        if os.environ.get('BOX'):
            bx0, by0, bx1, by1 = map(float, os.environ['BOX'].split(','))
            if not (bx0 <= g.centroid.x <= bx1 and by0 <= g.centroid.y <= by1):
                continue
        rest.append((c, g, key))
    if not rest:
        break
    c, cg, key = rest[0]
    tried.add(key)
    per, drills, KEEP = collect()
    x0, y0, x1, y1 = cg.buffer(WIN).bounds
    nx, ny = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
    Wb = box(x0, y0, x1, y1).buffer(1)
    m = RES * 0.75
    trk = []
    for l in SIG:
        gs = [g.buffer(cc + TW / 2 + m) for g, cc in per[l] if g.intersects(Wb)]
        gs += [k[0].buffer(TW / 2) for k in KEEP if k[2] and l in k[3] and k[0].intersects(Wb)]
        trk.append(~raster(gs, x0, y0, nx, ny))
    vg = []
    for l in ALL:
        vg += [g.buffer(cc + VD / 2 + m) for g, cc in per[l] if g.intersects(Wb)]
    vg += [Point(x, y).buffer(r + 0.20 + VDR + m) for x, y, r in drills if Wb.contains(Point(x, y))]
    vg += [k[0].buffer(VD / 2) for k in KEEP if k[1] and k[0].intersects(Wb)]
    via_ok = ~raster(vg, x0, y0, nx, ny)
    # board edge
    ed = b.GetBoardEdgesBoundingBox()
    via_ok &= raster([box(ed.GetLeft() / MM + 0.4, ed.GetTop() / MM + 0.4, ed.GetRight() / MM - 0.4, ed.GetBottom() / MM - 0.4)], x0, y0, nx, ny)
    for t_ in trk:
        t_ &= raster([box(ed.GetLeft() / MM + 0.3, ed.GetTop() / MM + 0.3, ed.GetRight() / MM - 0.3, ed.GetBottom() / MM - 0.3)], x0, y0, nx, ny)

    def masks(cc):
        """per signal layer: cells on own copper (track may start / end there, no via) ; via cells inside own fills"""
        on = []
        for l in SIG:
            gs = [item_geom(it, l).buffer(-0.03) for it in cc['items'] if l in layers_of(it)]
            gs += [f[1].buffer(-0.05) for f in cc['fills'] if f[0] == l]
            on.append(raster(gs, x0, y0, nx, ny))
        vf = raster([f[1].buffer(-VD / 2 - 0.03) for f in cc['fills'] if f[0] not in SIG] +
                    [item_geom(it, pcbnew.F_Cu).buffer(-0.01) for it in cc['items'] if it.GetClass() == 'PCB_VIA'], x0, y0, nx, ny)
        return on, vf & via_ok
    onS, vS = masks(c)
    onG, vG = masks(main)
    VC = 0.6
    dist = np.full((3, ny, nx), np.inf, np.float32)
    prev = {}
    hp = []
    for li in range(3):
        for msk, cost in ((onS[li] & trk[li], 0.0), (vS & trk[li] & ~onS[li], VC)):
            ys, xs = np.nonzero(msk)
            for yy, xx in zip(ys, xs):
                if cost < dist[li, yy, xx]:
                    dist[li, yy, xx] = cost; hp.append((cost, li, int(yy), int(xx)))
    heapq.heapify(hp)
    NB = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0), (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
    found = None
    while hp:
        d, li, yy, xx = heapq.heappop(hp)
        if d > dist[li, yy, xx]:
            continue
        if onG[li][yy, xx]:
            found = (li, yy, xx, False); break
        if vG[yy, xx] and not onS[li][yy, xx]:
            found = (li, yy, xx, True); break
        for dy, dx, cst in NB:
            y2, x2 = yy + dy, xx + dx
            if 0 <= y2 < ny and 0 <= x2 < nx and trk[li][y2, x2]:
                nd = d + cst * RES
                if nd < dist[li, y2, x2]:
                    dist[li, y2, x2] = nd; prev[(li, y2, x2)] = (li, yy, xx); heapq.heappush(hp, (nd, li, y2, x2))
        if via_ok[yy, xx]:
            for l2 in range(3):
                if l2 != li and trk[l2][yy, xx]:
                    nd = d + 1.5
                    if nd < dist[l2, yy, xx]:
                        dist[l2, yy, xx] = nd; prev[(l2, yy, xx)] = (li, yy, xx); heapq.heappush(hp, (nd, l2, yy, xx))
    desc = '%s cluster @(%s) [%s]' % (NET, key, ','.join(sorted({(it.GetParentFootprint().GetReference() if it.GetClass() == 'PAD' else it.GetClass()[4:]) for it in c['items']}))[:60])
    if not found:
        failed.append(desc + ': NO PATH'); print(failed[-1], flush=True); continue
    li, yy, xx, newv = found
    path = [(li, yy, xx)]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    P = lambda q: (round(x0 + q[2] * RES, 4), round(y0 + q[1] * RES, 4))
    vias = []
    s0 = path[0]
    if not onS[s0[0]][s0[1], s0[2]]:
        vias.append(P(s0))
    segs, cur = [], [path[0]]
    for q in path[1:]:
        if q[0] != cur[-1][0]:
            segs.append(cur); vias.append(P(q)); cur = [q]
        else:
            cur.append(q)
    segs.append(cur)
    if newv:
        vias.append(P(path[-1]))
    L = 0.0
    for sg in segs:
        if len(sg) < 2:
            continue
        lay = SIG[sg[0][0]]
        pts = [P(q) for q in sg]
        simp = [pts[0]]
        for i in range(1, len(pts) - 1):
            a, c_, e = simp[-1], pts[i], pts[i + 1]
            if abs((c_[0] - a[0]) * (e[1] - a[1]) - (c_[1] - a[1]) * (e[0] - a[0])) > 1e-7:
                simp.append(c_)
        simp.append(pts[-1])
        for (ax, ay), (bx_, by_) in zip(simp, simp[1:]):
            t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I(int(round(ax * MM)), int(round(ay * MM)))); t.SetEnd(pcbnew.VECTOR2I(int(round(bx_ * MM)), int(round(by_ * MM))))
            t.SetWidth(int(TW * MM)); t.SetLayer(lay); t.SetNet(net); t.SetLocked(True); b.Add(t)
            L += math.hypot(bx_ - ax, by_ - ay)
    for vx, vy in vias:
        v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(int(round(vx * MM)), int(round(vy * MM)))); v.SetWidth(int(VD * MM)); v.SetDrill(int(VDR * MM))
        v.SetNet(net); v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLocked(True); b.Add(v)
    made.append(desc + ': %.2f mm on %s, %d new vias' % (L, '/'.join(sorted({b.GetLayerName(SIG[q[0]]) for q in path})), len(vias)))
    print(made[-1], flush=True)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(dst)
print('linked %d, failed %d' % (len(made), len(failed)))
