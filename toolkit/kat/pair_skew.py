#!/usr/bin/env python3
"""Intra-pair skew trim for the loosely coupled high-speed pairs (HDMI TMDS, USB, Ethernet): accordion meanders on
the shorter line (tune2.add_length + exact clearance field).  Targets: HDMI <= 0.3 mm, USB / EPHY <= 1.0 mm.
usage: pair_skew.py IN OUT"""
import sys, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.getcwd())
import pcbnew
import tune2 as T
from shapely.geometry import Polygon as _Pg
MM = 1e6
import json as _json
# clearance per net class: env CLASS_CLR='{"Default": 0.15, "HDMI": 0.15}' (default = the H3 SBC classes)
CLS = _json.loads(os.environ['CLASS_CLR']) if os.environ.get('CLASS_CLR') else \
    {'Default': 0.10, 'DDR': 0.10, 'USB90': 0.12, 'HDMI100': 0.15, 'ETH100': 0.15, 'SDIO': 0.10, 'PWR': 0.12, 'GND': 0.10}
b = pcbnew.LoadBoard(sys.argv[1])
code_cls = {ni.GetNetCode(): CLS.get(ni.GetNetClassName(), 0.10) for ni in b.GetNetsByNetcode().values()}
# meander layers: env LAYERS='F.Cu,B.Cu' (default: outer + inner layers typed 'signal')
LAY = [b.GetLayerID(n) for n in os.environ['LAYERS'].split(',')] if os.environ.get('LAYERS') else \
    [l for l in b.GetEnabledLayers().CuStack() if l in (pcbnew.F_Cu, pcbnew.B_Cu) or b.GetLayerType(l) == pcbnew.LT_SIGNAL]
T.PITCH = 0.30
fld = T.Exact(b, LAY, lambda c: code_cls.get(c, 0.10))
for z in b.Zones():
    # H3 board: protect the split power layer's islands from meanders (env PROTECT_LAYER='In3.Cu', PROTECT_KEEP='VCC_3V3')
    if not os.environ.get('PROTECT_LAYER') or z.GetIsRuleArea() or z.GetLayer() != b.GetLayerID(os.environ['PROTECT_LAYER']) or \
            z.GetNetname() == os.environ.get('PROTECT_KEEP', ''):
        continue
    ps_ = z.GetFilledPolysList(z.GetLayer())
    for i in range(ps_.OutlineCount()):
        ol = ps_.Outline(i)
        fld._add(z.GetLayer(), _Pg([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())]).buffer(0.15), -999, 0.15)
fld._build()
full = {ni.GetNetname().split('/')[-1]: ni.GetNetname() for ni in b.GetNetsByNetcode().values()}


def lens():
    L = collections.defaultdict(float)
    for t in b.GetTracks():
        if t.GetClass() != 'PCB_VIA':
            L[t.GetNetname().split('/')[-1]] += t.GetLength() / MM
    return L


# pairs to trim: env PAIRS='HDMI_D0_P:HDMI_D0_N:0.3,USB_DP:USB_DM:1.0' (P : N : tolerance mm); default = H3 SBC set
if os.environ.get('PAIRS'):
    PAIRS = [(p, n, float(t)) for p, n, t in (x.split(':') for x in os.environ['PAIRS'].split(','))]
else:
    PAIRS = [('HDMI_D%d_P' % i, 'HDMI_D%d_N' % i, 0.3) for i in range(3)] + [('HDMI_CK_P', 'HDMI_CK_N', 0.3)] + \
            [('%s_DP' % u, '%s_DM' % u, 1.0) for u in ('USB0', 'USB0A', 'USB1', 'USB2', 'USB3', 'USBC')] + \
            [('EPHY_TXP', 'EPHY_TXN', 1.0), ('EPHY_RXP', 'EPHY_RXN', 1.0)]
L0 = lens()
for rnd in range(3):
    L = lens()
    for p, n, tol in PAIRS:
        a, c = L.get(p), L.get(n)
        if not a or not c or abs(a - c) <= tol:
            continue
        s = p if a < c else n
        T.add_length(b, fld, full[s], abs(a - c) - tol / 3, clr_seg=0.30)
L = lens()
for p, n, tol in PAIRS:
    if L.get(p) and L.get(n):
        print('%-11s %6.2f/%6.2f  skew %5.2f -> %5.2f mm' % (p[:-2], L[p], L[n], L0[p] - L0[n], L[p] - L[n]))
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(sys.argv[2])
