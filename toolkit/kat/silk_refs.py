#!/usr/bin/env python3
"""Re-place reference designators so none sits on a pad, on another reference, on a part outline or off the board.
For every footprint (both sides) its ref text is tried at the current spot and then around the part (above / below /
left / right, both orientations) at 0.8 / 0.7 / 0.6 mm height; the first legal spot wins.  A ref with no legal spot
is hidden on silk (it stays on the Fab drawing).   usage: silk_refs.py IN OUT"""
import sys
import pcbnew
from shapely.geometry import box, LineString, Point
from shapely.strtree import STRtree
MM = 1e6
src, dst = sys.argv[1:3]
b = pcbnew.LoadBoard(src)
eb = b.GetBoardEdgesBoundingBox()
EDGE = box(eb.GetLeft() / MM + 0.3, eb.GetTop() / MM + 0.3, eb.GetRight() / MM - 0.3, eb.GetBottom() / MM - 0.3)
SIDES = {False: (pcbnew.F_SilkS, pcbnew.F_Cu, pcbnew.F_Mask), True: (pcbnew.B_SilkS, pcbnew.B_Cu, pcbnew.B_Mask)}


def bb2(bb, g=0.0):
    return box(bb.GetLeft() / MM - g, bb.GetTop() / MM - g, bb.GetRight() / MM + g, bb.GetBottom() / MM + g)


obst = {False: [], True: []}
for f in b.GetFootprints():
    for p in f.Pads():
        for side in (False, True):
            cu = SIDES[side][1]
            if p.IsOnLayer(cu) or p.IsOnLayer(SIDES[side][2]):
                obst[side].append(bb2(p.GetBoundingBox(), 0.12))
    for g in f.GraphicalItems():
        for side in (False, True):
            if g.GetLayer() == SIDES[side][0] and g.GetClass() != 'PCB_TEXT':
                obst[side].append(bb2(g.GetBoundingBox(), 0.1))
for t in b.GetDrawings():
    for side in (False, True):
        if t.GetLayer() == SIDES[side][0]:
            obst[side].append(bb2(t.GetBoundingBox(), 0.1))
# vias are tented: silk over them is fine
for side in (False, True):
    for f in b.GetFootprints():
        for fld in (f.Value(),):
            pass
placed = {False: [], True: []}
trees = {s: STRtree(obst[s]) for s in (False, True)}


def legal(side, g):
    if not EDGE.contains(g):
        return False
    for k in trees[side].query(g):
        if obst[side][k].intersects(g):
            return False
    return not any(q.intersects(g) for q in placed[side])


moved = hidden = kept = 0
fps = sorted(b.GetFootprints(), key=lambda f: -f.GetBoundingBox(False).GetArea())
for f in fps:
    r = f.Reference()
    side = f.IsFlipped()
    if not r.IsVisible() or r.GetLayer() != SIDES[side][0]:
        continue
    cur = bb2(r.GetBoundingBox(), 0.05)
    if legal(side, cur):
        placed[side].append(cur); kept += 1; continue
    fb = f.GetBoundingBox(False)
    cx, cy = fb.Centre().x / MM, fb.Centre().y / MM
    w2, h2 = fb.GetWidth() / MM / 2, fb.GetHeight() / MM / 2
    done = False
    for hgt in (0.8, 0.7, 0.6):
        r.SetTextSize(pcbnew.VECTOR2I(int(hgt * MM), int(hgt * MM))); r.SetTextThickness(int(hgt * 0.15 * MM))
        for ang in (0.0, 90.0):
            r.SetTextAngleDegrees(ang)
            for gap in (0.25, 0.5, 0.9, 1.4):
                for (x, y) in ((cx, cy - h2 - gap - hgt / 2), (cx, cy + h2 + gap + hgt / 2), (cx - w2 - gap - hgt / 2, cy),
                               (cx + w2 + gap + hgt / 2, cy), (cx - w2, cy - h2 - gap - hgt / 2), (cx + w2, cy + h2 + gap + hgt / 2)):
                    r.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(y * MM)))
                    g = bb2(r.GetBoundingBox(), 0.05)
                    if legal(side, g):
                        placed[side].append(g); done = True; break
                if done:
                    break
            if done:
                break
        if done:
            break
    if done:
        moved += 1
    else:
        r.SetVisible(False); hidden += 1
b.Save(dst)
print('refs kept %d, moved %d, hidden %d' % (kept, moved, hidden))
