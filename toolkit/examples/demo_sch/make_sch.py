#!/usr/bin/env python3
"""Demo: generate a 2-sheet KiCad schematic (5 V input + 3.3 V LDO + LED, and an I2C sensor header) from Python with
kigen, then check it:  kicad-cli sch erc  and  netcheck.py.   usage: make_sch.py OUTDIR"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'schematic'))
from common import *          # noqa: Ctx, Sheet, Flow, load_lib, FP ...

out = sys.argv[1] if len(sys.argv) > 1 else 'demo_sch'
cx = Ctx('demo', rfp='R0603', cfp='C0603')
LDO = load_lib('Regulator_Linear', 'AMS1117-3.3')
CON2 = load_lib('Connector_Generic', 'Conn_01x02')
CON4 = load_lib('Connector_Generic', 'Conn_01x04')

sh = cx.PRJ.add_sheet(Sheet('Power', 'power.kicad_sch', '5 V input and 3.3 V regulator'))
fl = Flow(sh, 20, 25, 250)
fl.section('5 V INPUT', 'J1 pin 1 = +5 V')
fl.add(CON2, cx.ref('J'), '5V IN', {'1': '+5V', '2': 'GND'}, footprint='Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical')
cx.flag(fl, '+5V'); cx.flag(fl, 'GND')
fl.section('3.3 V LDO')
fl.add(LDO, cx.ref('U'), 'AMS1117-3.3', {'VI': '+5V', 'VO': '+3V3', 'GND': 'GND'}, footprint='Package_TO_SOT_SMD:SOT-223-3_TabPin2')
cx.CAPS(fl, '+5V', [('10uF', 'C0805', 1)])
cx.CAPS(fl, '+3V3', [('22uF', 'C0805', 1), ('100nF', None, 1)])
cx.LEDR(fl, 'GREEN', '1k', '+3V3', 'GND')

sh = cx.PRJ.add_sheet(Sheet('Sensor', 'sensor.kicad_sch', 'I2C sensor header'))
fl = Flow(sh, 20, 25, 250)
fl.section('I2C HEADER', '4.7k pull-ups to 3.3 V')
fl.add(CON4, cx.ref('J'), 'I2C', {'1': '+3V3', '2': 'SCL', '3': 'SDA', '4': 'GND'}, footprint='Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical')
cx.R(fl, '4.7k', '+3V3', 'SCL')
cx.R(fl, '4.7k', '+3V3', 'SDA')
cx.write(out, 'KAT demo schematic')
print('wrote', out)
