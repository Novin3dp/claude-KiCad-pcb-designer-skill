#!/usr/bin/env python3
"""Escalation-layer helpers: a plane layer signals may use only as a last resort after normal routing layers fail.

The helper shields high-speed copper on the reference layer, inherits named rule areas, provides deny patterns,
and reports track length, high-speed copper crossing cuts, bus runs along cuts, and plane fill pieces.
"""
import os, re, sys, json, collections
import pcbnew
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
MM=1e6
ESC_LAYER=os.environ.get('ESC_LAYER','In1.Cu'); ESC_REF=os.environ.get('ESC_REF','F.Cu')
ESC_COST=float(os.environ.get('ESC_COST',6)); ESC_SHIELD_MM=float(os.environ.get('ESC_SHIELD_MM',0.5))
ESC_PAR_MM=float(os.environ.get('ESC_PAR_MM',2.0))
ESC_SHIELD=re.compile(os.environ.get('ESC_SHIELD',r'^([AB]_(D[0-3]|CLK)_[PN]|USB_C?D[PM]|.*CLK.*|.*_PCLK|OSC.*|SSD[AB]_X.*)$'))
ESC_BUS=re.compile(os.environ.get('ESC_BUS',r'^(SSD_[AB]_|SDRAM_|FSMC_)'))
ESC_INHERIT=os.environ.get('ESC_INHERIT','1')=='1'
ESC_NO_INHERIT=[x for x in os.environ.get('ESC_NO_INHERIT','').split(',') if x]
ESC_DENY=re.compile(os.environ.get('ESC_DENY',r'^([AB]_(D[0-3]|CLK)_[PN]|USB_.*|\+.*|GND.*|VIN.*|VBUS|.*_SW|MOT_.*|.*CLK.*|OSC.*|PNL_V.*|BIAS_.*)$'))
def short(n): return n.split('/')[-1]
def _seg(t): return LineString([(t.GetStart().x/MM,t.GetStart().y/MM),(t.GetEnd().x/MM,t.GetEnd().y/MM)])
def _zone_polys(z):
    o=z.Outline(); out=[]
    for i in range(o.OutlineCount()):
        ol=o.Outline(i); out.append(Polygon([(ol.CPoint(k).x/MM,ol.CPoint(k).y/MM) for k in range(ol.PointCount())]).buffer(0))
    return out
def shield_polys(b):
    ref=b.GetLayerID(ESC_REF); out=[]
    for t in b.GetTracks():
        if t.GetClass()=='PCB_VIA' or t.GetLayer()!=ref: continue
        if ESC_SHIELD.match(short(t.GetNetname())): out.append(_seg(t).buffer(t.GetWidth()/MM/2+ESC_SHIELD_MM))
    for z in [z for f in b.GetFootprints() for z in f.Zones()]+list(b.Zones()):
        if ESC_INHERIT and z.GetIsRuleArea() and z.GetZoneName() and z.GetLayerSet().Contains(ref) and z.GetZoneName() not in ESC_NO_INHERIT:
            out += _zone_polys(z)
    return out
def dru_areas(b,board_path):
    out=[]; dru=os.path.splitext(board_path)[0]+'.kicad_dru'
    if not os.path.exists(dru): return out
    named={}
    for z in [z for f in b.GetFootprints() for z in f.Zones()]+list(b.Zones()):
        if z.GetIsRuleArea() and z.GetZoneName(): named.setdefault(z.GetZoneName(),[]).extend(_zone_polys(z))
    chunks=re.split(r'\(rule\s+',open(dru).read())[1:]
    for body in chunks:
        if '(constraint disallow' not in body: continue
        m=re.search(r"intersectsArea\('([^']+)'\)",body)
        if not m or m.group(1) not in named: continue
        lm=re.search(r'\(layer\s+"([^"]+)"\)',body); lays={b.GetLayerID(lm.group(1))} if lm else None
        allow=re.findall(r"A\.NetName == '([^']+)'",body); kinds={'track','via'}
        tm=re.search(r"A\.Type == '(\w+)'",body)
        if tm: kinds={tm.group(1).lower()}
        for g in named[m.group(1)]: out.append((g,lays,allow,kinds))
    return out
def area_ok(areas,net,geom,layer=None,kind=None):
    import fnmatch
    if kind is None: kind='via' if layer is None else 'track'
    for g,lays,allow,kinds in areas:
        if kind not in kinds or (layer is not None and lays is not None and layer not in lays): continue
        if g.intersects(geom) and not any(fnmatch.fnmatch(net,x) or fnmatch.fnmatch(short(net),x) for x in allow): return False
    return True
def denied(net): return bool(ESC_DENY.match(short(net)))
def report(path,quiet=False):
    b=pcbnew.LoadBoard(path); pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    esc,ref=b.GetLayerID(ESC_LAYER),b.GetLayerID(ESC_REF); lens=collections.Counter(); cuts=[]; reft=collections.defaultdict(list)
    for t in b.GetTracks():
        if t.GetClass()=='PCB_VIA': continue
        if t.GetLayer()==esc:
            g=_seg(t); lens[short(t.GetNetname())]+=g.length; cuts.append(g.buffer(t.GetWidth()/MM/2+0.2))
        elif t.GetLayer()==ref: reft[short(t.GetNetname())].append(_seg(t))
    cut=unary_union(cuts) if cuts else None; over_shield={}; par={}
    if cut is not None:
        for n,gs in reft.items():
            L=sum(g.intersection(cut).length for g in gs)
            if L<=0.05: continue
            if ESC_SHIELD.match(n): over_shield[n]=round(L,2)
            elif ESC_BUS.match(n) and L>ESC_PAR_MM: par[n]=round(L,2)
    pieces={}
    for z in b.Zones():
        if z.GetIsRuleArea() or not z.GetLayerSet().Contains(esc): continue
        ps=z.GetFilledPolysList(esc); pieces[z.GetNetname()]=pieces.get(z.GetNetname(),0)+ps.OutlineCount()
    rep={'layer':ESC_LAYER,'track_mm':{k:round(v,1) for k,v in sorted(lens.items())},'total_mm':round(sum(lens.values()),1),
         'shield_violations_mm':over_shield,'bus_parallel_over_cut_mm':par,'plane_fill_pieces':pieces}
    if not quiet:
        print('%s: %.1f mm of signal track %s'%(ESC_LAYER,rep['total_mm'],rep['track_mm']))
        print('  high-speed copper over a cut (must be none):',over_shield or 'none')
        print('  bus runs along a cut > %.1f mm (review):'%ESC_PAR_MM,par or 'none')
        print('  plane fill pieces on %s:'%ESC_LAYER,pieces)
    return rep
if __name__=='__main__':
    if len(sys.argv)>=3 and sys.argv[1]=='report':
        r=report(sys.argv[2])
        if len(sys.argv)>3: json.dump(r,open(sys.argv[3],'w'),indent=1)
    else: print(__doc__)
