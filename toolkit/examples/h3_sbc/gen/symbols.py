"""Custom schematic symbols for the Klipper H3 host board.

Pin data sources:
  * Allwinner H3: ball map parsed from Allwinner H3 Datasheet (Table 3-1 + Appendix pin map),
    cross-checked ball-by-ball against an independent KiCad H3 symbol (all 347 balls agree).
  * DDR3 x16 FBGA-96: JEDEC standard x16 ballout (Micron MT41K128M16 / Samsung K4B2G1646).
  * SY8106A / SY8089A / SY8008B / SY6280AAC / RTL8189FTV / RClamp0524P: pinouts as drawn in
    Xunlong Orange Pi PC Plus / Plus 2E reference schematics.
"""
import json, os, re
from kigen import make_ic

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = 'klipper_h3'

H3 = json.load(open(os.path.join(HERE, 'h3_pins.json')))   # ball -> [short, full, group]

PWR = 'power_in'


def _natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def _h3pins(pred):
    out = [(b, v) for b, v in H3.items() if pred(b, v)]
    out.sort(key=lambda bv: _natkey(bv[1][0]) + _natkey(bv[0]))
    return out


def _etype(short, group):
    if short in ('GND', 'HGND', 'AGND', 'GND_TV', 'GND-CPUFB'):
        return 'power_in'
    if short in ('RTC_VIO',):
        return 'power_out'
    if re.match(r'^(VDD|VCC|AVCC|HVCC|V33)', short) or short in ('EPHY_VCC', 'EPHY_VDD'):
        return 'passive' if short in ('VDD-CPUFB',) else 'power_in'
    if re.match(r'^P[A-L]\d+$', short):
        return 'bidirectional'
    if short in ('RESET', 'UBOOT', 'TEST', 'NMI', 'JTAG-SEL0', 'JTAG-SEL1'):
        return 'input'
    return 'passive'


def _p(ball):
    s, f, g = H3[ball]
    return (ball, f, _etype(s, g))


