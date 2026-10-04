#!/usr/bin/env python3
"""SBC - single-board Klipper host: Allwinner H3 + 512 MB DDR3 + carrier I/O on ONE 85 x 56 mm 6-layer board.

Assembled from the two proven generators (build_cn1.py = SoC/DDR/power/WiFi, build_mizban.py = 12-24 V input, USB, HDMI, RJ45,
microSD, header): the CM4 connector pair is dropped (nets are identical on both sides, so they simply join), and the signals
that never reached a connector (VCC_1V8 LDO, KEYADC, LINEOUT_L/R, TV_OUT) are removed.
Hole pattern: Raspberry Pi 58 x 49 mm.  CN1 blocks keep 0402 passives (BGA decoupling), carrier blocks use 0603.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import *            # noqa
from symbols import all_custom, H3, DDR3_NC, sy6280_symbol
import cm4

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'sbc', 'kicad')
cn1 = open(os.path.join(HERE, 'build_cn1.py')).read().split('\n')
miz = open(os.path.join(HERE, 'build_mizban.py')).read().split('\n')


def find(lines, key, start=0):
    for i in range(start, len(lines)):
        if lines[i].startswith(key):
            return i
    raise KeyError(key)


def cut(lines, a, b):   # a/b: line-start keys, [a, b)
    ia = find(lines, a)
    ib = find(lines, b, ia + 1) if b else len(lines)
    return '\n'.join(lines[ia:ib])


CU = all_custom()
CU['SY6280AAC'] = sy6280_symbol()
cx = Ctx('klipper_h3_sbc', rfp='R0402', cfp='C0402')
PRJ, LB = cx.PRJ, cx.lib
PRJ.refcount['U'] = 1   # U1 = Allwinner H3
R, C, CAPS, L, FBEAD = cx.R, cx.C, cx.CAPS, cx.L, cx.FBEAD
nc = 'NC'
g = globals()
# ---- library parts (union of both generators)
for src in (cn1, miz):
    for ln in src:
        if ln.startswith(('NFET_ =', 'COAX_ =', 'TPS563201_ =', 'TPS562201_ =', 'TPS3808_ =', 'L4018 =', 'L3015 =')) or \
           (ln.startswith(('TVS_', 'SCH1A_', 'ZEN_', 'PFET_', 'NFET2_', 'TERM_', 'HDR40_', 'HDR3_', 'HDR2_', 'SW_', 'SLIDE_', 'USBLC_',
                           'TPS54560_', 'TPD4E_', 'RJ45_', 'HDMI_', 'USBAS_', 'USBC_', 'MUX_', 'SD_')) and 'load_lib' in ln):
            exec(ln, g)
exec(cut(cn1, 'def H3U', '# ====') , g)
SD_ = load_lib('Connector', 'Micro_SD_Card_Det2')      # v5: DM3AT has a 2-contact detect switch (9 / 10)
TVSU_ = load_lib('Diode', 'SMAJ26A')                    # v5: unidirectional input TVS


def run(code, rfp, cfp):
    cx.rfp, cx.cfp = rfp, cfp
    exec(code, g)


# ================= CN1 blocks (0402) =================
p = cut(cn1, "sh = PRJ.add_sheet(Sheet('Power'", '# =============================================================== 3.')
a = p.index("fl.section('VCC_1V8"); b = p.index("fl.section('FILTERED SUB-RAILS'")
p = p[:a] + p[b:]
p = p.replace(", TLV755 1.8 V)", ")")
# v5 review: 3.3 V set to 3.26 V (worst case stays under the 3.4 V AVCC limit); CPUX feedback has a fitted 10R local
# fallback so an open T10 ball can no longer run the core rail away
p = p.replace("'V3', 'VCC_3V3', '33.2k 1%'", "'V3', 'VCC_3V3', '32.4k 1%'")
p = p.replace("R(fl, '0R DNP', 'VDD_CPUX', 'VDD_CPUX_FB', dnp=True)", "R(fl, '10R', 'VDD_CPUX', 'VDD_CPUX_FB')")
p = p.replace("FB top from ball VDD-CPUFB (remote sense).  DNP 0R = local sense.", "FB top from ball VDD-CPUFB (remote sense); 10R to the local rail = fallback if the ball is open.")
p = p.replace("0.768 V x (1 + 33.2k/10k) = 3.32 V", "0.768 V x (1 + 32.4k/10k) = 3.26 V")
run(p, 'R0402', 'C0402')
s = cut(cn1, "sh = PRJ.add_sheet(Sheet('SoC GPIO", '# =============================================================== 4.')
s = s.replace(", 'KEYADC': 'KEYADC'})", ", 'KEYADC': nc})")
s = s.replace("'LINEOUTL': 'LINEOUT_L', 'LINEOUTR': 'LINEOUT_R'", "'LINEOUTL': nc, 'LINEOUTR': nc").replace("'TVOUT': 'TV_OUT'", "'TVOUT': nc")
s = s.replace("R(fl, '100k', 'AVCC', 'KEYADC')\n", "")
run(s, 'R0402', 'C0402')
d = cut(cn1, "sh = PRJ.add_sheet(Sheet('SoC Power", "fl.section('MOUNTING")
# v2: the CPU feedback-ground ball goes straight to GND (the 0R R27 under the BGA had no escape left); R27 consumed
d = d.replace("'GND_CPUXFB': 'GND_CPUX_FB'", "'GND_CPUXFB': 'GND'").replace("R(fl, '0R', 'GND_CPUX_FB', 'GND')", "cx.ref('R')")
# v5 review (Allwinner / Orange Pi PC, One, PC Plus references): VDD_CPUS is fed by the internal RTC LDO (RTC_VIO, 4.7 uF),
# VDD_EFUSEBP gets only a 4.7 uF cap to GND (not 3.3 V).  The extra cap takes the free reference C132.
d = d.replace("'VDD_CPUS': 'VDD_SYS',", "'VDD_CPUS': 'RTC_VIO',").replace("'VDD_EFUSEBP': 'VCC_3V3'", "'VDD_EFUSEBP': 'EFUSE_BP'")
d = d.replace("'VDD_CPUS (J7/J8) runs from the 1.1 V VDD_SYS rail (as on the Orange Pi PC / NanoPi NEO references); RTC_VIO (M4) is the internal RTC LDO output: decoupling cap only.",
              "'VDD_CPUS (J7/J8) is fed by RTC_VIO (M4, internal RTC LDO) with 4.7 uF, as on the Orange Pi PC / One references.  VDD_EFUSEBP (H11): 4.7 uF to GND only.")
d = d.replace("CAPS(fl, 'RTC_VIO', [('1uF', None, 1)])", "CAPS(fl, 'RTC_VIO', [('4.7uF', None, 1)])\nfl.add(LB.C, 'C132', '4.7uF', {'1': 'EFUSE_BP', '2': 'GND'}, rot=90, footprint=FP['C0402'])\ncx.flag(fl, 'EFUSE_BP')")
assert "'RTC_VIO'," in d and 'C132' in d and 'EFUSE_BP' in d
run(d, 'R0402', 'C0402')
# ================= carrier blocks (0603) =================
m = cut(miz, "sh = PRJ.add_sheet(Sheet('Power Input", "PRJ.root_texts")
CONN4_ = load_lib('Connector_Generic', 'Conn_01x04')
PFET3_ = load_lib('Transistor_FET', 'AO3401A')
TP_ = load_lib('Connector', 'TestPoint')


def sub(m, a, b, once=True):
    """replace a code fragment of the Mizban generator; fail loudly if it is not there"""
    if a not in m:
        raise KeyError(a[:80])
    return m.replace(a, b, 1 if once else -1)


def between(m, a, b):
    i = m.index(a); j = m.index(b, i)
    return m[i:j]


# ---------------- v2 (2026-10-03): XH input, MP1584 module, USB-C power-only, no FAN2 / debug header, HDMI Type A
# every removed part still CONSUMES its reference so that all other references stay identical to v1 (the routed board
# is updated by ECO, not rebuilt).
m = sub(m, "fl.add(TERM_, cx.ref('J'), '12-24V IN', {'1': 'VIN_RAW', '2': 'GND'},\n       footprint='TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal')",
        "fl.add(TERM_, cx.ref('J'), '12-24V IN (XH)', {'1': 'VIN_RAW', '2': 'GND'},\n       footprint='Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical', fields={'MPN': 'JST B2B-XH-A (2.5 mm, 3 A/pin)'})")
m = sub(m, "'Screw terminal (printer PSU).", "'JST XH 2-pin (printer PSU, <= 3 A).")
m = sub(m, "fl.add(LB.FUSE, cx.ref('F'), '5A slow'", "fl.add(LB.FUSE, cx.ref('F'), '3A slow'")
m = sub(m, "fl.add(TVS_, cx.ref('D'), 'SMAJ30CA', {'1': 'VIN_PROT', '2': 'GND'}", "fl.add(TVS_, cx.ref('D'), 'SMAJ26CA', {'1': 'VIN_PROT', '2': 'GND'}")
m = sub(m, "-> 30 V TVS.\\n'\n           '9 V UVLO start (EN divider).  Everything rated >= 50 V except the TVS (30 V standoff).'",
        "-> 26 V TVS (the MP1584 module is rated 28 V max).\\n'\n           'Everything rated >= 35 V.'")
buck = between(m, "fl.section('5 V / 5 A BUCK (TPS54560, 500 kHz)'", "fl.section('FANS + 5 V INDICATOR'")
m = m.replace(buck, r"""fl.section('5 V - MP1584EN MODULE (4.5-28 V in, ~3 A), soldered flat on the BOTTOM side + OR diode',
           'Set the module pot to 5.30 V before fitting (lock it with a drop of glue); B560C Schottky -> VCC_5V ~4.9-5.0 V.\n'
           'Budget ~3 A total on 5 V: board ~1 A + USB-A ports.  The module has no protection: F1 / Q2 / TVS stay on this board.')
