#!/usr/bin/env python3
"""v5: widen the L4 VCC_5V feed to the USB switches (strip y 44.4-46.2 -> 45.3-48.0 for x 29.2-59: moved DOWN so the 3.3 V
band above it (the only L4 link of the 3.3 V area around the H3) gets wider, 1.6 -> 2.5 mm; vertical strip x 22.2-23.9 -> 22.2-24.4 above the VDD_SYS plane).  usage: v5_zone5v.py IN OUT"""
import sys, pcbnew
MM = 1e6
b = pcbnew.LoadBoard(sys.argv[1])
NEW = [(28.4, 17.9), (24.4, 17.9), (24.4, 6.6), (22.2, 6.6), (22.2, 33.0), (22.2, 34.8), (23.9, 34.8), (27.4, 34.8), (27.4, 44.4),
       (22.2, 44.4), (22.2, 46.2), (27.4, 46.2), (29.2, 46.2), (29.2, 48.0), (59.0, 48.0), (59.0, 45.3), (29.2, 45.3), (29.2, 44.4), (29.2, 34.8),
       (29.2, 33.0), (27.4, 33.0), (23.9, 33.0), (23.9, 23.4), (24.4, 23.4), (24.4, 19.4), (28.4, 19.4)]
z = [z for z in b.Zones() if z.GetNetname() == 'VCC_5V' and z.GetAssignedPriority() == 4]
assert len(z) == 1
o = z[0].Outline(); o.RemoveAllContours(); o.NewOutline()
for x, y in NEW:
    o.Append(int(x * MM), int(y * MM))
b.Save(sys.argv[2]); print('VCC_5V L4 feed widened')
