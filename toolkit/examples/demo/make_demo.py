#!/usr/bin/env python3
"""Build a small UNROUTED 4-layer demo board (45 x 32 mm) to try the toolkit on: two SOIC-8 parts, an 0603 RC
network, decoupling caps, a 2x5 header; GND plane on In1, +3V3 plane on In2.   usage: make_demo.py OUT.kicad_pcb"""
import sys
import pcbnew
MM = 1e6
FP = '/usr/share/kicad/footprints'
out = sys.argv[1] if len(sys.argv) > 1 else 'demo.kicad_pcb'
b = pcbnew.BOARD()
b.SetCopperLayerCount(4)
ds = b.GetDesignSettings()
ds.m_TrackMinWidth = int(0.15 * MM); ds.m_MinClearance = int(0.15 * MM)
W, H = 45.0, 32.0
for (x0, y0), (x1, y1) in zip([(0, 0), (W, 0), (W, H), (0, H)], [(W, 0), (W, H), (0, H), (0, 0)]):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(int(0.1 * MM))
    s.SetStart(pcbnew.VECTOR2I(int(x0 * MM), int(y0 * MM))); s.SetEnd(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM))); b.Add(s)
nets = {}


def net(n):
    if n not in nets:
        ni = pcbnew.NETINFO_ITEM(b, n); b.Add(ni); nets[n] = ni
    return nets[n]


def place(lib, name, ref, x, y, rot, pins):
    f = pcbnew.FootprintLoad('%s/%s.pretty' % (FP, lib), name)
    f.SetReference(ref); b.Add(f)
    f.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(y * MM))); f.SetOrientationDegrees(rot)
    for p in f.Pads():
        if p.GetNumber() in pins:
            p.SetNet(net(pins[p.GetNumber()]))
    return f


SO, R, C = ('Package_SO', 'SOIC-8_3.9x4.9mm_P1.27mm'), ('Resistor_SMD', 'R_0603_1608Metric'), ('Capacitor_SMD', 'C_0603_1608Metric')
place(*SO, 'U1', 14, 16, 0, {'1': 'IN_A', '2': 'FB_A', '3': 'REF', '4': 'GND', '5': 'REF', '6': 'FB_B', '7': 'OUT_B', '8': '+3V3'})
place(*SO, 'U2', 31, 16, 0, {'1': 'OUT_B', '2': 'SCL', '3': 'SDA', '4': 'GND', '5': 'EN', '6': 'OUT_A', '7': 'IRQ', '8': '+3V3'})
place(*R, 'R1', 8, 10, 90, {'1': 'IN_A', '2': 'FB_A'})
place(*R, 'R2', 8, 22, 90, {'1': 'FB_B', '2': 'OUT_B'})
place(*R, 'R3', 22, 9, 0, {'1': '+3V3', '2': 'REF'})
place(*R, 'R4', 22, 23, 0, {'1': 'REF', '2': 'GND'})
place(*R, 'R5', 36.5, 7, 0, {'1': '+3V3', '2': 'SCL'})
place(*R, 'R6', 36.5, 25, 0, {'1': '+3V3', '2': 'SDA'})
place(*C, 'C1', 14, 10, 0, {'1': '+3V3', '2': 'GND'})
place(*C, 'C2', 31, 10, 0, {'1': '+3V3', '2': 'GND'})
place(*C, 'C3', 17, 23, 0, {'1': 'FB_A', '2': 'OUT_A'})
place('Connector_PinHeader_2.54mm', 'PinHeader_2x05_P2.54mm_Vertical', 'J1', 40, 11, 0,
      {'1': '+3V3', '2': 'GND', '3': 'SCL', '4': 'SDA', '5': 'EN', '6': 'IRQ', '7': 'IN_A', '8': 'OUT_A', '9': 'GND', '10': 'GND'})
for layer, n in ((pcbnew.In1_Cu, 'GND'), (pcbnew.In2_Cu, '+3V3')):
    z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNet(net(n)); z.SetLocalClearance(int(0.25 * MM)); z.SetMinThickness(int(0.25 * MM))
    o = z.Outline(); o.NewOutline()
    for x, y in ((0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, H - 0.5), (0.5, H - 0.5)):
        o.Append(int(x * MM), int(y * MM))
    b.Add(z)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(out)
# design rules live in the .kicad_pro (KiCad 8+): write one so DRC and the router agree on the minimums
import json, os
pro = {'board': {'design_settings': {'rules': {'min_clearance': 0.15, 'min_track_width': 0.15, 'min_via_diameter': 0.3,
                                               'min_through_hole_diameter': 0.15, 'min_via_annular_width': 0.075,
                                               'min_copper_edge_clearance': 0.3}}},
       'meta': {'filename': os.path.basename(out)[:-len('.kicad_pcb')] + '.kicad_pro', 'version': 3}}
json.dump(pro, open(out[:-len('.kicad_pcb')] + '.kicad_pro', 'w'), indent=2)
print('wrote', out, len(nets), 'nets')
