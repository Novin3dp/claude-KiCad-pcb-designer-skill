#!/usr/bin/env python3
"""GND copper pour on the outer layers (L1, L6) plus stitching vias, IcePi style: every free area becomes GND, pads of
GND connect straight into it, and a 2.4 mm stitching lattice (only where a 0.40/0.20 via clears everything on all
layers) ties the pours to the L2 / L5 planes so no island floats.  Clearance to foreign copper 0.25 mm (>= 2.5 W,
keeps the routed 50 / 90 / 100 R lines close to their microstrip values), 0.5 mm around the 2.4 GHz feed.
usage: gnd_pour.py IN OUT"""
import sys, math
import pcbnew
from shapely.geometry import Point, LineString, Polygon, box
from shapely.strtree import STRtree
MM = 1e6
b = pcbnew.LoadBoard(sys.argv[1])
gnd = b.FindNet('GND')
edge = b.GetBoardEdgesBoundingBox()
X0, Y0, X1, Y1 = edge.GetLeft() / MM, edge.GetTop() / MM, edge.GetRight() / MM, edge.GetBottom() / MM
for lay, name in ((pcbnew.F_Cu, 'L1 GND pour'), (pcbnew.B_Cu, 'L6 GND pour')):
    z = pcbnew.ZONE(b)
    z.SetLayer(lay); z.SetNet(gnd)
    o = z.Outline(); o.NewOutline()
    for x, y in ((X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)):
        o.Append(int(x * MM), int(y * MM))
    z.SetAssignedPriority(0); z.SetLocalClearance(int(0.25 * MM)); z.SetMinThickness(int(0.20 * MM))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL); z.SetThermalReliefGap(int(0.25 * MM)); z.SetThermalReliefSpokeWidth(int(0.25 * MM))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetZoneName(name)
    b.Add(z)
# keep the pour away from the RF feed: rule area on L1 around the tracks of nets starting with env RF_PREFIX (e.g. WL_RF)
import os
RF_PREFIX = tuple(p for p in os.environ.get('RF_PREFIX', '').split(',') if p)
rf = []
for t in b.GetTracks():
    if t.GetClass() != 'PCB_VIA' and RF_PREFIX and t.GetNetname().split('/')[-1].startswith(RF_PREFIX):
        rf.append(LineString([(t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM)]).buffer(0.5 + t.GetWidth() / MM / 2))
if rf:
    from shapely.ops import unary_union
    g = unary_union(rf)
    for poly in (g.geoms if g.geom_type == 'MultiPolygon' else [g]):
        ra = pcbnew.ZONE(b); ra.SetIsRuleArea(True); ra.SetLayer(pcbnew.F_Cu)
        ra.SetDoNotAllowZoneFills(True); ra.SetDoNotAllowTracks(False); ra.SetDoNotAllowVias(False); ra.SetDoNotAllowPads(False); ra.SetDoNotAllowFootprints(False)
        o = ra.Outline(); o.NewOutline()
        for x, y in list(poly.exterior.coords)[:-1]:
            o.Append(int(x * MM), int(y * MM))
        ra.SetZoneName('RF keep pour away'); b.Add(ra)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
# stitching lattice
geo, gnet = [], []
for f in b.GetFootprints():
    for p in f.Pads():
        bb = p.GetBoundingBox()
        geo.append(box(bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)); gnet.append(p.GetNetCode())
    cy = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
    if cy.OutlineCount() and f.GetReference()[0] in 'UJ' and len(list(f.Pads())) > 6:
        bb = cy.BBox()      # no stitching inside IC / connector footprints
        geo.append(box(bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM)); gnet.append(-2)
DRL = []
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            DRL.append(Point(p.GetPosition().x / MM, p.GetPosition().y / MM).buffer(max(p.GetDrillSize().x, p.GetDrillSize().y) / MM / 2))
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA':
        DRL.append(Point(t.GetPosition().x / MM, t.GetPosition().y / MM).buffer(t.GetDrillValue() / MM / 2))
