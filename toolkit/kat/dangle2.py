#!/usr/bin/env python3
"""Remove dangling copper reported by DRC with EXACT matching (net, layer, length and the free end point), so a long
track that merely passes the reported point is never touched.   usage: dangle2.py IN OUT DRC_JSON"""
import sys, json, re
import pcbnew
MM = 1e6
b = pcbnew.LoadBoard(sys.argv[1])
d = json.load(open(sys.argv[3]))
TR = list(b.GetTracks())
kill = set()
for v in d['violations']:
    if v['type'] not in ('via_dangling', 'track_dangling'):
        continue
    it = v['items'][0]
    x, y = it['pos']['x'], it['pos']['y']
    m = re.match(r'(Track|Via) \[([^\]]*)\] on ([^,]+?)(?: - [^,]+)?(?:, length ([\d.]+) mm)?$', it['description'])
    if not m:
        print('skip', it['description']); continue
    kind, net, lay, ln = m.groups()
    hits = []
    for k, t in enumerate(TR):
        if t.GetNetname() != net:
            continue
        if kind == 'Via' and t.GetClass() == 'PCB_VIA':
            p = t.GetPosition()
            if abs(p.x / MM - x) < 0.002 and abs(p.y / MM - y) < 0.002:
                hits.append(k)
        elif kind == 'Track' and t.GetClass() == 'PCB_TRACK' and b.GetLayerName(t.GetLayer()) == lay:
            if abs(t.GetLength() / MM - float(ln)) > 0.0005:
                continue
            ends = [t.GetStart(), t.GetEnd()]
            if any(abs(q.x / MM - x) < 0.002 and abs(q.y / MM - y) < 0.002 for q in ends):
                hits.append(k)
    if len(hits) == 1:
        kill.add(hits[0])
    else:
        print('ambiguous / not found (%d): %s @ %.3f %.3f' % (len(hits), it['description'], x, y))
for k in sorted(kill):
    b.Remove(TR[k])
b.Save(sys.argv[2])
print('removed', len(kill))
