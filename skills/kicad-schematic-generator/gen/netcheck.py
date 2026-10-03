#!/usr/bin/env python3
"""netcheck - sanity checks on a KiCad netlist exported with `kicad-cli sch export netlist`.

usage: netcheck.py design.net [--fp-dir /usr/share/kicad/footprints] [--local-fp NAME=DIR ...]
Checks: duplicate refs, single-node nets, symbol pins missing from the assigned footprint,
missing footprints/empty footprint fields.  Exit code 1 if anything is wrong.
Also importable: load(netfile) -> (comps, nets, pin2net) for design-specific assertions.
Works with KiCad 9 (one-line) and KiCad 10 (pretty-printed) netlists.
"""
import re, os, sys


def load(path):
    t = re.sub(r'\s+', ' ', open(path).read()).replace('( ', '(').replace(' )', ')')
    comps = re.findall(r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)(?:\s*\(footprint "([^"]*)"\))?', t)
    nets, pin2net = {}, {}
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]*)"\)', t):
        s = m.end(); e = t.find('(net (code', s); blk = t[s:e if e > 0 else len(t)]
        name = m.group(1).split('/')[-1]
        nodes = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', blk)
        nets.setdefault(name, []).extend(nodes)
        for n in nodes:
            pin2net[n] = name
    return comps, nets, pin2net


def main():
    args = sys.argv[1:]
    net = args[0]
    fpdir = '/usr/share/kicad/footprints'
    local = {}
    i = 1
    while i < len(args):
        if args[i] == '--fp-dir': fpdir = args[i + 1]; i += 2
        elif args[i] == '--local-fp':
            k, v = args[i + 1].split('='); local[k] = v; i += 2
        else: i += 1
    comps, nets, pin2net = load(net)
    bad = 0
    if not comps:
        bad += 1; print('NO COMPONENTS PARSED - unknown netlist format?')
    refs = [c[0] for c in comps]
    dup = sorted({r for r in refs if refs.count(r) > 1})
    if dup: bad += 1; print('DUPLICATE REFS:', dup)
    for n, v in nets.items():
        if len(v) < 2 and not n.startswith('unconnected'):
            bad += 1; print('SINGLE-NODE NET:', n, v)
    pins = {}
    for (r, p) in pin2net: pins.setdefault(r, set()).add(p)
    seen = set()
    for ref, val, fp in comps:
        if ref.startswith('#') or ref.startswith('H') and not pins.get(ref):
            continue
        if not fp:
            bad += 1; print('NO FOOTPRINT:', ref, val); continue
        lib, name = fp.split(':', 1)
        d = local.get(lib, os.path.join(fpdir, lib + '.pretty'))
        path = os.path.join(d, name + '.kicad_mod')
        if not os.path.exists(path):
            if fp not in seen: bad += 1; print('MISSING FOOTPRINT FILE:', fp, '(%s)' % ref); seen.add(fp)
            continue
        pads = set(re.findall(r'\(pad "([^"]*)"', open(path).read()))
        miss = pins.get(ref, set()) - pads
        if miss: bad += 1; print('PINS NOT IN FOOTPRINT:', ref, val, fp, sorted(miss))
    print('components %d, nets %d, problems %d' % (len(comps), len(nets), bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
