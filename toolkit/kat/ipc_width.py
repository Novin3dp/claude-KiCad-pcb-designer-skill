#!/usr/bin/env python3
"""Track width and via count from current using the IPC-2221 formula.
Usage: ipc_width.py 'NET=AMPS[,NET=AMPS...]' [--dt 10] [--oz 1] [--inner-oz 0.5] [--max 2.0] [--spec]
--spec prints a neckdown.py spec string (outer-layer widths, capped by --max)."""
import sys, math
OZ_UM = 34.8
def width_mm(amps, dt=10.0, oz=1.0, inner=False):
    k = 0.024 if inner else 0.048
    area_mil2 = (amps / (k * dt ** 0.44)) ** (1 / 0.725)
    th_mil = oz * OZ_UM / 25.4
    return area_mil2 / th_mil * 0.0254
def via_amps(drill=0.2, plating_um=25, dt=10.0):
    a_mil2 = math.pi * (drill * 1000 / 25.4) * (plating_um / 25.4)
    return 0.024 * dt ** 0.44 * a_mil2 ** 0.725
def main():
    a = sys.argv
    dt = float(a[a.index('--dt') + 1]) if '--dt' in a else 10.0
    oz = float(a[a.index('--oz') + 1]) if '--oz' in a else 1.0
    ioz = float(a[a.index('--inner-oz') + 1]) if '--inner-oz' in a else 0.5
    mx = float(a[a.index('--max') + 1]) if '--max' in a else 2.0
    va = via_amps(dt=dt); spec = []
    print('dT %.0f C, outer %.1f oz, inner %.1f oz, via 0.2 mm drill carries %.2f A' % (dt, oz, ioz, va))
    for kv in a[1].split(','):
        n, i = kv.rsplit('=', 1); i = float(i)
        wo, wi = width_mm(i, dt, oz), width_mm(i, dt, ioz, True)
        nv = max(1, math.ceil(i / va))
        print('  %-14s %5.2f A  outer %5.2f mm  inner %5.2f mm  vias >= %d' % (n, i, wo, wi, nv))
        spec.append('%s=%.2f' % (n, min(mx, max(0.15, math.ceil(wo * 20) / 20))))
    if '--spec' in a: print(','.join(spec))
if __name__ == '__main__': main()
