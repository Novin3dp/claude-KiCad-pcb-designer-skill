#!/usr/bin/env python3
"""single-connection grid A* router with exact clearance (for short fixes inside dense areas, e.g. under the BGA).
usage: astar1.py IN OUT NET x0,y0,LAYER x1,y1,LAYER LAYERS WIN [W=0.1] [CL=0.1] [VIA=0.31/0.15] [STEP=0.025]
  LAYER of an endpoint: a layer name, or 'via' (endpoint is a through via / PTH: any layer)
  LAYERS: comma list of allowed layer names; WIN: x0,y0,x1,y1 search window
The path may change layer with a new via (checked against every hole and foreign copper)."""
import sys, heapq, math
import numpy as np
import pcbnew
import shapely
from shapely.geometry import Point, LineString
from viatool import Tool, short
MM = 1e6
src, dst, NET = sys.argv[1:4]
A, B = sys.argv[4].split(','), sys.argv[5].split(',')
b = pcbnew.LoadBoard(src)
LN = [b.GetLayerID(n) for n in sys.argv[6].split(',')]
wx0, wy0, wx1, wy1 = map(float, sys.argv[7].split(','))
W = float(sys.argv[8]) if len(sys.argv) > 8 else 0.1
CL = float(sys.argv[9]) if len(sys.argv) > 9 else 0.1
VD, VDR = map(float, (sys.argv[10] if len(sys.argv) > 10 else '0.31/0.15').split('/'))
ST = float(sys.argv[11]) if len(sys.argv) > 11 else 0.025
T = Tool(b, cl=CL, hole_gap=0.2)
xs = np.arange(wx0, wx1 + 1e-9, ST); ys = np.arange(wy0, wy1 + 1e-9, ST)
XX, YY = np.meshgrid(xs, ys)
from shapely.geometry import Polygon as _Poly
KEEP = []
for z in list(b.Zones()) + [z for f in b.GetFootprints() for z in f.Zones()]:
    if z.GetIsRuleArea() and (z.GetDoNotAllowTracks() or z.GetDoNotAllowVias()):
        o = z.Outline().Outline(0)
        KEEP.append((z.GetDoNotAllowTracks(), _Poly([(o.CPoint(i).x / MM, o.CPoint(i).y / MM) for i in range(o.PointCount())]), z, z.GetDoNotAllowVias()))
CL += 0.006
free = {}
for l in LN:
    gs = [og.buffer(W / 2 + CL - 0.002) for og, ol, n, hc, hr in T.obst if n != NET and (ol is None or ol == l) and og.bounds[2] > wx0 - 1 and og.bounds[0] < wx1 + 1 and og.bounds[3] > wy0 - 1 and og.bounds[1] < wy1 + 1]
    u = shapely.union_all(gs) if gs else None
    blocked = shapely.contains_xy(u, XX, YY) if u is not None else np.zeros(XX.shape, bool)
    for kz in KEEP:
        if kz[0] and kz[2].IsOnLayer(l):
            blocked |= shapely.contains_xy(kz[1].buffer(W / 2 + 0.01), XX, YY)
    free[l] = ~blocked
# via-capable cells
gsv = []
for og, ol, n, hc, hr in T.obst:
    if og.bounds[2] < wx0 - 1 or og.bounds[0] > wx1 + 1 or og.bounds[3] < wy0 - 1 or og.bounds[1] > wy1 + 1:
        continue
    if n != NET:
        gsv.append(og.buffer(VD / 2 + CL - 0.002))
    if hc is not None:
        gsv.append(hc.buffer(hr + VDR / 2 + 0.2))
for kz in KEEP:
    if kz[3]:
        gsv.append(kz[1].buffer(VD / 2 + 0.01))
uv = shapely.union_all(gsv)
vfree = ~shapely.contains_xy(uv, XX, YY)
for l in LN:
    vfree &= free[l]


def cell(x, y):
    return int(round((y - wy0) / ST)), int(round((x - wx0) / ST))


def ends(e):
    x, y, L = float(e[0]), float(e[1]), e[2]
    i, j = cell(x, y)
    if L == 'via':
        return [(i, j, l) for l in LN]
    return [(i, j, b.GetLayerID(L))]


S, G = ends(A), ends(B)
Gs = set(G)
for (i, j, l) in S + G:      # endpoints sit on own copper: open a small disc
    for di in range(-3, 4):
        for dj in range(-3, 4):
            if 0 <= i + di < XX.shape[0] and 0 <= j + dj < XX.shape[1]:
                free[l][i + di, j + dj] = True
gi, gj = G[0][0], G[0][1]
h = lambda i, j: math.hypot(i - gi, j - gj)
D8 = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
pq = [(h(i, j), 0.0, (i, j, l), None) for (i, j, l) in S]
heapq.heapify(pq)
prev, cost = {}, {}
found = None
while pq:
    f_, g_, n, p = heapq.heappop(pq)
    if n in prev:
        continue
    prev[n] = p
    if n in Gs:
        found = n; break
    i, j, l = n
    for di, dj, c in D8:
        m = (i + di, j + dj, l)
        if 0 <= m[0] < XX.shape[0] and 0 <= m[1] < XX.shape[1] and free[l][m[0], m[1]] and m not in prev:
            ng = g_ + c
            if ng < cost.get(m, 1e18):
                cost[m] = ng; heapq.heappush(pq, (ng + h(m[0], m[1]), ng, m, n))
    if vfree[i, j]:
        for l2 in LN:
            if l2 != l:
                m = (i, j, l2)
                ng = g_ + 40
                if m not in prev and ng < cost.get(m, 1e18):
                    cost[m] = ng; heapq.heappush(pq, (ng + h(i, j), ng, m, n))
if not found:
    print('NO PATH'); sys.exit(1)
path = []
n = found
while n:
    path.append(n); n = prev[n]
path.reverse()
# split by layer, simplify, emit
segs = []
cur = [path[0]]
for n in path[1:]:
    if n[2] != cur[-1][2]:
        segs.append(cur); cur = [n]
    else:
        cur.append(n)
segs.append(cur)
xy = lambda n: (round(float(xs[n[1]]), 4), round(float(ys[n[0]]), 4))
ax, ay = float(A[0]), float(A[1]); bx, by = float(B[0]), float(B[1])
for k, s in enumerate(segs):
    pts = [xy(n) for n in s]
    if k == 0:
        pts[0] = (ax, ay)
    if k == len(segs) - 1:
        pts[-1] = (bx, by)
    lay_ = s[0][2]
    # greedy line-of-sight simplification with the exact clearance check (endpoints on own copper excepted)
    out = [pts[0]]; i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1 and not T.track_ok([pts[i], pts[j]], NET, W, lay_):
            j -= 1
        out.append(pts[j]); i = j
    bad = [q for q in zip(out, out[1:]) if not T.track_ok(list(q), NET, W, lay_)]
    if bad:
        print('  WARNING: %d segment(s) near own-end copper fail the check (endpoint stubs): %s' % (len(bad), bad))
    pts = out
    T.track(pts, NET, W, lay_, check=False)
    print('  %s: %d pts %s' % (b.GetLayerName(s[0][2]), len(pts), [tuple(round(v,3) for v in p) for p in LineString(pts).simplify(0.03).coords]))
    if k < len(segs) - 1:
        x, y = xy(s[-1])
        T.via(x, y, NET, VD, VDR, check=False)
        print('  via %.3f %.3f' % (x, y))
T.commit(fill=False)
b.Save(dst)
print('ok', len(segs), 'layer runs')
