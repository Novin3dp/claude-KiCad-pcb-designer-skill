"""Accordion length tuning, v3: like tune2.add_length but
  * a meander may cover only a window of a straight segment (sliding windows, several per segment), so one blocked
    stretch no longer kills the whole segment;
  * amplitudes up to 2.0 mm, both sides, the largest legal amplitude wins;
  * the meander must also keep its distance from the net's OWN other copper (an accordion folding back onto its
    own track would short its loops and silently remove the added length).
Clearance to foreign copper is the exact shapely check of tune2.Exact."""
import math
import pcbnew
from shapely.geometry import LineString
import tune2 as T2
MM = 1e6
PITCH = 0.30
AMPS = (3.5, 3.0, 2.5, 2.0, 1.6, 1.3, 1.0, 0.8, 0.6, 0.45, 0.33, 0.25, 0.18)


def meander_window(ax, ay, bx, by, s0, n, A, side):
    """points of a segment a->b with n bumps of amplitude A starting s0 mm from a"""
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    nx_, ny_ = -uy * side, ux * side
    s = s0
    pts = [(ax, ay), (ax + ux * s, ay + uy * s)]
    for _ in range(n):
        pts.append((ax + ux * s + nx_ * A, ay + uy * s + ny_ * A)); s += PITCH
        pts.append((ax + ux * s + nx_ * A, ay + uy * s + ny_ * A))
        pts.append((ax + ux * s, ay + uy * s)); s += PITCH
        pts.append((ax + ux * s, ay + uy * s))
    pts.append((bx, by))
    return pts


def own_ok(own, pts, w, gap=0.18):
    """meander body (between its first and last bump) keeps `gap` from the net's other copper"""
    body = LineString(pts[2:-2]).buffer(w / 2)
    for g in own:
        if body.distance(g) < gap:
            return False
    return True


def add_length(b, fld, netname, dL, prefer=None, clr_seg=0.30, maxA=2.0, log=None):
    """add ~dL mm to `netname`; returns the length added"""
    rem = dL
    tracks = [t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK' and t.GetNetname() == netname]
    vias = [t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA' and t.GetNetname() == netname]
    segs = [t for t in tracks if prefer is None or prefer(t)]
    segs.sort(key=lambda t: -t.GetLength())
    # own copper geometry per layer (updated as meanders are added)
    own = {}
    for t in tracks:
        own.setdefault(t.GetLayer(), []).append((id(t), LineString([(t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM)]).buffer(t.GetWidth() / MM / 2)))
    from shapely.geometry import Point
    vg = [Point(v.GetPosition().x / MM, v.GetPosition().y / MM).buffer(v.GetWidth(pcbnew.F_Cu) / MM / 2) for v in vias]
    for t in segs:
        if rem < 0.12:
            break
        L = t.GetLength() / MM
        if L < 2 * PITCH + 2 * clr_seg:
            continue
        ax, ay, bx, by = t.GetStart().x / MM, t.GetStart().y / MM, t.GetEnd().x / MM, t.GetEnd().y / MM
        l, w, net = t.GetLayer(), t.GetWidth() / MM, t.GetNetCode()
        if l not in fld.tree:
            continue
        others = [g for k, g in own.get(l, []) if k != id(t)] + vg
        # windows: try the whole free span first, then sliding windows of decreasing size
        span = L - 2 * clr_seg
        nmax = int(span / (2 * PITCH))
        best = None
        for n in sorted({nmax, max(1, nmax * 3 // 4), max(1, nmax // 2), max(1, nmax // 3), max(1, nmax // 4), 2, 1}, reverse=True):
            if n < 1 or n > nmax:
                continue
            width = n * 2 * PITCH
            offs = [clr_seg + k * PITCH for k in range(int((span - width) / PITCH) + 1)] or [clr_seg]
            for A in AMPS:
                if A > maxA:
                    continue
                A2 = min(A, rem / (2 * n))
                if A2 < 0.15:
                    continue
                gain = 2 * A2 * n
                if best and gain <= best[0]:
                    break
                found = False
                for s0 in offs:
                    for side in (1, -1):
                        pts = meander_window(ax, ay, bx, by, s0, n, A2, side)
                        if fld.ok(l, net, pts[1:-1], w) and own_ok(others, pts, w):
                            best = (gain, pts); found = True; break
                    if found:
                        break
                if found:
                    break
        if not best:
            continue
        gain, pts = best
        ni = t.GetNet()
        # no Remove (pcbnew wrappers go stale after one): the old segment becomes the first leg
        segs_pts = [(p, q) for p, q in zip(pts, pts[1:]) if math.hypot(q[0] - p[0], q[1] - p[1]) >= 1e-4]
        (p0, q0) = segs_pts[0]
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(float(p0[0])), pcbnew.FromMM(float(p0[1]))))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(float(q0[0])), pcbnew.FromMM(float(q0[1]))))
        new = [t]
        for (x0, y0), (x1, y1) in segs_pts[1:]:
            nt = pcbnew.PCB_TRACK(b)
            nt.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(float(x0)), pcbnew.FromMM(float(y0))))
            nt.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(float(x1)), pcbnew.FromMM(float(y1))))
            nt.SetWidth(pcbnew.FromMM(w)); nt.SetLayer(l); nt.SetNet(ni)
            b.Add(nt); new.append(nt)
        fld.add(l, pts, w, net)
        own[l] = [(k, g) for k, g in own.get(l, []) if k != id(t)] + [(id(nt) if nt is not t else id(t), LineString([(nt.GetStart().x / MM, nt.GetStart().y / MM), (nt.GetEnd().x / MM, nt.GetEnd().y / MM)]).buffer(w / 2)) for nt in new]
        rem -= gain
        if log:
            log('   %s +%.2f on %s seg %.1f mm' % (netname.split('/')[-1], gain, b.GetLayerName(l), L))
    return dL - rem
