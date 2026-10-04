"""DDR3 length matching with accordion meanders, checked against exact clearance-slack fields (slack.Field).

match rules (per chip):
  * byte lane: DQ0-7 + DM matched to the lane's DQS pair  (target = longest member, tolerance +-0.5 mm, aim -0.1)
  * DQS / CK pairs: P and N within 0.1 mm
  * ADDR/CMD: every net within +-2.5 mm of CK at the same chip (T branch)
A meander replaces the middle of one straight segment:  n bumps of amplitude A, leg pitch 0.4 mm (gap 0.3 = 3W),
added length 2*A*n.  Every new segment is sampled every 0.02 mm and must keep slack > w/2 + 0.04 to all foreign
copper; the field is updated with the new copper so later meanders see it."""
import math, collections
import numpy as np
import pcbnew
import slack as SL
import ddr_report as DR

MM = 1e6
PITCH = 0.30          # leg pitch: gap 0.2 mm (2W) between serpentine legs


class Exact:
    """exact clearance check of new copper against the foreign copper of one layer (shapely STRtree)"""
    def __init__(self, b, layers, clr_of):
        import shapely
        from shapely.geometry import Point, LineString, Polygon
        self.S, self.P, self.L, self.Pg = shapely, Point, LineString, Polygon
        self.geoms = {l: [] for l in layers}
        self.nets = {l: [] for l in layers}
        self.clr = {l: [] for l in layers}
        for f in b.GetFootprints():
            for p in f.Pads():
                for l in layers:
                    if not p.IsOnLayer(l) or (l not in (pcbnew.F_Cu, pcbnew.B_Cu) and not p.FlashLayer(l)):
                        continue
                    ps = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(ps, l, 0, pcbnew.FromMM(0.002), pcbnew.ERROR_OUTSIDE)
                    for i in range(ps.OutlineCount()):
                        o = ps.Outline(i)
                        self._add(l, Polygon([(o.CPoint(k).x / MM, o.CPoint(k).y / MM) for k in range(o.PointCount())]),
                                  p.GetNetCode(), clr_of(p.GetNetCode()))
        for t in b.GetTracks():
            if t.GetClass() == 'PCB_VIA':
                g = Point(t.GetPosition().x / MM, t.GetPosition().y / MM).buffer(t.GetWidth(pcbnew.F_Cu) / MM / 2, 16)
                for l in layers:
                    self._add(l, g, t.GetNetCode(), clr_of(t.GetNetCode()))
            elif t.GetLayer() in layers:
                g = LineString([(t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM)]).buffer(t.GetWidth() / MM / 2, 8)
                self._add(t.GetLayer(), g, t.GetNetCode(), clr_of(t.GetNetCode()))
        self._build()

    def _add(self, l, g, net, clr):
        self.geoms[l].append(g); self.nets[l].append(net); self.clr[l].append(clr)

    def _build(self):
        self.tree = {l: self.S.STRtree(g) for l, g in self.geoms.items()}

    def ok(self, l, net, pts, w, clr=0.10):
        line = self.L(pts).buffer(w / 2, 8)
        for i in self.tree[l].query(line.buffer(0.3)):
            if self.nets[l][i] == net:
                continue
            if line.distance(self.geoms[l][i]) < max(clr, self.clr[l][i]) + 0.002:
                return False
        return True

    def add(self, l, pts, w, net, clr=0.10):
        self._add(l, self.L(pts).buffer(w / 2, 8), net, clr)
        self._build()


def seg_ok(fld, l, net, hw, pts, eps=0.04):
    s1, n1, s2 = fld.layer(l)
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        L = math.hypot(bx - ax, by - ay)
        k = max(2, int(L / 0.02) + 1)
        t = np.linspace(0, 1, k)
        xs = ax + (bx - ax) * t; ys = ay + (by - ay) * t
        i = np.round((xs - fld.ox) / fld.res).astype(int); j = np.round((ys - fld.oy) / fld.res).astype(int)
        if (i < 0).any() or (j < 0).any() or (i >= fld.W).any() or (j >= fld.H).any():
            return False
        s = np.where(n1[j, i] == net, s2[j, i], s1[j, i])
        if (s <= hw + eps).any():
            return False
    return True


