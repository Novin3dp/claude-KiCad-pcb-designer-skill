#!/usr/bin/env python3
"""Export a .kicad_pcb into compact JSON for the HTML viewer (units: micrometres, ints)."""
import sys, os, json, math, re
import pcbnew

LAYERS = [('F.Cu', pcbnew.F_Cu), ('In1.Cu', pcbnew.In1_Cu), ('In2.Cu', pcbnew.In2_Cu), ('In3.Cu', pcbnew.In3_Cu),
          ('In4.Cu', pcbnew.In4_Cu), ('B.Cu', pcbnew.B_Cu)]
LID = {lid: i for i, (_, lid) in enumerate(LAYERS)}


def u(v):
    return int(round(v / 1000.0))   # internal nm -> um


def P(p):
    return [u(p.x), u(p.y)]


def poly_list(ps):
    """SHAPE_POLY_SET -> list of polygons, each [outline, hole, hole...] with flat [x,y,x,y..] arrays."""
    out = []
    for i in range(ps.OutlineCount()):
        rings = []
        o = ps.Outline(i)
        rings.append([c for k in range(o.PointCount()) for c in P(o.CPoint(k))])
        for h in range(ps.HoleCount(i)):
            hh = ps.Hole(i, h)
            rings.append([c for k in range(hh.PointCount()) for c in P(hh.CPoint(k))])
        out.append(rings)
    return out


def shape_segments(s):
    """graphic shape -> list of polylines (list of [x,y])"""
    t = s.GetShape()
    if t == pcbnew.SHAPE_T_SEGMENT:
        return [[P(s.GetStart()), P(s.GetEnd())]]
    if t == pcbnew.SHAPE_T_RECTANGLE:
        c = s.GetRectCorners()
        pts = [P(c[i]) for i in range(len(c))]
        return [pts + [pts[0]]]
    if t == pcbnew.SHAPE_T_CIRCLE:
        cx, cy = s.GetCenter().x, s.GetCenter().y
        r = s.GetRadius()
        return [[[u(cx + r * math.cos(a * math.pi / 12)), u(cy + r * math.sin(a * math.pi / 12))] for a in range(25)]]
    if t == pcbnew.SHAPE_T_ARC:
        c = s.GetCenter(); r = s.GetRadius()
        a0 = math.atan2(s.GetStart().y - c.y, s.GetStart().x - c.x)
        a1 = math.atan2(s.GetEnd().y - c.y, s.GetEnd().x - c.x)
        sweep = s.GetArcAngle().AsRadians()
        n = max(4, int(abs(sweep) / (math.pi / 16)))
        return [[[u(c.x + r * math.cos(a0 + sweep * k / n)), u(c.y + r * math.sin(a0 + sweep * k / n))] for k in range(n + 1)]]
    if t == pcbnew.SHAPE_T_POLY:
        ps = s.GetPolyShape()
        res = []
        for i in range(ps.OutlineCount()):
            o = ps.Outline(i)
            pts = [P(o.CPoint(k)) for k in range(o.PointCount())]
            res.append(pts + [pts[0]])
        return res
    return []


def drc_rats(path, nets, refill=False):
    import subprocess, tempfile
    out = tempfile.mktemp(suffix='.json')
    cmd = ['kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-all', '-o', out, path]
    if refill:
        cmd.insert(3, '--refill-zones')
    subprocess.run(cmd, capture_output=True)
    rep = json.load(open(out))
    code = {n: i for i, n in enumerate(nets)}
    rats = []
    for it in rep.get('unconnected_items', []):
        a, c = it['items'][0], it['items'][1]
        m = re.search(r"\[(.*?)\]", a.get('description', ''))
        n = code.get(m.group(1), 0) if m else 0
        rats.append([int(a['pos']['x'] * 1000), int(a['pos']['y'] * 1000), int(c['pos']['x'] * 1000), int(c['pos']['y'] * 1000), n])
    viol = [dict(t=v['type'], s=v['severity'], d=v['description'],
                 items=[[int(i['pos']['x'] * 1000), int(i['pos']['y'] * 1000), i.get('description', '')] for i in v['items']])
            for v in rep.get('violations', [])]
    return rats, len(rats), viol


