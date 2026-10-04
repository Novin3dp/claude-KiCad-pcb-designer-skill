"""ncroute configuration for the single-board SBC (6 layers: route on L1, L3, L6 (+ L4 hybrid); L2 / L5 GND, L4 power split)."""
import os, re, math
import pcbnew
from shapely.geometry import box, Point

LAYERS = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.B_Cu]      # L1, L3, L4 (hybrid power / slow signals), L6
ALL_CU = LAYERS
ORIGIN = (0.025, 0.025)          # grid lines through the H3 ball-gap mid-lines (H3 centre 33.5 / 17.0, pitch 0.65)
W, H, RC = 85.0, 56.0, 3.0
EDGE = 0.25
VIA = (0.31, 0.15)             # esys level 3: annular ring >= 0.0762 mm (0.30/0.15 gave 0.075)
VIA_COST, B45, B90 = 25.0, 3.0, 15.0
HADD, PGROW, RIPALL_AFTER, PAIR_BONUS = 2.0, 1.2, 0, 0.55
PAIR_OUT = 2.2
PAIR_HARD = True
PAIR_BREAKOUT = 1.2
DEFAULT_CLR = 0.10
CLASS_CLR = {'Default': 0.10, 'DDR': 0.10, 'USB90': 0.12, 'HDMI100': 0.15, 'ETH100': 0.15, 'SDIO': 0.10, 'PWR': 0.12, 'GND': 0.10}
PLANE_NETS = {'GND', 'VCC_3V3', 'VCC_DRAM', 'VDD_CPUX', 'VDD_SYS'}    # VCC_5V is routed (its L4 pour is only a helper)
LANE = re.compile(r'DDR_(DQ\d+|DM\d|DQS\d_[PN])$')


def LANE_OF(s):
    m = re.match(r'DDR_DQ(\d+)$', s)
    if m:
        return int(m.group(1)) // 8
    return int(re.search(r'(\d)', s[4:]).group(1))
ADDR = re.compile(r'DDR_(A\d+|BA\d|RAS_N|CAS_N|WE_N|CS_N|CKE|ODT|RESET_N|CK_[PN])$')


def short(n):
    return n.split('/')[-1].rstrip('&')


def route_net(net, cls):
    s = short(net)
    return s not in PLANE_NETS and s != 'NC' and not net.startswith('unconnected')


def width(net, cls):
    s = short(net)
    if s.endswith('_SW'):
        return 0.50         # short switch-node links (< 5 mm on L1 / L6): 0.5 mm carries the 3-5 A ripple peaks
    if s == 'VIN_PROT':
        return 0.60         # must enter the TPS54560 VIN pin between EN and BOOT (1.27 mm pitch)
    if s in ('VIN_RAW', 'VIN_FUSED', 'VIN_TVS'):
        return 0.80
    if s == 'VCC_5V':
        return 0.50
    if s.startswith('VBUS_') or s in ('USBC_VBUS', 'FAN2_N', 'VCC_5V_HDMI', 'SD_VDD'):
        return 0.30
    if s in ('AVCC', 'VCC_EPHY', 'VDD1V1_EPHY', 'VDD_CPUS', 'AGND'):
        return 0.10         # low-current H3 domain supplies / analog reference (tens of mA): must pass between 0.65 mm balls
    if s in ('VCC_WIFI', 'VCC_1V8', 'GND_CPUX_FB'):
        return 0.25
    if s.endswith('_BST'):
        return 0.20
    if s in RF_NETS:
        return 0.12         # 50 ohm microstrip on L1 over 1080 prepreg (0.0764 mm, Dk 3.91, JLC06161H-1080B) with mask, field-solved (50.7 R)
    return 0.10


RF_NETS = ('WL_RF', 'WL_RF_A', 'WL_RF_B')     # 2.4 GHz antenna feed: top layer only, no vias, over the L2 GND plane


def layer_cost(net):
    """cost per layer [L1, L3, L4, L6]"""
    s = short(net)
    if s in L4_BGA_NETS[:4]:
        return [1.3, 1.3, 1.0, 1.3]
    if s in RF_NETS:
        return [1.0, 999.0, 999.0, 999.0]
    if LANE.match(s):
        return [1.0, 1.0, 1.4, 1.6]
    if ADDR.match(s):
        return [1.2, 1.0, 1.4, 1.2]
    if s.startswith('HDMI_') and s[5:7] in ('D0', 'D1', 'D2', 'CK'):
        return [1.2, 1.0, 999.0, 1.2]
    if partner(net) or s.startswith('X24M') or s.startswith('X32K') or s == 'WL_RF':
        return [1.0, 1.1, 999.0, 1.15]
    if s.endswith('_SW') or s.endswith('_BST'):
        return [1.0, 999.0, 999.0, 1.0]
    if s in ('VIN_RAW', 'VIN_FUSED', 'VIN_PROT', 'VCC_5V'):
        return [1.0, 999.0, 999.0, 1.0]
    return [1.0, 1.1, 1.5, 1.05]


