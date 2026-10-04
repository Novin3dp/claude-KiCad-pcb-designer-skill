"""Raspberry Pi CM4 module-connector pinout (2 x Hirose DF40, 100 pins each) + symbol/footprint builders.

Pin names follow the CM4 datasheet (section 2.1, "Module connector pinout").  Connector A carries pins 1-100,
connector B pins 101-200.  Our custom footprints for connector B are numbered 101..200, so the netlist uses CM4
pin numbers directly (pad k of the Hirose part = CM4 pin 100 + k).
"""
import os, re
from kigen import make_ic

LIB = 'klipper_h3'

CM4 = {}
_A = '''1 GND|2 GND|3 Ethernet_Pair3_P|4 Ethernet_Pair1_P|5 Ethernet_Pair3_N|6 Ethernet_Pair1_N|7 GND|8 GND|
9 Ethernet_Pair2_N|10 Ethernet_Pair0_N|11 Ethernet_Pair2_P|12 Ethernet_Pair0_P|13 GND|14 GND|15 Ethernet_nLED3|
16 Ethernet_SYNC_IN|17 Ethernet_nLED2|18 Ethernet_SYNC_OUT|19 Ethernet_nLED1|20 EEPROM_nWP|21 PI_nLED_Activity|22 GND|
23 GND|24 GPIO26|25 GPIO21|26 GPIO19|27 GPIO20|28 GPIO13|29 GPIO16|30 GPIO6|31 GPIO12|32 GND|33 GND|34 GPIO5|
35 ID_SC|36 ID_SD|37 GPIO7|38 GPIO11|39 GPIO8|40 GPIO9|41 GPIO25|42 GND|43 GND|44 GPIO10|45 GPIO24|46 GPIO22|
47 GPIO23|48 GPIO27|49 GPIO18|50 GPIO17|51 GPIO15|52 GND|53 GND|54 GPIO4|55 GPIO14|56 GPIO3|57 SD_CLK|58 GPIO2|
59 GND|60 GND|61 SD_DAT3|62 SD_CMD|63 SD_DAT0|64 SD_DAT5|65 GND|66 GND|67 SD_DAT1|68 SD_DAT4|69 SD_DAT2|70 SD_DAT7|
71 GND|72 SD_DAT6|73 SD_VDD_OVERRIDE|74 GND|75 SD_PWR_ON|76 RESERVED_76|77 +5V_IN|78 GPIO_VREF|79 +5V_IN|80 SCL0|
81 +5V_IN|82 SDA0|83 +5V_IN|84 +3V3_OUT|85 +5V_IN|86 +3V3_OUT|87 +5V_IN|88 +1V8_OUT|89 WL_nDISABLE|90 +1V8_OUT|
91 BT_nDISABLE|92 RUN_PG|93 nRPIBOOT|94 AnalogIP1|95 PI_LED_nPWR|96 AnalogIP0|97 Camera_GPIO|98 GND|99 GLOBAL_EN|100 nEXTRST'''
_B = '''101 USB_OTG_ID|102 PCIe_CLK_nREQ|103 USB_N|104 RESERVED_104|105 USB_P|106 RESERVED_106|107 GND|108 GND|109 PCIe_nRST|
110 PCIe_CLK_P|111 VDAC_COMP|112 PCIe_CLK_N|113 GND|114 GND|115 CAM1_D0_N|116 PCIe_RX_P|117 CAM1_D0_P|118 PCIe_RX_N|
119 GND|120 GND|121 CAM1_D1_N|122 PCIe_TX_P|123 CAM1_D1_P|124 PCIe_TX_N|125 GND|126 GND|127 CAM1_C_N|128 CAM0_D0_N|
129 CAM1_C_P|130 CAM0_D0_P|131 GND|132 GND|133 CAM1_D2_N|134 CAM0_D1_N|135 CAM1_D2_P|136 CAM0_D1_P|137 GND|138 GND|
139 CAM1_D3_N|140 CAM0_C_N|141 CAM1_D3_P|142 CAM0_C_P|143 HDMI1_HOTPLUG|144 GND|145 HDMI1_SDA|146 HDMI1_TX2_P|
147 HDMI1_SCL|148 HDMI1_TX2_N|149 HDMI1_CEC|150 GND|151 HDMI0_CEC|152 HDMI1_TX1_P|153 HDMI0_HOTPLUG|154 HDMI1_TX1_N|
155 GND|156 GND|157 DSI0_D0_N|158 HDMI1_TX0_P|159 DSI0_D0_P|160 HDMI1_TX0_N|161 GND|162 GND|163 DSI0_D1_N|
164 HDMI1_CLK_P|165 DSI0_D1_P|166 HDMI1_CLK_N|167 GND|168 GND|169 DSI0_C_N|170 HDMI0_TX2_P|171 DSI0_C_P|
172 HDMI0_TX2_N|173 GND|174 GND|175 DSI1_D0_N|176 HDMI0_TX1_P|177 DSI1_D0_P|178 HDMI0_TX1_N|179 GND|180 GND|
181 DSI1_D1_N|182 HDMI0_TX0_P|183 DSI1_D1_P|184 HDMI0_TX0_N|185 GND|186 GND|187 DSI1_C_N|188 HDMI0_CLK_P|
189 DSI1_C_P|190 HDMI0_CLK_N|191 GND|192 GND|193 DSI1_D2_N|194 DSI1_D3_N|195 DSI1_D2_P|196 DSI1_D3_P|197 GND|198 GND|
199 HDMI0_SDA|200 HDMI0_SCL'''
for blk in (_A, _B):
    for it in blk.replace('\n', '').split('|'):
        n, name = it.split(' ', 1)
        CM4[int(n)] = name
