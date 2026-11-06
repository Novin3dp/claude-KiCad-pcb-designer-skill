#!/usr/bin/env python3
"""Improvement gate: accept a routed board only when neither net completion nor open-link count regresses.
usage: gate.py BEFORE.kicad_pcb AFTER.kicad_pcb [--promote OUT.kicad_pcb]"""
import os, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle
before, after = sys.argv[1], sys.argv[2]
pb, pa = oracle.per_net(before), oracle.per_net(after)
lost = sorted(n for n in pa if n not in pb)
gained = sorted(n for n in pb if n not in pa)
tb, ta = sum(pb.values()), sum(pa.values())
worse = sorted(n for n in pa if n in pb and pa[n] > pb[n])
ok = len(lost) <= len(gained) and ta <= tb
print('open links %d -> %d; nets gained %d %s; lost %d %s; worse %s' % (tb, ta, len(gained), gained[:12], len(lost), lost[:12], worse[:12]))
print('ACCEPTED' if ok else 'REJECTED')
if '--promote' in sys.argv:
    out = sys.argv[sys.argv.index('--promote') + 1]
    src = after if ok else before
    for e in ('.kicad_pcb', '.kicad_pro', '.kicad_dru'):
        s = os.path.splitext(src)[0] + e
        if os.path.exists(s):
            shutil.copyfile(s, os.path.splitext(out)[0] + e)
sys.exit(0 if ok else 1)
