#!/usr/bin/env python3
"""v2 ECO: apply the new netlist (XH input, MP1584 module, USB-C power only, no FAN2 / debug header, HDMI Type A) to the
routed v1 board without rebuilding it.  Footprints removed from the netlist are deleted with every track / via touching
their pads; footprints whose library footprint changed are swapped in place (same position / side / rotation); new parts
are added at the board origin (placed later); every pad gets its net from the new netlist; copper of nets that no
longer exist is deleted.   usage: eco.py IN.kicad_pcb NEW.net OUT.kicad_pcb   (env FP_LIBS=nick=/path/lib.pretty for project libraries)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import geom
from geom import load_fp
from netlist import load
MM = 1e6
src, netf, dst = sys.argv[1:4]
# project footprint libraries: env FP_LIBS='nick=/path/to/lib.pretty,nick2=/path2.pretty' (system libraries are found automatically)
for _kv in filter(None, os.environ.get('FP_LIBS', '').split(',')):
    _k, _v = _kv.split('=', 1); geom.LOCAL[_k] = _v
comps, nets = load(netf)
pin_net = {}
for n, nodes in nets.items():
    for r, p in nodes:
        pin_net[(r, p)] = n
b = pcbnew.LoadBoard(src)
FPS = {f.GetReference(): f for f in b.GetFootprints()}
log = []


def pads_touching(t, fp):
    pts = [t.GetPosition()] if t.GetClass() == 'PCB_VIA' else [t.GetStart(), t.GetEnd()]
    return any(p.HitTest(q) for p in fp.Pads() for q in pts if p.GetNetCode() == t.GetNetCode())


def strip(fp):
    """delete the copper hanging on this footprint's pads (stubs, fan-out vias, via-in-pad)"""
    gone = [t for t in b.GetTracks() if pads_touching(t, fp)]
    for t in gone:
        b.Remove(t)
    return len(gone)


# ---- phase A: read everything (pcbnew wrappers go stale after a Remove, so all reads come first)
have = {}
for code, ni in b.GetNetsByNetcode().items():
    have[ni.GetNetname()] = ni
TR = list(b.GetTracks())
kill_t, kill_f, swaps = set(), [], []
for ref in sorted(set(FPS) - set(comps)):
    k = {i for i, t in enumerate(TR) if pads_touching(t, FPS[ref])}
    kill_t |= k; kill_f.append(ref); log.append('removed %s (+%d copper)' % (ref, len(k)))
for ref, c in comps.items():
    f = FPS.get(ref)
    if f is None:
        continue
    lid = '%s:%s' % (f.GetFPID().GetLibNickname().wx_str(), f.GetFPID().GetLibItemName().wx_str())
    if lid != c['footprint']:
        k = {i for i, t in enumerate(TR) if pads_touching(t, f)}
        kill_t |= k
        swaps.append((ref, f.GetPosition(), f.GetOrientationDegrees(), f.IsFlipped()))
        log.append('swapped %s %s -> %s (+%d copper)' % (ref, lid, c['footprint'], len(k)))
    elif f.GetValue() != c['value']:
        log.append('value %s %s -> %s' % (ref, f.GetValue(), c['value'])); f.SetValue(c['value'])
alive = set(nets)
van = {i for i, t in enumerate(TR) if t.GetNetname() and t.GetNetname() not in alive}
log.append('deleting %d tracks/vias of vanished nets (%s)' % (len(van - kill_t), ', '.join(sorted({TR[i].GetNetname().split('/')[-1] for i in van}))))
kill_t |= van
for n in nets:
    if n not in have:
        ni = pcbnew.NETINFO_ITEM(b, n); b.Add(ni); have[n] = ni; log.append('new net ' + n)
NEWF = {}
for ref, pos, rot, flip in swaps:
    NEWF[ref] = load_fp(comps[ref]['footprint'])
for ref in sorted(set(comps) - set(FPS)):
    NEWF[ref] = load_fp(comps[ref]['footprint'])
PADS = {ref: list(f.Pads()) for ref, f in FPS.items() if ref in comps and ref not in NEWF}
PADS.update({ref: list(f.Pads()) for ref, f in NEWF.items()})
ASSIGN = []
for ref, pl in PADS.items():
    for p in pl:
        ASSIGN.append((p, pin_net.get((ref, p.GetNumber())), bool(p.GetNumber())))
DNP = [(NEWF.get(ref, FPS.get(ref)), bool(c.get('dnp'))) for ref, c in comps.items()]
# ---- phase B: mutate only
for i in kill_t:
    b.Remove(TR[i])
for ref in kill_f:
    b.Remove(FPS[ref])
for ref, pos, rot, flip in swaps:
    b.Remove(FPS[ref])
    nf = NEWF[ref]; nf.SetReference(ref); nf.SetValue(comps[ref]['value'])
    b.Add(nf); nf.SetPosition(pos); nf.SetOrientationDegrees(rot)
    if flip:
        nf.Flip(pos, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
for ref in sorted(set(comps) - set(FPS)):
    nf = NEWF[ref]; nf.SetReference(ref); nf.SetValue(comps[ref]['value'])
    b.Add(nf); nf.SetPosition(pcbnew.VECTOR2I(int(-10 * MM), int(-10 * MM)))
    log.append('added %s %s' % (ref, comps[ref]['footprint']))
for p, n, numbered in ASSIGN:
    if n:
        p.SetNet(have[n])
    elif numbered:
        p.SetNetCode(0)
for f, d in DNP:
    f.SetDNP(d)
b.Save(dst)
print('\n'.join(log))