fl.add(CONN4_, cx.ref('U'), 'MP1584EN module', {'1': 'VIN_PROT', '2': 'GND', '3': 'VMOD_5V', '4': 'GND'},
       footprint='klipper_h3:MP1584_Module_Bottom', fields={'Note': 'D-SUN 22x17 mm; pin 1 IN+, 2 IN-, 3 OUT+, 4 OUT-; set 5.30 V, hand-soldered flat after assembly'})
R(fl, '1k', 'VMOD_5V', 'USBC_GATE')
R(fl, '100k', 'USBC_GATE', 'GND')
R(fl, '1k', 'VMOD_5V', 'GND')
C(fl, '10uF 10V', 'VMOD_5V', 'GND', 'C0805')
fl.add(LB.DSCH, cx.ref('D'), 'B560C', {'K': 'VCC_5V', 'A': 'VMOD_5V'}, footprint='Diode_SMD:D_SMC')
cx.ref('L'); cx.ref('R'); cx.ref('R'); cx.ref('R'); cx.ref('C'); cx.ref('C')
CAPS(fl, 'VCC_5V', [('47uF 10V', 'C1210', 3), ('100nF', None, 1)])
cx.flag(fl, 'VCC_5V')
""")
fans = between(m, "fl.section('FANS + 5 V INDICATOR'", "# =============================================================== 3. USB")
m = m.replace(fans, r"""fl.section('FAN + 5 V INDICATOR + USB-C 5 V INPUT PATH',
           'FAN1 always on.  USB-C (power only, sink: CC 5.1k) feeds VCC_5V through Q3 (AO3401A).  Q3 is held OFF while the\n'
           'MP1584 module is running (gate pulled to VMOD_5V), so the 12-24 V input has priority and the two sources never fight.')