def ratsnest(b):
    b.BuildConnectivity()
    conn = b.GetConnectivity()
    by_net = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetCode() > 0:
                by_net.setdefault(p.GetNetCode(), []).append(p)
    rats = []
    total = 0
    for code, pads in by_net.items():
        if len(pads) < 2:
            continue
        left = {id(p): p for p in pads}
        clusters = []
        while left:
            k, p = next(iter(left.items()))
            conn_ids = set()
            for it in conn.GetConnectedItems(p):
                conn_ids.add(it.m_Uuid.AsString())
            cl = [p]
            del left[k]
            for k2 in list(left):
                if left[k2].m_Uuid.AsString() in conn_ids:
                    cl.append(left.pop(k2))
            clusters.append([(q.GetPosition().x, q.GetPosition().y) for q in cl])
        if len(clusters) < 2:
            continue
        total += len(clusters) - 1
        # Prim MST over clusters
        inside = [clusters[0]]
        rest = clusters[1:]
        while rest:
            best = None
            for i, c in enumerate(rest):
                for a in (pt_ for cl in inside for pt_ in cl):
                    for bpt in c:
                        dd = (a[0] - bpt[0]) ** 2 + (a[1] - bpt[1]) ** 2
                        if best is None or dd < best[0]:
                            best = (dd, i, a, bpt)
            _, i, a, bpt = best
            rats.append([u(a[0]), u(a[1]), u(bpt[0]), u(bpt[1]), code])
            inside.append(rest.pop(i))
    return rats, total


