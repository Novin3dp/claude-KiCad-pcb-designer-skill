#!/usr/bin/env python3
"""Mizban - carrier board for CN1 (or CB1 / CM4 with the same pin use), 4 layers, standard fab rules, <= 100 x 100 mm.

12-24 V in -> 5 V / 5 A, 4 x USB-A host + USB-C device (FEL / gadget) via FSUSB42 on USB0, HDMI-A, 10/100 RJ45 MagJack,
microSD with switched card power, 40-pin Raspberry Pi header, debug UART, reset / FEL / user keys, LEDs, 2 fan headers.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *            # noqa
from symbols import sy6280_symbol
import cm4

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'mizban', 'kicad')

CU = {'CM4_A_rcpt': cm4.conn_symbol('A', 'rcpt'), 'CM4_B_rcpt': cm4.conn_symbol('B', 'rcpt'), 'SY6280AAC': sy6280_symbol()}
cx = Ctx('mizban', rfp='R0603', cfp='C0603')
PRJ, LB = cx.PRJ, cx.lib
R, C, CAPS, L, FBEAD = cx.R, cx.C, cx.CAPS, cx.L, cx.FBEAD
nc = 'NC'

TVS_ = load_lib('Diode', 'SMAJ30CA')
SCH1A_ = load_lib('Diode', '1N5819WS')
ZEN_ = load_lib('Diode', 'BZT52Bxx')
PFET_ = load_lib('Transistor_FET', 'SUD50P06-15')
NFET_ = load_lib('Transistor_FET', 'BSS138')
NFET2_ = load_lib('Transistor_FET', 'AO3400A')
TERM_ = load_lib('Connector', 'Screw_Terminal_01x02')
HDR40_ = load_lib('Connector_Generic', 'Conn_02x20_Odd_Even')
HDR3_ = load_lib('Connector_Generic', 'Conn_01x03')
HDR2_ = load_lib('Connector_Generic', 'Conn_01x02')
SW_ = load_lib('Switch', 'SW_Push')
SLIDE_ = load_lib('Switch', 'SW_SPDT')
USBLC_ = load_lib('Power_Protection', 'USBLC6-2SC6')
TPS54560_ = load_lib('Regulator_Switching', 'TPS54560BDDA')
TPD4E_ = load_lib('Power_Protection', 'TPD4E05U06DQA')
RJ45_ = load_lib('Connector', 'RJ45_Hanrun_HR911105A_Horizontal')
HDMI_ = load_lib('Connector', 'HDMI_A')
USBAS_ = load_lib('Connector', 'USB_A_Stacked')
USBC_ = load_lib('Connector', 'USB_C_Receptacle_USB2.0_16P')
MUX_ = load_lib('Interface_USB', 'FSUSB42MUX')
SD_ = load_lib('Connector', 'Micro_SD_Card_Det1')

# CM4 pins the Mizban does not use (CN1 drives them, carrier leaves them open)
MIZ_NC = {88, 90,            # 1.8 V out (not needed here)
          96, 99,            # KEYADC, GLOBAL_EN (module pull-ups)
          104, 106, 111}     # line-out L/R, TV out: brought out in a later revision
USE = {n: v for n, v in cm4.USE.items() if n not in MIZ_NC}

# =============================================================== 1. module sockets
sh = PRJ.add_sheet(Sheet('Module Sockets', 'sockets.kicad_sch', 'CN1 / CM4 module sockets (Hirose DF40C-100DS receptacles, 1.5 mm stack)', paper='A2'))
fl = Flow(sh, 20, 25, 560, gap=10)
fl.section('CM4 MODULE SOCKETS  (J1 = pins 1-100, J2 = pins 101-200)',
           'Keep-out under the module: no parts taller than 0.9 mm between the sockets (CN1 has 0402 decoupling on its bottom side).\n'
           'M2.5 standoffs 1.5 mm on the CM4 pattern (48 x 33 mm) hold the module.  Net names are identical on CN1 and Mizban.\n'
           'Not used on this carrier: 1.8 V out (88/90), KEYADC (96), GLOBAL_EN (99), line-out (104/106), TV out (111), and all CM4-only pins (PCIe, CAM1, DSI, HDMI1).')
for which in ('A', 'B'):
    sd = CU['CM4_%s_rcpt' % which]
    conns = {p.num: USE.get(int(p.num), nc) for p in sd.pins}
    fl.add(sd, cx.ref('J'), 'DF40C-100DS-0.4V(51)', conns, footprint=sd_fp(sd), fields={'LCSC': 'C597931'})
CAPS(fl, 'VCC_5V', [('22uF 10V', 'C1206', 2), ('100nF', None, 2)])
CAPS(fl, 'VCC_3V3', [('10uF', None, 1), ('100nF', None, 1)])
cx.flag(fl, 'VCC_3V3')
fl.section('MOUNTING  (H1-H4: board corners, H5-H8: module standoffs on the CM4 48 x 33 mm pattern)')
for i in range(8):
    fl.add(LB.MHP, 'H%d' % (i + 1), 'M2.5', {'1': 'GND'}, footprint='MountingHole:MountingHole_2.7mm_M2.5_Pad_Via')

# =============================================================== 2. power input
sh = PRJ.add_sheet(Sheet('Power Input 12-24V', 'power_input.kicad_sch', '12-24 V input, protection, 5 V / 5 A buck', paper='A3'))
fl = Flow(sh, 20, 25, 385)
fl.section('12-24 V DC INPUT + PROTECTION',
           'Screw terminal (printer PSU).  F1 fuse -> Q1 P-MOSFET reverse-polarity protection (Vgs clamped by 12 V zener) -> 30 V TVS.\n'
           '9 V UVLO start (EN divider).  Everything rated >= 50 V except the TVS (30 V standoff).')
fl.add(TERM_, cx.ref('J'), '12-24V IN', {'1': 'VIN_RAW', '2': 'GND'},
       footprint='TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal')
fl.add(LB.FUSE, cx.ref('F'), '5A slow', {'1': 'VIN_RAW', '2': 'VIN_FUSED'}, rot=90, footprint='Fuse:Fuse_1812_4532Metric')
fl.add(PFET_, cx.ref('Q'), 'SUD50P06-15', {'G': 'Q1_GATE', 'D': 'VIN_FUSED', 'S': 'VIN_PROT'}, footprint='Package_TO_SOT_SMD:TO-252-2')
fl.add(ZEN_, cx.ref('D'), 'BZT52B12', {'K': 'VIN_PROT', 'A': 'Q1_GATE'}, footprint='Diode_SMD:D_SOD-123F')
R(fl, '100k', 'Q1_GATE', 'GND')
fl.add(TVS_, cx.ref('D'), 'SMAJ30CA', {'1': 'VIN_PROT', '2': 'GND'}, footprint='Diode_SMD:D_SMA')
fl.add(LB.CP, cx.ref('C'), '100uF 35V', {'1': 'VIN_PROT', '2': 'GND'}, rot=90, footprint='Capacitor_SMD:CP_Elec_8x10')
CAPS(fl, 'VIN_PROT', [('4.7uF 50V', 'C1210', 2), ('100nF 50V', None, 1)])
cx.flag(fl, 'VIN_PROT')
cx.flag(fl, 'GND')
fl.section('5 V / 5 A BUCK (TPS54560, 500 kHz)',
           'Vout = 0.8 V x (1 + 52.3k/10k) = 4.98 V.   RT = 191k -> ~505 kHz.  EN divider 226k/33.2k: start ~9 V, stop ~8 V.\n'
           'Budget: CN1 ~1.5 A, 4 x USB 1 A (limited), HDMI 55 mA, fans.  Compensation 16.9k + 4.7nF (+47pF) - confirm with TI WEBENCH.')
fl.add(TPS54560_, cx.ref('U'), 'TPS54560BDDA', {'VIN': 'VIN_PROT', 'EN': 'BUCK_EN', 'COMP': 'BUCK_COMP', 'RT/CLK': 'BUCK_RT', 'GND': 'GND',
                                                'BOOT': 'BUCK_BOOT', 'SW': 'BUCK_SW', 'FB': 'BUCK_FB'},
       footprint='Package_SO:Texas_R-PDSO-G8_EP2.95x4.9mm_Mask2.4x3.1mm_ThermalVias')
R(fl, '226k 1%', 'VIN_PROT', 'BUCK_EN')
R(fl, '33.2k 1%', 'BUCK_EN', 'GND')
R(fl, '191k 1%', 'BUCK_RT', 'GND')
C(fl, '100nF', 'BUCK_BOOT', 'BUCK_SW')
fl.add(LB.DSCH, cx.ref('D'), 'B560C', {'K': 'BUCK_SW', 'A': 'GND'}, footprint='Diode_SMD:D_SMC')
L(fl, '10uH 7A', 'BUCK_SW', 'VCC_5V', 'Inductor_SMD:L_Bourns_SRP1245A', 'SRP1245A-100M')
R(fl, '52.3k 1%', 'VCC_5V', 'BUCK_FB')
R(fl, '10k 1%', 'BUCK_FB', 'GND')
R(fl, '16.9k', 'BUCK_COMP', 'BUCK_COMP_RC')
C(fl, '4.7nF', 'BUCK_COMP_RC', 'GND')
C(fl, '47pF', 'BUCK_COMP', 'GND')
CAPS(fl, 'VCC_5V', [('47uF 10V', 'C1210', 3), ('100nF', None, 1)])
cx.flag(fl, 'VCC_5V')
fl.section('FANS + 5 V INDICATOR',
           'FAN1: always on.  FAN2: low-side AO3400A switched by GPIO13 (PWM1, header pin 33 - do not use pin 33 for anything else when FAN2 is fitted).')
cx.LEDR(fl, 'GREEN', '4.7k', 'VCC_5V', 'GND')
fl.add(HDR2_, cx.ref('J'), 'FAN1 5V', {'1': 'VCC_5V', '2': 'GND'}, footprint='Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical')
fl.add(HDR2_, cx.ref('J'), 'FAN2 5V PWM', {'1': 'VCC_5V', '2': 'FAN2_N'}, footprint='Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical')
fl.add(NFET2_, cx.ref('Q'), 'AO3400A', {'G': 'FAN2_G', 'S': 'GND', 'D': 'FAN2_N'}, footprint='Package_TO_SOT_SMD:SOT-23')
R(fl, '1k', 'GPIO13_PWM1', 'FAN2_G')
R(fl, '100k', 'FAN2_G', 'GND')
fl.add(SCH1A_, cx.ref('D'), '1N5819WS', {'A': 'FAN2_N', 'K': 'VCC_5V'}, footprint='Diode_SMD:D_SOD-323')

# =============================================================== 3. USB
sh = PRJ.add_sheet(Sheet('USB', 'usb.kicad_sch', '4 x USB-A host (USB1/2/3 native, USB0 via FSUSB42) + USB-C device port (FEL / OTG)', paper='A2'))
fl = Flow(sh, 20, 25, 560)
fl.section('4 x USB-A HOST - no hub: the H3 has four USB 2.0 controllers (CN1 brings all four out, like CB1)',
           'Each port: SY6280AAC current-limited switch (Rset 6.8k -> 1.0 A), USBLC6-2SC6 ESD at the connector, 47 uF bulk.  90 ohm differential routing.\n'
           'USB1 -> port A1, USB2 -> A2, USB3 -> A3, USB0 -> FSUSB42 HSD1 -> A4 (host).  USB_VBUS_EN pulled up: ports always powered.')
for i, (port, dp, dm) in enumerate((('A1', 'USB1_DP', 'USB1_DM'), ('A2', 'USB2_DP', 'USB2_DM'), ('A3', 'USB3_DP', 'USB3_DM'), ('A4', 'USB0A_DP', 'USB0A_DM'))):
    vb = 'VBUS_%s' % port
    fl.add(CU['SY6280AAC'], cx.ref('U'), 'SY6280AAC', {'IN': 'VCC_5V', 'EN': 'USB_VBUS_EN', 'GND': 'GND', 'OUT': vb, 'ISET': 'ISET_%s' % port},
           footprint='Package_TO_SOT_SMD:SOT-23-5')
    R(fl, '6.8k 1%', 'ISET_%s' % port, 'GND')
    fl.add(USBLC_, cx.ref('U'), 'USBLC6-2SC6', {'1': dp, '6': dp, '3': dm, '4': dm, '5': vb, '2': 'GND'}, footprint='Package_TO_SOT_SMD:SOT-23-6')
    C(fl, '47uF 10V', vb, 'GND', 'C1206')
    C(fl, '100nF', vb, 'GND')
    if i % 2 == 1:
        a = 'A%d' % i
        pa = (('USB1_DP', 'USB1_DM'), ('USB2_DP', 'USB2_DM'), ('USB3_DP', 'USB3_DM'), ('USB0A_DP', 'USB0A_DM'))
        (adp, adm), (bdp, bdm) = pa[i - 1], pa[i]
        fl.add(USBAS_, cx.ref('J'), 'USB-A x2 stacked (%s / %s)' % ('A%d' % i, 'A%d' % (i + 1)),
               {'VBUS1': 'VBUS_A%d' % i, 'D1-': adm, 'D1+': adp, 'GND1': 'GND',
                'VBUS2': 'VBUS_A%d' % (i + 1), 'D2-': bdm, 'D2+': bdp, 'GND2': 'GND', 'Shield': 'GND'},
               footprint='Connector_USB:USB_A_Wuerth_61400826021_Horizontal_Stacked',
               fields={'Note': 'any 2-port stacked right-angle USB-A; check pinout vs footprint'})
    fl.newrow()
R(fl, '10k', 'VCC_3V3', 'USB_VBUS_EN')
CAPS(fl, 'VCC_5V', [('10uF', None, 2), ('100nF', None, 2)])
fl.section('USB0 ROLE SWITCH - FSUSB42 (as on the BTT PI4B adapter) + USB-C device port',
           'SW1 "USB0" slide switch: HOST (default, USB_MODE low) -> USB0 on USB-A port 4, H3 USB0_ID (PG12, CM4 pin 101) low.\n'
           'DEVICE (USB_MODE high) -> USB0 on the USB-C port: FEL recovery (with the FEL key) or Linux USB gadget.  USB-C is a sink: CC 5.1k, VBUS not tied to 5 V.')
fl.add(MUX_, cx.ref('U'), 'FSUSB42MUX', {'VCC': 'VCC_3V3', 'SEL': 'USB_MODE', 'D+': 'USB0_DP', 'D-': 'USB0_DM', 'GND': 'GND',
                                         'HSD1+': 'USB0A_DP', 'HSD1-': 'USB0A_DM', 'HSD2+': 'USBC_DP', 'HSD2-': 'USBC_DM', '~{OE}': 'GND'},
       footprint='Package_SO:MSOP-10_3x3mm_P0.5mm')
C(fl, '100nF', 'VCC_3V3', 'GND')
fl.add(SLIDE_, cx.ref('SW'), 'USB0 HOST/DEV', {'1': 'GND', '2': 'USB_MODE', '3': 'VCC_3V3'},
       footprint='Button_Switch_SMD:SW_SPDT_PCM12')
R(fl, '10k', 'USB_MODE', 'USB0_ID')
R(fl, '100k', 'USB_MODE', 'GND')
fl.add(USBC_, cx.ref('J'), 'USB-C (USB0 device)', {'A1': 'GND', 'A12': 'GND', 'B1': 'GND', 'B12': 'GND', 'A4': 'USBC_VBUS', 'A9': 'USBC_VBUS',
                                                    'B4': 'USBC_VBUS', 'B9': 'USBC_VBUS', 'A5': 'USBC_CC1', 'B5': 'USBC_CC2',
                                                    'A6': 'USBC_DP', 'B6': 'USBC_DP', 'A7': 'USBC_DM', 'B7': 'USBC_DM',
                                                    'A8': nc, 'B8': nc, 'SH': 'GND'},
       footprint='Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12')
R(fl, '5.1k', 'USBC_CC1', 'GND')
R(fl, '5.1k', 'USBC_CC2', 'GND')
C(fl, '1uF 16V', 'USBC_VBUS', 'GND')
R(fl, '100k', 'USBC_VBUS', 'GND')
fl.add(USBLC_, cx.ref('U'), 'USBLC6-2SC6', {'1': 'USBC_DP', '6': 'USBC_DP', '3': 'USBC_DM', '4': 'USBC_DM', '5': 'USBC_VBUS', '2': 'GND'},
       footprint='Package_TO_SOT_SMD:SOT-23-6')

# =============================================================== 4. HDMI
sh = PRJ.add_sheet(Sheet('HDMI', 'hdmi.kicad_sch', 'HDMI 1.4 Type-A output (KlipperScreen)', paper='A3'))
fl = Flow(sh, 20, 25, 385)
fl.section('HDMI OUTPUT',
           'TMDS pairs 100 ohm differential, length matched (CM4 pins 170-190), flow-through ESD (TPD4E05U06) next to the connector.\n'
           'HPD goes straight to the module (CN1 divides it to 3.3 V).  DDC 1.8k to +5V_HDMI (HDMI spec).  CEC isolated with BSS138 (module-off safe).')
fl.add(HDMI_, cx.ref('J'), 'HDMI-A', {'D2+': 'HDMI_D2_P', 'D2-': 'HDMI_D2_N', 'D1+': 'HDMI_D1_P', 'D1-': 'HDMI_D1_N', 'D0+': 'HDMI_D0_P',
                                      'D0-': 'HDMI_D0_N', 'CK+': 'HDMI_CK_P', 'CK-': 'HDMI_CK_N', 'CEC': 'HDMI_CEC_C', 'SCL': 'HDMI_SCL',
                                      'SDA': 'HDMI_SDA', 'UTILITY': nc, 'HPD': 'HDMI_HPD', 'D2S': 'GND', 'D1S': 'GND', 'D0S': 'GND',
                                      'CKS': 'GND', 'GND': 'GND', 'SH': 'GND', '+5V': 'VCC_5V_HDMI'},
       footprint='Connector_Video:HDMI_A_Molex_208658-1001_Horizontal')
for a, b, c_, d in (('HDMI_D2_P', 'HDMI_D2_N', 'HDMI_D1_P', 'HDMI_D1_N'), ('HDMI_D0_P', 'HDMI_D0_N', 'HDMI_CK_P', 'HDMI_CK_N')):
    fl.add(TPD4E_, cx.ref('D'), 'TPD4E05U06DQA', {'1': a, '2': b, '4': c_, '5': d, '3': 'GND', '8': 'GND', '10': a, '9': b, '7': c_, '6': d},
           footprint='Package_SON:USON-10_2.5x1.0mm_P0.5mm')
fl.newrow()
fl.add(SCH1A_, cx.ref('D'), '1N5819WS', {'A': 'VCC_5V', 'K': 'VCC_5V_HDMI'}, footprint='Diode_SMD:D_SOD-323')
C(fl, '100nF', 'VCC_5V_HDMI', 'GND')
R(fl, '1.8k', 'VCC_5V_HDMI', 'HDMI_SCL')
R(fl, '1.8k', 'VCC_5V_HDMI', 'HDMI_SDA')
fl.add(NFET_, cx.ref('Q'), 'BSS138', {'G': 'VCC_3V3', 'S': 'HDMI_CEC', 'D': 'HDMI_CEC_C'}, footprint='Package_TO_SOT_SMD:SOT-23')
R(fl, '27k', 'HDMI_CEC_C', 'CEC_PU')
fl.add(SCH1A_, cx.ref('D'), '1N5819WS', {'A': 'CEC_PU', 'K': 'VCC_3V3'}, footprint='Diode_SMD:D_SOD-323')
cx.flag(fl, 'VCC_5V_HDMI')

# =============================================================== 5. Ethernet + microSD
sh = PRJ.add_sheet(Sheet('Ethernet & microSD', 'eth_sd.kicad_sch', '10/100 Ethernet MagJack + microSD socket with switched card power', paper='A3'))
fl = Flow(sh, 20, 25, 385)
fl.section('10/100 ETHERNET (H3 internal EPHY on CN1, auto MDI/MDI-X)',
           'EPHY TX (CM4 pins 4/6) -> TD+/TD-, RX (12/10) -> RD+/RD-: 100 ohm differential straight to the HR911105A (magnetics inside).\n'
           'LED outputs active low (CM4 pins 15 / 17).  Center taps AC-coupled to GND.  Shield to GND through 1 nF / 2 kV || 1M.')
fl.add(RJ45_, cx.ref('J'), 'HR911105A', {'1': 'EPHY_TXP', '2': 'EPHY_TXN', '3': 'EPHY_RXP', '6': 'EPHY_RXN', '4': 'ETH_TCT', '5': 'ETH_RCT',
                                         '7': nc, '8': 'ETH_CHASSIS', 'SH': 'ETH_CHASSIS', '12': 'ETH_LED1_A', '11': 'EPHY_LINK_LED',
                                         '9': 'ETH_LED2_A', '10': 'EPHY_SPD_LED'},
       footprint='Connector_RJ:RJ45_Hanrun_HR911105A_Horizontal')
C(fl, '100nF', 'ETH_TCT', 'GND')
C(fl, '100nF', 'ETH_RCT', 'GND')
R(fl, '330R', 'VCC_3V3', 'ETH_LED1_A')
R(fl, '330R', 'VCC_3V3', 'ETH_LED2_A')
C(fl, '1nF 2kV', 'ETH_CHASSIS', 'GND', 'C1206')
R(fl, '1M', 'ETH_CHASSIS', 'GND')
cx.flag(fl, 'ETH_CHASSIS')
fl.section('microSD (SDC0 - boot device)',
           'Card power switched by SD_PWR_ON (CM4 pin 75, high from reset on CN1) through a SY6280 (Rset 10k -> ~0.7 A), as the PI4B adapter does.\n'
           'Pull-ups and the 33R CLK series resistor are on the module.  DET low = card present.')
fl.add(SD_, cx.ref('J'), 'microSD', {'DAT2': 'SD_D2', 'DAT3/CD': 'SD_D3', 'CMD': 'SD_CMD', 'VDD': 'SD_VDD', 'CLK': 'SD_CLK', 'VSS': 'GND',
                                     'DAT0': 'SD_D0', 'DAT1': 'SD_D1', 'DET': 'SD_DET', 'SHIELD': 'GND'},
       footprint='Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5')
fl.add(CU['SY6280AAC'], cx.ref('U'), 'SY6280AAC', {'IN': 'VCC_3V3', 'EN': 'SD_PWR_ON', 'GND': 'GND', 'OUT': 'SD_VDD', 'ISET': 'SD_ISET'},
       footprint='Package_TO_SOT_SMD:SOT-23-5')
R(fl, '10k 1%', 'SD_ISET', 'GND')
CAPS(fl, 'SD_VDD', [('10uF', None, 1), ('100nF', None, 1)])
C(fl, '1uF', 'VCC_3V3', 'GND')

# =============================================================== 6. IO
sh = PRJ.add_sheet(Sheet('GPIO Header, Debug, Keys', 'io.kicad_sch', '40-pin Raspberry Pi header, debug UART, reset / FEL / user keys, LEDs', paper='A3'))
fl = Flow(sh, 20, 25, 560)
fl.section('40-PIN GPIO HEADER - Raspberry Pi physical layout and BCM GPIO positions (CM4 pins -> H3 on CN1)',
           'I2C GPIO2/3 = TWI0, UART GPIO14/15 = UART0 (console), SPI0 GPIO7-11, SPI1 GPIO16-21 (SPI1 on 18-21), UART1 GPIO16/17, UART2 GPIO4/5, PWM1 GPIO13.\n'
           'ID_SD/ID_SC (27/28) = TWI1.  All IO are 3.3 V only.  1.8k pull-ups on GPIO2/3 as on the Raspberry Pi.')
hdr = {1: 'VCC_3V3', 2: 'VCC_5V', 3: 'GPIO2_SDA', 4: 'VCC_5V', 5: 'GPIO3_SCL', 6: 'GND', 7: 'GPIO4_TX2', 8: 'GPIO14_TXD0', 9: 'GND',
       10: 'GPIO15_RXD0', 11: 'GPIO17_RX1', 12: 'GPIO18_SPI1_CS', 13: 'GPIO27', 14: 'GND', 15: 'GPIO22', 16: 'GPIO23', 17: 'VCC_3V3',
       18: 'GPIO24', 19: 'GPIO10_MOSI', 20: 'GND', 21: 'GPIO9_MISO', 22: 'GPIO25', 23: 'GPIO11_SCLK', 24: 'GPIO8_CE0', 25: 'GND',
       26: 'GPIO7_CE1', 27: 'ID_SD', 28: 'ID_SC', 29: 'GPIO5_RX2', 30: 'GND', 31: 'GPIO6', 32: 'GPIO12', 33: 'GPIO13_PWM1', 34: 'GND',
       35: 'GPIO19_SPI1_MISO', 36: 'GPIO16_TX1', 37: 'GPIO26', 38: 'GPIO20_SPI1_MOSI', 39: 'GND', 40: 'GPIO21_SPI1_CLK'}
fl.add(HDR40_, cx.ref('J'), 'GPIO 2x20', {str(k): v for k, v in hdr.items()}, footprint='Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical')
R(fl, '1.8k', 'VCC_3V3', 'GPIO2_SDA')
R(fl, '1.8k', 'VCC_3V3', 'GPIO3_SCL')
R(fl, '4.7k', 'VCC_3V3', 'ID_SD')
R(fl, '4.7k', 'VCC_3V3', 'ID_SC')
fl.section('DEBUG UART0 (GPIO14/15 = H3 PA4/PA5, 115200 8N1 - U-Boot + Linux console; same signals as header pins 8/10)')
fl.add(HDR3_, cx.ref('J'), 'DEBUG', {'1': 'GND', '2': 'DBG_RX', '3': 'DBG_TX'}, footprint='Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical')
R(fl, '100R', 'GPIO14_TXD0', 'DBG_TX')
R(fl, '100R', 'DBG_RX', 'GPIO15_RXD0')
fl.section('KEYS',
           'RESET pulls RUN_PG (CM4 pin 92) low.  FEL (CM4 pin 93, nRPIBOOT position) held during reset -> USB-FEL on USB0 (set SW1 to DEVICE).\n'
           'USER key on CM4 pin 97 (H3 PL3, gpio-keys KEY_POWER for a clean shutdown).  Pull-ups are on CN1.')
fl.add(SW_, cx.ref('SW'), 'RESET', {'1': 'RUN_PG', '2': 'GND'}, footprint='Button_Switch_SMD:SW_SPST_TL3342')
fl.add(SW_, cx.ref('SW'), 'FEL', {'1': 'FEL_N', '2': 'GND'}, footprint='Button_Switch_SMD:SW_SPST_TL3342')
fl.add(SW_, cx.ref('SW'), 'USER', {'1': 'KEY_USER', '2': 'GND'}, footprint='Button_Switch_SMD:SW_SPST_TL3342')
fl.section('LEDs (CM4 LED pins are active low: LED from 3.3 V to the pin)',
           'ACT (green) on PI_nLED_Activity (pin 21, H3 PA17), PWR (red) on PI_LED_nPWR (pin 95, H3 PL10).')
cx.LEDR(fl, 'GREEN', '1k', 'VCC_3V3', 'LED_ACT_N')
cx.LEDR(fl, 'RED', '1k', 'VCC_3V3', 'LED_PWR_N')

PRJ.root_texts = [
    ('MIZBAN  -  carrier board for the CN1 H3 module (CM4 / CB1 footprint), 4 layers, standard rules, <= 100 x 100 mm', 25, 185, 2.5),
    ('12-24 V -> F1 -> Q1 (reverse polarity) -> TPS54560 5 V / 5 A -> CN1 (5 V in) ; CN1 3.3 V out -> SD card switch, LEDs, header\n'
     '4 x USB-A (USB1/2/3 + USB0 via FSUSB42) | USB-C device (FEL) | HDMI-A | RJ45 10/100 | microSD | 40-pin RPi header | debug UART | 3 keys | 2 fans', 25, 195, 1.8),
    ('Generated by h3-two-board/gen/build_mizban.py - net names match CN1 on every module pin', 25, 207, 1.8),
]
cx.write(OUT, 'Mizban - CN1 carrier board', CU)
cm4.write_footprints(os.path.join(OUT, 'klipper_h3.pretty'))
print('Mizban sheets:', len(PRJ.sheets), 'global nets:', len(PRJ.global_nets))
