#!/usr/bin/env python3
"""DDR3 length matching to explicit targets with tune3 windowed accordions.
  pairs: DQS0 / DQS1 / CK legs matched (shorter leg grown)
  lanes: DQS legs grown to T<lane> - 0.05, DQ / DM grown to T<lane> - 0.1   (env T0, T1; default = DQS length)
  addr/cmd: CK legs grown to TCK (env, default current CK), every ADDR/CMD net grown to TCK - ADDR_SLACK (env, 2.0)
usage: ddr_tune.py IN OUT"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.getcwd())
import pcbnew
import importlib
importlib.import_module(os.environ.get('DDR_PROFILE', 'ddr_profile'))   # board-specific DDR settings (layer depths, chip refs)
import ddr_report as DR
import tune2 as T2
import tune3 as T3
src, dst = sys.argv[1], sys.argv[2]
CLS = {'Default': 0.10, 'DDR': 0.10, 'USB90': 0.12, 'HDMI100': 0.15, 'ETH100': 0.15, 'SDIO': 0.10, 'PWR': 0.12, 'GND': 0.10}
b = pcbnew.LoadBoard(src)
code_cls = {ni.GetNetCode(): CLS.get(ni.GetNetClassName(), 0.10) for ni in b.GetNetsByNetcode().values()}
LAY = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]          # never meander on the L4 power layer
fld = T2.Exact(b, LAY, lambda c: code_cls.get(c, 0.10))
full = {ni.GetNetname().split('/')[-1]: ni.GetNetname() for ni in b.GetNetsByNetcode().values()}
MAXA = float(os.environ.get('MAXA', 2.0))
log = []


def lengths():
    return {r['net']: r['len'] for r in DR.report(b) if r['len'] is not None}


def grow(n, dl):
    if dl < 0.15 or n not in full:
        return 0.0
    got = T3.add_length(b, fld, full[n], dl, maxA=MAXA)
    log.append((n, round(dl, 2), round(got, 2)))
    return got


L = lengths()
for p, n in (('DDR_DQS0_P', 'DDR_DQS0_N'), ('DDR_DQS1_P', 'DDR_DQS1_N'), ('DDR_CK_P', 'DDR_CK_N')):
    a, c = L[p], L[n]
    if abs(a - c) > 0.05:
        grow(p if a < c else n, abs(a - c) - 0.02)
L = lengths()
for lane in (0, 1):
    dqs = ['DDR_DQS%d_P' % lane, 'DDR_DQS%d_N' % lane]
    mem = ['DDR_DQ%d' % i for i in range(lane * 8, lane * 8 + 8)] + ['DDR_DM%d' % lane]
    T = float(os.environ.get('T%d' % lane, max(L[d] for d in dqs)))
    lo, hi = sorted(dqs, key=lambda d: L[d])
    grow(lo, T - L[lo] - 0.05)               # the lagging leg first: the pair stays matched
    L = lengths()
    Teff = min(T, L[lo] + 0.05)
    grow(hi, Teff - L[hi] - 0.02)
    L = lengths()
    Teff = min(L[lo], L[hi])
    print('lane %d: target %.2f, DQS reached %.2f / %.2f' % (lane, T, L[dqs[0]], L[dqs[1]]))
    for m in mem:
        grow(m, Teff - L[m] - 0.1)
L = lengths()
TCK = float(os.environ.get('TCK', max(L['DDR_CK_P'], L['DDR_CK_N'])))
lo, hi = sorted(('DDR_CK_P', 'DDR_CK_N'), key=lambda d: L[d])
grow(lo, TCK - L[lo] - 0.03)
L = lengths()
grow(hi, min(TCK, L[lo]) - L[hi] - 0.02)
L = lengths()
TCK = (L['DDR_CK_P'] + L['DDR_CK_N']) / 2
print('CK reached %.2f / %.2f' % (L['DDR_CK_P'], L['DDR_CK_N']))
SL = float(os.environ.get('ADDR_SLACK', 2.0))
for m in DR.ADDR:
    if m in L:
        grow(m, TCK - SL - L[m])
b.Save(dst)
short = [x for x in log if x[2] < x[1] - 0.25]
print('meanders requested %.1f mm, added %.1f mm on %d nets; short of target: %d' % (sum(x[1] for x in log), sum(x[2] for x in log), len(log), len(short)))
for x in log:
    print('  %-12s want +%5.2f got +%5.2f%s' % (x[0], x[1], x[2], '   <<' if x[2] < x[1] - 0.25 else ''))