cx.LEDR(fl, 'GREEN', '4.7k', 'VCC_5V', 'GND')
fl.add(HDR2_, cx.ref('J'), 'FAN1 5V', {'1': 'VCC_5V', '2': 'GND'}, footprint='Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical')
cx.ref('J')
fl.add(PFET3_, cx.ref('Q'), 'AO3401A', {'G': 'USBC_GATE', 'D': 'USBC_VBUS', 'S': 'VCC_5V'}, footprint='Package_TO_SOT_SMD:SOT-23')
cx.ref('R'); cx.ref('R')
fl.add(TVS_, cx.ref('D'), 'SMAJ5.0CA', {'1': 'USBC_VBUS', '2': 'GND'}, footprint='Diode_SMD:D_SMA')

""")
m = sub(m, "('A4', 'USB0A_DP', 'USB0A_DM')", "('A4', 'USB0_DP', 'USB0_DM')")
m = sub(m, "('USB3_DP', 'USB3_DM'), ('USB0A_DP', 'USB0A_DM'))", "('USB3_DP', 'USB3_DM'), ('USB0_DP', 'USB0_DM'))")
m = sub(m, "USB0 -> FSUSB42 HSD1 -> A4 (host)", "USB0 -> A4 (host, ID pulled low)")
role = between(m, "fl.section('USB0 ROLE SWITCH", "# =============================================================== 4. HDMI")
m = m.replace(role, r"""fl.section('USB-C - 5 V POWER INPUT ONLY (no data; USB0 is the 4th USB-A host port)',
           'Sink: CC1 / CC2 5.1k to GND (5 V / 3 A from any USB-C supply).  VBUS -> Q3 (power-input sheet) -> VCC_5V.\n'
           'USB0_ID tied low through 10k: USB0 always host.  FEL recovery over USB is no longer available (boot from microSD).')