assert sorted(CM4) == list(range(1, 201)), len(CM4)

# ---- H3 (CN1) use of every CM4 pin.  Signals named after the H3 function; CB1 (H616) positions followed.
# value = net name on both boards (the Mizban uses the same names), None = not connected on CN1.
GND_PINS = [n for n, v in CM4.items() if v == 'GND']
USE = {
    # Ethernet (H3 internal 10/100 EPHY, auto MDI/MDI-X) - same pins as CB1
    4: 'EPHY_TXP', 6: 'EPHY_TXN', 12: 'EPHY_RXP', 10: 'EPHY_RXN',
    15: 'EPHY_LINK_LED', 17: 'EPHY_SPD_LED',               # active low (CB1: LINK_LED / SPD_LED)
    21: 'LED_ACT_N',                                       # PI_nLED_Activity, active low (CB1: SYS-LED)
    95: 'LED_PWR_N',                                       # PI_LED_nPWR, active low
    # 40-pin header GPIOs - Raspberry Pi function positions
    58: 'GPIO2_SDA', 56: 'GPIO3_SCL', 54: 'GPIO4_TX2', 34: 'GPIO5_RX2', 30: 'GPIO6', 37: 'GPIO7_CE1', 39: 'GPIO8_CE0',
    40: 'GPIO9_MISO', 44: 'GPIO10_MOSI', 38: 'GPIO11_SCLK', 31: 'GPIO12', 28: 'GPIO13_PWM1', 55: 'GPIO14_TXD0',
    51: 'GPIO15_RXD0', 29: 'GPIO16_TX1', 50: 'GPIO17_RX1', 49: 'GPIO18_SPI1_CS', 26: 'GPIO19_SPI1_MISO',
    27: 'GPIO20_SPI1_MOSI', 25: 'GPIO21_SPI1_CLK', 46: 'GPIO22', 47: 'GPIO23', 45: 'GPIO24', 41: 'GPIO25',
    24: 'GPIO26', 48: 'GPIO27', 36: 'ID_SD', 35: 'ID_SC',
    # SD card (SDC0) - carrier holds the socket, CN1 holds pull-ups + series R
    57: 'SD_CLK', 62: 'SD_CMD', 63: 'SD_D0', 67: 'SD_D1', 69: 'SD_D2', 61: 'SD_D3', 76: 'SD_DET', 75: 'SD_PWR_ON',
    # power
    **{p: 'VCC_5V' for p in (77, 79, 81, 83, 85, 87)}, 84: 'VCC_3V3', 86: 'VCC_3V3', 88: 'VCC_1V8', 90: 'VCC_1V8',
    # system
    92: 'RUN_PG', 93: 'FEL_N', 99: 'GLOBAL_EN', 96: 'KEYADC', 97: 'KEY_USER',
    # USB: USB1 on the standard CM4 USB pins, USB0 (OTG) / USB2 / USB3 on the CAM0 lanes as CB1 does
    103: 'USB1_DM', 105: 'USB1_DP', 128: 'USB3_DM', 130: 'USB3_DP', 134: 'USB2_DM', 136: 'USB2_DP',
    140: 'USB0_DM', 142: 'USB0_DP', 101: 'USB0_ID',
    # audio / TV (CB1 positions)
    104: 'LINEOUT_L', 106: 'LINEOUT_R', 111: 'TV_OUT',
    # HDMI0
    170: 'HDMI_D2_P', 172: 'HDMI_D2_N', 176: 'HDMI_D1_P', 178: 'HDMI_D1_N', 182: 'HDMI_D0_P', 184: 'HDMI_D0_N',
    188: 'HDMI_CK_P', 190: 'HDMI_CK_N', 151: 'HDMI_CEC', 153: 'HDMI_HPD', 199: 'HDMI_SDA', 200: 'HDMI_SCL',
    **{p: 'GND' for p in GND_PINS},
}


