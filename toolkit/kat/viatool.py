"""Clearance-checked via / track placement on a loaded pcbnew board (no zones considered: planes refill around new
copper).  Obstacles = all tracks, vias and pads of other nets on all layers; drills of every net for the hole gap."""
import pcbnew
import numpy as np
from shapely.geometry import Point, LineString, box
MM = 1e6
short = lambda n: n.split('/')[-1]


def P(x, y):
    return pcbnew.VECTOR2I(int(round(x * MM)), int(round(y * MM)))


class Tool:
    def __init__(self, b, cl=0.15, hole_gap=0.25):
        self.b, self.cl, self.hg = b, cl, hole_gap
        self.NET = {short(ni.GetNetname()): ni for ni in b.GetNetsByNetcode().values()}
        self.obst, self.new = [], []
        for t in b.GetTracks():
            n = short(t.GetNetname())
            if t.GetClass() == 'PCB_VIA':
                c = Point(t.GetPosition().x / MM, t.GetPosition().y / MM)
                self.obst.append((c.buffer(t.GetWidth(pcbnew.F_Cu) / MM / 2), None, n, c, t.GetDrillValue() / MM / 2))
            else:
                g = LineString([(t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM)]).buffer(t.GetWidth() / MM / 2)
                self.obst.append((g, t.GetLayer(), n, None, 0))
        for f in b.GetFootprints():
            for p in f.Pads():
                bb = p.GetBoundingBox()
                g = box(bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)
                n = short(p.GetNetname())
                if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                    self.obst.append((g, None, n, Point(p.GetPosition().x / MM, p.GetPosition().y / MM), p.GetDrillSize().x / MM / 2))
                else:
                    self.obst.append((g, pcbnew.B_Cu if f.IsFlipped() else pcbnew.F_Cu, n, None, 0))

    def via_ok(self, x, y, net, d, dr):
        c = Point(x, y); g = c.buffer(d / 2 + self.cl)
        for og, lay, n, hc, hr in self.obst:
            if hc is not None and hc.distance(c) < hr + dr / 2 + self.hg:
                return False
            if n != net and g.intersects(og):
                return False
        return True

    def track_ok(self, pts, net, w, lay):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            g = LineString([(x0, y0), (x1, y1)]).buffer(w / 2 + self.cl)
            for og, l, n, hc, hr in self.obst:
                if n != net and (l is None or l == lay) and g.intersects(og):
                    return False
        return True

    def via(self, x, y, net, d=0.4, dr=0.2, check=True):
        if check and not self.via_ok(x, y, net, d, dr):
            return False
        v = pcbnew.PCB_VIA(self.b); v.SetPosition(P(x, y)); v.SetWidth(int(d * MM)); v.SetDrill(int(dr * MM))
        v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetNet(self.NET[net]); v.SetLocked(True); self.new.append(v)
        c = Point(x, y); self.obst.append((c.buffer(d / 2), None, net, c, dr / 2))
        return True

    def track(self, pts, net, w, lay, check=True):
        if check and not self.track_ok(pts, net, w, lay):
            return False
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.b); t.SetStart(P(x0, y0)); t.SetEnd(P(x1, y1)); t.SetWidth(int(w * MM)); t.SetLayer(lay)
            t.SetNet(self.NET[net]); t.SetLocked(True); self.new.append(t)
            self.obst.append((LineString([(x0, y0), (x1, y1)]).buffer(w / 2), lay, net, None, 0))
        return True

    def vias_in(self, region, net, nmax, pitch=0.85, d=0.6, dr=0.3, step=0.05):
        x0, y0, x1, y1 = region.bounds
        got = []
        for y in np.arange(y0 + d / 2, y1 - d / 2 + 1e-6, step):
            for x in np.arange(x0 + d / 2, x1 - d / 2 + 1e-6, step):
                if len(got) >= nmax:
                    return got
                if not region.contains(Point(x, y)):
                    continue
                if any(np.hypot(x - gx, y - gy) < pitch for gx, gy in got):
                    continue
                if self.via(float(x), float(y), net, d, dr):
                    got.append((round(float(x), 3), round(float(y), 3)))
        return got

    def commit(self, fill=True):
        for it in self.new:
            self.b.Add(it)
        if fill:
            pcbnew.ZONE_FILLER(self.b).Fill(self.b.Zones())
        return len(self.new)