cx.ref('U'); cx.ref('C'); cx.ref('SW')
R(fl, '10k', 'USB0_ID', 'GND')
cx.ref('R')
fl.add(USBC_, cx.ref('J'), 'USB-C 5V IN', {'A1': 'GND', 'A12': 'GND', 'B1': 'GND', 'B12': 'GND', 'A4': 'USBC_VBUS', 'A9': 'USBC_VBUS',
                                            'B4': 'USBC_VBUS', 'B9': 'USBC_VBUS', 'A5': 'USBC_CC1', 'B5': 'USBC_CC2',
                                            'A6': nc, 'B6': nc, 'A7': nc, 'B7': nc, 'A8': nc, 'B8': nc, 'SH': 'GND'},
       footprint='Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12')
R(fl, '5.1k', 'USBC_CC1', 'GND')
R(fl, '5.1k', 'USBC_CC2', 'GND')
C(fl, '10uF 10V', 'USBC_VBUS', 'GND', 'C0805')
R(fl, '100k', 'USBC_VBUS', 'GND')
cx.ref('U')

""")
dbg = between(m, "fl.add(HDR3_, cx.ref('J'), 'DEBUG'", "R(fl, '100R', 'GPIO14_TXD0', 'DBG_TX')")
m = m.replace(dbg, """cx.ref('J')
for tp, net in (('TP1', 'GND'), ('TP2', 'DBG_RX'), ('TP3', 'DBG_TX')):
    fl.add(TP_, tp, net, {'1': net}, footprint='TestPoint:TestPoint_Pad_1.5x1.5mm')
