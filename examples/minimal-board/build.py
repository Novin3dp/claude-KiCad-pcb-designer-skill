"""Minimal kigen example: an LED indicator driven from a header, using only custom symbols.

Run from this folder:
    python3 build.py            # writes ./kicad/minimal.kicad_pro + .kicad_sch + sub-sheet

It needs no KiCad installation to generate the files. To verify them, install KiCad 9/10 and run
    kicad-cli sch erc -o erc.rpt --severity-all kicad/minimal.kicad_sch
(see skills/kicad-schematic-generator/SKILL.md for the full verification workflow).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'skills', 'kicad-schematic-generator', 'gen'))
from kigen import Project, Sheet, Flow, make_ic  # noqa: E402

P = Project('minimal')

# Custom symbols (a real design would prefer stock library symbols via load_lib()).
HDR = make_ic('mylib:HDR_1x3', [dict(name='J', left=[('1', 'VCC', 'passive'), ('2', 'CTRL', 'passive'), ('3', 'GND', 'passive')])],
              ref='J', footprint='Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical')
RES = make_ic('mylib:R', [dict(name='R', left=[('1', '1', 'passive')], right=[('2', '2', 'passive')])],
              ref='R', footprint='Resistor_SMD:R_0402_1005Metric', min_w=5.08)
LED = make_ic('mylib:LED', [dict(name='LED', left=[('1', 'A', 'passive')], right=[('2', 'K', 'passive')])],
              ref='D', footprint='LED_SMD:LED_0603_1608Metric', min_w=5.08)

sh = P.add_sheet(Sheet('Indicator', 'indicator.kicad_sch', 'LED indicator'))
fl = Flow(sh, 20, 25, 200)
fl.section('INDICATOR', 'I_LED = (3.3 V - 2.0 V) / 330 ohm = 3.9 mA')
fl.add(HDR, P.ref('J'), 'CTRL_HDR', {'1': '3V3', '2': 'LED_CTRL', '3': 'GND'})
fl.add(RES, P.ref('R'), '330R', {'1': 'LED_CTRL', '2': 'LED_A'})
fl.add(LED, P.ref('D'), 'GREEN', {'A': 'LED_A', 'K': 'GND'})

out = os.path.join(HERE, 'kicad')
P.write(out)

# Custom symbol library + library tables so KiCad can resolve 'mylib:*'
lib = ['(kicad_symbol_lib (version 20231120) (generator "kigen") (generator_version "9.0")']
for sd in (HDR, RES, LED):
    lib.append(sd.text.replace('(symbol "mylib:', '(symbol "', 1))
open(os.path.join(out, 'mylib.kicad_sym'), 'w').write('\n'.join(lib + [')']))
open(os.path.join(out, 'sym-lib-table'), 'w').write(
    '(sym_lib_table (version 7)\n (lib (name "mylib")(type "KiCad")(uri "${KIPRJMOD}/mylib.kicad_sym")(options "")(descr ""))\n)\n')
print('wrote', out)
