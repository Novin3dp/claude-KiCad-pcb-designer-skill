"""DDR3 length report for CN1 (one x16 chip U7, lanes 0/1, point-to-point address/command)."""
import sys, os, collections, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sbclib'))
import pcbnew
import ddr_report as DR

# 6-layer 1.6 mm JLC06161H-1080B: copper depth from the top surface
DR.Z = {pcbnew.F_Cu: 0.0, pcbnew.In1_Cu: 0.111, pcbnew.In2_Cu: 0.227, pcbnew.In3_Cu: 1.363, pcbnew.In4_Cu: 1.478, pcbnew.B_Cu: 1.569}
_orig_graph = DR.build_graph


def build_graph(b, netname):
    g = collections.defaultdict(list)
    CU = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu)
    for t in b.GetTracks():
        if t.GetNetname() != netname:
            continue
        if t.GetClass() == 'PCB_VIA':
            x, y = t.GetPosition().x, t.GetPosition().y
            ks = [DR.key(x, y, l) for l in CU]
            for a in ks:
                for c in ks:
                    if a != c:
                        g[a].append((c, abs(DR.Z[a[2]] - DR.Z[c[2]]), 'via'))
        else:
            l = t.GetLayer()
            a = DR.key(t.GetStart().x, t.GetStart().y, l); c = DR.key(t.GetEnd().x, t.GetEnd().y, l)
            L = t.GetLength() / DR.MM
            g[a].append((c, L, 'trk')); g[c].append((a, L, 'trk'))
    # pads that are passed through (e.g. the CK termination resistor) join the copper they contain
    for f in b.GetFootprints():
        if f.GetReference() in ('U1', 'U7'):
            continue
        for p in f.Pads():
            if p.GetNetname() == netname:
                DR.attach_pad(g, p)
    return g


DR.build_graph = build_graph
DR.GROUPS = collections.OrderedDict()
for lane in (0, 1):
    DR.GROUPS['Lane %d (DQ%d-%d)' % (lane, lane * 8, lane * 8 + 7)] = dict(
        chip='U7', nets=['DDR_DQ%d' % i for i in range(lane * 8, lane * 8 + 8)] + ['DDR_DM%d' % lane],
        ref=['DDR_DQS%d_P' % lane, 'DDR_DQS%d_N' % lane], tol=0.5)
DR.GROUPS['CK'] = dict(chip='U7', nets=[], ref=['DDR_CK_P', 'DDR_CK_N'], tol=0.1)
DR.GROUPS['ADDR/CMD'] = dict(chip='U7', nets=DR.ADDR, ref=['DDR_CK_P', 'DDR_CK_N'], tol=2.5)


def summary(b):
    rows = DR.report(b)
    out = []
    for gname, gd in DR.GROUPS.items():
        rs = [r for r in rows if r['group'] == gname]
        ref = [r['len'] for r in rs if r['net'] in gd['ref'] and r['len'] is not None]
        mem = [r for r in rs if r['net'] in gd['nets']]
        refL = sum(ref) / len(ref) if ref else None
        lens = [r['len'] for r in mem if r['len'] is not None]
        miss = [r['net'] for r in rs if r['len'] is None]
        spread = (max(lens) - min(lens)) if lens else 0
        worst = max((abs(l - refL) for l in lens), default=0) if refL else None
        out.append(dict(group=gname, ref=refL, n=len(mem), min=min(lens) if lens else None, max=max(lens) if lens else None,
                        worst_vs_ref=worst, tol=gd['tol'], pair_skew=(max(ref) - min(ref)) if len(ref) == 2 else None, missing=miss))
    return rows, out


if __name__ == '__main__':
    b = pcbnew.LoadBoard(sys.argv[1])
    rows, s = summary(b)
    for g in s:
        print('%-18s ref %6s  members %2d  len %s..%s  worst |dL| %s (tol %.1f)  pair skew %s  missing %s' % (
            g['group'], '%.2f' % g['ref'] if g['ref'] else '-', g['n'], g['min'], g['max'],
            '%.2f' % g['worst_vs_ref'] if g['worst_vs_ref'] is not None else '-', g['tol'],
            '%.3f' % g['pair_skew'] if g['pair_skew'] is not None else '-', g['missing']))
    json.dump(rows, open(sys.argv[1].replace('.kicad_pcb', '_ddrlen.json'), 'w'), indent=1)
