#!/usr/bin/env python3
"""Negotiated-congestion (PathFinder) router for a whole board, built on libncr.so (A* on a 0.05 mm grid).

 * every net with more than one copper cluster is a routing object; clusters are joined as a tree (nearest first)
 * static legality per net from exact clearance-slack fields of all existing copper (slack.Field)
 * differential pairs: the N wire gets a cost bonus exactly one pair pitch away from the P wire on the same layer
 * conflicts between routed objects are negotiated (present usage x history) until none remain
 * the result is written as KiCad tracks + through vias

Board specifics come from a config module (cfg_cn1.py / cfg_mizban.py): layers, grid origin, net filter,
widths, clearances, layer costs, via size, pairs, keep-out masks.
usage: ncroute.py CFG IN.kicad_pcb OUT.kicad_pcb [MAXIT]
"""
import os, sys, math, re, json, time, ctypes, collections, importlib, pickle
import numpy as np
from scipy import ndimage
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.getcwd())     # board configs (cfg_*.py) may live in the working directory
import pcbnew
import slack as SL
from shapely.geometry import Point, box, Polygon
from shapely import vectorized as SV
import shapely
import shapely.prepared
import shapely.geometry

if sys.argv[1].endswith('.py'):      # a config given as a file path
    sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
    sys.argv[1] = os.path.splitext(os.path.basename(sys.argv[1]))[0]
CFG = importlib.import_module(sys.argv[1])
SRC, DST = sys.argv[2], sys.argv[3]
MAXIT = int(sys.argv[4]) if len(sys.argv) > 4 else 40
MM = 1e6
RES = getattr(CFG, 'RES', 0.05)
EPS = float(os.environ.get('EPS', 0.045))     # track/via rasterisation margin; override to test

lib = ctypes.CDLL(os.environ.get('NCR_LIB', os.path.join(HERE, 'libncr.so')))   # build: make (csrc/ncr.c)
P = ctypes.c_void_p
lib.ncr_init.argtypes = [ctypes.c_int] * 3
lib.ncr_mark.argtypes = [P, ctypes.c_int, ctypes.c_float, ctypes.c_float, ctypes.c_int]
lib.ncr_conflicts.argtypes = [P, ctypes.c_int, ctypes.c_float, ctypes.c_float, ctypes.c_float]
lib.ncr_conflicts.restype = ctypes.c_int
lib.ncr_route.argtypes = [P, P, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, P, ctypes.c_int, P, ctypes.c_int,
                          ctypes.c_float, ctypes.c_float, P, ctypes.c_float, ctypes.c_float, ctypes.c_float,
                          ctypes.c_float, ctypes.c_float, P, ctypes.c_float, ctypes.c_int, P, ctypes.c_int]
lib.ncr_route.restype = ctypes.c_int
lib.ncr_hist.restype = ctypes.POINTER(ctypes.c_float)


def ptr(a):
    return a.ctypes.data_as(P) if a is not None else None


t0 = time.time()
b = pcbnew.LoadBoard(SRC)
LAY = CFG.LAYERS
ALLCU = CFG.ALL_CU
WX0, WY0 = CFG.ORIGIN
bb = b.GetBoardEdgesBoundingBox()
BW, BH = bb.GetRight() / MM, bb.GetBottom() / MM
W, H = int((BW - WX0) / RES) + 1, int((BH - WY0) / RES) + 1
N = W * H
lib.ncr_init(W, H, len(LAY))
NETS = {n.GetNetname(): n for n in b.GetNetsByNetcode().values()}
CODE = {k: v.GetNetCode() for k, v in NETS.items()}
NAME = {v: k for k, v in CODE.items()}
maxcode = max(CODE.values()) + 2
clr_of = np.full(maxcode + 1, CFG.DEFAULT_CLR, np.float32)
for k, ni in NETS.items():
    clr_of[ni.GetNetCode() + 1] = CFG.CLASS_CLR.get(ni.GetNetClassName(), CFG.DEFAULT_CLR)

FLD = SL.Field(WX0, WY0, RES, W, H)
# .kicad_dru "BGA escape H3": any two non-zone items with one inside the BGA_U1 rule area need only 0.10 mm (custom rules
# override the netclass clearance); obstacles inside that area therefore carry min(class clearance, 0.10)
_BGA_REL = []
for _z in b.Zones():
    if _z.GetIsRuleArea() and _z.GetZoneName() in getattr(CFG, 'BGA_RULE_AREAS', ()):
        _o = _z.Outline()
        for _i in range(_o.OutlineCount()):
            _ol = _o.Outline(_i)
            _BGA_REL.append(shapely.prepared.prep(Polygon([(_ol.CPoint(k).x / MM, _ol.CPoint(k).y / MM) for k in range(_ol.PointCount())])))
_BGA_CLR = getattr(CFG, 'BGA_RULE_CLR', 0.10)
def _clr_adj(x, y, c):
    return min(c, _BGA_CLR) if _BGA_REL and any(g.contains(shapely.geometry.Point(x, y)) for g in _BGA_REL) else c
FLD.add_board(b, ALLCU, lambda n: float(clr_of[n + 1]) if n >= 0 else CFG.DEFAULT_CLR, clr_adj=_clr_adj)
print('BGA rule areas for clearance relief:', len(_BGA_REL), flush=True)
# second field with the minimum clearance for every item: an object with a larger own clearance c must keep
# dist >= hw + c from everything  <=>  slack_min > hw + (c - CMIN);  together with FLD this is dist >= hw + max(c, c_foreign)
_CMIN = min(CFG.CLASS_CLR.values())
FLD2 = SL.Field(WX0, WY0, RES, W, H)
FLD2.add_board(b, ALLCU, lambda n: _CMIN)
# board outline / keep-out masks
xs = WX0 + np.arange(W) * RES
ys = WY0 + np.arange(H) * RES
XX, YY = np.meshgrid(xs, ys)
BOARD = CFG.board_poly()
EDGE_D = np.full((H, W), 99.0, np.float32)
inside = SV.contains(BOARD, XX, YY)
EDGE_D = np.where(inside, shapely.distance(BOARD.boundary, shapely.points(XX.ravel(), YY.ravel())).reshape(XX.shape), 0.0).astype(np.float32)   # exact distance to the outline
EDGE_M = CFG.EDGE + 0.06                    # grid EDT is approximate: keep a small margin to the outline
CMIN = min(CFG.CLASS_CLR.values())
VSLK = FLD.min_all(ALLCU)
VSLK2 = FLD2.min_all(ALLCU)
VKEEP = np.zeros((H, W), bool)
RELAX = np.zeros((H, W), bool)
for g in (CFG.relax_areas(b) if hasattr(CFG, 'relax_areas') else []):
    RELAX |= SV.contains(g, XX, YY)
for g in CFG.via_keepouts(b):
    VKEEP |= SV.contains(g, XX, YY)
# track safety margin: EPS everywhere, CFG.EPS_BGA inside the areas where the grid is aligned to the ball-gap
# mid-lines (a trace through a 0.35 mm gap between 0.30 mm balls is then exact: 0.125 mm each side, DRC 0.10)
EPS_T = np.full((H, W), EPS, np.float32)
if getattr(CFG, 'EPS_BGA', None) is not None and hasattr(CFG, 'eps_bga_areas'):
    for g in CFG.eps_bga_areas(b):
        EPS_T[SV.contains(g, XX, YY)] = CFG.EPS_BGA
    print('track EPS %.3f, %.3f in %d aligned BGA area(s)' % (EPS, CFG.EPS_BGA, len(CFG.eps_bga_areas(b))), flush=True)
