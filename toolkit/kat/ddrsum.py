#!/usr/bin/env python3
"""compact DDR length table: per group target / min / max / worst vs reference, plus per-net deltas
usage: ddrsum.py BOARD"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.getcwd())
import pcbnew
import importlib
sbc_ddr = importlib.import_module(os.environ.get('DDR_PROFILE', 'ddr_profile'))
import ddr_report as DR
b = pcbnew.LoadBoard(sys.argv[1])
rows, summ = sbc_ddr.summary(b)
L = {r['net']: r['len'] for r in rows}
for s in summ:
    print('%-18s ref %6.2f  members %5.2f..%5.2f  worst |dL| %5.2f  pair skew %s' % (
        s['group'], s['ref'] or 0, s['min'] or 0, s['max'] or 0, s['worst_vs_ref'] or 0, '%.2f' % s['pair_skew'] if s['pair_skew'] is not None else '-'))
for g, gd in DR.GROUPS.items():
    ref = [L[n] for n in gd['ref'] if L.get(n)]
    r = sum(ref) / len(ref)
    print('  ' + g + ': ' + ' '.join('%s%+.1f' % (n.replace('DDR_', ''), L[n] - r) for n in gd['nets'] if L.get(n)))
