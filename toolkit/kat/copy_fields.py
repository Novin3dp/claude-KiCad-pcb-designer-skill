#!/usr/bin/env python3
"""Copy schematic symbol fields (MPN, LCSC, Note, ...) from the netlist onto the footprints (hidden, Fab layer) so
schematic parity stays 0, set DNP flags from the netlist, and drop hand-fitted parts (env NO_POS=U9,J5) from the
position / CPL files.
usage: copy_fields.py IN.kicad_pcb NETLIST.net OUT.kicad_pcb   (netlist: kicad-cli sch export netlist)"""
import sys, re
import pcbnew
MM = 1e6
src, netf, dst = sys.argv[1:4]
txt = open(netf).read()
fields, dnp = {}, set()
for m in re.finditer(r'\(comp\s+\(ref "([^"]+)"\)(.*?)\n\t\t\)\n', txt, re.S):
    ref, body = m.group(1), m.group(2)
    fl = dict(re.findall(r'\(field\s+\(name "([^"]+)"\)\s*"((?:[^"\\]|\\.)*)"\)', body))
    fields[ref] = {k: v for k, v in fl.items() if k not in ('Footprint', 'Datasheet', 'Description') and v}
    if re.search(r'\(name "dnp"\)', body):
        dnp.add(ref)
b = pcbnew.LoadBoard(src)
n_f = 0
for f in b.GetFootprints():
    r = f.GetReference()
    for k, v in fields.get(r, {}).items():
        if f.HasField(k) and f.GetFieldText(k) == v:
            continue
        f.SetField(k, v); n_f += 1
        for fl in f.GetFields():
            if fl.GetName() == k and k not in ('Reference', 'Value'):
                fl.SetVisible(False); fl.SetLayer(pcbnew.B_Fab if f.IsFlipped() else pcbnew.F_Fab)
    if r in fields:
        f.SetDNP(r in dnp)
import os
for _r in filter(None, os.environ.get('NO_POS', '').split(',')):
    _f = b.FindFootprintByReference(_r)
    _f.SetAttributes(_f.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
print('fields set', n_f, ' DNP', sorted(dnp), ' excluded from pos:', os.environ.get('NO_POS', '-'))


b.Save(dst)
