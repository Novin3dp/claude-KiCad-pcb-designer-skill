"""plot selected nets (regex -> colour) on all copper layers, other copper faint grey (solid = top, dotted = bottom).
usage: netplot.py BOARD OUT.png x0,y0,x1,y1 "REGEX=colour" ["REGEX2=colour2" ...]"""
import sys, re, pcbnew
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
MM = 1e6
b = pcbnew.LoadBoard(sys.argv[1]); out = sys.argv[2]
x0, y0, x1, y1 = [float(v) for v in sys.argv[3].split(',')]
groups = [(re.compile(g.split('=')[0]), g.split('=')[1]) for g in sys.argv[4:]]
FW = 15.0
fig, ax = plt.subplots(figsize=(FW, FW * (y1 - y0) / (x1 - x0)))
PPM = FW * 72 / (x1 - x0) * 0.92
_ls = ['-', '--', '-.', ':']
style = {l: ('-' if l == pcbnew.F_Cu else ':' if l == pcbnew.B_Cu else _ls[1 + i % 2]) for i, l in enumerate(b.GetEnabledLayers().CuStack())}
for f in b.GetFootprints():
    for p in f.Pads():
        q = p.GetBoundingBox()
        ax.add_patch(plt.Rectangle((q.GetLeft() / MM, q.GetTop() / MM), q.GetWidth() / MM, q.GetHeight() / MM, fc='#dddddd', ec='none'))
for t in b.GetTracks():
    n = t.GetNetname().split('/')[-1]
    col = next((c for rx, c in groups if rx.search(n)), None)
    if t.GetClass() == 'PCB_VIA':
        p = t.GetPosition(); ax.add_patch(plt.Circle((p.x / MM, p.y / MM), 0.15, fc=col or '#bbbbbb', ec='k' if col else 'none', lw=0.3))
        continue
    ax.plot([t.GetStart().x / MM, t.GetEnd().x / MM], [t.GetStart().y / MM, t.GetEnd().y / MM], color=col or '#cccccc',
            ls=style.get(t.GetLayer(), '-'), lw=max(0.6, t.GetWidth() / MM * PPM) if col else 0.6)
ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect('equal')
ax.set_title(' / '.join('%s=%s' % (rx.pattern, c) for rx, c in groups) + '   (solid L1, dashed L3, dotted L6)', fontsize=9)
ax.set_position([0.03, 0.03, 0.94, 0.92]); plt.savefig(out, dpi=100)