_lvia = {}
NETVIA = bool(os.environ.get('NETVIA'))
if NETVIA:
    # per-net via legality: the net-agnostic VSLK counts a net's own pads / tracks / vias as foreign copper, so no
    # via is ever allowed next to the pad it serves.  With NETVIA the via is checked like a track (own copper
    # excluded) on every layer, plus the two rules the blind spot used to cover implicitly:
    #   * no via copper within 0.06 mm of any soldered SMD pad (no via-in-pad / solder wicking, whatever the net)
    #   * hole-to-hole >= 0.20 mm (+margin) to every existing drill (vias and PTH), own net included
    _HOLE2HOLE = 0.20
    FLD_SMD = SL.Field(WX0, WY0, RES, W, H)
    FLD_SMD.add_board(b, [pcbnew.F_Cu, pcbnew.B_Cu], lambda n: 0.0,
                      skip=lambda it: not (it.GetClass() == 'PAD' and it.GetAttribute() == pcbnew.PAD_ATTRIB_SMD))
    SMDSLK = FLD_SMD.min_all([pcbnew.F_Cu, pcbnew.B_Cu])
    FLD_H = SL.Field(WX0, WY0, RES, W, H)
    for f_ in b.GetFootprints():
        for p_ in f_.Pads():
            if p_.GetDrillSize().x > 0:
                FLD_H.circle(pcbnew.F_Cu, p_.GetPosition().x / MM, p_.GetPosition().y / MM, p_.GetDrillSize().x / MM / 2, _HOLE2HOLE, -1)
    for t_ in b.GetTracks():
        if t_.GetClass() == 'PCB_VIA':
            FLD_H.circle(pcbnew.F_Cu, t_.GetPosition().x / MM, t_.GetPosition().y / MM, t_.GetDrillValue() / MM / 2, _HOLE2HOLE, -1)
    HSLK = FLD_H.layer(pcbnew.F_Cu)[0]
    _VBASE = (EDGE_D > EDGE_M + CFG.VIA[0] / 2) & ~VKEEP & (SMDSLK > CFG.VIA[0] / 2 + 0.06 + EPS / 2) & (HSLK > CFG.VIA[1] / 2 + EPS / 2)
    print('NETVIA: per-net via legality on', flush=True)


def lvia(xtra, code=None):
    if NETVIA and code is not None:
        k = (round(xtra, 4), code)
        if k not in _lvia:
            s1m = np.full((H, W), 99.0, np.float32); s2m = np.full((H, W), 99.0, np.float32)
            for l in ALLCU:
                a1, n1, a2 = FLD.layer(l)
                np.minimum(s1m, np.where(n1 == code, a2, a1), out=s1m)
                c1, m1, c2 = FLD2.layer(l)
                np.minimum(s2m, np.where(m1 == code, c2, c1), out=s2m)
            m = (s1m > CFG.VIA[0] / 2 + EPS) & ((s2m > CFG.VIA[0] / 2 + EPS + xtra) | RELAX) & _VBASE
            _lvia[k] = np.ascontiguousarray(m.astype(np.uint8).ravel())
        return _lvia[k]
    k = round(xtra, 4)
    if k not in _lvia:
        m = (VSLK > CFG.VIA[0] / 2 + EPS) & ((VSLK2 > CFG.VIA[0] / 2 + EPS + xtra) | RELAX) & (EDGE_D > EDGE_M + CFG.VIA[0] / 2) & ~VKEEP
        _lvia[k] = np.ascontiguousarray(m.astype(np.uint8).ravel())
    return _lvia[k]
print('grid %dx%d x %d layers, fields %.1fs' % (W, H, len(LAY), time.time() - t0), flush=True)
# footprint / board rule areas that forbid tracks or vias
RULE_T = np.zeros((len(LAY), H, W), bool)
for z in list(b.Zones()) + [z for f in b.GetFootprints() for z in f.Zones()]:
    if not z.GetIsRuleArea() or not (z.GetDoNotAllowTracks() or z.GetDoNotAllowVias()):
        continue
    o_ = z.Outline()
    for i in range(o_.OutlineCount()):
        ol = o_.Outline(i)
        poly = Polygon([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())])
        m = SV.contains(poly.buffer(0.11), XX, YY)                       # track half width 0.05 + margin
        for li, l in enumerate(LAY):
            if z.IsOnLayer(l) and z.GetDoNotAllowTracks():
                RULE_T[li] |= m
        if z.GetDoNotAllowVias():
            VKEEP |= SV.contains(poly.buffer(CFG.VIA[0] / 2 + 0.05), XX, YY)   # the whole via annulus stays outside
for li_, g in (CFG.track_keepouts(b) if hasattr(CFG, 'track_keepouts') else []):
    RULE_T[li_] |= SV.contains(g, XX, YY)
# nets allowed on L4 under the BGA inside the non-core pours: same rule areas, zone-only L4 keepout
RULE_T_OPEN = None
if getattr(CFG, 'L4_BGA_NETS', None) and hasattr(CFG, 'track_keepouts_l4open'):
    RULE_T_OPEN = RULE_T.copy()
    for li_, g in CFG.track_keepouts_l4open(b):
        RULE_T_OPEN[li_] = SV.contains(g, XX, YY)          # zone-only L4 keepout replaces the BGA blanket
    # keep the explicit rule-area keepouts on that layer
    for z in list(b.Zones()) + [z for f in b.GetFootprints() for z in f.Zones()]:
        if not z.GetIsRuleArea() or not z.GetDoNotAllowTracks():
            continue
        o_ = z.Outline()
        for i in range(o_.OutlineCount()):
            ol = o_.Outline(i)
            poly = Polygon([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())])
            for li, l in enumerate(LAY):
                if z.IsOnLayer(l):
                    RULE_T_OPEN[li] |= SV.contains(poly.buffer(0.05), XX, YY)
    OPEN_CODES = {CODE[n] for n in CODE if n.split('/')[-1] in CFG.L4_BGA_NETS}
    print('L4 opened under the BGA for', sorted(n.split('/')[-1] for n in CODE if CODE[n] in OPEN_CODES), flush=True)
else:
    OPEN_CODES = set()
_legal = {}


def legal(code, hw, xtra=0.0):
    k = (code, round(hw, 4), round(xtra, 4))
    if k not in _legal:
        out = np.zeros((len(LAY), H, W), np.uint8)
        for i, l in enumerate(LAY):
            ok = FLD.legal_track(l, code, hw, EPS_T) & (EDGE_D > EDGE_M + hw) & ~(RULE_T_OPEN[i] if code in OPEN_CODES else RULE_T[i])
            if xtra > 0:
                ok &= FLD2.legal_track(l, code, hw + xtra, EPS_T) | RELAX
            out[i] = ok
        _legal[k] = np.ascontiguousarray(out.ravel())
    return _legal[k]


def cell(x, y, li):
    return li * N + int(round((y - WY0) / RES)) * W + int(round((x - WX0) / RES))


def cxy(lc):
    c = lc % N
    return WX0 + (c % W) * RES, WY0 + (c // W) * RES, lc // N


# ------------------------------------------------------------------ copper clusters per net
conn = b.GetConnectivity()
b.BuildConnectivity()
by_net = collections.defaultdict(list)
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetNetCode() > 0:
            by_net[p.GetNetname()].append(p)
tr_by_net = collections.defaultdict(list)
for t in b.GetTracks():
    tr_by_net[t.GetNetname()].append(t)


def access(item, net):
    """grid access points (x, y, layer index) of a pad or via"""
    out = []
    if item.GetClass() == 'PCB_VIA':
        x, y = item.GetPosition().x / MM, item.GetPosition().y / MM
        return [(x, y, li) for li in range(len(LAY))]
    p = item
    x, y = p.GetPosition().x / MM, p.GetPosition().y / MM
    for li, l in enumerate(LAY):
        if not p.IsOnLayer(l):
            continue
        # all grid points inside the pad (shrunk by 0.03) + the pad centre
        bx0, by0 = p.GetBoundingBox().GetLeft() / MM, p.GetBoundingBox().GetTop() / MM
        bx1, by1 = p.GetBoundingBox().GetRight() / MM, p.GetBoundingBox().GetBottom() / MM
        pts = [(x, y)]
        i0, i1 = int(math.ceil((bx0 + 0.03 - WX0) / RES)), int(math.floor((bx1 - 0.03 - WX0) / RES))
        j0, j1 = int(math.ceil((by0 + 0.03 - WY0) / RES)), int(math.floor((by1 - 0.03 - WY0) / RES))
        cand = [(WX0 + i * RES, WY0 + j * RES) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)]
        for q in cand:
            if p.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(q[0]), pcbnew.FromMM(q[1]))):
                pts.append(q)
        out += [(q[0], q[1], li) for q in pts]
    return out


