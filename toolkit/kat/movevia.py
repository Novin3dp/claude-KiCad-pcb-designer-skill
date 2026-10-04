#!/usr/bin/env python3
"""move a via (and the ends of its own-net tracks that touch it). usage: movevia.py IN OUT x,y dx,dy [x,y dx,dy ...]"""
import sys, pcbnew
MM = 1e6
b = pcbnew.LoadBoard(sys.argv[1])
args = sys.argv[3:]
TR = list(b.GetTracks())
for k in range(0, len(args), 2):
    x, y = map(float, args[k].split(',')); dx, dy = map(float, args[k + 1].split(','))
    v = [t for t in TR if t.GetClass() == 'PCB_VIA' and abs(t.GetPosition().x / MM - x) < 0.01 and abs(t.GetPosition().y / MM - y) < 0.01]
    assert len(v) == 1, (x, y, len(v))
    v = v[0]; net = v.GetNetCode(); p = v.GetPosition()
    np_ = pcbnew.VECTOR2I(p.x + int(dx * MM), p.y + int(dy * MM))
    for t in TR:
        if t.GetClass() == 'PCB_TRACK' and t.GetNetCode() == net:
            if (t.GetStart() - p).EuclideanNorm() < 2000: t.SetStart(np_)
            if (t.GetEnd() - p).EuclideanNorm() < 2000: t.SetEnd(np_)
    v.SetPosition(np_)
    print('moved', v.GetNetname(), x, y, '->', np_.x / MM, np_.y / MM)
b.Save(sys.argv[2])
