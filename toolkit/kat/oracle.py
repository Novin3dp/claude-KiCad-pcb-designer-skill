#!/usr/bin/env python3
"""KiCad as the connectivity oracle. Runs a staged DRC copy with non-connectivity rules ignored.

Usage:
  oracle.py BOARD.kicad_pcb
  oracle.py BOARD.kicad_pcb --json OUT
  oracle.py BOARD.kicad_pcb --netrx [--skip GND,+3V3]
Library: links(board) -> [(net, endpoint_a, endpoint_b)]; per_net(board) -> {net: open_link_count}.
"""
import json, os, re, shutil, subprocess, sys, tempfile, collections
IGNORE = ["clearance", "creepage", "hole_clearance", "edge_clearance", "hole_near_hole", "hole_to_hole",
"track_width", "annular_width", "drill_out_of_range", "via_diameter", "padstack", "microvia_drill_out_of_range",
"courtyards_overlap", "malformed_courtyard", "pth_inside_courtyard", "npth_inside_courtyard", "item_on_disabled_layer",
"invalid_outline", "duplicate_footprints", "missing_footprint", "net_conflict", "unresolved_variable",
"assertion_failure", "via_dangling", "track_dangling", "copper_sliver", "silk_over_copper", "silk_overlap",
"silk_edge_clearance", "text_height", "text_thickness", "length_out_of_range", "skew_out_of_range",
"via_count_exceeded", "diff_pair_gap_out_of_range", "diff_pair_uncoupled_length_too_long", "footprint_type_mismatch",
"through_hole_pad_without_hole", "extra_footprint", "solder_mask_bridge", "silk_mask_clearance", "starved_thermal",
"connection_width", "zone_has_empty_net", "lib_footprint_issues", "lib_footprint_mismatch", "footprint",
"holes_co_located", "items_not_allowed", "shorting_items", "isolated_copper", "footprint_symbol_mismatch",
"text_on_edge_cuts", "nonmirrored_text_on_back_layer"]
NET_RE = re.compile(r'\[(.*)\]')
LAYER_RE = re.compile(r'\bon ([A-Za-z0-9_.]+\.Cu)\b(?!\s*-)')
def kicad_cli():
    for c in (os.environ.get('KICAD_CLI'), shutil.which('kicad-cli'), r'C:\\Program Files\\KiCad\\10.0\\bin\\kicad-cli.exe'):
        if c and os.path.exists(c): return c
    raise SystemExit('kicad-cli not found (set KICAD_CLI)')
def _stage(board):
    pro = os.path.splitext(board)[0] + '.kicad_pro'
    proj = json.load(open(pro, encoding='utf-8')) if os.path.exists(pro) else {}
    ds = proj.setdefault('board', {}).setdefault('design_settings', {})
    sev = dict(ds.get('rule_severities', {}))
    for k in IGNORE: sev[k] = 'ignore'
    sev['unconnected_items'] = 'error'; ds['rule_severities'] = sev
    proj.setdefault('meta', {'filename':'oracle.kicad_pro','version':1})
    tmp = tempfile.mkdtemp(prefix='kat_oracle_'); stem = os.path.splitext(os.path.basename(board))[0]
    shutil.copyfile(board, os.path.join(tmp, stem + '.kicad_pcb'))
    json.dump(proj, open(os.path.join(tmp, stem + '.kicad_pro'), 'w', encoding='utf-8'), indent=1)
    dru = os.path.splitext(board)[0] + '.kicad_dru'
    if os.path.isfile(dru): shutil.copyfile(dru, os.path.join(tmp, stem + '.kicad_dru'))
    return os.path.join(tmp, stem + '.kicad_pcb'), tmp
def _item(it):
    d=it.get('description',''); p=it.get('pos') or {}; m=NET_RE.search(d)
    if not m or 'x' not in p: return None
    lm=None if ' - ' in d else LAYER_RE.search(d)
    kind='zone' if d.startswith('Zone') else 'via' if d.startswith('Via') else 'pad' if 'pad' in d.lower().split('[')[0] else 'track'
    return m.group(1), float(p['x']), float(p['y']), (lm.group(1) if lm else None), kind
def links(board, timeout=300):
    staged,tmp=_stage(board); out=os.path.join(tmp,'drc.json')
    try:
        subprocess.run([kicad_cli(),'pcb','drc',staged,'--format','json','-o',out,'--severity-all','--refill-zones'],
                       capture_output=True,text=True,timeout=timeout)
        data=json.load(open(out))
    finally: shutil.rmtree(tmp,ignore_errors=True)
    res=[]
    for u in data.get('unconnected_items',[]):
        its=u.get('items',[])
        if len(its)<2: continue
        a,b=_item(its[0]),_item(its[1])
        if a and b and a[0]==b[0]: res.append((a[0],a[1:],b[1:]))
    return res
def per_net(board): return collections.Counter(n for n,_,_ in links(board))
if __name__=='__main__':
    bd=sys.argv[1]; L=links(bd)
    if '--json' in sys.argv:
        json.dump([{'net':n,'a':a,'b':b} for n,a,b in L],open(sys.argv[sys.argv.index('--json')+1],'w'),indent=1)
    if '--netrx' in sys.argv:
        skip=set(sys.argv[sys.argv.index('--skip')+1].split(',')) if '--skip' in sys.argv else set()
        nets=sorted({n for n,_,_ in L if n.split('/')[-1] not in skip})
        print('^('+'|'.join(re.escape(n) for n in nets)+')$')
    else:
        c=collections.Counter(n for n,_,_ in L); print('open links %d in %d nets'%(len(L),len(c)))
        for n,k in c.most_common(): print('  %4d  %s'%(k,n))
