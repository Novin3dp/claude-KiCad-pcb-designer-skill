"""Wrap a board config and append one last-resort routing layer without changing existing layer indices."""
import os, sys, importlib.util
import pcbnew
_p = os.path.abspath(os.environ['BASE_CFG'])
sys.path.insert(0, os.path.dirname(_p))
_spec = importlib.util.spec_from_file_location('_base_cfg', _p)
BASE = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(BASE)
for _k in dir(BASE):
    if not _k.startswith('__'): globals()[_k] = getattr(BASE, _k)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import esc_layer as ESC
_NAMES = {'F.Cu': pcbnew.F_Cu, 'B.Cu': pcbnew.B_Cu, 'In1.Cu': pcbnew.In1_Cu, 'In2.Cu': pcbnew.In2_Cu,
          'In3.Cu': getattr(pcbnew, 'In3_Cu', None), 'In4.Cu': getattr(pcbnew, 'In4_Cu', None)}
ESC_ID = _NAMES[ESC.ESC_LAYER]; REF_ID = _NAMES[ESC.ESC_REF]
assert ESC_ID not in BASE.LAYERS, 'escalation layer already routed by the base config'
LAYERS = list(BASE.LAYERS) + [ESC_ID]; ESC_IDX = len(LAYERS)-1
REF_IDX = list(BASE.LAYERS).index(REF_ID)
ALL_CU = list(BASE.ALL_CU) if ESC_ID in BASE.ALL_CU else list(BASE.ALL_CU)+[ESC_ID]
PLANE_NETS = set(getattr(BASE, 'PLANE_NETS', set()))
def layer_cost(net):
    c=list(BASE.layer_cost(net))
    return c+[999.0 if ESC.denied(net) else ESC.ESC_COST*min(c)]
def track_keepouts(b):
    base=list(BASE.track_keepouts(b)) if hasattr(BASE,'track_keepouts') else []
    extra=[(ESC_IDX,g) for li,g in base if li==REF_IDX] if ESC.ESC_INHERIT else []
    sh=ESC.shield_polys(b)
    print('escalation layer %s: cost x%.1f, %d shield / inherited keep-out polygons'%(ESC.ESC_LAYER,ESC.ESC_COST,len(sh)),flush=True)
    return base+extra+[(ESC_IDX,g) for g in sh]
_NOI=set(ESC.ESC_NO_INHERIT); _CORR=getattr(BASE,'CORRIDOR',None)
def net_keepouts(net):
    base=list(BASE.net_keepouts(net)) if hasattr(BASE,'net_keepouts') else []
    if not ESC.ESC_INHERIT: return base
    inh=[(ESC_IDX,g) for li,g in base if li==REF_IDX]
    if _NOI and _CORR is not None and any('CORRIDOR' in n.upper() for n in _NOI):
        inh=[(li,g) for li,g in inh if not g.equals(_CORR)]
    return base+inh
def layer_block(net):
    lb=list(BASE.layer_block(net)) if hasattr(BASE,'layer_block') else []
    if ESC.denied(net): lb.append(ESC_IDX)
    return lb