def h3_symbol():
    units = []
    # A: DRAM interface
    dram_ctrl = [b for b, v in _h3pins(lambda b, v: v[2] == 'DRAM' and not re.match(r'SDQ', v[0]))]
    order = ['SA%d' % i for i in range(16)] + ['SBA0', 'SBA1', 'SBA2', 'SRAS', 'SCAS', 'SWE', 'SCS0', 'SCS1', 'SCKE0', 'SCKE1',
                                              'SODT0', 'SODT1', 'SCK', 'SCKB', 'SRST', 'SZQ', 'SVREF']
    by = {H3[b][0]: b for b in H3}
    left = [_p(by[n]) for n in order]
    right = [_p(by['SDQ%d' % i]) for i in range(32)] + [None] + [_p(by['SDQM%d' % i]) for i in range(4)] + [None] + \
            sum([[_p(by['SDQS%d' % i]), _p(by['SDQS%dB' % i])] for i in range(4)], [])
    units.append(dict(name='DRAM', left=left, right=right))
    # B: Port A + Port F
    units.append(dict(name='GPIO PA / PF',
                      left=[_p(by['PA%d' % i]) for i in range(22)],
                      right=[_p(by['PF%d' % i]) for i in range(7)]))
    # C: Port C + Port G
    units.append(dict(name='GPIO PC / PG',
                      left=[_p(by['PC%d' % i]) for i in range(17)],
                      right=[_p(by['PG%d' % i]) for i in range(14)]))
    # D: Port D + Port E
    units.append(dict(name='GPIO PD / PE',
                      left=[_p(by['PD%d' % i]) for i in range(18)],
                      right=[_p(by['PE%d' % i]) for i in range(16)]))
    # E: Port L (CPUS) + system
    sysn = ['RESET', 'NMI', 'UBOOT', 'TEST', 'JTAG-SEL0', 'JTAG-SEL1', 'X24MIN', 'X24MOUT', 'NC', 'X32KIN', 'X32KOUT',
            'X32KFOUT', 'PLLTEST', 'KEYADC']
    units.append(dict(name='PL / SYSTEM',
                      left=[_p(by['PL%d' % i]) for i in range(12)],
                      right=[_p(by[n]) for n in sysn]))
    # F: HDMI / USB / EPHY / TV / Audio
    hd = ['HTX0P', 'HTX0N', 'HTX1P', 'HTX1N', 'HTX2P', 'HTX2N', 'HTXCP', 'HTXCN', 'HHPD', 'HCEC', 'HSCL', 'HSDA']
    us = ['USB_DP0', 'USB_DM0', 'USB_DP1', 'USB_DM1', 'USB_DP2', 'USB_DM2', 'USB_DP3', 'USB_DM3']
    ep = ['EPHY_TXP', 'EPHY_TXN', 'EPHY_RXP', 'EPHY_RXN', 'EPHY_LINK_LED', 'EPHY_SPD_LED', 'EPHY_RTX']
    au = ['MICIN1P', 'MICIN1N', 'MICIN2P', 'MICIN2N', 'MBIAS', 'LINEINL', 'LINEINR', 'LINEOUTL', 'LINEOUTR', 'VRA1', 'VRA2', 'VRP',
          'TVOUT']
    units.append(dict(name='HDMI / USB / EPHY / AUDIO',
                      left=[_p(by[n]) for n in hd] + [None] + [_p(by[n]) for n in us],
                      right=[_p(by[n]) for n in ep] + [None] + [_p(by[n]) for n in au]))
    # G: power
    def balls(name):
        return [b for b in sorted(H3, key=_natkey) if H3[b][0] == name]
    pl = []
    for n in ['VDD_CPUX']:
        pl += [(b, 'VDD_CPUX', PWR) for b in balls(n)]
    pl += [None, (by['VDD-CPUFB'], 'VDD_CPUXFB', 'passive'), (by['GND-CPUFB'], 'GND_CPUXFB', 'passive'), None]
    pl += [(b, 'VDD_CPUS', PWR) for b in balls('VDD_CPUS')]
    pl += [(by['RTC_VIO'], 'RTC_VIO', 'power_out')]
    pr = [(b, 'VDD_SYS', PWR) for b in balls('VDD_SYS')] + [None]
    pr += [(b, 'VCC_DRAM', PWR) for b in balls('VCC-DRAM')]
    units.append(dict(name='CORE POWER', left=pl, right=pr))
    # H: IO power + analog power
    io_l = [(b, 'VCC_IO', PWR) for b in balls('VCC_IO')] + [None,
            (by['VCC_PD'], 'VCC_PD', PWR), (by['VCC_PG'], 'VCC_PG', PWR), (by['VCC_USB'], 'VCC_USB', PWR),
            (by['HVCC'], 'HVCC', PWR), (by['EPHY_VCC'], 'EPHY_VCC', PWR), (by['EPHY_VDD'], 'EPHY_VDD', PWR),
            (by['V33_TV'], 'V33_TV', PWR), None,
            (by['VDD_EFUSE'], 'VDD_EFUSE', PWR), (by['VDD_EFUSEBP'], 'VDD_EFUSEBP', PWR)]
    io_r = [(by['AVCC'], 'AVCC', PWR), (by['VCC_PLL'], 'VCC_PLL', PWR), (by['VCC_RTC'], 'VCC_RTC', PWR), None,
            (by['AGND'], 'AGND', 'passive'), (by['HGND'], 'HGND', PWR), (by['GND_TV'], 'GND_TV', PWR)]
    units.append(dict(name='IO / ANALOG POWER', left=io_l, right=io_r))
    # I: ground
    g = [(b, 'GND', PWR) for b in balls('GND')]
    half = (len(g) + 1) // 2
    units.append(dict(name='GND', left=g[:half], right=g[half:]))
    # sanity: every ball exactly once
    used = [p[0] for u in units for side in ('left', 'right') for p in u[side] if p]
    assert len(used) == len(set(used)) == 347, (len(used), len(set(used)))
    return make_ic(LIB + ':Allwinner_H3', units, ref='U', value='Allwinner H3',
                   footprint=LIB + ':Allwinner_H3_TFBGA-347_14x14mm_P0.65mm',
                   datasheet='https://linux-sunxi.org/images/4/4b/Allwinner_H3_Datasheet_V1.2.pdf',
                   desc='Allwinner H3 quad-core Cortex-A7 SoC, TFBGA-347', min_w=35.56)