def export(path, extra=None):
    b = pcbnew.LoadBoard(path)
    nets = [''] * (b.GetNetCount() + 1)
    for code, ni in b.GetNetsByNetcode().items():
        if code < len(nets):
            nets[code] = ni.GetNetname()
    data = dict(nets=nets, fps=[], pads=[], silk={'F': [], 'B': []}, fab={'F': [], 'B': []}, tracks=[], vias=[],
                zones=[], outlines=[], rats=[], edge=[])
    for d in b.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and d.GetClass() == 'PCB_SHAPE':
            data['edge'] += shape_segments(d)
    bb = b.GetBoardEdgesBoundingBox()
    data['board'] = [u(bb.GetLeft()), u(bb.GetTop()), u(bb.GetRight()), u(bb.GetBottom())]
    for fi, f in enumerate(sorted(b.GetFootprints(), key=lambda f: f.GetReference())):
        side = 'B' if f.IsFlipped() else 'T'
        cyl = pcbnew.B_CrtYd if side == 'B' else pcbnew.F_CrtYd
        cy = f.GetCourtyard(cyl)
        cyp = poly_list(cy)[0][0] if cy.OutlineCount() else []
        if not cyp:
            bx = f.GetBoundingBox(False)
            cyp = [u(bx.GetLeft()), u(bx.GetTop()), u(bx.GetRight()), u(bx.GetTop()), u(bx.GetRight()), u(bx.GetBottom()),
                   u(bx.GetLeft()), u(bx.GetBottom())]
        data['fps'].append(dict(r=f.GetReference(), v=f.GetValue(), fp=f.GetFPID().GetLibItemName().wx_str(),
                                x=u(f.GetPosition().x), y=u(f.GetPosition().y), rot=round(f.GetOrientationDegrees(), 1),
                                s=side, cy=cyp))
        for g in f.GraphicalItems():
            if g.GetClass() != 'PCB_SHAPE':
                continue
            ln = g.GetLayer()
            key = None
            if ln == pcbnew.F_SilkS: key = ('silk', 'F')
            elif ln == pcbnew.B_SilkS: key = ('silk', 'B')
            elif ln == pcbnew.F_Fab: key = ('fab', 'F')
            elif ln == pcbnew.B_Fab: key = ('fab', 'B')
            if key:
                w = u(g.GetWidth())
                for pl in shape_segments(g):
                    data[key[0]][key[1]].append([w] + [c for p in pl for c in p])
        for p in f.Pads():
            ls = []
            if p.IsOnLayer(pcbnew.F_Cu): ls.append('F')
            if p.IsOnLayer(pcbnew.B_Cu): ls.append('B')
            th = p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            lay = 'A' if th else ('F' if 'F' in ls else 'B')
            ref_layer = pcbnew.F_Cu if lay in ('A', 'F') else pcbnew.B_Cu
            ps = pcbnew.SHAPE_POLY_SET()
            p.TransformShapeToPolygon(ps, ref_layer, 0, pcbnew.FromMM(0.003), pcbnew.ERROR_INSIDE)
            pl = poly_list(ps)
            ent = dict(f=fi, n=p.GetNetCode(), l=lay, num=p.GetNumber(), x=u(p.GetPosition().x), y=u(p.GetPosition().y))
            if p.GetShape(ref_layer) == pcbnew.PAD_SHAPE_CIRCLE:
                ent['c'] = u(p.GetSize(ref_layer).x / 2)
            else:
                ent['p'] = pl[0][0] if pl else []
            if th:
                ent['d'] = u(p.GetDrillSize().x / 2)
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    ent['np'] = 1
            data['pads'].append(ent)
    for t in b.GetTracks():
        cls = t.GetClass()
        if cls == 'PCB_VIA':
            v = t
            top, bot = v.TopLayer(), v.BottomLayer()
            data['vias'].append([u(v.GetPosition().x), u(v.GetPosition().y), u(v.GetWidth(pcbnew.F_Cu) / 2),
                                 u(v.GetDrillValue() / 2), v.GetNetCode(), LID.get(top, 0), LID.get(bot, 5)])
        elif cls == 'PCB_ARC':
            c = t.GetCenter(); r = t.GetRadius()
            a0 = math.atan2(t.GetStart().y - c.y, t.GetStart().x - c.x)
            sweep = t.GetAngle().AsRadians()
            n = max(3, int(abs(sweep) / (math.pi / 16)))
            pts = [(c.x + r * math.cos(a0 + sweep * k / n), c.y + r * math.sin(a0 + sweep * k / n)) for k in range(n + 1)]
            for k in range(n):
                data['tracks'].append([u(pts[k][0]), u(pts[k][1]), u(pts[k + 1][0]), u(pts[k + 1][1]), u(t.GetWidth()),
                                       LID.get(t.GetLayer(), 0), t.GetNetCode()])
        else:
            data['tracks'].append([u(t.GetStart().x), u(t.GetStart().y), u(t.GetEnd().x), u(t.GetEnd().y), u(t.GetWidth()),
                                   LID.get(t.GetLayer(), 0), t.GetNetCode()])
    for z in b.Zones():
        for lname, lid in LAYERS:
            if not z.IsOnLayer(lid):
                continue
            if z.GetIsRuleArea():
                o = z.Outline()
                data['outlines'].append(dict(l=LID[lid], n=0, ka=1, name=z.GetZoneName(), p=poly_list(o)))
                continue
            fp_ = z.GetFilledPolysList(lid)
            if fp_ and fp_.OutlineCount():
                data['zones'].append(dict(l=LID[lid], n=z.GetNetCode(), p=poly_list(fp_)))
            data['outlines'].append(dict(l=LID[lid], n=z.GetNetCode(), name=z.GetZoneName(), p=poly_list(z.Outline())))
    # DRC (errors/warnings) from kicad-cli; ratsnest from pcbnew connectivity clusters (MST between islands)
    _, _, data['drc'] = drc_rats(path, nets)
    data['rats'], data['unrouted'] = ratsnest(b)
    if extra:
        data.update(extra)
    return data


if __name__ == '__main__':
    d = export(sys.argv[1])
    json.dump(d, open(sys.argv[2], 'w'), separators=(',', ':'))
    print('fps', len(d['fps']), 'pads', len(d['pads']), 'tracks', len(d['tracks']), 'vias', len(d['vias']),
          'rats', len(d['rats']), 'unrouted', d['unrouted'], 'bytes', os.path.getsize(sys.argv[2]))
