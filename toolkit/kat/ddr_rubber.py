#!/usr/bin/env python3
"""Rubber-band the DDR3 single-ended nets: walk each net's H3 -> DDR3 path, and on every run of tracks on one layer
replace the longest legal sub-polyline P[i..j] by the straight segment P[i] -> P[j] (exact clearance check against
all foreign copper of that layer, own net ignored).  This removes old accordion meanders and doglegs, so every net
starts from its shortest routed length before it is re-tuned to the lane / CK target.  Locked tracks are kept;
differential pairs (DQS, CK) are not touched.   usage: ddr_rubber.py IN OUT [NETREGEX]"""
import sys, os, re, math, heapq, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.getcwd())
import pcbnew
import importlib
importlib.import_module(os.environ.get('DDR_PROFILE', 'ddr_profile'))   # board-specific DDR settings (layer depths, chip refs)          # patches ddr_report.build_graph for this board
import ddr_report as DR
import tune2 as T
MM = 1e6
src, dst = sys.argv[1], sys.argv[2]
RX = re.compile(sys.argv[3] if len(sys.argv) > 3 else r'^DDR_(DQ\d+|DM\d|A\d+|BA\d|RAS_N|CAS_N|WE_N|CS_N|CKE|ODT|RESET_N)$')
CLS = {'Default': 0.10, 'DDR': 0.10, 'USB90': 0.12, 'HDMI100': 0.15, 'ETH100': 0.15, 'SDIO': 0.10, 'PWR': 0.12, 'GND': 0.10}
b = pcbnew.LoadBoard(src)
code_cls = {ni.GetNetCode(): CLS.get(ni.GetNetClassName(), 0.10) for ni in b.GetNetsByNetcode().values()}
LAY = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.B_Cu]
fld = T.Exact(b, LAY, lambda c: code_cls.get(c, 0.10))
# keep clear of the L4 power islands as the tuner does (signals on L4 must not cut them further)
U1, U7 = b.FindFootprintByReference(DR.SOC_REF), b.FindFootprintByReference(DR.MEM_REFS[0])
short = lambda n: n.split('/')[-1]


def path_tracks(full):
    g = DR.build_graph(b, full)
    s = DR.attach_pad(g, [p for p in U1.Pads() if p.GetNetname() == full][0])
    t = DR.attach_pad(g, [p for p in U7.Pads() if p.GetNetname() == full][0])
    dist, prev, pq = {s: 0.0}, {}, [(0.0, s)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == t:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, w, kind in g.get(u, ()):
            if d + w < dist.get(v, 1e18):
                dist[v] = d + w; prev[v] = (u, kind); heapq.heappush(pq, (d + w, v))
    if t not in prev:
        return None, None
    seq, u = [t], t
    while u in prev:
        u = prev[u][0]; seq.append(u)
    seq.reverse()
    return seq, dist[t]


TRK = collections.defaultdict(list)
for tr in b.GetTracks():
    if tr.GetClass() == 'PCB_TRACK':
        a = DR.key(tr.GetStart().x, tr.GetStart().y, tr.GetLayer()); c = DR.key(tr.GetEnd().x, tr.GetEnd().y, tr.GetLayer())
        TRK[(tr.GetNetname(), a, c)].append(tr); TRK[(tr.GetNetname(), c, a)].append(tr)
nets = sorted({ni.GetNetname() for ni in b.GetNetsByNetcode().values() if RX.search(short(ni.GetNetname()))})
total_saved = 0.0
report = []
ALLKILL, ALLADD = [], []
for full in nets:
    seq, L0 = path_tracks(full)
    if seq is None:
        report.append((short(full), 'no path')); continue
    # runs of consecutive same-layer track nodes
    runs, cur = [], []
    for a, c in zip(seq, seq[1:]):
        trs = TRK.get((full, a, c)) if a[0] != 'pad' and c[0] != 'pad' else None
        if trs and a[2] == c[2]:
            if cur and cur[-1][1] == a:
                cur.append((a, c, trs[0]))
            else:
                if cur:
                    runs.append(cur)
                cur = [(a, c, trs[0])]
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    saved = 0.0
    kill, add = [], []
    for run in runs:
        if len(run) < 2:
            continue
        lay = run[0][0][2]
        if lay not in fld.tree:
            continue
        pts = [(run[0][0][0] / 1000.0, run[0][0][1] / 1000.0)] + [(c[0] / 1000.0, c[1] / 1000.0) for a, c, t in run]
        trs = [t for a, c, t in run]
        w = trs[0].GetWidth() / MM
        net = trs[0].GetNetCode()
        i = 0
        while i < len(pts) - 1:
            best = i + 1
            for j in range(len(pts) - 1, i + 1, -1):
                if any(trs[k].IsLocked() for k in range(i, j)):
                    continue
                if fld.ok(lay, net, [pts[i], pts[j]], w):
                    best = j; break
            if best > i + 1:
                old = sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]) for k in range(i, best))
                new = math.hypot(pts[best][0] - pts[i][0], pts[best][1] - pts[i][1])
                if old - new > 0.02:
                    kill += trs[i:best]
                    add.append((lay, pts[i], pts[best], w, trs[i].GetNet()))
                    fld.add(lay, [pts[i], pts[best]], w, net)
                    saved += old - new
            i = best
    ALLKILL.extend(kill); ALLADD.extend(add)
    total_saved += saved
    report.append((short(full), round(L0, 2), round(L0 - saved, 2)))
# mutate only at the end (pcbnew wrappers go stale after a Remove)
for t in {id(t): t for t in ALLKILL}.values():
    b.Remove(t)
for lay, p, q, w, ni in ALLADD:
    nt = pcbnew.PCB_TRACK(b)
    nt.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1]))); nt.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(q[0]), pcbnew.FromMM(q[1])))
    nt.SetWidth(pcbnew.FromMM(w)); nt.SetLayer(lay); nt.SetNet(ni); b.Add(nt)
b.Save(dst)
for r in report:
    print('  %-12s %s' % (r[0], r[1:]))
print('saved %.1f mm over %d nets' % (total_saved, len(nets)))