def conn_symbol(which, role):
    """which 'A' (1-100) or 'B' (101-200); role 'plug' (module, DF40C-100DP) or 'rcpt' (carrier, DF40C-100DS)."""
    base = 0 if which == 'A' else 100
    left, right = [], []
    for k in range(1, 101):
        n = base + k
        name = CM4[n]
        et = 'passive'
        (left if k % 2 else right).append((str(n), name, et))
    part = 'DF40C-100DP-0.4V(51)' if role == 'plug' else 'DF40C-100DS-0.4V(51)'
    fp = '%s:CM4_%s_%s' % (LIB, 'DF40C-100DP' if role == 'plug' else 'DF40C-100DS', which)
    units = [dict(name='CM4 %s %d-%d' % (which, base + 1, base + 100), left=left, right=right)]
    if role == 'plug':
        units[0]['bottom'] = [('MP', 'MP', 'passive')]
    return make_ic('%s:CM4_%s_%s' % (LIB, which, role), units, ref='J', value=part, footprint=fp,
                   desc='Raspberry Pi CM4-compatible module connector %s (pins %d-%d), Hirose %s' % (which, base + 1, base + 100, part),
                   min_w=40.64)


def write_footprints(outdir):
    """copy the KiCad Hirose DF40 footprints, renumber pads to CM4 pin numbers (A: 1-100, B: 101-200)."""
    os.makedirs(outdir, exist_ok=True)
    src = '/usr/share/kicad/footprints/Connector_Hirose_DF40.pretty/'
    for role, fn in (('DF40C-100DP', 'Hirose_DF40C-100DP-0.4V_2x50-1MP_P0.4mm.kicad_mod'),
                     ('DF40C-100DS', 'Hirose_DF40C-100DS-0.4V_2x50_P0.4mm.kicad_mod')):
        t = open(src + fn).read()
        for which, base in (('A', 0), ('B', 100)):
            name = 'CM4_%s_%s' % (role, which)
            s = re.sub(r'\(footprint "[^"]*"', '(footprint "%s"' % name, t, count=1)
            s = re.sub(r'\(pad "(\d+)"', lambda m: '(pad "%d"' % (int(m.group(1)) + base), s)
            s = re.sub(r'\(property "Value" "[^"]*"', '(property "Value" "%s"' % name, s, count=1)
            open(os.path.join(outdir, name + '.kicad_mod'), 'w').write(s)
