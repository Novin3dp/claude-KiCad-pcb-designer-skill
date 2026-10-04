#!/usr/bin/env python3
"""Build a self-contained interactive HTML viewer for one or more .kicad_pcb files (one "stage" per board).

Per-layer toggles, via / zone / ratsnest / DRC display, net + part search and highlight, placement table, stage
picker and per-stage notes.  Ratsnest and DRC markers come from `kicad-cli pcb drc` (exact), so put the board's
.kicad_pro / .kicad_dru next to it.

usage:
  make_viewer.py -o out.html [--name "My board"] [--notes STAGE=notes.html] [--group "Name=#hex=NETREGEX"] \
                 board_a.kicad_pcb[=Title] [board_b.kicad_pcb[=Title] ...]
  stages are named s1, s2, ... in the order given (the first one opens first).
"""
import argparse, json, os, re, sys, html
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcbnew
import export_geom as EG

COLORS = ['#e5483f', '#58c46c', '#eda23a', '#d65c9b', '#3fc4cf', '#9b7bff', '#c9b03a', '#4f82e6']
ap = argparse.ArgumentParser()
ap.add_argument('boards', nargs='+')
ap.add_argument('-o', '--out', required=True)
ap.add_argument('--name', default='')
ap.add_argument('--notes', action='append', default=[], help='STAGE=file.html (STAGE = s1, s2, ...)')
ap.add_argument('--group', action='append', default=[], help='colour a net group: "Name=#hex=regex"')
a = ap.parse_args()
notes = dict(n.split('=', 1) for n in a.notes)
groups = [g.split('=', 2) for g in a.group]


def layers_of(b):
    out = []
    ids = list(b.GetEnabledLayers().CuStack())
    for i, lid in enumerate(ids):
        k = pcbnew.LayerName(lid)          # canonical F.Cu / In1.Cu / B.Cu
        c = COLORS[0] if i == 0 else COLORS[-1] if i == len(ids) - 1 else COLORS[1 + (i - 1) % (len(COLORS) - 2)]
        typ = {pcbnew.LT_SIGNAL: 'signal', pcbnew.LT_POWER: 'power plane', pcbnew.LT_MIXED: 'mixed', pcbnew.LT_JUMPER: 'jumper'}.get(b.GetLayerType(lid), '')
        out.append(dict(k=k, role='L%d · %s' % (i + 1, typ), c=c))
    return out, ids


def stack_html(b):
    rows = []
    try:
        st = b.GetDesignSettings().GetStackupDescriptor()
        for i in range(st.GetCount()):
            it = st.GetStackupLayer(i)
            rows.append('<tr><td>%s</td><td>%s</td><td>%.4f</td></tr>' % (html.escape(it.GetLayerName()), html.escape(it.GetTypeName()),
                                                                          it.GetThickness() / 1e6))
    except Exception:
        pass
    ds = b.GetDesignSettings()
    return ('<h2>Stackup</h2><div class="tblwrap"><table><thead><tr><th>Layer</th><th>Type</th><th>Thickness mm</th></tr></thead>'
            '<tbody>%s</tbody></table></div><p class="lead">Min track %.3f mm, min clearance %.3f mm, min via %.3f / %.3f mm.</p>' % (
                ''.join(rows) or '<tr><td colspan=3>no stackup in the board file</td></tr>',
                ds.m_TrackMinWidth / 1e6, ds.m_MinClearance / 1e6, ds.m_ViasMinSize / 1e6, ds.m_MinThroughDrill / 1e6))


tpl = open(os.path.join(HERE, 'viewer_template.html')).read()
blocks, meta, first = [], [], None
for i, spec in enumerate(a.boards):
    path, _, title = spec.partition('=')
    path = os.path.abspath(path)
    sid = 's%d' % (i + 1)
    b = pcbnew.LoadBoard(path)
    first = first or b
    lays, ids = layers_of(b)
    EG.LAYERS = [(l['k'], lid) for l, lid in zip(lays, ids)]
    EG.LID = {lid: k for k, (_, lid) in enumerate(EG.LAYERS)}
    d = EG.export(path)
    d['layers'] = lays
    d['boardName'] = a.name or os.path.basename(path)
    rats, n, _ = EG.drc_rats(path, d['nets'])
    d['rats'], d['unrouted'] = rats, n
    d['ov'], d['legend'] = [], []
    gl = []
    for name, col, rx in groups:
        codes = [k for k, nm in enumerate(d['nets']) if nm and re.search(rx, nm.split('/')[-1])]
        if codes:
            gl.append(dict(name=name, c=col, nets=codes))
    if gl:
        d['groups'] = gl
        d['legend'] = [dict(c=g['c'], l=g['name']) for g in gl]
    errs = sum(1 for v in d['drc'] if v['s'] == 'error')
    meta.append(dict(id=sid, title=title or os.path.basename(path), sub='DRC errors %d · unconnected %d' % (errs, n), state='done'))
    blocks.append('<script type="application/json" id="stage-%s">%s</script>' % (sid, json.dumps(d, separators=(',', ':')).replace('</', '<\\/')))
    note = open(notes[sid]).read() if sid in notes else \
        '<h2>%s</h2><p class="lead">%d footprints, %d tracks, %d vias. DRC errors: %d, unconnected: %d.</p>' % (
            html.escape(title or os.path.basename(path)), len(d['fps']), len(d['tracks']), len(d['vias']), errs, n)
    blocks.append('<template id="notes-%s">%s</template>' % (sid, note))
    print(sid, os.path.basename(path), 'tracks', len(d['tracks']), 'vias', len(d['vias']), 'unconnected', n, 'drc errors', errs, flush=True)
blocks.insert(0, '<script type="application/json" id="stages-meta">%s</script>' % json.dumps(meta))
blocks.append('<template id="stack-html">%s</template>' % stack_html(first))
out = tpl.replace('<!--DATA-->', '\n'.join(blocks))
if a.name:
    out = out.replace('<b id="title">KiCad board viewer</b>', '<b id="title">%s</b>' % html.escape(a.name))
open(a.out, 'w').write(out)
print('wrote', a.out, os.path.getsize(a.out) // 1024, 'KB')
