"""Exact clearance-slack fields on a routing grid.

For every grid cell centre and copper layer:  slack = distance to the copper of an item - clearance(item's netclass).
Kept as the two best values from *different* nets (s1 with its net n1, s2 from any other net), so the legality of a
cell for net N is   (n1 == N ? s2 : s1) > half_width  without recomputing per net.
Distances are exact (circles and capsules analytically, polygon pads via shapely), so a grid of 0.05 mm can use the
0.35 mm gap between 0.65 mm-pitch BGA balls when its origin sits on the gap mid-lines."""
import numpy as np
import shapely
from shapely.geometry import Polygon
import pcbnew

MM = 1e6
BIG = 99.0


class Field:
    def __init__(self, ox, oy, res, W, H, reach=0.55):
        self.ox, self.oy, self.res, self.W, self.H, self.reach = ox, oy, res, W, H, reach
        self.xs = ox + np.arange(W) * res
        self.ys = oy + np.arange(H) * res
        self.L = {}
        self._pts = None

    def layer(self, l):
        if l not in self.L:
            self.L[l] = [np.full((self.H, self.W), BIG, np.float32), np.full((self.H, self.W), -9, np.int32),
                         np.full((self.H, self.W), BIG, np.float32)]
        return self.L[l]

    def _win(self, x0, y0, x1, y1):
        r = self.reach
        i0 = max(0, int(np.floor((x0 - r - self.ox) / self.res))); i1 = min(self.W, int(np.ceil((x1 + r - self.ox) / self.res)) + 1)
        j0 = max(0, int(np.floor((y0 - r - self.oy) / self.res))); j1 = min(self.H, int(np.ceil((y1 + r - self.oy) / self.res)) + 1)
        return i0, i1, j0, j1

    def _update(self, l, win, s, net):
        i0, i1, j0, j1 = win
        s1, n1, s2 = self.layer(l)
        S1, N1, S2 = s1[j0:j1, i0:i1], n1[j0:j1, i0:i1], s2[j0:j1, i0:i1]
        same = N1 == net
        # same net as the current best: only the best can improve
        np.minimum(S1, np.where(same, s, BIG), out=S1)
        other = ~same
        better = other & (s < S1)
        S2[better] = S1[better]
        S1[better] = s[better]
        N1[better] = net
        worse = other & ~better
        S2[worse] = np.minimum(S2[worse], s[worse])

    def circle(self, l, cx, cy, r, clr, net):
        win = self._win(cx - r, cy - r, cx + r, cy + r)
        i0, i1, j0, j1 = win
        if i0 >= i1 or j0 >= j1:
            return
        X, Y = np.meshgrid(self.xs[i0:i1], self.ys[j0:j1])
        s = (np.hypot(X - cx, Y - cy) - r - clr).astype(np.float32)
        self._update(l, win, s, net)

    def capsule(self, l, ax, ay, bx, by, w, clr, net):
        win = self._win(min(ax, bx) - w, min(ay, by) - w, max(ax, bx) + w, max(ay, by) + w)
        i0, i1, j0, j1 = win
        if i0 >= i1 or j0 >= j1:
            return
        X, Y = np.meshgrid(self.xs[i0:i1], self.ys[j0:j1])
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1) if L2 > 0 else 0
        d = np.hypot(X - (ax + t * dx), Y - (ay + t * dy))
        s = (d - w / 2 - clr).astype(np.float32)
        self._update(l, win, s, net)

    def polygon(self, l, pts, clr, net):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        win = self._win(min(xs), min(ys), max(xs), max(ys))
        i0, i1, j0, j1 = win
        if i0 >= i1 or j0 >= j1:
            return
        X, Y = np.meshgrid(self.xs[i0:i1], self.ys[j0:j1])
        g = Polygon(pts)
        d = shapely.distance(g, shapely.points(X.ravel(), Y.ravel())).reshape(X.shape)
        s = (d - clr).astype(np.float32)
        self._update(l, win, s, net)

    # ------------------------------------------------------------------ board
    def add_board(self, b, layers, clr_of_net, skip=lambda item: False, clr_adj=lambda x, y, c: c):
        x_lo, y_lo = self.ox - 1, self.oy - 1
        x_hi, y_hi = self.ox + self.W * self.res + 1, self.oy + self.H * self.res + 1
        inside = lambda x, y: x_lo < x < x_hi and y_lo < y < y_hi
        for f in b.GetFootprints():
            for p in f.Pads():
                x, y = p.GetPosition().x / MM, p.GetPosition().y / MM
                if not inside(x, y) or skip(p):
                    continue
                net = p.GetNetCode() or -1
                clr = clr_adj(x, y, clr_of_net(net))
                for l in layers:
                    if not p.IsOnLayer(l):
                        continue
                    if l not in (pcbnew.F_Cu, pcbnew.B_Cu) and not p.FlashLayer(l):
                        if p.GetDrillSize().x:
                            self.circle(l, x, y, p.GetDrillSize().x / MM / 2, max(clr, 0.15), net)
                        continue
                    if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
                        self.circle(l, x, y, p.GetSize().x / MM / 2, clr, net)
                        continue
                    ps = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(ps, l, 0, pcbnew.FromMM(0.002), pcbnew.ERROR_OUTSIDE)
                    for i in range(ps.OutlineCount()):
                        o = ps.Outline(i)
                        self.polygon(l, [(o.CPoint(k).x / MM, o.CPoint(k).y / MM) for k in range(o.PointCount())], clr, net)
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    for l in layers:
                        self.circle(l, x, y, p.GetDrillSize().x / MM / 2, 0.2, -1)
        for t in b.GetTracks():
            if skip(t):
                continue
            net = t.GetNetCode() or -1
            clr = clr_of_net(net)
            if t.GetClass() == 'PCB_VIA':
                x, y = t.GetPosition().x / MM, t.GetPosition().y / MM
                clr = clr_adj(x, y, clr)
                if inside(x, y):
                    for l in layers:
                        self.circle(l, x, y, t.GetWidth(pcbnew.F_Cu) / MM / 2, clr, net)
                continue
            l = t.GetLayer()
            if l not in layers:
                continue
            ax, ay, bx, by = t.GetStart().x / MM, t.GetStart().y / MM, t.GetEnd().x / MM, t.GetEnd().y / MM
            if inside(ax, ay) or inside(bx, by):
                self.capsule(l, ax, ay, bx, by, t.GetWidth() / MM, clr_adj((ax + bx) / 2, (ay + by) / 2, clr), net)

    def legal_track(self, l, net, hw, eps):
        s1, n1, s2 = self.layer(l)
        return np.where(n1 == net, s2, s1) > hw + eps

    def min_all(self, layers):
        m = np.full((self.H, self.W), BIG, np.float32)
        for l in layers:
            m = np.minimum(m, self.layer(l)[0])
        return m
