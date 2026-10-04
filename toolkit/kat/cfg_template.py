"""ncroute board configuration - TEMPLATE.  Copy to cfg_<board>.py next to your board and edit.

Every name below is read by ncroute.py.  Units are mm.  Net names arrive as KiCad full names ('/Sheet/NET' or 'NET');
use short() to compare.  A real 6-layer example with DDR3 / HDMI / USB rules is examples/h3_sbc/cfg_sbc.py.
"""
import os, re, sys
import pcbnew
from shapely.geometry import box, Point, Polygon

# ---------------------------------------------------------------- layers and grid
# routing layers in cost-list order (layer_cost() returns one value per entry)
LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]            # 4-layer with signal inner: [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
ALL_CU = LAYERS                                 # layers a through via must clear (add plane layers if they are routed)
RES = 0.05                                      # grid pitch; 0.025 for 0.4-0.5 mm pitch escapes (4x memory / time)
ORIGIN = (0.025, 0.025)                         # grid offset from the board's top-left; align it with BGA ball gaps
EDGE = 0.30                                     # copper-to-edge clearance

# ---------------------------------------------------------------- vias and costs
VIA = (0.40, 0.20)                              # (diameter, drill) of router vias
VIA_COST, B45, B90 = 25.0, 3.0, 15.0            # via cost, 45 deg bend cost, 90 deg bend cost (in grid steps)
HADD, PGROW, RIPALL_AFTER, PAIR_BONUS = 2.0, 1.2, 0, 0.55   # history add, present-cost growth, rip-all iteration, pair bonus
PAIR_OUT = 2.2                                  # mm a pair may run uncoupled out of its pads
PAIR_HARD = True                                # keep P/N exactly one pitch apart where coupled
PAIR_BREAKOUT = 1.2

# ---------------------------------------------------------------- clearances (match your .kicad_dru / net classes)
DEFAULT_CLR = 0.15
CLASS_CLR = {'Default': 0.15, 'PWR': 0.20}
PLANE_NETS = {'GND'}                            # nets served by zones: not routed (plane_via.py connects their pads)


def short(n):
    return n.split('/')[-1].rstrip('&')


def route_net(net, cls):
    """True = this net is routed"""
    s = short(net)
    return s not in PLANE_NETS and not net.startswith('unconnected') and s != 'NC'


def width(net, cls):
    s = short(net)
    if cls == 'PWR' or s.startswith(('VCC', 'VIN', '+')):
        return 0.40
    return 0.20


def layer_cost(net):
    """multiplier per entry of LAYERS (999 = forbidden)"""
    return [1.0] * len(LAYERS)


def partner(net):
    """the other net of a differential pair, or None.  Example: USB_DP <-> USB_DM, X_P <-> X_N"""
    s = short(net)
    m = re.match(r'(.*_D)([PM])$', s)
    if m:
        return m.group(1) + ('M' if m.group(2) == 'P' else 'P')
    m = re.match(r'(.*)_([PN])$', s)
    if m:
        return m.group(1) + '_' + ('N' if m.group(2) == 'P' else 'P')
    return None


def pair_gap(net):
    """edge-to-edge gap of a coupled pair (from your impedance calculation)"""
    return 0.15


def PAIR_FAT(net):
    """True = route the pair as one 'fat' centre line split into P/N afterwards (fails in tight breakouts)"""
    return True


FAT_R = 4.0


def order_key(o):
    """routing order: pairs first, then nets with many terminals"""
    return (0 if o['partner'] else 1, -len(o['terms']), short(o['name']))


def max_len(net, straight, o):
    """length bound for one tree branch (0 = unbounded), e.g. straight * 1.2 + 4 for memory nets"""
    return 0.0


def via_cost(net):
    return VIA_COST


# ---------------------------------------------------------------- geometry
def board_poly():
    """routable area = the Edge.Cuts outline of the board being routed (ncroute argv[2])"""
    b = pcbnew.LoadBoard(sys.argv[2])
    ps = pcbnew.SHAPE_POLY_SET()
    try:
        b.GetBoardPolygonOutlines(ps, True)       # KiCad 10
    except TypeError:
        b.GetBoardPolygonOutlines(ps)             # KiCad 8 / 9
    o = ps.Outline(0)
    return Polygon([(o.CPoint(k).x / 1e6, o.CPoint(k).y / 1e6) for k in range(o.PointCount())]).buffer(0)


def via_keepouts(b):
    """list of shapely polygons where the router must not drop vias (e.g. plane necks, under fine-pitch parts)"""
    return []


def track_keepouts(b):
    """list of (index into LAYERS, polygon) where no track may run on that layer"""
    return []


def relax_areas(b):
    """polygons where the net-class extra clearance is waived (BGA escape areas with their own DRU rule)"""
    return []


EPS_BGA = 0.015


def eps_bga_areas(b):
    """polygons where a finer rasterisation margin is used (inside BGA courtyards, grid aligned with the balls)"""
    return []


BGA_RULE_AREAS = ()          # names of rule areas in the board that a .kicad_dru BGA rule refers to
BGA_RULE_CLR = 0.10