def meander(ax, ay, bx, by, n, A, side):
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    nx_, ny_ = -uy * side, ux * side
    s = (L - n * 2 * PITCH) / 2
    pts = [(ax, ay), (ax + ux * s, ay + uy * s)]
    for _ in range(n):
        pts.append((ax + ux * s + nx_ * A, ay + uy * s + ny_ * A)); s += PITCH
        pts.append((ax + ux * s + nx_ * A, ay + uy * s + ny_ * A))
        pts.append((ax + ux * s, ay + uy * s)); s += PITCH
        pts.append((ax + ux * s, ay + uy * s))
    pts.append((bx, by))
    return pts


def add_length(b, fld, netname, dL, prefer=None, clr_seg=0.35):
    """add ~dL mm to net, spread over as many straight segments as needed (longest first);
    `prefer(track)->bool` restricts candidate segments (e.g. one T branch).  Returns the length added."""
    segs = [t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK' and t.GetNetname() == netname and (prefer is None or prefer(t))]
    segs.sort(key=lambda t: -t.GetLength())
    rem = dL
    for t in segs:
        if rem < 0.15:
            break
        L = t.GetLength() / MM
        if L < 2 * PITCH + 2 * clr_seg:
            continue
        ax, ay, bx, by = t.GetStart().x / MM, t.GetStart().y / MM, t.GetEnd().x / MM, t.GetEnd().y / MM
        l, w, net = t.GetLayer(), t.GetWidth() / MM, t.GetNetCode()
        if l not in fld.tree:
            continue
        nmax = int((L - 2 * clr_seg) / (2 * PITCH))
        done = False
        for A in (1.2, 0.9, 0.7, 0.5, 0.35, 0.25, 0.18):
            n = max(1, min(nmax, int(math.ceil(rem / (2 * A)))))
            A2 = min(A, rem / (2 * n))
            if A2 < 0.15:
                continue
            for side in (1, -1):
                pts = meander(ax, ay, bx, by, n, A2, side)
                if not fld.ok(l, net, pts[1:-1], w):
                    continue
                ni = t.GetNet()
                b.Remove(t)
                for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                    if math.hypot(x1 - x0, y1 - y0) < 1e-4:
                        continue
                    nt = pcbnew.PCB_TRACK(b)
                    nt.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(float(x0)), pcbnew.FromMM(float(y0))))
                    nt.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(float(x1)), pcbnew.FromMM(float(y1))))
                    nt.SetWidth(pcbnew.FromMM(w)); nt.SetLayer(l); nt.SetNet(ni)
                    b.Add(nt)
                fld.add(l, pts, w, net)
                rem -= 2 * A2 * n
                done = True
                break
            if done:
                break
    return dL - rem


def lengths(b):
    return {(r['net'], r['chip']): r['len'] for r in DR.report(b) if r['len'] is not None}


