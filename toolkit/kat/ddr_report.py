"""DDR3 length report: routed length from each H3 ball to each DDR3 ball along the real copper (Dijkstra over
track segments; vias join layers and add their barrel length).  Groups follow JEDEC/H3 matching rules."""
import math, re, heapq, collections, os
import pcbnew

MM = 1e6
VIA_LEN = 1.6      # (legacy) board thickness
# copper depth of each layer in the JLC06161H-3313 stack (mm from the top surface); a layer change through a via
# adds the barrel length actually travelled between the two layers
Z = {pcbnew.F_Cu: 0.0, pcbnew.In1_Cu: 0.13, pcbnew.In2_Cu: 0.72, pcbnew.In3_Cu: 0.86, pcbnew.In4_Cu: 1.47, pcbnew.B_Cu: 1.6}
SOC_REF = os.environ.get('SOC_REF', 'U1')                         # the controller (SoC) footprint
MEM_REFS = tuple(os.environ.get('MEM_REFS', 'U7').split(','))      # DRAM chip footprint(s)
GROUPS = collections.OrderedDict()
for lane, chip, dqs in ((0, MEM_REFS[0], 0), (1, MEM_REFS[-1], 1)):
    GROUPS['Lane %d (DQ%d-%d)' % (lane, lane * 8, lane * 8 + 7)] = dict(
        chip=chip, nets=['DDR_DQ%d' % i for i in range(lane * 8, lane * 8 + 8)] + ['DDR_DM%d' % lane],
        ref=['DDR_DQS%d_P' % dqs, 'DDR_DQS%d_N' % dqs], tol=0.5)
GROUPS['CK'] = dict(chip='both', nets=[], ref=['DDR_CK_P', 'DDR_CK_N'], tol=0.1)
ADDR = ['DDR_A%d' % i for i in range(16)] + ['DDR_BA%d' % i for i in range(3)] + \
       ['DDR_RAS_N', 'DDR_CAS_N', 'DDR_WE_N', 'DDR_CS_N', 'DDR_CKE', 'DDR_ODT', 'DDR_RESET_N']
GROUPS['ADDR/CMD'] = dict(chip='both', nets=ADDR, ref=['DDR_CK_P', 'DDR_CK_N'], tol=2.5)


def short(n):
    return n.split('/')[-1]


def key(x, y, l):
    return (round(x / 1000), round(y / 1000), l)      # 1 um grid


def build_graph(b, netname):
    g = collections.defaultdict(list)
    pads = {}
    for t in b.GetTracks():
        if t.GetNetname() != netname:
            continue
        if t.GetClass() == 'PCB_VIA':
            x, y = t.GetPosition().x, t.GetPosition().y
            ls = [l for l in range(pcbnew.F_Cu, pcbnew.B_Cu + 1) if t.IsOnLayer(l)] or [pcbnew.F_Cu, pcbnew.B_Cu]
            ks = [key(x, y, l) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu)]
            for a in ks:
                for c in ks:
                    if a != c:
                        g[a].append((c, abs(Z[a[2]] - Z[c[2]]), 'via'))
        else:
            l = t.GetLayer()
            a = key(t.GetStart().x, t.GetStart().y, l); c = key(t.GetEnd().x, t.GetEnd().y, l)
            L = t.GetLength() / MM
            g[a].append((c, L, 'trk')); g[c].append((a, L, 'trk'))
    # connect track endpoints that land inside pads, and pads to their node
    return g


def attach_pad(g, p):
    """virtual node for pad p connected (0 length) to every graph node inside the pad on its copper layers"""
    node = ('pad', p.GetParentFootprint().GetReference(), p.GetNumber())
    for k in list(g.keys()):
        if k[0] == 'pad':
            continue
        if k[2] in (pcbnew.F_Cu, pcbnew.B_Cu) and p.IsOnLayer(k[2]):
            if p.HitTest(pcbnew.VECTOR2I(k[0] * 1000, k[1] * 1000)):
                g[node].append((k, 0.0, 'pad')); g[k].append((node, 0.0, 'pad'))
    return node


def dijkstra(g, s, t):
    dist = {s: 0.0}
    vias = {s: 0}
    pq = [(0.0, 0, s)]
    while pq:
        d, nv, u = heapq.heappop(pq)
        if u == t:
            return d, nv
        if d > dist.get(u, 1e18):
            continue
        for v, w, kind in g.get(u, ()):
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                heapq.heappush(pq, (nd, nv + (1 if kind == 'via' else 0), v))
    return None, None


def report(b):
    nets = {short(ni.GetNetname()): ni.GetNetname() for ni in b.GetNetsByNetcode().values()}
    u1 = b.FindFootprintByReference(SOC_REF)
    chips = {r: b.FindFootprintByReference(r) for r in MEM_REFS}
    rows = []
    for gname, gd in GROUPS.items():
        members = gd['nets'] + gd['ref']
        for nm in members:
            full = nets.get(nm)
            if not full:
                continue
            g = build_graph(b, full)
            src = [p for p in u1.Pads() if p.GetNetname() == full]
            if not src:
                continue
            s = attach_pad(g, src[0])
            targets = []
            for cr, cf in chips.items():
                if gd['chip'] not in ('both', cr):
                    continue
                for p in cf.Pads():
                    if p.GetNetname() == full:
                        targets.append((cr, attach_pad(g, p)))
            for cr, t in targets:
                L, nv = dijkstra(g, s, t)
                rows.append(dict(group=gname, net=nm, chip=cr, len=None if L is None else round(L, 3),
                                 vias=nv))
    return rows