DTREE = STRtree(DRL)
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA':
        geo.append(Point(t.GetPosition().x / MM, t.GetPosition().y / MM).buffer(t.GetWidth(pcbnew.F_Cu) / MM / 2)); gnet.append(t.GetNetCode())
    else:
        geo.append(LineString([(t.GetStart().x / MM, t.GetStart().y / MM), (t.GetEnd().x / MM, t.GetEnd().y / MM)]).buffer(t.GetWidth() / MM / 2)); gnet.append(t.GetNetCode())
for z in [z for f in b.GetFootprints() for z in f.Zones()] + list(b.Zones()):
    if z.GetIsRuleArea():
        o = z.Outline()
        for i in range(o.OutlineCount()):
            ol = o.Outline(i)
            geo.append(Polygon([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())]).buffer(0)); gnet.append(-1)
tree = STRtree(geo)
fills = {}
for z in b.Zones():
    if not z.GetIsRuleArea() and z.GetNetname() == 'GND' and z.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
        ps = z.GetFilledPolysList(z.GetLayer())
        fills[z.GetLayer()] = [Polygon([(ps.Outline(i).CPoint(k).x / MM, ps.Outline(i).CPoint(k).y / MM) for k in range(ps.Outline(i).PointCount())]).buffer(-0.25)
                               for i in range(ps.OutlineCount())]
from shapely.prepared import prep
# split power layer(s) (env SPLIT_LAYERS='In3.Cu'): a stitching hole must not land in a narrow part of any pour there
# (it would cut a neck) - only deep inside it.  Default: every inner layer that carries a non-GND zone.
_SPL = [b.GetLayerID(n) for n in os.environ['SPLIT_LAYERS'].split(',')] if os.environ.get('SPLIT_LAYERS') else \
    sorted({z.GetLayer() for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname() != 'GND' and z.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)})
L4DEEP, L4ANY = [], []
for z in b.Zones():
    if z.GetIsRuleArea() or z.GetLayer() not in _SPL:
        continue
    ps = z.GetFilledPolysList(z.GetLayer())
    for i in range(ps.OutlineCount()):
        g = Polygon([(ps.Outline(i).CPoint(k).x / MM, ps.Outline(i).CPoint(k).y / MM) for k in range(ps.Outline(i).PointCount())]).buffer(0)
        L4ANY.append(prep(g)); d_ = g.buffer(-0.9)
        if not d_.is_empty:
            L4DEEP.append(prep(d_))
FT = [prep(g) for g in fills.get(pcbnew.F_Cu, [])]; FB = [prep(g) for g in fills.get(pcbnew.B_Cu, [])]
n = 0
STEP = 2.4
y = Y0 + 1.2
while y < Y1 - 1.0:
    x = X0 + 1.2 + (STEP / 2 if int((y - Y0) / STEP) % 2 else 0)
    while x < X1 - 1.0:
        pnt = Point(x, y)
        if any(g.contains(pnt) for g in FT) and any(g.contains(pnt) for g in FB) and \
                (any(g.contains(pnt) for g in L4DEEP) or not any(g.contains(pnt) for g in L4ANY)):
            vg = pnt.buffer(0.20)
            hole = pnt.buffer(0.10)
            if any(hole.distance(DRL[i]) < 0.30 for i in DTREE.query(pnt.buffer(1.5))):     # hole-to-hole (any net)
                x += STEP; continue
            if all(gnet[i] == gnd.GetNetCode() or vg.distance(geo[i]) >= 0.25 for i in tree.query(vg.buffer(0.3))):
                v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(y * MM))); v.SetWidth(int(0.40 * MM)); v.SetDrill(int(0.20 * MM))
                v.SetNet(gnd); v.SetViaType(pcbnew.VIATYPE_THROUGH); v.SetLocked(True); b.Add(v); n += 1
        x += STEP
    y += STEP * math.sqrt(3) / 2
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(sys.argv[2])
print('GND pours on L1 / L6, stitching vias:', n)