def clusters(net):
    items = list(by_net[net]) + [t for t in tr_by_net[net] if t.GetClass() == 'PCB_VIA']
    if len(items) < 2:
        return []
    ids = {}
    groups = []
    for it in items:
        k = it.m_Uuid.AsString()
        if k in ids:
            continue
        g = len(groups)
        mem = [it]
        ids[k] = g
        for o in conn.GetConnectedItems(it):
            ok = o.m_Uuid.AsString()
            if o.GetNetCode() == it.GetNetCode() and ok not in ids and (o.GetClass() in ('PAD', 'PCB_VIA')):
                ids[ok] = g
                mem.append(o)
        groups.append(mem)
    # merge groups that share members found later
    out = []
    for g in groups:
        acc = []
        for it in g:
            acc += access(it, net)
        acc = [a for a in acc if 0 <= int(round((a[0] - WX0) / RES)) < W and 0 <= int(round((a[1] - WY0) / RES)) < H]
        if acc:
            px = sum(a[0] for a in acc) / len(acc); py = sum(a[1] for a in acc) / len(acc)
            out.append(dict(acc=acc, pad=(px, py), items=[it.GetParentFootprint().GetReference() if it.GetClass() == 'PAD' else 'via' for it in g],
                            anchored=any(it.GetClass() == 'PCB_VIA' or (it.GetClass() == 'PAD' and it.GetAttribute() == pcbnew.PAD_ATTRIB_PTH) for it in g)))
    return out


objs = collections.OrderedDict()
for net in sorted(by_net):
    if not CFG.route_net(net, NETS[net].GetNetClassName()):
        continue
    if os.environ.get('NETRX') and not re.search(os.environ['NETRX'], net):
        continue
    cl = clusters(net)
    if len(cl) < 2:
        continue
    w = CFG.width(net, NETS[net].GetNetClassName())
    clr = float(clr_of[CODE[net] + 1])
    o = dict(name=net, code=CODE[net], terms=cl, paths=[], ok=False, w=w, clr=clr,
             lcost=np.array(CFG.layer_cost(net), np.float32), partner=CFG.partner(net),
             xtra=max(0.0, clr - min(CFG.CLASS_CLR.values())),
             rt=(w + clr) / 2 / RES + max(0.0, clr - min(CFG.CLASS_CLR.values())) / 2 / RES + 0.1,
             rv=(CFG.VIA[0] + clr) / 2 / RES + max(0.0, clr - min(CFG.CLASS_CLR.values())) / 2 / RES + 0.1)
    # root: the cluster with most pads (e.g. the BGA side)
    o['terms'].sort(key=lambda t: -len(t['acc']))
    objs[net] = o
# plane-net pads with no via of their own ("orphans"): short stub objects to the nearest via-anchored copper of the net
if getattr(CFG, 'PLANE_STUBS', False):
    STUB_R = float(os.environ.get('STUB_R', getattr(CFG, 'STUB_R', 4.0)))
    STUB_REFS = set(os.environ['STUB_REFS'].split(',')) if os.environ.get('STUB_REFS') else None
    for net in sorted(by_net):
        if net.split('/')[-1] not in CFG.PLANE_NETS:
            continue
        if os.environ.get('NETRX') and not re.search(os.environ['NETRX'], net) and not os.environ.get('STUBS_ALWAYS'):
            continue
        cl = clusters(net)
        anch = [t for t in cl if t['anchored']]
        for k, t in enumerate(cl):
            if t['anchored'] or not anch:
                continue
            if STUB_REFS is not None and not (set(t['items']) & STUB_REFS):
                continue
            near = sorted(anch, key=lambda a: min(math.hypot(q[0] - t['pad'][0], q[1] - t['pad'][1]) for q in a['acc']))[:6]
            near = [a for a in near if min(math.hypot(q[0] - t['pad'][0], q[1] - t['pad'][1]) for q in a['acc']) < STUB_R]
            if not near:
                print('  orphan without anchor in reach:', net, t['items'], t['pad'])
                continue
            dst_ = dict(acc=[q for a in near for q in a['acc']], pad=near[0]['pad'], items=['anchor'], anchored=True)
            w = float(os.environ.get('STUB_W', getattr(CFG, 'STUB_W', 0.2)))
            clr = float(clr_of[CODE[net] + 1])
            nm = '%s#%d' % (net, k)
            objs[nm] = dict(name=nm, net=net, code=CODE[net], terms=[dst_, t], paths=[], ok=False, w=w, clr=clr,
                            lcost=np.array(CFG.layer_cost(net), np.float32), partner=None,
                            xtra=max(0.0, clr - min(CFG.CLASS_CLR.values())),
                            rt=(w + clr) / 2 / RES + max(0.0, clr - min(CFG.CLASS_CLR.values())) / 2 / RES + 0.1,
                            rv=(CFG.VIA[0] + clr) / 2 / RES + max(0.0, clr - min(CFG.CLASS_CLR.values())) / 2 / RES + 0.1)
    print('plane stubs:', sum(1 for k in objs if '#' in k))
# ------------------------------------------------------------------ coupled pairs as one fat object (centre line, split later)
FATSRC = {}
_FO = None


def foreign_near(x, y, r, codes):
    """copper items (pads, vias, tracks) near (x, y) not belonging to `codes`: list of (shapely geom, layer set)"""
    global _FO
    if _FO is None:
        _FO = []
        for f_ in b.GetFootprints():
            for p_ in f_.Pads():
                bb_ = p_.GetBoundingBox()
                g_ = box(bb_.GetLeft() / MM, bb_.GetTop() / MM, bb_.GetRight() / MM, bb_.GetBottom() / MM)
                _FO.append((g_, p_.GetNetCode(), {l for l in LAY if p_.IsOnLayer(l)}))
        for t_ in b.GetTracks():
            if t_.GetClass() == 'PCB_VIA':
                _FO.append((Point(t_.GetPosition().x / MM, t_.GetPosition().y / MM).buffer(t_.GetWidth() / MM / 2, 8), t_.GetNetCode(), set(LAY)))
            else:
                from shapely.geometry import LineString as _LS
                _FO.append((_LS([(t_.GetStart().x / MM, t_.GetStart().y / MM), (t_.GetEnd().x / MM, t_.GetEnd().y / MM)]).buffer(t_.GetWidth() / MM / 2, 4),
                            t_.GetNetCode(), {t_.GetLayer()}))
    q_ = Point(x, y).buffer(r)
    return [(g_, ls_) for g_, c_, ls_ in _FO if c_ not in codes and g_.intersects(q_)]


def fo_ok(fo, x, y, layer, d):
    pt_ = Point(x, y)
    return all(g_.distance(pt_) >= d for g_, ls_ in fo if layer in ls_)




def _is_p(s):
    return s.endswith('_P') or s.endswith('_DP') or (s.startswith('EPHY_') and s.endswith('P'))


