#!/usr/bin/env python3
"""Enlarge every via of the given nets (v3), e.g. the layer changes of a supply that carries amps:
a 0.4 mm drill is good for ~1-1.5 A in 1/2 oz plating, 0.6 mm for ~2 A.
usage: fat_vias.py IN OUT DIAMETER DRILL NET[,NET] (net names short, without the /Sheet/ prefix)
Run DRC afterwards: a bigger via may no longer clear its neighbours - then leave that net alone or re-route it
with layer_cost() keeping it on one layer (no vias at all)."""
import sys, pcbnew
src, dst, d, dr, nets = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5].split(',')
b = pcbnew.LoadBoard(src)
n = 0
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA' and t.GetNetname().split('/')[-1] in nets:
        t.SetWidth(pcbnew.FromMM(d)); t.SetDrill(pcbnew.FromMM(dr)); n += 1
b.Save(dst); print('enlarged', n, 'vias to %.2f/%.2f' % (d, dr))
