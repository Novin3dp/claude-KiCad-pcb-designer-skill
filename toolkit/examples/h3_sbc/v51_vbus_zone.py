#!/usr/bin/env python3
"""v5.1: USB-C VBUS feed J7 (A4/B9, A9/B4) -> Q3 drain as a top-layer copper pour instead of 0.3 mm tracks
(solid pad connection, priority above the GND pour).   usage: v51_vbus_zone.py IN OUT"""
import sys, pcbnew
MM = 1e6
b = pcbnew.LoadBoard(sys.argv[1])
net = b.FindNet('USBC_VBUS')
z = pcbnew.ZONE(b)
z.SetLayer(pcbnew.F_Cu); z.SetNet(net); z.SetAssignedPriority(10)
z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
z.SetLocalClearance(int(0.15 * MM)); z.SetMinThickness(int(0.2 * MM))
z.SetZoneName('USBC_VBUS_FEED')
o = z.Outline(); o.NewOutline()
for x, y in [(59.55, 45.15), (60.45, 45.15), (60.45, 46.3), (67.0, 46.3), (67.0, 47.6), (66.0, 47.6), (66.0, 47.45),
             (61.9, 47.45), (61.9, 47.6), (61.1, 47.6), (61.1, 47.45), (59.55, 47.0)]:
    o.Append(int(x * MM), int(y * MM))
b.Add(z)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
fp = z.GetFilledPolysList(pcbnew.F_Cu)
print('USBC_VBUS pour: %d island(s), %.2f mm2' % (fp.OutlineCount(), fp.Area() / 1e12))
b.Save(sys.argv[2])