if hasattr(CFG, 'PAIR_FAT'):
    _full = {k.split('/')[-1]: k for k in objs}
    for name in list(objs):
        o = objs.get(name)
        if o is None or not o['partner'] or not CFG.PAIR_FAT(name) or not _is_p(name.split('/')[-1]):
            continue
        qn = _full.get(o['partner'].split('/')[-1])
        if qn is None or qn not in objs:
            continue
        q = objs[qn]
        cp, cn_ = o['terms'], q['terms']
        if len(cp) != len(cn_):
            print('  fat pair skipped (terminal count):', name)
            continue
        pairs, used = [], set()
        for tp in cp:
            j = min((j for j in range(len(cn_)) if j not in used), key=lambda j: math.hypot(cn_[j]['pad'][0] - tp['pad'][0], cn_[j]['pad'][1] - tp['pad'][1]))
            used.add(j); pairs.append((tp, cn_[j]))
        if max(math.hypot(a['pad'][0] - c['pad'][0], a['pad'][1] - c['pad'][1]) for a, c in pairs) > 3.0:
            print('  fat pair skipped (terminals apart):', name)
            continue
        w = max(o['w'], q['w']); gap = CFG.pair_gap(name); off = (w + gap) / 2; hwf = off + w / 2
        clr = max(o['clr'], q['clr']); xtra = max(o['xtra'], q['xtra'])
        # "through" terminals: P/N pads side by side (socket, flow-through ESD) - the pair runs straight over them
        thr = [math.hypot(tp['pad'][0] - tn['pad'][0], tp['pad'][1] - tn['pad'][1]) <= getattr(CFG, 'FAT_THROUGH', 0.65) for tp, tn in pairs]
        if len(pairs) > 2:
            ij = max(((i, j) for i in range(len(pairs)) for j in range(i + 1, len(pairs))),
                     key=lambda ij: math.hypot(pairs[ij[0]][0]['pad'][0] - pairs[ij[1]][0]['pad'][0], pairs[ij[0]][0]['pad'][1] - pairs[ij[1]][0]['pad'][1]))
            keep = [k_ for k_ in range(len(pairs)) if k_ in ij or thr[k_]]     # other in-line parts get stubs
            # chain order: from one end, nearest next
            cur = ij[0]; seq = [cur]; rest = [k_ for k_ in keep if k_ != cur]
            while rest:
                cur = min(rest, key=lambda k_: math.hypot(pairs[k_][0]['pad'][0] - pairs[seq[-1]][0]['pad'][0], pairs[k_][0]['pad'][1] - pairs[seq[-1]][0]['pad'][1]))
                seq.append(cur); rest.remove(cur)
            pairs = [pairs[k_] for k_ in seq]; thr = [thr[k_] for k_ in seq]
        SMR = 0.35 * RES           # centre-line smoothing allowance (the offsets are drawn from the simplified line)
        lf = (legal(o['code'], hwf + SMR, xtra) & legal(q['code'], hwf + SMR, xtra)).astype(np.uint8)
        vo = max(off, (CFG.VIA[0] + clr) / 2 + 0.03)
        rvv = vo + CFG.VIA[0] / 2
        lvf = (VSLK > rvv + EPS) & ((VSLK2 > rvv + EPS + xtra) | RELAX) & (EDGE_D > EDGE_M + rvv) & ~VKEEP
        lf3 = lf.reshape(len(LAY), H, W)
        FR = int(getattr(CFG, 'FAT_R', 2.5) / RES)
        # break-out cells must lie in the big connected free region of their layer (not a pocket inside a BGA field)
        MAINC = []
        for li in range(len(LAY)):
            lab, nl = ndimage.label(lf3[li])
            if nl == 0:
                MAINC.append(np.zeros((H, W), bool)); continue
            sz = np.bincount(lab.ravel()); sz[0] = 0
            MAINC.append(lab == int(np.argmax(sz)))
        fterms = []
        for ti_, (tp, tn) in enumerate(pairs):
            mx, my = (tp['pad'][0] + tn['pad'][0]) / 2, (tp['pad'][1] + tn['pad'][1]) / 2
            lays = {a[2] for a in tp['acc']} & {a[2] for a in tn['acc']} or {a[2] for a in tp['acc']}
            gx, gy = int(round((mx - WX0) / RES)), int(round((my - WY0) / RES))
            if thr[ti_]:
                # corridor across the pad pair: legal wherever foreign copper keeps hwf + clr
                ux, uy = tn['pad'][0] - tp['pad'][0], tn['pad'][1] - tp['pad'][1]; L_ = math.hypot(ux, uy) or 1.0; ux, uy = ux / L_, uy / L_
                vx_, vy_ = -uy, ux
                TL = getattr(CFG, 'FAT_THROUGH_L', 1.8)
                acc = []
                fo = foreign_near(mx, my, TL + 2.0, {o['code'], q['code']})
                for li in lays:
                    for t_ in np.arange(-TL, TL + 1e-6, RES):
                        for s_ in (0.0,):
                            px_, py_ = mx + vx_ * t_ + ux * s_, my + vy_ * t_ + uy * s_
                            cx_, cy_ = int(round((px_ - WX0) / RES)), int(round((py_ - WY0) / RES))
                            if not (0 <= cx_ < W and 0 <= cy_ < H):
                                continue
                            qx, qy = WX0 + cx_ * RES, WY0 + cy_ * RES
                            if EDGE_D[cy_, cx_] > EDGE_M + hwf and fo_ok(fo, qx, qy, LAY[li], hwf + clr + EPS):
                                lf3[li, cy_, cx_] = 1
                                if math.hypot(qx - mx, qy - my) < RES * 0.75:
                                    acc.append((qx, qy, li))
                if not acc:
                    break
                fterms.append(dict(acc=acc, pad=(mx, my), items=['fat'], anchored=True, tp=tp, tn=tn))
                continue
            ox_ = [((a['pad'][0] + c['pad'][0]) / 2, (a['pad'][1] + c['pad'][1]) / 2) for k_, (a, c) in enumerate(pairs) if k_ != ti_]
            tox, toy = (sum(v[0] for v in ox_) / len(ox_) - mx, sum(v[1] for v in ox_) / len(ox_) - my) if ox_ else (0.0, 0.0)
            cand = []
            for li in lays:
                y0_, x0_ = max(0, gy - FR), max(0, gx - FR)
                sub = lf3[li, y0_:gy + FR + 1, x0_:gx + FR + 1]
                yy_, xx_ = np.nonzero(sub)
                for yv, xv in zip(yy_ + y0_, xx_ + x0_):
                    d = math.hypot(xv - gx, yv - gy)
                    if d <= FR and (xv - gx) * tox + (yv - gy) * toy >= 0 and MAINC[li][yv, xv]:     # towards the far end, never behind the part
                        cand.append((d, WX0 + xv * RES, WY0 + yv * RES, li))
            cand.sort()
            if not cand:
                if os.environ.get('DBGFAT'):
                    print('    fat breakout fail: term', ti_, 'pad', (mx, my), 'lays', lays, 'gx,gy', gx, gy)
                break
            fterms.append(dict(acc=[(x, y, li) for d, x, y, li in cand[:30]], pad=(mx, my), items=['fat'], anchored=True, tp=tp, tn=tn))
        if len(fterms) != len(pairs):
            print('  fat pair skipped (no breakout):', name)
            continue
        nm = name + '&'
        objs[nm] = dict(name=nm, net=name, code=o['code'], terms=fterms, paths=[], ok=False, w=w, clr=clr, fat=True, chain=True,
                        off=off, vo=vo, lg=lf, lv=np.ascontiguousarray(lvf.astype(np.uint8).ravel()), pn=(name, qn),
                        lcost=o['lcost'], partner=None, xtra=xtra,
                        rt=(2 * (hwf + SMR) + clr) / 2 / RES + xtra / 2 / RES + 0.1, rv=(2 * rvv + clr) / 2 / RES + xtra / 2 / RES + 0.1)
        FATSRC[nm] = (objs.pop(name), objs.pop(qn))
    print('fat pairs:', len(FATSRC))
SHORTMAP = {k.split('/')[-1]: k for k in objs}
for o in objs.values():
    if o['partner']:
        o['partner'] = SHORTMAP.get(o['partner'].split('/')[-1])
print('%d routing objects (%d paired), %.1fs' % (len(objs), sum(1 for o in objs.values() if o['partner']), time.time() - t0), flush=True)
RV = (CFG.VIA[0] + CFG.DEFAULT_CLR) / 2 / RES + 0.1
OUTBUF = np.zeros(600000, np.int32)
MARGIN = int(3.0 / RES)
LENFIX = json.loads(os.environ.get('LENFIX', '{}'))
CM = {}


def short_(n):
    return n.split('/')[-1]


def cells_of(o):
    return np.concatenate([np.asarray(p, np.int32) for p in o['paths']]) if o['paths'] else np.zeros(0, np.int32)


def mark(o, d):
    c = cells_of(o)
    if len(c):
        lib.ncr_mark(ptr(c), len(c), o['rt'] - 0.1, o['rv'] - 0.1, d)


def conflicts(o, hadd):
    c = cells_of(o)
    if o.get('fixed') is not None and o.get('geo'):
        # split pair: the offset tracks are exact geometry, only the stubs are checked
        rest = o['paths'][len(o['fixed']):]
        c = np.concatenate([np.asarray(p, np.int32) for p in rest]) if rest else np.zeros(0, np.int32)
    if not len(c):
        return 0
    mark(o, -1)
    n = lib.ncr_conflicts(ptr(c), len(c), o['rt'], o['rv'], hadd)
    mark(o, +1)
    return n