# ---------------------------------------------------------------- DDR3 x16
DDR3_BALLS = {
    'A0': 'N3', 'A1': 'P7', 'A2': 'P3', 'A3': 'N2', 'A4': 'P8', 'A5': 'P2', 'A6': 'R8', 'A7': 'R2', 'A8': 'T8', 'A9': 'R3',
    'A10/AP': 'L7', 'A11': 'R7', 'A12/BC#': 'N7', 'A13': 'T3', 'A14': 'T7', 'A15': 'M7',
    'BA0': 'M2', 'BA1': 'N8', 'BA2': 'M3', 'RAS#': 'J3', 'CAS#': 'K3', 'WE#': 'L3', 'CS#': 'L2', 'CKE': 'K9', 'ODT': 'K1',
    'CK': 'J7', 'CK#': 'K7', 'RESET#': 'T2', 'ZQ': 'L8', 'VREFCA': 'M8', 'VREFDQ': 'H1',
    'DQL0': 'E3', 'DQL1': 'F7', 'DQL2': 'F2', 'DQL3': 'F8', 'DQL4': 'H3', 'DQL5': 'H8', 'DQL6': 'G2', 'DQL7': 'H7',
    'DQU0': 'D7', 'DQU1': 'C3', 'DQU2': 'C8', 'DQU3': 'C2', 'DQU4': 'A7', 'DQU5': 'A2', 'DQU6': 'B8', 'DQU7': 'A3',
    'DML': 'E7', 'DMU': 'D3', 'DQSL': 'F3', 'DQSL#': 'G3', 'DQSU': 'C7', 'DQSU#': 'B7',
}
DDR3_VDD = ['B2', 'D9', 'G7', 'K2', 'K8', 'N1', 'N9', 'R1', 'R9']
DDR3_VDDQ = ['A1', 'A8', 'C1', 'C9', 'D2', 'E9', 'F1', 'H2', 'H9']
DDR3_VSS = ['A9', 'B3', 'E1', 'G8', 'J2', 'J8', 'M1', 'M9', 'P1', 'P9', 'T1', 'T9']
DDR3_VSSQ = ['B1', 'B9', 'D1', 'D8', 'E2', 'E8', 'F9', 'G1', 'G9']
DDR3_NC = ['J1', 'J9', 'L1', 'L9']


def ddr3_symbol():
    b = DDR3_BALLS
    left = [(b[n], n, 'input') for n in ['A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10/AP', 'A11', 'A12/BC#',
                                         'A13', 'A14', 'A15', 'BA0', 'BA1', 'BA2']] + [None] + \
           [(b[n], n, 'input') for n in ['RAS#', 'CAS#', 'WE#', 'CS#', 'CKE', 'ODT', 'CK', 'CK#', 'RESET#']] + [None] + \
           [(b['ZQ'], 'ZQ', 'passive'), (b['VREFCA'], 'VREFCA', 'passive'), (b['VREFDQ'], 'VREFDQ', 'passive')] + [None] + \
           [(n, 'NC', 'no_connect') for n in DDR3_NC]
    right = [(b['DQL%d' % i], 'DQL%d' % i, 'bidirectional') for i in range(8)] + \
            [(b['DQU%d' % i], 'DQU%d' % i, 'bidirectional') for i in range(8)] + [None] + \
            [(b[n], n, 'input') for n in ['DML', 'DMU']] + \
            [(b[n], n, 'bidirectional') for n in ['DQSL', 'DQSL#', 'DQSU', 'DQSU#']] + [None] + \
            [(x, 'VDD', PWR) for x in DDR3_VDD] + [(x, 'VDDQ', PWR) for x in DDR3_VDDQ] + \
            [(x, 'VSS', PWR) for x in DDR3_VSS] + [(x, 'VSSQ', PWR) for x in DDR3_VSSQ]
    allb = [p[0] for p in left + right if p]
    assert len(allb) == len(set(allb)) == 96, len(set(allb))
    return make_ic(LIB + ':DDR3_x16_FBGA96', [dict(name='DDR3 x16', left=left, right=right)], ref='U',
                   value='K4B2G1646F-BCK0', footprint='Package_BGA:BGA-96_9.0x13.0mm_Layout2x3x16_P0.8mm',
                   desc='DDR3 SDRAM 2Gbit (128M x16), FBGA-96, JEDEC x16 ballout', min_w=20.32)