def partner(net):
    s = short(net)
    if os.environ.get('NOPAIR') and re.search(os.environ['NOPAIR'], s):
        return None
    m = re.match(r'(.*_(?:DQS\d|CK))_([PN])$', s) or re.match(r'(HDMI_(?:D\d|CK))_([PN])$', s)
    if m:
        return m.group(1) + '_' + ('N' if m.group(2) == 'P' else 'P')
    m = re.match(r'(USB[0-9]A?|USBC)_D([PM])$', s)
    if m:
        return m.group(1) + '_D' + ('M' if m.group(2) == 'P' else 'P')
    # EPHY TX/RX (100BASE-TX): routed as two independent 50 ohm single-ended traces (2 x Z0 = 100 ohm differential);
    # the ETH100 class has no DRU pair rules and the H3 south-east corner (A3/B3/A4/B4) has no room for coupled breakouts.
    # Length match is checked after routing.
    return None


def pair_gap(net):
    s = short(net)
    if s.startswith('USB'):
        return 0.16
    if s.startswith('DDR'):
        return 0.12
    return 0.21


def order_key(o):
    s = short(o['name'])
    pri = 0 if LANE.match(s) else 1 if ADDR.match(s) else 2 if o['partner'] else 3
    return (pri, -len(o['terms']), s)


def board_poly():
    B = box(0, 0, W, H)
    for cx, cy in ((RC, RC), (W - RC, RC), (RC, H - RC), (W - RC, H - RC)):
        q = box(cx - RC if cx < W / 2 else cx, cy - RC if cy < H / 2 else cy, cx if cx < W / 2 else cx + RC, cy if cy < H / 2 else cy + RC)
        B = B.difference(q.difference(Point(cx, cy).buffer(RC, 32)))
    return B


def via_keepouts(b):
    """core-rail necks on L4 (VDD_CPUX / VDD_SYS / VCC_DRAM pours where they leave the H3 ball field): no router vias,
    a via hole there would cut the narrow neck.  Taken from the actual L4 zones, so it follows any H3 orientation."""
    MM = 1e6
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    u1 = b.FindFootprintByReference('U1')
    xs = [p.GetPosition().x / MM for p in u1.Pads()]; ys = [p.GetPosition().y / MM for p in u1.Pads()]
    reach = box(min(xs) - 1.9, min(ys) - 1.9, max(xs) + 1.9, max(ys) + 1.9)     # necks incl. their 1.6 mm wide exits
    out = []
    for z in b.Zones():
        if z.GetIsRuleArea() or z.GetLayer() != pcbnew.In3_Cu or z.GetNetname() not in ('VDD_CPUX', 'VDD_SYS', 'VCC_DRAM'):
            continue
        o_ = z.Outline()
        for i in range(o_.OutlineCount()):
            ol = o_.Outline(i)
            g = Polygon([(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())]).buffer(0)
            g = g.intersection(reach)
            if not g.is_empty:
                out.append(g.buffer(0.15))
    return out


def max_len(net, straight, o):
    """routed-length bound in mm for one tree branch (0 = unbounded)"""
    s = short(net)
    if net.endswith('&'):
        return 0.0                         # coupled centre line: bounded by the lane tuning afterwards
    if LANE.match(s):
        return straight * 1.2 + 4.0
    if ADDR.match(s):
        return straight * 1.25 + 6.0
    return 0.0


def via_cost(net):
    s = short(net)
    return 60.0 if LANE.match(s) else 40.0 if ADDR.match(s) else VIA_COST


def relax_areas(b):
    """BGA escape rule areas (.kicad_dru: clearance 0.10 inside BGA_U1 / BGA_U7): class extra clearance waived"""
    MM = 1e6
    out = []
    for ref in ('U1', 'U7'):
        f = b.FindFootprintByReference(ref)
        cy = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
        out.append(box(cy.GetLeft() / MM - 0.8, cy.GetTop() / MM - 0.8, cy.GetRight() / MM + 0.8, cy.GetBottom() / MM + 0.8))
    return out