def pair_cmul(o):
    """cost multiplier map: bonus one pair pitch away from the partner's copper on the same layer"""
    pn = o['partner']
    if not pn or pn not in objs or not objs[pn]['paths']:
        return None
    q = objs[pn]
    c = cells_of(q)
    lay = c // N; cc = c % N
    out_m = getattr(CFG, 'PAIR_OUT', 1.0)
    cm = np.full((len(LAY), H, W), out_m, np.float32)
    pitch = (o['w'] + CFG.pair_gap(o['name'])) / RES
    # free break-out near the object's own terminals
    rr = int(getattr(CFG, 'PAIR_BREAKOUT', 1.0) / RES)
    allow = np.zeros((len(LAY), H, W), bool)
    for t in o['terms']:
        cx_, cy_ = int(round((t['pad'][0] - WX0) / RES)), int(round((t['pad'][1] - WY0) / RES))
        cm[:, max(0, cy_ - rr):cy_ + rr + 1, max(0, cx_ - rr):cx_ + rr + 1] = 1.0
        allow[:, max(0, cy_ - rr):cy_ + rr + 1, max(0, cx_ - rr):cx_ + rr + 1] = True
    # partner vias: a coupled via pair needs more than one pitch, so the band opens up around each partner via
    rv_ = int(getattr(CFG, 'PAIR_VIA_OPEN', 1.0) / RES)
    for p in q['paths']:
        p = np.asarray(p)
        for i in range(len(p) - 1):
            if p[i] % N == p[i + 1] % N:
                vy_, vx_ = divmod(int(p[i] % N), W)
                cm[:, max(0, vy_ - rv_):vy_ + rv_ + 1, max(0, vx_ - rv_):vx_ + rv_ + 1] = 1.0
                allow[:, max(0, vy_ - rv_):vy_ + rv_ + 1, max(0, vx_ - rv_):vx_ + rv_ + 1] = True
    for li in range(len(LAY)):
        s_ = lay == li
        if not s_.any():
            continue
        m = np.zeros((H, W), bool)
        m[cc[s_] // W, cc[s_] % W] = True
        # restrict the EDT to the bounding box of the partner (+margin) for speed
        yy, xx = np.nonzero(m)
        y0, y1 = max(0, yy.min() - 20), min(H, yy.max() + 21); x0, x1 = max(0, xx.min() - 20), min(W, xx.max() + 21)
        d = ndimage.distance_transform_edt(~m[y0:y1, x0:x1])
        sub = cm[li, y0:y1, x0:x1]
        band = (d > pitch - 0.6) & (d < pitch + 0.6)
        sub[band] = CFG.PAIR_BONUS
        allow[li, y0:y1, x0:x1] |= band
    return np.ascontiguousarray(cm.ravel()), np.ascontiguousarray(allow.ravel().astype(np.uint8))


def route(o, pres, hist_w=1.0):
    if o.get('fat'):
        return route1(o, pres, hist_w, o['lg'], None)
    if o.get('fixed') is not None:
        return route1(o, pres, hist_w, legal(o['code'], o['w'] / 2, o['xtra']), None)
    pc = pair_cmul(o)
    if pc is None:
        return route1(o, pres, hist_w, legal(o['code'], o['w'] / 2, o['xtra']), None)
    cm, allow = pc
    lg = legal(o['code'], o['w'] / 2, o['xtra'])
    ph = getattr(CFG, 'PAIR_HARD', False)
    if (ph(o['name']) if callable(ph) else ph) and route1(o, pres, hist_w, np.ascontiguousarray(lg & allow), cm):
        o['coupled'] = True
        return True
    o['coupled'] = False
    return route1(o, pres, hist_w, lg, cm)


def route1(o, pres, hist_w, lg, cm):
    tree = [cell(*a) for a in o['terms'][0]['acc']]
    full = set(tree)
    paths = [np.asarray(fp, np.int32) for fp in o.get('fixed') or []]
    pending = list(o['terms'][1:])
    skipped = 0
    while pending:
        if o.get('chain'):
            full = set(tree)
        tc = np.array([cxy(v)[:2] for v in tree])
        pending.sort(key=lambda t: np.min(np.abs(tc[:, 0] - t['pad'][0]) + np.abs(tc[:, 1] - t['pad'][1])))
        t = pending.pop(0)
        dst = np.array([cell(*a) for a in t['acc']], np.int32)
        # sources: tree cells near the terminal (limits the search start set)
        srcs = np.array(sorted(full, key=lambda v: abs(cxy(v)[0] - t['pad'][0]) + abs(cxy(v)[1] - t['pad'][1]))[:4000], np.int32)
        pts = [cxy(v) for v in list(srcs[:200]) + list(dst)]
        xs_ = [int(round((p[0] - WX0) / RES)) for p in pts]; ys_ = [int(round((p[1] - WY0) / RES)) for p in pts]
        wx0, wx1 = max(0, min(xs_) - MARGIN), min(W, max(xs_) + MARGIN + 1)
        wy0, wy1 = max(0, min(ys_) - MARGIN), min(H, max(ys_) + MARGIN + 1)
        n = -1
        # length bound (cells): straight octile distance from the tree to the terminal + the config allowance
        tpts = np.array([cxy(v)[:2] for v in tree]); dx_ = np.abs(tpts[:, 0] - t['pad'][0]); dy_ = np.abs(tpts[:, 1] - t['pad'][1])
        straight = float(np.min(np.maximum(dx_, dy_) + 0.41421 * np.minimum(dx_, dy_))) / RES
        ml = CFG.max_len(o['name'], straight * RES, o) / RES if hasattr(CFG, 'max_len') else 0.0
        if short_(o['name']) in LENFIX and len(o['terms']) == 2:
            ml = LENFIX[short_(o['name'])] / RES
        for grow in (0, 60, 200):
            n = lib.ncr_route(ptr(lg), ptr(o['lv'] if 'lv' in o else lvia(o['xtra'], o['code'])), max(0, wx0 - grow), max(0, wy0 - grow), min(W, wx1 + grow), min(H, wy1 + grow),
                              ptr(srcs), len(srcs), ptr(dst), len(dst), o['rt'], o['rv'], ptr(o['lcost']), CFG.via_cost(o['name']) if hasattr(CFG, 'via_cost') else CFG.VIA_COST,
                              CFG.B45, CFG.B90, pres, hist_w, ptr(cm), ml, 4000000 if grow < 200 else 25000000, ptr(OUTBUF), len(OUTBUF))
            if n > 0:
                break
        if n <= 0:
            if os.environ.get('DBGFAT') and o.get('fat'):
                import pickle as _pk
                _pk.dump(dict(lg=np.asarray(lg).copy(), tree=tree, dst=dst.tolist(), paths=[np.asarray(pp) for pp in paths], W=W, H=H), open('/tmp/claude-0/-home-claude/cb9fac10-5a9d-5a0a-852d-91a811c28cb9/scratchpad/fatfail.pkl', 'wb'))
            if os.environ.get('DBGFAIL'):
                print('    fail term', t['items'][:3], t['pad'], 'acc', len(t['acc']), 'legal', int(sum(lg[c] for c in dst)), 'tree', len(tree), 'srclegal', int(sum(lg[c] for c in srcs[:50])), flush=True)
            if os.environ.get('SKIPFAIL'):
                skipped += 1           # leave this terminal unconnected, keep joining the others
                continue
            o['paths'] = paths; o['ok'] = False
            return False
        p = OUTBUF[:n].copy()
        paths.append(p)
        if o.get('fat') and pending:
            # self-avoidance: later chain segments may not reuse the corridor of this one (except right at terminals)
            if lg is o['lg']:
                lg = lg.copy()
            rr_ = int(math.ceil(2 * o['rt']))
            lg3 = lg.reshape(len(LAY), H, W)
            tpts = [t2['pad'] for t2 in o['terms']]
            for lc in p:
                x_, y_, li_ = cxy(lc)
                if min(math.hypot(x_ - a[0], y_ - a[1]) for a in tpts) < (rr_ + 1) * RES:
                    continue
                cy_, cx_ = divmod(int(lc % N), W)
                lg3[:, max(0, cy_ - rr_):cy_ + rr_ + 1, max(0, cx_ - rr_):cx_ + rr_ + 1] = 0
        for i, lc in enumerate(p):
            c = lc % N
            add = [li * N + c for li in range(len(LAY))] if (i + 1 < n and p[i + 1] % N == c) else [int(lc)]
            full.update(add)
        for a in t['acc']:
            full.add(cell(*a))
        tree = [cell(*a) for a in t['acc']] if o.get('chain') else list(full)
    o['paths'] = paths; o['ok'] = not skipped
    return not skipped


# ------------------------------------------------------------------ negotiation
_OL = re.compile(os.environ['ORDER_LAST']) if os.environ.get('ORDER_LAST') else None
order = sorted(objs.values(), key=lambda o: (1 if (_OL and _OL.search(o['name'])) else 0, 0 if '#' in o['name'] else 1, CFG.order_key(o)))
pres = 0.5
todo = list(order)
BEST = [1e18, None]
statef = os.path.splitext(DST)[0] + '_ncstate.pkl'
if os.environ.get('LOAD') and os.path.exists(statef):
    st = pickle.load(open(statef, 'rb'))
    for k, ps in st.items():
        if k in objs:
            objs[k]['paths'] = [np.asarray(p, np.int32) for p in ps]
            objs[k]['ok'] = len(ps) == len(objs[k]['terms']) - 1
            mark(objs[k], +1)
    todo = [o for o in order if not o['ok'] or conflicts(o, 0) or short_(o['name']) in LENFIX]
    pres = float(os.environ.get('PRES', 8.0))
import signal
STOP = [False]
signal.signal(signal.SIGTERM, lambda *a: STOP.__setitem__(0, True))
signal.signal(signal.SIGUSR1, lambda *a: STOP.__setitem__(0, True))
STAG = int(os.environ.get('STAG', 999))
last_best_it = 0
for it in range(MAXIT):
    if STOP[0]:
        print('stop requested'); break
    ti = time.time()
    for o in todo:
        if o['paths']:
            mark(o, -1)
        tt = time.time()
        route(o, pres)
        if time.time() - tt > 5:
            print('  slow %s %.1fs ok=%s' % (o['name'], time.time() - tt, o['ok']), flush=True)
        if o['paths']:
            mark(o, +1)
    bad = [o for o in order if not o['ok']]
    conf = {o['name']: conflicts(o, CFG.HADD) for o in order}
    cn = [k for k, v in conf.items() if v]
    score = sum(conf.values()) + 1000 * len(bad)
    print('it %2d pres %7.2f routed %d/%d conflicting %d (%d cells) %.0fs' % (
        it, pres, len(order) - len(bad), len(order), len(cn), sum(conf.values()), time.time() - ti), flush=True)
    if bad:
        print('  failed:', ' '.join(short_(o['name']) for o in bad), flush=True)
    if score < BEST[0]:
        last_best_it = it
    if score <= BEST[0]:
        BEST[0] = score
        BEST[1] = {k: [np.asarray(p).copy() for p in o['paths']] for k, o in objs.items()}
    pickle.dump({k: [np.asarray(p) for p in o['paths']] for k, o in objs.items()}, open(statef, 'wb'))
    if not cn and not bad:
        break
    if it - last_best_it >= STAG and BEST[0] < 1000 * (len(bad) + 1):
        print('stagnant for %d iterations, stopping' % STAG); break
    names = set(cn) | {o['name'] for o in bad}
    for k in list(names):
        if objs[k]['partner'] in objs:
            names.add(objs[k]['partner'])
    todo = sorted([o for o in order if o['name'] in names], key=lambda o: -conf.get(o['name'], 0)) if it < int(os.environ.get('RIPALL_AFTER', CFG.RIPALL_AFTER)) else \
        (list(order) if _OL else sorted(order, key=lambda o: -conf.get(o['name'], 0)))
    pres = min(pres * CFG.PGROW, 4000.0)

cur = sum(conflicts(o, 0) for o in order) + 1000 * sum(1 for o in order if not o['ok'])
if BEST[1] is not None and BEST[0] < cur:
    print('restoring best state (%d < %d)' % (BEST[0], cur))
    for o in order:
        if o['paths']:
            mark(o, -1)
        o['paths'] = BEST[1][o['name']]; o['ok'] = len(o['paths']) == len(o['terms']) - 1
        if o['paths']:
            mark(o, +1)
lib.ncr_occ.restype = ctypes.POINTER(ctypes.c_int16)
OCC = np.ctypeslib.as_array(lib.ncr_occ(), shape=(len(LAY) * N,))
hot = collections.Counter()
for o in order:
    if not o['paths'] or not conflicts(o, 0):
        continue
    mark(o, -1)
    occ3 = OCC.reshape(len(LAY), H, W)
    c = cells_of(o)
    r = int(math.ceil(o['rt']))
    for lc in c[::2]:
        l, cc = lc // N, lc % N
        x, y = cc % W, cc // W
        win = occ3[l, max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
        if win.max() > 0:
            hot[(round(WX0 + x * RES, 1), round(WY0 + y * RES, 1), l, short_(o['name']))] += 1
    mark(o, +1)
by_obj = collections.defaultdict(list)
for (x, y, l, nm), k in hot.items():
    by_obj[nm].append((x, y, l))
for nm, pts in by_obj.items():
    xs_ = [p[0] for p in pts]; ys_ = [p[1] for p in pts]
    print('  conflict %-14s n=%3d  x %.1f-%.1f y %.1f-%.1f layers %s' % (nm, len(pts), min(xs_), max(xs_), min(ys_), max(ys_), sorted({p[2] for p in pts})))
# drop conflicting objects entirely so the written board is DRC-clean (they are reported as unrouted)
dropped = []
for o in order:
    if o['paths'] and conflicts(o, 0):
        mark(o, -1); o['paths'] = []; o['ok'] = False; dropped.append(o['name'])
print('dropped (conflicting):', dropped)

def polylines(p):
    runs, vias, cur_ = [], [], [p[0]]
    for lc in p[1:]:
        if lc % N == cur_[-1] % N and lc // N != cur_[-1] // N:
            runs.append(cur_); vias.append(cxy(lc)[:2]); cur_ = [lc]
        else:
            cur_.append(lc)
    runs.append(cur_)
    out = []
    for r in runs:
        pts = [cxy(v)[:2] for v in r]
        red = [pts[0]]
        for i in range(1, len(pts) - 1):
            ax, ay = red[-1]; bx_, by_ = pts[i]; cx_, cy_ = pts[i + 1]
            if abs((bx_ - ax) * (cy_ - by_) - (by_ - ay) * (cx_ - bx_)) > 1e-9:
                red.append(pts[i])
        if len(pts) > 1:
            red.append(pts[-1])
        out.append((LAY[r[0] // N], red))
    return out, vias



# ------------------------------------------------------------------ fat pairs -> two offset tracks + short stubs to the pads
from shapely.geometry import LineString


def _offset(pts, d):
    """parallel copy of a polyline at signed distance d (mitre joins), same direction"""
    if len(pts) < 2:
        return list(pts)
    g = LineString(pts).offset_curve(d, join_style=2, mitre_limit=4.0)
    if g.geom_type != 'LineString' or g.is_empty:
        return None
    q = list(g.coords)
    if math.hypot(q[0][0] - pts[0][0], q[0][1] - pts[0][1]) > math.hypot(q[-1][0] - pts[0][0], q[-1][1] - pts[0][1]):
        q = q[::-1]
    return q


def _raster(pts, li):
    out = []
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        L = math.hypot(xb - xa, yb - ya); n = max(1, int(L / (RES * 0.5)))
        for k in range(n + 1):
            c = cell(xa + (xb - xa) * k / n, ya + (yb - ya) * k / n, li)
            if not out or out[-1] != c:
                out.append(c)
    if len(pts) == 1:
        out.append(cell(pts[0][0], pts[0][1], li))
    return out


def split_fat(o):
    """returns {net: dict(lines=[(layer_idx, pts)], vias=[(x, y)])} for P and N, or None if the split is not clean"""
    pnet, nnet = o['pn']
    geo = {pnet: dict(lines=[], vias=[]), nnet: dict(lines=[], vias=[])}
    off, vo = o['off'], o['vo']
    for k, p in enumerate(o['paths']):
        # the terminal this path starts from / ends at (chain order = order of routing)
        runs, cur_ = [], [p[0]]
        for lc in p[1:]:
            if lc % N == cur_[-1] % N and lc // N != cur_[-1] // N:
                runs.append(cur_); cur_ = [lc]
            else:
                cur_.append(lc)
        runs.append(cur_)
        a0 = cxy(p[0])[:2]
        ta = min(o['terms'], key=lambda t: min(math.hypot(q[0] - a0[0], q[1] - a0[1]) for q in t['acc']))
        pref = ta['tp']['pad']                       # P side reference: the P pad at the start terminal
        if os.environ.get('DBGFAT'):
            print('    fatpath', o['name'], k, 'start', [round(v, 2) for v in a0], 'end', [round(v, 2) for v in cxy(p[-1])[:2]], 'runs', [(r[0] // N, len(r)) for r in runs],
                  'P', [round(v, 2) for v in ta['tp']['pad']], 'N', [round(v, 2) for v in ta['tn']['pad']])
        prevP = prevN = None
        for ri, r in enumerate(runs):
            li = r[0] // N
            pts = [cxy(v)[:2] for v in r]
            red = [pts[0]]
            for i in range(1, len(pts) - 1):
                ax, ay = red[-1]; bx_, by_ = pts[i]; cx_, cy_ = pts[i + 1]
                if abs((bx_ - ax) * (cy_ - by_) - (by_ - ay) * (cx_ - bx_)) > 1e-9:
                    red.append(pts[i])
            if len(pts) > 1:
                red.append(pts[-1])
            if len(red) > 2:
                red = [tuple(v) for v in LineString(red).simplify(0.35 * RES, preserve_topology=False).coords]
            if len(red) >= 2:
                A, B = _offset(red, off), _offset(red, -off)
                if A is None or B is None:
                    print('    split: offset failed', o['name'], red[:4]); return None
                if prevP is not None:
                    swap = math.hypot(A[0][0] - prevP[0], A[0][1] - prevP[1]) > math.hypot(B[0][0] - prevP[0], B[0][1] - prevP[1])
                else:
                    # the side of P: P pad minus N pad projected on the left normal of the first segment
                    dx0, dy0 = red[1][0] - red[0][0], red[1][1] - red[0][1]
                    pp, nn_ = ta['tp']['pad'], ta['tn']['pad']
                    swap = ((pp[0] - nn_[0]) * -dy0 + (pp[1] - nn_[1]) * dx0) < 0
                if swap:
                    A, B = B, A
                if prevP is not None:
                    A = [prevP] + A; B = [prevN] + B
                geo[pnet]['lines'].append((li, A)); geo[nnet]['lines'].append((li, B))
                endP, endN, dirv = A[-1], B[-1], (red[-1][0] - red[-2][0], red[-1][1] - red[-2][1])
            else:
                endP, endN = prevP or red[0], prevN or red[0]
                dirv = (1.0, 0.0)
            if ri < len(runs) - 1:
                vx, vy = red[-1]
                L = math.hypot(*dirv) or 1.0
                nx_, ny_ = -dirv[1] / L, dirv[0] / L
                nr = runs[ri + 1]
                if len(nr) > 1:        # bisector of the incoming and outgoing normals: the via pair sits square to the turn
                    q0, q1 = cxy(nr[0])[:2], cxy(nr[min(3, len(nr) - 1)])[:2]
                    dx2, dy2 = q1[0] - q0[0], q1[1] - q0[1]; L2 = math.hypot(dx2, dy2) or 1.0
                    bx2, by2 = nx_ + (-dy2 / L2), ny_ + dx2 / L2
                    if math.hypot(bx2, by2) > 0.3:
                        Lb = math.hypot(bx2, by2); nx_, ny_ = bx2 / Lb, by2 / Lb
                v1, v2 = (vx + nx_ * vo, vy + ny_ * vo), (vx - nx_ * vo, vy - ny_ * vo)
                if math.hypot(v1[0] - endP[0], v1[1] - endP[1]) > math.hypot(v2[0] - endP[0], v2[1] - endP[1]):
                    v1, v2 = v2, v1
                if len(red) >= 2:
                    geo[pnet]['lines'][-1][1].append(v1); geo[nnet]['lines'][-1][1].append(v2)
                geo[pnet]['vias'].append(v1); geo[nnet]['vias'].append(v2)
                prevP, prevN = v1, v2
    # sanity: the two nets must not touch
    from shapely.geometry import MultiLineString
    gp = [LineString(l) for li, l in geo[pnet]['lines'] if len(l) > 1]
    gn = [LineString(l) for li, l in geo[nnet]['lines'] if len(l) > 1]
    for li in range(len(LAY)):
        a_ = [LineString(l) for lj, l in geo[pnet]['lines'] if lj == li and len(l) > 1]
        b_ = [LineString(l) for lj, l in geo[nnet]['lines'] if lj == li and len(l) > 1]
        if a_ and b_ and MultiLineString(a_).distance(MultiLineString(b_)) < o['w'] + o['clr'] - 0.005:
            from shapely.ops import nearest_points
            np_ = nearest_points(MultiLineString(a_), MultiLineString(b_))
            if os.environ.get('DBGFAT'):
                import pickle as _pk
                _pk.dump(dict(geo=geo, paths=[np.asarray(pp) for pp in o['paths']], W=W, H=H, N=N, WX0=WX0, WY0=WY0, RES=RES),
                         open('/tmp/claude-0/-home-claude/cb9fac10-5a9d-5a0a-852d-91a811c28cb9/scratchpad/split_%s.pkl' % short_(o['name']).strip('&'), 'wb'))
            print('    split: P-N too close on layer', li, o['name'], round(MultiLineString(a_).distance(MultiLineString(b_)), 3), 'at', [round(v, 2) for v in np_[0].coords[0]])
            return None
    return geo


def validate_fat(o, geo):
    """exact copper check of the split pair: P vs N and both vs static foreign copper"""
    from shapely.ops import unary_union
    pnet, nnet = o['pn']
    codes = {CODE[pnet], CODE[nnet]}
    cop = {}
    for nt in (pnet, nnet):
        g = geo[nt]
        per = collections.defaultdict(list)
        for li, pts in g['lines']:
            if len(pts) > 1:
                per[li].append(LineString(pts).buffer(o['w'] / 2, 8))
        for v in g['vias']:
            for li in range(len(LAY)):
                per[li].append(Point(v).buffer(CFG.VIA[0] / 2, 16))
        cop[nt] = {li: unary_union(v) for li, v in per.items()}
    for li in range(len(LAY)):
        a_, b_ = cop[pnet].get(li), cop[nnet].get(li)
        if a_ is not None and b_ is not None and a_.distance(b_) < o['clr'] - 0.003:
            print('    validate: P-N', round(a_.distance(b_), 3), o['name']); return False
    foreign_near(0, 0, 0.1, codes)            # builds the static copper list
    for nt in (pnet, nnet):
        for li, g_ in cop[nt].items():
            gb = g_.buffer(o['clr'] - 0.003)
            for fg, fc, ls_ in _FO:
                if fc in codes or LAY[li] not in ls_:
                    continue
                if fg.intersects(gb):
                    print('    validate: foreign copper', o['name'], [round(v, 2) for v in fg.centroid.coords[0]]); return False
    return True


STUBS = []
if FATSRC:
    new_order = []
    for o in order:
        if not o.get('fat'):
            new_order.append(o); continue
        src = FATSRC[o['name']]
        if not o['ok'] or not o['paths']:
            if o['paths']:
                mark(o, -1)
            for so in src:
                so['paths'] = []; so['ok'] = False; new_order.append(so)
            continue
        geo = split_fat(o)
        mark(o, -1)
        if geo is not None and not validate_fat(o, geo):
            geo = None
        if geo is None:
            print('  fat split failed, pair routed as two single nets:', o['name'])
            for so in src:
                so['paths'] = []; so['ok'] = False; new_order.append(so); STUBS.append(so)
            continue
        for so in src:
            g = geo[so['name']]
            fixed = [_raster(l, li) for li, l in g['lines']] + [[cell(x, y, 0), cell(x, y, len(LAY) - 1)] for x, y in g['vias']]
            acc = [cxy(c) for fp in fixed for c in fp]
            so['terms0'], so['rt0'], so['rv0'] = so['terms'], so['rt'], so['rv']
            so['terms'] = [dict(acc=acc, pad=acc[0][:2], items=['track'], anchored=True)] + so['terms']
            so['fixed'] = fixed; so['geo'] = g; so['paths'] = [np.asarray(fp, np.int32) for fp in fixed]
            # exact pair spacing in the occupancy model (the generic radii carry margins that would make P and N collide)
            so['rt'] = (so['w'] + so['clr']) / 2 / RES - 0.25
            so['rv'] = (CFG.VIA[0] + so['clr']) / 2 / RES - 0.25
            mark(so, +1)
            STUBS.append(so); new_order.append(so)
    order = new_order

    def stub_loop(lst):
        pres_s = 2.0
        for it in range(40):
            todo_s = [so for so in lst if not so['ok'] or conflicts(so, 0)]
            if not todo_s:
                break
            for so in todo_s:
                if so['paths']:
                    mark(so, -1)
                route(so, pres_s)
                if so['paths']:
                    mark(so, +1)
            pres_s *= 1.4

    def copper_of(so):
        per = collections.defaultdict(list)
        nfix = len(so.get('fixed') or []) if so.get('geo') else 0
        lines, vias = [], []
        if so.get('geo'):
            lines += [(li, pts) for li, pts in so['geo']['lines']]; vias += list(so['geo']['vias'])
        for p in so['paths'][nfix:]:
            ls, vs = polylines(p)
            lines += [(LAY.index(l), pts) for l, pts in ls]; vias += vs
        for li, pts in lines:
            if len(pts) > 1:
                per[li].append(LineString(pts).buffer(so['w'] / 2, 8))
            elif pts:
                per[li].append(Point(pts[0]).buffer(so['w'] / 2, 8))
        for v in vias:
            for li in range(len(LAY)):
                per[li].append(Point(v).buffer(CFG.VIA[0] / 2, 16))
        from shapely.ops import unary_union
        return {li: unary_union(g) for li, g in per.items()}

    stub_loop(STUBS)
    # exact P/N check of every split pair (grid rasters of the offset tracks are approximate): failures become two singles
    redo = []
    for nm, (a_, b_) in FATSRC.items():
        if not (a_.get('geo') and b_.get('geo') and a_['ok'] and b_['ok']):
            continue
        ca, cb = copper_of(a_), copper_of(b_)
        dmin = min((ca[li].distance(cb[li]) for li in ca if li in cb), default=9.0)
        if dmin < a_['clr'] - 0.003:
            print('    exact P/N %.3f -> singles: %s' % (dmin, short_(nm)))
            for so in (a_, b_):
                if so['paths']:
                    mark(so, -1)
                so['paths'] = []; so['ok'] = False; so['geo'] = None; so['fixed'] = None
                so['terms'], so['rt'], so['rv'] = so['terms0'], so['rt0'], so['rv0']
                redo.append(so)
    if redo:
        stub_loop(redo)
    bad_s = [so for so in STUBS if not so['ok'] or conflicts(so, 0)]
    if os.environ.get('DBGFAT'):
        byname = {so['name']: so for so in STUBS}
        for so in bad_s:
            other = byname.get(next(n for n in FATSRC[so['name'].split('|')[0]] if False) if False else None)
        for nm, (a_, b_) in FATSRC.items():
            for x_, y_ in ((a_, b_), (b_, a_)):
                c0 = conflicts(x_, 0) if x_['paths'] else -1
                if y_['paths']:
                    mark(y_, -1)
                c1 = conflicts(x_, 0) if x_['paths'] else -1
                if y_['paths']:
                    mark(y_, +1)
                print('    stub', short_(x_['name']), 'ok', x_['ok'], 'conf', c0, 'without partner', c1)
    print('pair stubs: %d objects, %d unresolved' % (len(STUBS), len(bad_s)))
    for so in bad_s:
        mark(so, -1); so['paths'] = []; so['ok'] = False; so['geo'] = None; dropped.append(so['name'])


# ------------------------------------------------------------------ write copper
def write(o):
    ni = NETS[o.get('net', o['name'])]
    nt = nv = 0
    lines, allv = [], []
    nfix = len(o.get('fixed') or []) if o.get('geo') else 0
    for p in o['paths'][nfix:]:
        ls, vs = polylines(p)
        lines += [[l, list(pts)] for l, pts in ls]
        allv += vs
    if o.get('geo'):
        lines += [[LAY[li], [tuple(q) for q in pts]] for li, pts in o['geo']['lines'] if len(pts) > 1]
        allv += [tuple(v) for v in o['geo']['vias']]
    # T-junctions: a branch that ends on the interior of another segment splits that segment there
    for ln in lines:
        for end in (ln[1][0], ln[1][-1]):
            for other in lines:
                if other is ln or other[0] != ln[0]:
                    continue
                q = other[1]
                for i in range(len(q) - 1):
                    (ax, ay), (bx_, by_) = q[i], q[i + 1]
                    LL = math.hypot(bx_ - ax, by_ - ay)
                    if LL < 1e-6:
                        continue
                    tt = ((end[0] - ax) * (bx_ - ax) + (end[1] - ay) * (by_ - ay)) / LL / LL
                    if 1e-4 < tt < 1 - 1e-4:
                        px_, py_ = ax + (bx_ - ax) * tt, ay + (by_ - ay) * tt
                        if math.hypot(px_ - end[0], py_ - end[1]) < 1e-3:
                            q.insert(i + 1, end)
                            break
    for vv in [None]:
        ls, vs = [(l, pts) for l, pts in lines], allv
        for l, pts in ls:
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                if math.hypot(xb - xa, yb - ya) < 1e-4:
                    continue
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(float(xa)), pcbnew.FromMM(float(ya))))
                t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(float(xb)), pcbnew.FromMM(float(yb))))
                t.SetWidth(pcbnew.FromMM(o['w'])); t.SetLayer(l); t.SetNet(ni)
                b.Add(t); nt += 1
        for x, y in vs:
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(float(x)), pcbnew.FromMM(float(y))))
            v.SetWidth(pcbnew.FromMM(CFG.VIA[0])); v.SetDrill(pcbnew.FromMM(CFG.VIA[1]))
            v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(ni)
            v.SetFrontTentingMode(pcbnew.TENTING_MODE_TENTED); v.SetBackTentingMode(pcbnew.TENTING_MODE_TENTED)
            b.Add(v); nv += 1
    # short stubs from the grid end points to the exact terminal centres (pads / vias are off-grid)
    accs = [a for t in o['terms'] for a in t['acc']]
    ends = set()
    for p in o['paths']:
        for lc in (p[0], p[-1]):
            ends.add(int(lc))
    for lc in ends:
        x, y, li = cxy(lc)
        best = None
        for (ax, ay, al) in accs:
            if al != li:
                continue
            d = math.hypot(ax - x, ay - y)
            if d < RES * 0.75 and d > 1e-4 and (best is None or d < best[0]):
                best = (d, ax, ay)
        # prefer the exact centre of a via / pad when the grid point is only an access point inside it
        if best is None:
            continue
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(float(x)), pcbnew.FromMM(float(y))))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(float(best[1])), pcbnew.FromMM(float(best[2]))))
        t.SetWidth(pcbnew.FromMM(o['w'])); t.SetLayer(LAY[li]); t.SetNet(ni)
        b.Add(t); nt += 1
    return nt, nv


tot = [0, 0]
for o in order:
    if o['paths']:
        a, c_ = write(o)
        tot[0] += a; tot[1] += c_
print('written %d segments, %d vias' % tuple(tot))
b.BuildConnectivity()
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(DST)
import shutil
for ext in ('.kicad_pro', '.kicad_dru'):          # project netclasses / custom rules follow the board
    s_, d_ = os.path.splitext(SRC)[0] + ext, os.path.splitext(DST)[0] + ext
    if os.path.exists(s_) and os.path.abspath(s_) != os.path.abspath(d_):
        shutil.copy(s_, d_)
json.dump(dict(failed=[o['name'] for o in order if not o['ok']], dropped=dropped), open(os.path.splitext(DST)[0] + '_nclog.json', 'w'), indent=1)
print('done %.0fs' % (time.time() - t0))