def sy8106a_symbol():
    left = [('2', 'IN1', PWR), ('3', 'IN2', PWR), ('4', 'IN3', PWR), ('5', 'IN4', PWR), None, ('12', 'EN', 'input'),
            ('9', 'SCL', 'input'), ('10', 'SDA', 'bidirectional'), None,
            ('7', 'GND1', PWR), ('8', 'GND2', PWR), ('18', 'GND3', PWR), ('21', 'GND4', PWR)]
    right = [('1', 'BS', 'passive'), ('6', 'LX1', 'passive'), ('19', 'LX2', 'passive'), ('20', 'LX3', 'passive'), None,
             ('16', 'OUT', 'passive'), ('15', 'FB', 'input'), None, ('11', 'PG', 'open_collector'), ('17', 'VL', 'passive'),
             ('14', 'SS', 'passive'), ('13', 'FS', 'passive')]
    return make_ic(LIB + ':SY8106A', [dict(name='SY8106A', left=left, right=right)], ref='U', value='SY8106A',
                   footprint=LIB + ':Silergy_QFN-21_3x3mm', desc='Silergy 6A synchronous buck with I2C VID (addr 0x65)')


def sy_sot23_buck(name):
    left = [('4', 'IN', PWR), ('1', 'EN', 'input'), ('2', 'GND', PWR)]
    right = [('3', 'LX', 'power_out'), ('5', 'FB', 'input')]
    return make_ic(LIB + ':' + name, [dict(name='', left=left, right=right)], ref='U', value=name,
                   footprint='Package_TO_SOT_SMD:SOT-23-5', desc='Silergy synchronous buck, Vout = 0.6V*(1+Rtop/Rbot)', min_w=10.16)


def sy6280_symbol():
    left = [('5', 'IN', PWR), ('4', 'EN', 'input'), ('2', 'GND', PWR)]
    right = [('1', 'OUT', 'power_out'), ('3', 'ISET', 'passive')]
    return make_ic(LIB + ':SY6280AAC', [dict(name='', left=left, right=right)], ref='U', value='SY6280AAC',
                   footprint='Package_TO_SOT_SMD:SOT-23-5', desc='USB power switch, Ilim(A) = 6800/Rset(ohm)', min_w=10.16)


def rtl8189_symbol():
    left = [('19', 'VDIO_SDIO', PWR), ('1', 'VD33X', PWR), ('4', 'VD33SYNVCO', PWR), ('5', 'VDSYN', PWR), ('6', 'VD33PA', PWR),
            ('8', 'VD33TR', PWR), ('9', 'VDTR', PWR), ('12', 'VD33LDO', PWR), ('11', 'VD12D', 'passive'), None,
            ('3', 'XI', 'input'), ('2', 'XO', 'output'), None, ('23', 'GNDD', PWR), ('25', 'EPAD', PWR)]
    right = [('16', 'SD_CLK', 'input'), ('15', 'SD_CMD', 'bidirectional'), ('17', 'SD_D0', 'bidirectional'),
             ('18', 'SD_D1', 'bidirectional'), ('13', 'SD_D2', 'bidirectional'), ('14', 'SD_D3', 'bidirectional'), None,
             ('10', 'CHIP_EN', 'input'), ('20', 'INT/GPIO0', 'bidirectional'), ('21', 'CLK_REQ/GPIO1', 'bidirectional'),
             ('22', 'HOST_WAKE_DEV/GPIO2', 'bidirectional'), ('24', 'TEST_MODE/GPIO3', 'bidirectional'), None,
             ('7', 'RF_INOUT', 'passive')]
    return make_ic(LIB + ':RTL8189FTV', [dict(name='RTL8189FTV', left=left, right=right)], ref='U', value='RTL8189FTV',
                   footprint='Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.15x2.15mm',
                   desc='Realtek 802.11b/g/n 1T1R SDIO WLAN, QFN-24')


def rclamp0524p_symbol():
    left = [('1', 'IN1', 'passive'), ('2', 'IN2', 'passive'), ('4', 'IN3', 'passive'), ('5', 'IN4', 'passive'), None,
            ('3', 'GND1', 'passive'), ('8', 'GND2', 'passive')]
    right = [('10', 'OUT1', 'passive'), ('9', 'OUT2', 'passive'), ('7', 'OUT3', 'passive'), ('6', 'OUT4', 'passive')]
    return make_ic(LIB + ':RClamp0524P', [dict(name='', left=left, right=right)], ref='D', value='RClamp0524P',
                   footprint=LIB + ':Semtech_SLP2510P8', desc='4-line flow-through ESD array for HDMI/TMDS (INx=OUTx internally)',
                   min_w=12.7)


def all_custom():
    syms = [h3_symbol(), ddr3_symbol(), sy6280_symbol(), rtl8189_symbol()]
    return {s.lib_id.split(':')[1]: s for s in syms}