def track_keepouts(b):
    """L4 (index 2): no tracks inside the core-rail pours (VDD_CPUX / VDD_SYS / VCC_DRAM / VCC_5V) or under the BGAs,
    so signals only take VCC_3V3 area outside the H3 / DDR footprints"""
    MM = 1e6
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    zone_polys = []      # real power/gnd pour FILL shape (post rule-area keepouts), buffered for clearance - NEVER carved into
    for z in b.Zones():
        if z.GetIsRuleArea() or z.GetLayer() != pcbnew.In3_Cu or z.GetNetname() == 'VCC_3V3':
            continue
        pset = z.GetFilledPolysList(pcbnew.In3_Cu)
        for i in range(pset.OutlineCount()):
            ol = pset.Outline(i)
            pts = [(ol.CPoint(k).x / MM, ol.CPoint(k).y / MM) for k in range(ol.PointCount())]
            holes = [[(pset.Hole(i, h).CPoint(k).x / MM, pset.Hole(i, h).CPoint(k).y / MM) for k in range(pset.Hole(i, h).PointCount())]
                     for h in range(pset.HoleCount(i))]
            zone_polys.append(Polygon(pts, holes).buffer(0.15))   # 0.15mm >= PWR clearance (0.12) and hole_clearance (0.15)
    zone_poly = unary_union(zone_polys)
    courtyard_polys = []  # blanket "no L4 track under the whole BGA" reach - safe to carve a verified escape into
    for ref in ('U1', 'U7'):
        f = b.FindFootprintByReference(ref)
        cy = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
        courtyard_polys.append(box(cy.GetLeft() / MM - 0.3, cy.GetTop() / MM - 0.3, cy.GetRight() / MM + 0.3, cy.GetBottom() / MM + 0.3))
    courtyard_poly = unary_union(courtyard_polys)
    poly = unary_union([zone_poly, courtyard_poly])
    global L4_ZONE_ONLY
    L4_ZONE_ONLY = zone_poly         # real core-rail pours only (no BGA blanket): used for L4_BGA_NETS
    return [(2, poly)]


# DC nets that may run on L4 under the H3 inside the VCC_3V3 fill (never through the VDD_CPUX / VDD_SYS / VCC_DRAM /
# VCC_5V islands): they only cut a thin slot in the 3.3 V pour and free the BGA escape channels on the signal layers
# DC nets that may run on L4 under the H3 inside the VCC_3V3 fill (never through the VDD_CPUX / VDD_SYS / VCC_DRAM /
# VCC_5V islands): they only cut a thin slot in the 3.3 V pour and free the BGA escape channels on the signal layers.
# The 3.3 V web pieces they cut off are re-joined afterwards (plane_check.py + the final VCC_3V3 bridging pass).
L4_BGA_NETS = ('AVCC', 'VCC_EPHY', 'VDD1V1_EPHY', 'RTC_VIO',
               'GPIO2_SDA', 'GPIO3_SCL', 'GPIO4_TX2', 'GPIO5_RX2', 'GPIO6', 'GPIO7_CE1', 'GPIO8_CE0', 'GPIO12', 'GPIO13_PWM1',
               'GPIO14_TXD0', 'GPIO15_RXD0', 'GPIO16_TX1', 'GPIO17_RX1', 'GPIO18_SPI1_CS', 'GPIO22', 'GPIO23', 'GPIO24',
               'GPIO25', 'GPIO26', 'GPIO27', 'ID_SC', 'ID_SD', 'KEY_USER', 'KEYADC', 'LED_ACT_N', 'LED_PWR_N', 'FEL_N',
               'CPUX_VSEL', 'RUN_PG', 'PWR_STB', 'PWR_DRAM', 'NMI_N', 'SD_DET', 'USB0_ID', 'WL_PMU_EN', 'WL_WAKE_HOST',
               'HDMI_CEC', 'HHPD', 'EPHY_LINK_LED', 'EPHY_SPD_LED')
L4_ZONE_ONLY = None


def track_keepouts_l4open(b):
    if L4_ZONE_ONLY is None:
        track_keepouts(b)
    return [(2, L4_ZONE_ONLY)]


def PAIR_FAT(net):
    s = short(net)
    if s.startswith('DDR_'):
        return False   # DDR pairs escape BGA to BGA through a dense channel: routed as coupled singles
    if s.startswith('USB2_'):
        return False   # USB2 breakout point is too tight for a fat centre-line: routed as coupled singles
    if s.startswith(('HDMI_CK', 'HDMI_D1')):
        return False   # H3 east-edge breakout (balls F2/G2, E2/E3) has no room for a fat centre line: coupled singles
    return True         # HDMI, USB0/1/3, Ethernet: one coupled centre line
FAT_R = 4.0


# the 0.05 mm grid (ORIGIN) sits on the H3 ball-gap mid-lines: inside the H3 courtyard a trace between two adjacent
# balls is exact (0.35 mm gap, 0.10 mm trace -> 0.125 mm each side vs the 0.10 mm BGA rule), so the rasterisation
# margin can drop there; with the global 0.045 mm margin no orthogonal channel between two balls was ever usable.
EPS_BGA = 0.015          # grid 0.0325 is exact on both BGA line families; simplify tolerance 0.011


def eps_bga_areas(b):
    MM = 1e6
    f = b.FindFootprintByReference('U1')
    cy = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
    return [box(cy.GetLeft() / MM, cy.GetTop() / MM, cy.GetRight() / MM, cy.GetBottom() / MM)]

BGA_RULE_AREAS = ('BGA_U1',)      # rule-area names matching the .kicad_dru 'BGA escape H3' rule (clearance 0.10 mm)
BGA_RULE_CLR = 0.10