""")
m = sub(m, "fl.section('DEBUG UART0 (GPIO14/15 = H3 PA4/PA5, 115200 8N1 - U-Boot + Linux console; same signals as header pins 8/10)')",
        "fl.section('DEBUG UART0 test pads TP1 GND / TP2 RX / TP3 TX (H3 PA4/PA5, 115200 8N1; same signals as header pins 8/10)')")
m = sub(m, "FEL (CM4 pin 93, nRPIBOOT position) held during reset -> USB-FEL on USB0 (set SW1 to DEVICE).", "FEL (H3 FEL pin) kept for completeness - USB0 is a host port now, so USB-FEL is not used.")
m = m.replace('Button_Switch_SMD:SW_SPST_TL3342', 'Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2')
# ---------------- v5 (full review)
m = sub(m, "R(fl, '6.8k 1%', 'ISET_%s' % port, 'GND')", "R(fl, '10k 1%', 'ISET_%s' % port, 'GND')")
m = sub(m, "(Rset 6.8k -> 1.0 A)", "(Rset 10k -> ~0.68 A; 4 ports + board stay inside the 3 A module)")
m = sub(m, "fl.add(SCH1A_, cx.ref('D'), '1N5819WS', {'A': 'VCC_5V', 'K': 'VCC_5V_HDMI'}", "fl.add(SCH1A_, cx.ref('D'), 'PMEG2010AEJ', {'A': 'VCC_5V', 'K': 'VCC_5V_HDMI'}")
m = sub(m, "fl.add(SCH1A_, cx.ref('D'), '1N5819WS', {'A': 'CEC_PU', 'K': 'VCC_3V3'}", "fl.add(SCH1A_, cx.ref('D'), '1N5819WS', {'A': 'VCC_3V3', 'K': 'CEC_PU'}")
m = sub(m, "'DAT0': 'SD_D0', 'DAT1': 'SD_D1', 'DET': 'SD_DET', 'SHIELD': 'GND'}", "'DAT0': 'SD_D0', 'DAT1': 'SD_D1', 'DET_B': 'SD_DET', 'DET_A': 'GND', 'SHIELD': 'GND'}")
m = sub(m, "{'1': 'VIN_RAW', '2': 'VIN_FUSED'}, rot=90, footprint='Fuse:Fuse_1812_4532Metric')", "{'1': 'VIN_RAW', '2': 'VIN_FUSED'}, rot=90, footprint='Fuse:Fuse_1206_3216Metric', fields={'MPN': 'Littelfuse 0468003.NRHF (3 A slow, 32 VDC)'})")
m = sub(m, "fl.add(TVS_, cx.ref('D'), 'SMAJ26CA', {'1': 'VIN_PROT', '2': 'GND'}", "fl.add(TVSU_, cx.ref('D'), 'SMAJ26A', {'1': 'VIN_PROT', '2': 'GND'}")
run(m, 'R0603', 'C0603')

fl.section('MOUNTING  (4 x M2.5, Raspberry Pi 4 / BTT Pi pattern 58 x 49 mm (board rotated 180 deg): (23.5, 3.5) (81.5, 3.5) (23.5, 52.5) (81.5, 52.5), pads on GND)')
for i in range(4):
    fl.add(LB.MHP, 'H%d' % (i + 1), 'M2.5', {'1': 'GND'}, footprint='MountingHole:MountingHole_2.7mm_M2.5_Pad_Via')

PRJ.root_texts = [
    ('KLIPPER H3 SBC  -  single board 85 x 56 mm, 6 layers, Allwinner H3 + 512 MB DDR3', 25, 185, 2.5),
    ('H3 quad A7 | 1 x DDR3 x16 | RTL8189FTV WiFi + u.FL | 10/100 RJ45 | 4 x USB-A host | HDMI 1.4 Type A | microSD | 40-pin RPi header\n'
     '12-24 V (XH) -> F1 -> Q2 -> MP1584 module 5 V / 3 A (bottom) -> B560C ; USB-C 5 V in -> Q3 ; 5 V -> TPS563201 3.3 V -> VDD_CPUX | VDD_SYS 1.2 V | VCC_DRAM 1.5 V', 25, 195, 1.8),
    ('Generated by h3-two-board/gen/build_sbc.py from the CN1 + Mizban generators (module connectors removed)', 25, 212, 1.8),
]
cx.write(OUT, 'Klipper H3 SBC', CU)
import glob as _glob, re as _re
for _f in _glob.glob(os.path.join(OUT, '*.kicad_sch')):        # mounting holes: not part of the BOM
    _t = open(_f).read()
    _t2 = _re.sub(r'(\(symbol \(lib_id "[^"]+"\)[^\n]*?\(in_bom )yes(\)[^\n]*?\(property "Reference" "(?:H|TP)\d")', r'\1no\2', _t)
    # v3: 0402 -> 0603 for the parts that fit outside the BGA shadows (list from pcb/place0603.py rounds)
    _up = set(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'upgrade_0603.txt')).read().strip().split(','))
    _lines = _t2.split('\n')
    for _i, _l in enumerate(_lines):
        _m = _re.search(r'\(property "Reference" "([A-Z]+\d+)"', _l)
        if _m and _m.group(1) in _up and '_0402_1005Metric' in _l:
            _lines[_i] = _l.replace('_0402_1005Metric', '_0603_1608Metric')
    _t2 = '\n'.join(_lines)
    # v5: MPN + LCSC part number on every BOM line (review/lcsc_map.csv, each number checked on the JLC parts API)
    import csv as _csv
    _map = {}
    for _row in _csv.DictReader(open(os.path.join(HERE, '..', 'review', 'lcsc_map.csv'))):
        for _tok in _row['Reference(s)'].replace(' ', '').split(','):
            _tok = _re.sub(r'\(.*\)', '', _tok)
            _mm = _re.match(r'([A-Z]+)(\d+)-(?:[A-Z]+)?(\d+)$', _tok)
            _refs = ['%s%d' % (_mm.group(1), _k) for _k in range(int(_mm.group(2)), int(_mm.group(3)) + 1)] if _mm else [_tok]
            for _r in _refs:
                if _row['LCSC'].startswith('C'):
                    _map[_r] = (_row['MPN'].replace('"', "'"), _row['LCSC'])
    _lines = _t2.split('\n')
    for _i, _l in enumerate(_lines):
        _m = _re.search(r'\(property "Reference" "([A-Z]+\d+)"', _l)
        if not (_m and _m.group(1) in _map and _l.lstrip().startswith('(symbol (lib_id')):
            continue
        _mpn, _lc = _map[_m.group(1)]
        _at = _re.search(r'\(at ([\d.\-]+) ([\d.\-]+)', _l)
        _hid = ' (at %s %s 0) (effects (font (size 1.27 1.27)) (hide yes)))' % (_at.group(1), _at.group(2))
        if '(property "MPN"' in _l:
            _l = _re.sub(r'\(property "MPN" "[^"]*"', '(property "MPN" "%s"' % _mpn, _l)
        else:
            _l = _l.replace(' (pin ', ' (property "MPN" "%s"%s (pin ' % (_mpn, _hid), 1)
        _l = _l.replace(' (pin ', ' (property "LCSC" "%s"%s (pin ' % (_lc, _hid), 1)
        _lines[_i] = _l
    _t2 = '\n'.join(_lines)
    if _t2 != _t:
        open(_f, 'w').write(_t2)
import subprocess
subprocess.run([sys.executable, '/home/claude/klipper-h3-host/gen/gen_fp.py', os.path.join(OUT, 'klipper_h3.pretty')], check=True)
cm4.write_footprints(os.path.join(OUT, 'klipper_h3.pretty'))


def mp1584_footprint(path):
    """MP1584EN 22 x 17 mm buck module ('D-SUN' style) soldered FLAT on the board: its pad side down, parts facing away.
    Drawn in module TOP view, landscape (22 mm along x).  The module's back silkscreen reads, seen from the back:
    OUT- top-left, IN- top-right, OUT+ bottom-left, IN+ bottom-right - mirrored to the top view that is
    IN- top-left, OUT- top-right, IN+ bottom-left, OUT+ bottom-right.  Each terminal is a vertical pair of plated holes
    (~2.5 mm apart, ~1.6 mm from the short edge); one 2.4 x 4.4 mm pad per terminal covers both holes with +-0.8 mm
    tolerance and the solder wicks into them.  Placed flipped on B.Cu.
    Pins: 1 IN+, 2 IN-, 3 OUT+, 4 OUT-."""
    pads = [('1', -9.4, 5.8), ('2', -9.4, -5.8), ('3', 9.4, 5.8), ('4', 9.4, -5.8)]
    t = ['(footprint "MP1584_Module_Bottom"', '  (version 20240108)', '  (generator "klipper_h3_gen")', '  (layer "F.Cu")',
         '  (descr "MP1584EN 22x17 mm buck module (D-SUN), soldered flat on its plated holes - mount on the bottom side")',
         '  (tags "MP1584 buck module")', '  (attr smd)',
         '  (fp_text reference "REF**" (at 0 -9.6) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
         '  (fp_text value "MP1584EN module" (at 0 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
         '  (fp_text user "IN+" (at -6.4 5.8) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))',
         '  (fp_text user "IN-" (at -6.4 -5.8) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))',
         '  (fp_text user "OUT+" (at 6.2 5.8) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))',
         '  (fp_text user "OUT-" (at 6.2 -5.8) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))',
         '  (fp_rect (start -11 -8.5) (end 11 8.5) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))',
         '  (fp_rect (start -11.12 -8.62) (end 11.12 8.62) (stroke (width 0.12) (type solid)) (fill none) (layer "F.SilkS"))',
         '  (fp_rect (start -11.4 -8.9) (end 11.4 8.9) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))']
    for n, x, y in pads:
        t.append('  (pad "%s" smd roundrect (at %g %g) (size 2.4 4.4) (layers "F.Cu" "F.Mask") (roundrect_rratio 0.15))' % (n, x, y))   # v5: no paste (hand-soldered module)
    t.append(')')
    open(os.path.join(path, 'MP1584_Module_Bottom.kicad_mod'), 'w').write('\n'.join(t) + '\n')


mp1584_footprint(os.path.join(OUT, 'klipper_h3.pretty'))
print('SBC sheets:', len(PRJ.sheets), 'global nets:', len(PRJ.global_nets))