def branch_filter(b, netname, chip):
    """segments that belong only to the H3->chip branch of a T net (not to the stem shared with the other chip)"""
    g = DR.build_graph(b, netname)
    u1 = [p for p in b.FindFootprintByReference(DR.SOC_REF).Pads() if p.GetNetname() == netname][0]
    s = DR.attach_pad(g, u1)
    paths = {}
    for cr in ('U8', 'U9'):
        ps = [p for p in b.FindFootprintByReference(cr).Pads() if p.GetNetname() == netname]
        if not ps:
            return None
        t = DR.attach_pad(g, ps[0])
        # dijkstra with predecessor
        import heapq
        dist, prev, pq = {s: 0.0}, {}, [(0.0, s)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == t:
                break
            if d > dist.get(u, 1e18):
                continue
            for v, wgt, kind in g.get(u, ()):
                if d + wgt < dist.get(v, 1e18):
                    dist[v] = d + wgt; prev[v] = u; heapq.heappush(pq, (d + wgt, v))
        nodes, u = set(), t
        while u in prev:
            nodes.add(u); u = prev[u]
        paths[cr] = nodes
    mine, other = paths[chip], paths['U9' if chip == 'U8' else 'U8']
    only = mine - other

    def ok(t):
        a = DR.key(t.GetStart().x, t.GetStart().y, t.GetLayer()); c = DR.key(t.GetEnd().x, t.GetEnd().y, t.GetLayer())
        return a in only and c in only
    return ok


def tune_board(b, fld, log=print):
    done = collections.Counter()
    L = lengths(b)
    # 1) pair skew  (DQS per lane, CK per chip branch)
    for lane in range(4):
        chip = 'U8' if lane < 2 else 'U9'
        p, n = 'DDR_DQS%d_P' % lane, 'DDR_DQS%d_N' % lane
        a, c = L.get((p, chip)), L.get((n, chip))
        if a and c and abs(a - c) > 0.08:
            short, dl = (p, c - a) if a < c else (n, a - c)
            full = [k.GetNetname() for k in b.GetNetsByNetcode().values() if k.GetNetname().endswith(short)][0]
            got = add_length(b, fld, full, dl)
            log('pair %s: +%.2f of %.2f' % (short, got, dl))
    L = lengths(b)
    # 2) byte lanes: everything up to the longest member (aim 0.1 below it)
    for lane in range(4):
        chip = 'U8' if lane < 2 else 'U9'
        members = ['DDR_DQ%d' % i for i in range(lane * 8, lane * 8 + 8)] + ['DDR_DM%d' % lane]
        dqs = ['DDR_DQS%d_P' % lane, 'DDR_DQS%d_N' % lane]
        tgt = max(L.get((m, chip), 0) for m in members + dqs)
        for m in members + dqs:
            cur = L.get((m, chip))
            if cur is None:
                continue
            dl = tgt - cur - 0.1
            if dl > 0.3:
                full = [k.GetNetname() for k in b.GetNetsByNetcode().values() if k.GetNetname().endswith('/' + m) or k.GetNetname() == m][0]
                got = add_length(b, fld, full, dl)
                done['lane%d' % lane] += got > 0
                log('lane %d %s: +%.2f of %.2f' % (lane, m, got, dl))
    # 3) address / command: per chip, bring every net up to (CK - 1.0) on its own branch to that chip
    L = lengths(b)
    ADDR = ['DDR_A%d' % i for i in range(16)] + ['DDR_BA%d' % i for i in range(3)] + \
           ['DDR_RAS_N', 'DDR_CAS_N', 'DDR_WE_N', 'DDR_CS_N', 'DDR_CKE', 'DDR_ODT', 'DDR_RESET_N']
    full_of = {k.GetNetname().split('/')[-1]: k.GetNetname() for k in b.GetNetsByNetcode().values()}
    for chip in ('U8', 'U9'):
        ck = [L.get(('DDR_CK_P', chip)), L.get(('DDR_CK_N', chip))]
        ck = [c for c in ck if c]
        if not ck:
            continue
        tgt = sum(ck) / len(ck)
        for m in ADDR:
            cur = L.get((m, chip))
            if cur is None or m not in full_of:
                continue
            dl = tgt - cur - 1.0
            if dl > 0.5:
                flt = branch_filter(b, full_of[m], chip)
                got = add_length(b, fld, full_of[m], dl, prefer=flt)
                done['addr_' + chip] += got > 0
                log('addr %s %s: +%.2f of %.2f (CK %.1f)' % (chip, m, got, dl, tgt))
    return done
