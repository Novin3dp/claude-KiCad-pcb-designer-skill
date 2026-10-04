"""Shared helpers on top of kigen.py: Ctx (reference counters, R / C / CAPS / L / FBEAD helpers with default footprints), Lib (common Device symbols), FP (footprint shortcuts)."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kigen import *            # noqa
import kigen

FP = dict(
    R0402='Resistor_SMD:R_0402_1005Metric', R0603='Resistor_SMD:R_0603_1608Metric',
    C0402='Capacitor_SMD:C_0402_1005Metric', C0603='Capacitor_SMD:C_0603_1608Metric',
    C0805='Capacitor_SMD:C_0805_2012Metric', C1206='Capacitor_SMD:C_1206_3216Metric',
    C1210='Capacitor_SMD:C_1210_3225Metric', FB0402='Inductor_SMD:L_0402_1005Metric', FB0603='Inductor_SMD:L_0603_1608Metric',
    FB0805='Inductor_SMD:L_0805_2012Metric', LED0603='LED_SMD:LED_0603_1608Metric', LED0402='LED_SMD:LED_0402_1005Metric',
)


class Lib:
    def __init__(self):
        g = lambda a, b: load_lib(a, b)
        self.R, self.C, self.CP, self.L = g('Device', 'R'), g('Device', 'C'), g('Device', 'C_Polarized'), g('Device', 'L')
        self.FB, self.LED, self.FUSE, self.PFUSE = g('Device', 'FerriteBead_Small'), g('Device', 'LED'), g('Device', 'Fuse'), g('Device', 'Polyfuse')
        self.DSCH, self.XTAL4, self.XTAL2 = g('Device', 'D_Schottky'), g('Device', 'Crystal_GND24'), g('Device', 'Crystal')
        self.FLAG, self.MH, self.MHP = g('power', 'PWR_FLAG'), g('Mechanical', 'MountingHole'), g('Mechanical', 'MountingHole_Pad')


class Ctx:
    """one schematic project: reference counters + passive helpers with per-board default footprints"""
    def __init__(self, name, rfp='R0603', cfp='C0603'):
        self.PRJ = Project(name)
        self.lib = Lib()
        self.rfp, self.cfp = rfp, cfp
        self.nflag = 0

    def ref(self, p):
        return self.PRJ.ref(p)

    def flag(self, fl, net):
        self.nflag += 1
        fl.add(self.lib.FLAG, '#FLG%02d' % self.nflag, 'PWR_FLAG', {'1': net})

    def R(self, fl, val, a, b, fp=None, dnp=False, **kw):
        return fl.add(self.lib.R, self.ref('R'), val, {'1': a, '2': b}, rot=90, footprint=FP[fp or self.rfp], dnp=dnp, **kw)

    def C(self, fl, val, a, b='GND', fp=None, dnp=False, **kw):
        return fl.add(self.lib.C, self.ref('C'), val, {'1': a, '2': b}, rot=90, footprint=FP[fp or self.cfp], dnp=dnp, **kw)

    def CAPS(self, fl, net, spec):
        for val, fp, n in spec:
            for _ in range(n):
                self.C(fl, val, net, 'GND', fp)

    def L(self, fl, val, a, b, fp, mpn=None):
        return fl.add(self.lib.L, self.ref('L'), val, {'1': a, '2': b}, rot=90, footprint=fp, fields={'MPN': mpn} if mpn else None)

    def FBEAD(self, fl, val, a, b, fp=None):
        return fl.add(self.lib.FB, self.ref('FB'), val, {'1': a, '2': b}, rot=90, footprint=FP[fp or ('FB0402' if self.rfp == 'R0402' else 'FB0603')])

    def LEDR(self, fl, color, rval, a, k, led_fp=None):
        """resistor from `a` to the LED anode, LED cathode to `k`"""
        an = 'LED_%s_A%d' % (color, self.PRJ.refcount.get('D', 0) + 1)
        self.R(fl, rval, a, an)
        fl.add(self.lib.LED, self.ref('D'), color, {'A': an, 'K': k}, footprint=FP[led_fp or ('LED0402' if self.rfp == 'R0402' else 'LED0603')])

    def write(self, out, title, custom=None, lib='project'):
        """write the project; `custom` = {name: SymDef} of generated symbols, saved as <lib>.kicad_sym (their lib_id must be
        '<lib>:<name>'), plus sym-lib-table / fp-lib-table entries for <lib>.kicad_sym and <lib>.pretty"""
        custom = custom or {}
        self.PRJ.write(out, root_title=title)
        import glob
        for f in glob.glob(os.path.join(out, '*.kicad_sch')):
            t = open(f).read().replace('(company "Klipper H3 Host")', '(company %s)' % q(title.split(' - ')[0]))
            open(f, 'w').write(t)
        lines = ['(kicad_symbol_lib (version 20231120) (generator "kigen") (generator_version "9.0")']
        for name, sd in custom.items():
            lines.append('  ' + sd.text.replace('(symbol "%s:%s"' % (lib, name), '(symbol "' + name + '"', 1))
        lines.append(')')
        open(os.path.join(out, lib + '.kicad_sym'), 'w').write('\n'.join(lines))
        open(os.path.join(out, 'sym-lib-table'), 'w').write(
            '(sym_lib_table\n  (version 7)\n  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.kicad_sym")(options "")(descr "generated symbols"))\n)\n' % (lib, lib))
        open(os.path.join(out, 'fp-lib-table'), 'w').write(
            '(fp_lib_table\n  (version 7)\n  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.pretty")(options "")(descr "project footprints"))\n)\n' % (lib, lib))


def sd_fp(sd):
    m = re.search(r'\(property "Footprint" "([^"]*)"', sd.text)
    return m.group(1) if m else ''


def ti_buck(cx, fl, part, sym, vin, en, pre, out, rtop, rbot, lval, lfp, lmpn, cin, cout, fb_top=None):
    """TPS56x201 family: VIN=3 EN=5 GND=1 SW=2 VBST=6 VFB=4, Vref = 0.768 V."""
    fl.add(sym, cx.ref('U'), part, {'VIN': vin, 'EN': en, 'GND': 'GND', 'SW': pre + '_SW', 'VBST': pre + '_BST', 'VFB': pre + '_FB'},
           footprint='Package_TO_SOT_SMD:SOT-23-6')
    cx.C(fl, '100nF', pre + '_BST', pre + '_SW')
    cx.L(fl, lval, pre + '_SW', out, lfp, lmpn)
    cx.R(fl, rtop, fb_top or out, pre + '_FB')
    cx.R(fl, rbot, pre + '_FB', 'GND')
    cx.CAPS(fl, vin, cin)
    cx.CAPS(fl, out, cout)
