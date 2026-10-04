"""plot one copper layer: zone fills coloured by net, tracks, vias, pads on that layer.
usage: layerplot.py BOARD OUT.png LAYER [x0,y0,x1,y1]   (LAYER = F.Cu, In1.Cu, ..., B.Cu)"""
import sys, pcbnew, colorsys, hashlib
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
MM = 1e6
b = pcbnew.LoadBoard(sys.argv[1]); out = sys.argv[2]; lname = sys.argv[3]
win = [float(v) for v in sys.argv[4].split(',')] if len(sys.argv) > 4 else None
lid = b.GetLayerID(lname)
def col(n):
    h = int(hashlib.md5(n.encode()).hexdigest()[:6], 16) / 0xffffff
    return colorsys.hsv_to_rgb(h, 0.65, 0.95)
FIX = {'GND': (0.3, 0.75, 0.4), 'VCC_3V3': (0.55, 0.8, 0.3), 'VCC_5V': (0.9, 0.3, 0.3), 'VDD_CPUX': (1, 0.6, 0.3),
       'VDD_SYS': (0.95, 0.85, 0.3), 'VCC_DRAM': (0.7, 0.55, 1.0)}
bb = b.GetBoardEdgesBoundingBox(); W, H = bb.GetWidth() / MM, bb.GetHeight() / MM
x0, y0, x1, y1 = win or (0, 0, W, H)
FW = 14.0
fig, ax = plt.subplots(figsize=(FW, FW * (y1 - y0) / (x1 - x0)))
PPM = FW * 72 / (x1 - x0) * 0.92   # points per mm
for z in b.Zones():
    if z.GetIsRuleArea() or not z.IsOnLayer(lid): continue
    fp = z.GetFilledPolysList(lid)
    c = FIX.get(z.GetNetname(), col(z.GetNetname()))
    for i in range(fp.OutlineCount()):
        o = fp.Outline(i)
        ax.fill([o.CPoint(k).x / MM for k in range(o.PointCount())], [o.CPoint(k).y / MM for k in range(o.PointCount())], fc=c + (0.45,), ec=c, lw=0.3)
        for h in range(fp.HoleCount(i)):
            hh = fp.Hole(i, h)
            ax.fill([hh.CPoint(k).x / MM for k in range(hh.PointCount())], [hh.CPoint(k).y / MM for k in range(hh.PointCount())], fc='white', ec='none')
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA':
        p = t.GetPosition(); ax.add_patch(plt.Circle((p.x / MM, p.y / MM), t.GetWidth(pcbnew.F_Cu) / MM / 2, fc=FIX.get(t.GetNetname(), (0.5, 0.5, 0.5)), ec='k', lw=0.2))
    elif t.GetLayer() == lid:
        ax.plot([t.GetStart().x / MM, t.GetEnd().x / MM], [t.GetStart().y / MM, t.GetEnd().y / MM], color=FIX.get(t.GetNetname(), col(t.GetNetname())), lw=max(0.5, t.GetWidth() / MM * PPM), solid_capstyle='round')
for f in b.GetFootprints():
    for p in f.Pads():
        if p.IsOnLayer(lid) and (lid in (pcbnew.F_Cu, pcbnew.B_Cu)):
            q = p.GetBoundingBox(); ax.add_patch(plt.Rectangle((q.GetLeft() / MM, q.GetTop() / MM), q.GetWidth() / MM, q.GetHeight() / MM, fc=(0.8, 0.3, 0.2, 0.7), ec='none'))
    if lid in (pcbnew.F_Cu, pcbnew.B_Cu) and (f.IsFlipped() == (lid == pcbnew.B_Cu)):
        q = f.GetPosition()
        if x0 < q.x / MM < x1 and y0 < q.y / MM < y1:
            ax.text(q.x / MM, q.y / MM, f.GetReference(), fontsize=6, ha='center', va='center')
ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect('equal'); ax.set_title(lname)
ax.set_position([0.03, 0.03, 0.94, 0.92]); plt.savefig(out, dpi=110)
