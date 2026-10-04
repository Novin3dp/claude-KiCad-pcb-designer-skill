#!/usr/bin/env python3
"""CN1 - Allwinner H3 compute module, Raspberry Pi CM4 form factor (55 x 40 mm, 2 x Hirose DF40 100-pin).

Pin positions follow BIGTREETECH CB1 (H616) so CN1 is a drop-in on CB1 / CM4 carriers (PI4B adapter, Manta, CM4IO)
for Ethernet, USB, HDMI0, SD, UART0 and the 40-pin GPIO header.  5 V in, 3.3 V / 1.8 V out.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *            # noqa
from symbols import all_custom, H3, DDR3_NC
import cm4

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cn1', 'kicad')

CU = all_custom()
CU['CM4_A_plug'] = cm4.conn_symbol('A', 'plug')
CU['CM4_B_plug'] = cm4.conn_symbol('B', 'plug')
cx = Ctx('cn1', rfp='R0402', cfp='C0402')
PRJ, LB = cx.PRJ, cx.lib
PRJ.refcount['U'] = 1   # U1 = Allwinner H3 (multi-unit)
R, C, CAPS, L, FBEAD = cx.R, cx.C, cx.CAPS, cx.L, cx.FBEAD

NFET_ = load_lib('Transistor_FET', 'BSS138')
COAX_ = load_lib('Connector', 'Conn_Coaxial')
TPS563201_ = load_lib('Regulator_Switching', 'TPS563201')
TPS562201_ = load_lib('Regulator_Switching', 'TPS562200')   # TPS562201 = same pinout / Vref (FCCM variant)
TPS3808_ = load_lib('Power_Supervisor', 'TPS3808DBV')
LDO18_ = load_lib('Regulator_Linear', 'TLV75518PDBV')
nc = 'NC'
L4018 = 'Inductor_SMD:L_Bourns-SRN4018'
L3015 = 'Inductor_SMD:L_Taiyo-Yuden_NR-30xx'


def H3U(fl, unit, conns, ref='U1'):
    sd = CU['Allwinner_H3']
    full = {}
    for p in sd.unit_pins(unit):
        short = H3[p.num][0]
        for k in (p.num, short, p.name):
            if k in conns:
                full[p.num] = conns[k]
                break
    return fl.add(sd, ref, 'Allwinner H3', full, unit=unit, footprint=sd_fp(sd))


# =============================================================== 1. module connectors
sh = PRJ.add_sheet(Sheet('Module Connectors', 'connectors.kicad_sch', 'CM4-compatible module connectors (Hirose DF40C-100DP plugs, bottom side)', paper='A2'))
fl = Flow(sh, 20, 25, 560, gap=10)
fl.section('CM4 MODULE CONNECTORS  (J1 = pins 1-100, J2 = pins 101-200, bottom side, 1.5 mm stack with DF40C-100DS on the carrier)',
           'Pin positions follow BIGTREETECH CB1: Ethernet 4/6/10/12, LEDs 15/17/21, UART0 on GPIO14/15 (55/51), SD on 57-76, 5 V in 77-87,\n'
           '3.3 V out 84/86, 1.8 V out 88/90, RUN_PG 92, nRPIBOOT = FEL 93, USB1 103/105, USB3/USB2/USB0 on CAM0 lanes 128-142, HDMI0 151-200.\n'
           'Differences to CB1: EPHY RX uses the CM4 P/N labels (RXP on 12), header GPIOs keep the Raspberry Pi functions (I2C GPIO2/3, SPI0 GPIO7-11, SPI1 GPIO16-21).')
for which in ('A', 'B'):
    sd = CU['CM4_%s_plug' % which]
    conns = {}
    for p in sd.pins:
        if p.num == 'MP':
            conns['MP'] = 'GND'
            continue
        conns[p.num] = cm4.USE.get(int(p.num), nc)
    fl.add(sd, cx.ref('J'), 'DF40C-100DP-0.4V(51)', conns, footprint=sd_fp(sd),
           fields={'LCSC': 'C531031', 'Side': 'bottom'})
cx.flag(fl, 'VCC_5V')
cx.flag(fl, 'GND')
CAPS(fl, 'VCC_5V', [('22uF 10V', 'C0805', 2), ('100nF', None, 1)])

# =============================================================== 2. power
sh = PRJ.add_sheet(Sheet('Power', 'power.kicad_sch', 'H3 rails from the 5 V module input (TI TPS563201 / TPS562201, TLV755 1.8 V)', paper='A2'))
fl = Flow(sh, 20, 25, 560)
fl.section('VCC_3V3 3.3 V / 3 A  (TPS563201DDCR) - first rail, enabled by GLOBAL_EN (CM4 pin 99, pull low = module off)',
           'Vout = 0.768 V x (1 + 33.2k/10k) = 3.32 V.  Feeds VCC-IO/PC/PD/PG, AVCC/RTC/PLL (through FB), USB PHY, HDMI, EPHY, WiFi and the 3.3 V output (pins 84/86).\n'
           'All other bucks are enabled from pull-ups to VCC_3V3 (PL8 / PL9), so they start after 3.3 V - the H3 power-on order (AVCC/RTC first).')
ti_buck(cx, fl, 'TPS563201DDCR', TPS563201_, 'VCC_5V', 'GLOBAL_EN', 'V3', 'VCC_3V3', '33.2k 1%', '10k 1%', '2.2uH 3.4A', L4018, 'SRN4018-2R2M',
        [('10uF', 'C0603', 2), ('100nF', None, 1)], [('22uF', 'C0805', 2), ('100nF', None, 1)])
R(fl, '100k', 'VCC_5V', 'GLOBAL_EN')
cx.flag(fl, 'VCC_3V3')

fl.section('VDD_CPUX 1.1 / 1.3 V / 3 A  (TPS563201DDCR, PL6 voltage select - Orange Pi One / NanoPi scheme)',
           'Q off (PL6 = 0 / reset): 0.768 x (1 + 9.53k/22.1k) = 1.10 V.   Q on (PL6 = 1): Rbot || 36.5k -> 1.30 V (1.2 GHz).\n'
           'FB top from ball VDD-CPUFB (remote sense).  DNP 0R = local sense.  EN = PWR_STB (PL8, pull-up to 3.3 V).')
ti_buck(cx, fl, 'TPS563201DDCR', TPS563201_, 'VCC_5V', 'PWR_STB', 'CPUX', 'VDD_CPUX', '9.53k 1%', '22.1k 1%', '2.2uH 3.4A', L4018, 'SRN4018-2R2M',
        [('10uF', 'C0603', 2), ('100nF', None, 1)], [('22uF', 'C0805', 3), ('100nF', None, 1)], fb_top='VDD_CPUX_FB')
R(fl, '36.5k 1%', 'CPUX_FB', 'CPUX_SEL_D')
fl.add(NFET_, cx.ref('Q'), 'BSS138', {'G': 'CPUX_VSEL', 'S': 'GND', 'D': 'CPUX_SEL_D'}, footprint='Package_TO_SOT_SMD:SOT-23')
R(fl, '100k', 'CPUX_VSEL', 'GND')
R(fl, '0R DNP', 'VDD_CPUX', 'VDD_CPUX_FB', dnp=True)
cx.flag(fl, 'VDD_CPUX')

fl.section('VDD_SYS 1.2 V / 2 A  (TPS562201DDCR)', 'Vout = 0.768 x (1 + 5.62k/10k) = 1.20 V.  EN = PWR_STB (PL8).')
ti_buck(cx, fl, 'TPS562201DDCR', TPS562201_, 'VCC_5V', 'PWR_STB', 'SYS', 'VDD_SYS', '5.62k 1%', '10k 1%', '2.2uH 3.4A', L4018, 'SRN4018-2R2M',
        [('10uF', 'C0603', 1), ('100nF', None, 1)], [('22uF', 'C0805', 2), ('100nF', None, 1)])
cx.flag(fl, 'VDD_SYS')

fl.section('VCC_DRAM 1.5 V / 2 A  (TPS562201DDCR)', 'Vout = 0.768 x (1 + 9.53k/10k) = 1.50 V (DDR3).  DDR3L 1.35 V: R_top = 7.68k.  EN = PWR_DRAM (PL9).  One x16 chip: < 0.5 A.')
ti_buck(cx, fl, 'TPS562201DDCR', TPS562201_, 'VCC_5V', 'PWR_DRAM', 'DRAM', 'VCC_DRAM', '9.53k 1%', '10k 1%', '2.2uH 1.5A', L3015, 'NR3015T2R2M',
        [('10uF', 'C0603', 1), ('100nF', None, 1)], [('22uF', 'C0805', 2), ('100nF', None, 1)])
cx.flag(fl, 'VCC_DRAM')
R(fl, '10k', 'VCC_3V3', 'PWR_STB')
R(fl, '10k', 'VCC_3V3', 'PWR_DRAM')

fl.section('VCC_1V8 1.8 V / 0.5 A LDO (TLV75518PDBV) - CM4 1.8 V output on pins 88/90 (carrier use only, not used by the H3)')
fl.add(LDO18_, cx.ref('U'), 'TLV75518PDBV', {'IN': 'VCC_3V3', 'GND': 'GND', 'EN': 'VCC_3V3', 'NC': nc, 'OUT': 'VCC_1V8'},
       footprint='Package_TO_SOT_SMD:SOT-23-5')
CAPS(fl, 'VCC_1V8', [('1uF', None, 1)])

fl.section('FILTERED SUB-RAILS',
           'AVCC = VCC-RTC = VCC-PLL = V33-TV (analog / always-on group) through a ferrite from 3.3 V.  EPHY 1.1 V from VDD_SYS through 2R (Orange Pi practice).\n'
           'EPHY 3.3 V and WiFi 3.3 V through ferrite beads.  Power LED (green) on 3.3 V, like CB1.')
FBEAD(fl, '120R@100MHz', 'VCC_3V3', 'AVCC')
CAPS(fl, 'AVCC', [('10uF', 'C0603', 1)])
R(fl, '2R 1%', 'VDD_SYS', 'VDD1V1_EPHY')
CAPS(fl, 'VDD1V1_EPHY', [('1uF', None, 1)])
FBEAD(fl, '120R@100MHz', 'VCC_3V3', 'VCC_EPHY')
CAPS(fl, 'VCC_EPHY', [('10uF', 'C0603', 1)])
FBEAD(fl, '120R@100MHz 2A', 'VCC_3V3', 'VCC_WIFI', 'FB0603')
CAPS(fl, 'VCC_WIFI', [('10uF', 'C0603', 1)])
for n in ('AVCC', 'VDD1V1_EPHY', 'VCC_EPHY', 'VCC_WIFI'):
    cx.flag(fl, n)
cx.LEDR(fl, 'GREEN', '1k', 'VCC_3V3', 'GND')

# =============================================================== 3. SoC GPIO / system
sh = PRJ.add_sheet(Sheet('SoC GPIO & System', 'soc_system.kicad_sch', 'Allwinner H3 - GPIO, clocks, reset, HDMI/USB/EPHY/audio pins', paper='A1'))
fl = Flow(sh, 20, 25, 560, gap=6)
fl.section('PORT A / C / F / G -> CM4 connector',
           'PA: 40-pin header (UART0 = GPIO14/15, UART2 = GPIO4/5, TWI0 = GPIO2/3, TWI1 = ID_SD/ID_SC, SPI1 = GPIO18-21, PWM1 = GPIO13).  PA17 = activity LED.\n'
           'PC0-PC3: SPI0 = GPIO10/9/11/8 (Klipper ADXL345 wiring of the Raspberry Pi).  PF: SD card (SDC0, boot).  PG0-5: WiFi SDIO.  PG6/7: UART1 = GPIO16/17.  PG12: USB0 ID.')
H3U(fl, 2, {'PA0': 'GPIO4_TX2', 'PA1': 'GPIO5_RX2', 'PA2': 'GPIO12', 'PA3': 'GPIO6', 'PA4': 'GPIO14_TXD0', 'PA5': 'GPIO15_RXD0',
            'PA6': 'GPIO13_PWM1', 'PA7': 'GPIO22', 'PA8': 'GPIO23', 'PA9': 'GPIO24', 'PA10': 'GPIO25', 'PA11': 'GPIO3_SCL', 'PA12': 'GPIO2_SDA',
            'PA13': 'GPIO18_SPI1_CS', 'PA14': 'GPIO21_SPI1_CLK', 'PA15': 'GPIO20_SPI1_MOSI', 'PA16': 'GPIO19_SPI1_MISO', 'PA17': 'LED_ACT_N',
            'PA18': 'ID_SC', 'PA19': 'ID_SD', 'PA20': 'GPIO26', 'PA21': 'GPIO27',
            'PF0': 'SD_D1', 'PF1': 'SD_D0', 'PF2': 'SD_CLK_H3', 'PF3': 'SD_CMD', 'PF4': 'SD_D3', 'PF5': 'SD_D2', 'PF6': 'SD_DET'})
H3U(fl, 3, dict({'PC0': 'GPIO10_MOSI', 'PC1': 'GPIO9_MISO', 'PC2': 'GPIO11_SCLK', 'PC3': 'GPIO8_CE0', 'PC4': 'GPIO7_CE1',
                 'PG0': 'WL_SDIO_CLK', 'PG1': 'WL_SDIO_CMD', 'PG2': 'WL_SDIO_D0', 'PG3': 'WL_SDIO_D1', 'PG4': 'WL_SDIO_D2',
                 'PG5': 'WL_SDIO_D3', 'PG6': 'GPIO16_TX1', 'PG7': 'GPIO17_RX1', 'PG8': nc, 'PG9': nc,
                 'PG10': 'WL_WAKE_HOST', 'PG11': nc, 'PG12': 'USB0_ID', 'PG13': nc},
                **{'PC%d' % i: nc for i in range(5, 17)}))
fl.newrow()
fl.section('PORT D / E (unused) and PORT L / SYSTEM',
           'PL3 = user key (CM4 pin 97).  PL6 = VDD_CPUX select.  PL7 = WiFi enable.  PL8 / PL9 = rail enables.  PL10 = power LED (CM4 pin 95, active low).\n'
           'RESET = RUN_PG (CM4 pin 92): open-drain, TPS3808 + carrier reset key.  UBOOT = FEL_N (CM4 pin 93, nRPIBOOT position).')
H3U(fl, 4, dict({'PD%d' % i: nc for i in range(18)}, **{'PE%d' % i: nc for i in range(16)}))
H3U(fl, 5, {'PL0': nc, 'PL1': nc, 'PL2': nc, 'PL3': 'KEY_USER', 'PL4': nc, 'PL5': nc, 'PL6': 'CPUX_VSEL', 'PL7': 'WL_PMU_EN',
            'PL8': 'PWR_STB', 'PL9': 'PWR_DRAM', 'PL10': 'LED_PWR_N', 'PL11': nc,
            'RESET': 'RUN_PG', 'NMI': 'NMI_N', 'UBOOT': 'FEL_N', 'TEST': nc, 'JTAG-SEL0': nc, 'JTAG-SEL1': nc,
            'X24MIN': 'X24M_IN', 'X24MOUT': 'X24M_OUT', 'NC': nc, 'X32KIN': 'X32K_IN', 'X32KOUT': 'X32K_OUT', 'X32KFOUT': nc,
            'PLLTEST': nc, 'KEYADC': 'KEYADC'})
H3U(fl, 6, {'HTX0P': 'HDMI_D0_P', 'HTX0N': 'HDMI_D0_N', 'HTX1P': 'HDMI_D1_P', 'HTX1N': 'HDMI_D1_N', 'HTX2P': 'HDMI_D2_P', 'HTX2N': 'HDMI_D2_N',
            'HTXCP': 'HDMI_CK_P', 'HTXCN': 'HDMI_CK_N', 'HHPD': 'HHPD', 'HCEC': 'HDMI_CEC', 'HSCL': 'HDMI_SCL', 'HSDA': 'HDMI_SDA',
            'USB_DP0': 'USB0_DP', 'USB_DM0': 'USB0_DM', 'USB_DP1': 'USB1_DP', 'USB_DM1': 'USB1_DM', 'USB_DP2': 'USB2_DP', 'USB_DM2': 'USB2_DM',
            'USB_DP3': 'USB3_DP', 'USB_DM3': 'USB3_DM',
            'EPHY_TXP': 'EPHY_TXP', 'EPHY_TXN': 'EPHY_TXN', 'EPHY_RXP': 'EPHY_RXP', 'EPHY_RXN': 'EPHY_RXN',
            'EPHY_LINK_LED': 'EPHY_LINK_LED', 'EPHY_SPD_LED': 'EPHY_SPD_LED', 'EPHY_RTX': 'EPHY_RTX',
            'MICIN1P': nc, 'MICIN1N': nc, 'MICIN2P': nc, 'MICIN2N': nc, 'MBIAS': nc, 'LINEINL': nc, 'LINEINR': nc,
            'LINEOUTL': 'LINEOUT_L', 'LINEOUTR': 'LINEOUT_R', 'VRA1': 'VRA1', 'VRA2': 'VRA2', 'VRP': 'VRP', 'TVOUT': 'TV_OUT'})
fl.newrow()
fl.section('CLOCKS', 'Y1 24 MHz 2016 (CL 8 pF), Y2 32.768 kHz 2012 (CL 9 pF) - adjust load capacitors to the crystals actually used.')
fl.add(LB.XTAL4, cx.ref('Y'), '24MHz 2016', {'1': 'X24M_IN', '3': 'X24M_OUT', '2': 'GND'}, footprint='Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm')
C(fl, '12pF', 'X24M_IN', 'GND')
C(fl, '12pF', 'X24M_OUT', 'GND')
fl.add(LB.XTAL2, cx.ref('Y'), '32.768kHz', {'1': 'X32K_IN', '2': 'X32K_OUT'}, footprint='Crystal:Crystal_SMD_2012-2Pin_2.0x1.2mm')
C(fl, '15pF', 'X32K_IN', 'GND')
C(fl, '15pF', 'X32K_OUT', 'GND')
fl.section('RESET SUPERVISOR, SYSTEM PULL-UPS, ANALOG REFERENCES, EPHY BIAS',
           'TPS3808G33 holds RUN_PG low until 3.3 V > 3.07 V (+ ~20 ms).  RUN_PG is wired-OR: the carrier reset key pulls it low (CM4 behaviour).\n'
           'NMI: no PMIC -> pull-up.  EPHY_RTX 6.04k 1% close to the ball.  VRA1/VRA2/VRP decoupled (line-out used).  AGND joined to GND at one point.')
fl.add(TPS3808_, cx.ref('U'), 'TPS3808G33DBV', {'SENSE': 'VCC_3V3', '~{MR}': nc, 'CT': nc, 'VDD': 'VCC_3V3', 'GND': 'GND', '~{RESET}': 'RUN_PG'},
       footprint='Package_TO_SOT_SMD:SOT-23-6')
R(fl, '10k', 'VCC_3V3', 'RUN_PG')
C(fl, '100nF', 'RUN_PG', 'GND')
R(fl, '47k', 'VCC_3V3', 'FEL_N')
R(fl, '47k', 'VCC_3V3', 'KEY_USER')
R(fl, '47k', 'AVCC', 'NMI_N')
R(fl, '100k', 'AVCC', 'KEYADC')
R(fl, '10k', 'VCC_3V3', 'SD_PWR_ON')
R(fl, '6.04k 1%', 'EPHY_RTX', 'GND')
C(fl, '1uF', 'VRA1', 'AGND')
C(fl, '4.7uF', 'VRA2', 'AGND', 'C0603')
C(fl, '10uF', 'VRP', 'AGND', 'C0603')
C(fl, '100nF', 'VRP', 'AGND')
R(fl, '0R', 'AGND', 'GND')
cx.flag(fl, 'AGND')
fl.section('HDMI HOT-PLUG DIVIDER + CEC PULL-UP (module side, so carriers can wire HDMI0 straight to the connector as on CM4)',
           'HPD 5 V from the sink -> 20k/27k -> ~2.9 V at HHPD.  CEC 27k to 3.3 V.  DDC 5 V pull-ups (1.8k) sit on the carrier next to the HDMI connector.')
R(fl, '20k', 'HDMI_HPD', 'HHPD')
R(fl, '27k', 'HHPD', 'GND')
R(fl, '27k', 'VCC_3V3', 'HDMI_CEC')

# =============================================================== 4. SoC power pins
sh = PRJ.add_sheet(Sheet('SoC Power & Decoupling', 'soc_power.kicad_sch', 'Allwinner H3 - power balls and decoupling', paper='A2'))
fl = Flow(sh, 20, 25, 385, gap=6)
fl.section('H3 CORE / IO / GROUND BALLS',
           'VDD_CPUS (J7/J8) runs from the 1.1 V VDD_SYS rail (as on the Orange Pi PC / NanoPi NEO references); RTC_VIO (M4) is the internal RTC LDO output: decoupling cap only.  VCC-RTC / VCC-PLL / V33-TV share the AVCC ferrite rail.')
H3U(fl, 7, {'VDD_CPUX': 'VDD_CPUX', 'VDD_CPUXFB': 'VDD_CPUX_FB', 'GND_CPUXFB': 'GND_CPUX_FB', 'VDD_CPUS': 'VDD_SYS',
            'RTC_VIO': 'RTC_VIO', 'VDD_SYS': 'VDD_SYS', 'VCC_DRAM': 'VCC_DRAM'})
H3U(fl, 8, {'VCC_IO': 'VCC_3V3', 'VCC_PD': 'VCC_3V3', 'VCC_PG': 'VCC_3V3', 'VCC_USB': 'VCC_3V3', 'HVCC': 'VCC_3V3', 'EPHY_VCC': 'VCC_EPHY',
            'EPHY_VDD': 'VDD1V1_EPHY', 'V33_TV': 'AVCC', 'VDD_EFUSE': 'VCC_3V3', 'VDD_EFUSEBP': 'VCC_3V3', 'AVCC': 'AVCC',
            'VCC_PLL': 'AVCC', 'VCC_RTC': 'AVCC', 'AGND': 'AGND', 'HGND': 'GND', 'GND_TV': 'GND'})
H3U(fl, 9, {'GND': 'GND'})
R(fl, '0R', 'GND_CPUX_FB', 'GND')
fl.section('DECOUPLING  (0402 under the BGA on the bottom side, 0603 bulk around it)')
CAPS(fl, 'VDD_CPUX', [('10uF', 'C0603', 1), ('1uF', None, 3), ('100nF', None, 4)])
CAPS(fl, 'VDD_SYS', [('10uF', 'C0603', 1), ('1uF', None, 2), ('100nF', None, 3)])
CAPS(fl, 'VDD_SYS', [('4.7uF', 'C0603', 1)])      # local bulk at the CPUS balls J7/J8
CAPS(fl, 'RTC_VIO', [('1uF', None, 1)])
CAPS(fl, 'VCC_3V3', [('10uF', 'C0603', 1), ('1uF', None, 1), ('100nF', None, 6)])
CAPS(fl, 'VCC_EPHY', [('100nF', None, 2)])
CAPS(fl, 'VDD1V1_EPHY', [('100nF', None, 2)])
CAPS(fl, 'AVCC', [('100nF', None, 4)])

# =============================================================== 5. DDR3
sh = PRJ.add_sheet(Sheet('DDR3 512MB', 'ddr3.kicad_sch', 'DDR3 x16, one 4 Gbit chip = 512 MB (16-bit bus, NanoPi NEO / Orange Pi Zero topology)', paper='A1'))
fl = Flow(sh, 20, 25, 560, gap=6)
fl.section('H3 DRAM CONTROLLER - 16-bit half-width mode (byte lanes 0/1)',
           'Point-to-point, no T branch.  SDQ16-31 / SDQM2-3 / SDQS2-3 unconnected (U-Boot detects the 16-bit width).  Single rank (SCS0/SCKE0/SODT0).\n'
           'SZQ 240R 1%.  SVREF = VCC_DRAM / 2.  A15 goes to the chip ball (NC on 4 Gbit x16, used by 8 Gbit).')
dconn = {'SA%d' % i: 'DDR_A%d' % i for i in range(16)}
dconn.update({'SBA%d' % i: 'DDR_BA%d' % i for i in range(3)})
dconn.update({'SRAS': 'DDR_RAS_N', 'SCAS': 'DDR_CAS_N', 'SWE': 'DDR_WE_N', 'SCS0': 'DDR_CS_N', 'SCS1': nc, 'SCKE0': 'DDR_CKE',
              'SCKE1': nc, 'SODT0': 'DDR_ODT', 'SODT1': nc, 'SCK': 'DDR_CK_P', 'SCKB': 'DDR_CK_N', 'SRST': 'DDR_RESET_N',
              'SZQ': 'DDR_SZQ', 'SVREF': 'DDR_VREF'})
dconn.update({'SDQ%d' % i: ('DDR_DQ%d' % i if i < 16 else nc) for i in range(32)})
dconn.update({'SDQM%d' % i: ('DDR_DM%d' % i if i < 2 else nc) for i in range(4)})
dconn.update({'SDQS%d' % i: ('DDR_DQS%d_P' % i if i < 2 else nc) for i in range(4)})
dconn.update({'SDQS%dB' % i: ('DDR_DQS%d_N' % i if i < 2 else nc) for i in range(4)})
H3U(fl, 1, dconn)
# DQ bit order inside a byte lane may be swapped later for routing (DQ only, never DQS/DM) - DQ_SWAP is filled in by the PCB stage.
DQ_SWAP = {"DDR_DQ1": "DDR_DQ5", "DDR_DQ2": "DDR_DQ3", "DDR_DQ3": "DDR_DQ4", "DDR_DQ4": "DDR_DQ1", "DDR_DQ5": "DDR_DQ7", "DDR_DQ6": "DDR_DQ2", "DDR_DQ7": "DDR_DQ6", "DDR_DQ9": "DDR_DQ15", "DDR_DQ11": "DDR_DQ14", "DDR_DQ13": "DDR_DQ9", "DDR_DQ14": "DDR_DQ11", "DDR_DQ15": "DDR_DQ13"}   # PCB stage 3 (pcb/out/cn1_dq_swap.json): DDR pin that carried <value> now carries <key>
c = {n: 'DDR_A%d' % i for i, n in enumerate(['A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'A10/AP', 'A11', 'A12/BC#', 'A13', 'A14', 'A15'])}
c.update({'BA0': 'DDR_BA0', 'BA1': 'DDR_BA1', 'BA2': 'DDR_BA2', 'RAS#': 'DDR_RAS_N', 'CAS#': 'DDR_CAS_N', 'WE#': 'DDR_WE_N',
          'CS#': 'DDR_CS_N', 'CKE': 'DDR_CKE', 'ODT': 'DDR_ODT', 'CK': 'DDR_CK_P', 'CK#': 'DDR_CK_N', 'RESET#': 'DDR_RESET_N',
          'ZQ': 'DDR_ZQ0', 'VREFCA': 'DDR_VREF', 'VREFDQ': 'DDR_VREF', 'VDD': 'VCC_DRAM', 'VDDQ': 'VCC_DRAM', 'VSS': 'GND', 'VSSQ': 'GND'})
for i in range(8):
    c['DQL%d' % i] = 'DDR_DQ%d' % i
    c['DQU%d' % i] = 'DDR_DQ%d' % (8 + i)
c.update({'DML': 'DDR_DM0', 'DMU': 'DDR_DM1', 'DQSL': 'DDR_DQS0_P', 'DQSL#': 'DDR_DQS0_N', 'DQSU': 'DDR_DQS1_P', 'DQSU#': 'DDR_DQS1_N'})
orig = dict(c)
for new_net, old_net in DQ_SWAP.items():
    for pin, net in orig.items():
        if net == old_net and pin.startswith('DQ') and not pin.startswith('DQS'):
            c[pin] = new_net
cb = {p.num: (nc if p.num in DDR3_NC else c[p.name]) for p in CU['DDR3_x16_FBGA96'].pins}
fl.add(CU['DDR3_x16_FBGA96'], cx.ref('U'), 'K4B4G1646E-BYMA', cb, footprint=sd_fp(CU['DDR3_x16_FBGA96']),
       fields={'Note': '4 Gbit x16 DDR3/DDR3L (1.5 / 1.35 V), alt. MT41K256M16TW-107'})
fl.newrow()
fl.section('ZQ, VREF, CLOCK TERMINATION, DECOUPLING',
           'CK 100R differential termination at the DRAM.  VCC_DRAM: 10uF x2 + 1uF x3 + 100nF x8 (DRAM balls) + SoC side from the Power sheet.')
R(fl, '240R 1%', 'DDR_SZQ', 'GND')
R(fl, '240R 1%', 'DDR_ZQ0', 'GND')
R(fl, '1k 1%', 'VCC_DRAM', 'DDR_VREF')
R(fl, '1k 1%', 'DDR_VREF', 'GND')
CAPS(fl, 'DDR_VREF', [('100nF', None, 3)])
R(fl, '100R 1%', 'DDR_CK_P', 'DDR_CK_N')
CAPS(fl, 'VCC_DRAM', [('10uF', 'C0603', 2), ('1uF', None, 3), ('100nF', None, 8)])

# =============================================================== 6. SD / WiFi
sh = PRJ.add_sheet(Sheet('SD & WiFi', 'sd_wifi.kicad_sch', 'SDC0 pull-ups (socket on the carrier) and RTL8189FTV WiFi on SDC1', paper='A3'))
fl = Flow(sh, 20, 25, 385)
fl.section('SD CARD INTERFACE (SDC0, boot device) - socket and card power switch are on the carrier',
           '33R series on CLK at the SoC, 47k pull-ups on CMD/DAT and card detect.  SD_PWR_ON (CM4 pin 75) pulled high: card powered from reset.')
R(fl, '33R', 'SD_CLK_H3', 'SD_CLK')
for n in ['SD_CMD', 'SD_D0', 'SD_D1', 'SD_D2', 'SD_D3', 'SD_DET']:
    R(fl, '47k', 'VCC_3V3', n)
fl.section('RTL8189FTV WiFi 802.11 b/g/n (Orange Pi PC Plus circuit)',
           'SDIO on PG0-PG5 (SDC1).  CHIP_EN = WL_PMU_EN (PL7), host wake -> PG10.  26 MHz 2016 crystal.\n'
           'RF: 50 ohm coplanar trace -> pi-match (tune on the finished board) -> u.FL (CB1 uses an IPEX antenna as well).')
fl.add(CU['RTL8189FTV'], cx.ref('U'), 'RTL8189FTV',
       {'VDIO_SDIO': 'VCC_WIFI', 'VD33X': 'VCC_WIFI', 'VD33SYNVCO': 'VCC_WIFI', 'VDSYN': 'VCC_WIFI', 'VD33PA': 'VCC_WIFI', 'VD33TR': 'VCC_WIFI',
        'VDTR': 'VCC_WIFI', 'VD33LDO': 'VCC_WIFI', 'VD12D': 'WL_VD12', 'XI': 'WL_XI', 'XO': 'WL_XO', 'GNDD': 'GND', 'EPAD': 'GND',
        'SD_CLK': 'WL_SDIO_CLK', 'SD_CMD': 'WL_SDIO_CMD', 'SD_D0': 'WL_SDIO_D0', 'SD_D1': 'WL_SDIO_D1', 'SD_D2': 'WL_SDIO_D2',
        'SD_D3': 'WL_SDIO_D3', 'CHIP_EN': 'WL_PMU_EN', 'INT/GPIO0': 'WL_WAKE_HOST', 'CLK_REQ/GPIO1': nc,
        'HOST_WAKE_DEV/GPIO2': nc, 'TEST_MODE/GPIO3': nc, 'RF_INOUT': 'WL_RF'},
       footprint=sd_fp(CU['RTL8189FTV']))
C(fl, '1uF', 'WL_VD12', 'GND')       # VD12D = internal 1.2 V core LDO output (datasheet table 3 / 6.3.3): needs local decoupling
fl.add(LB.XTAL4, cx.ref('Y'), '26MHz 2016', {'1': 'WL_XI', '3': 'WL_XO', '2': 'GND'}, footprint='Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm')
C(fl, '15pF', 'WL_XI', 'GND')
C(fl, '15pF', 'WL_XO', 'GND')
for n in ['WL_SDIO_CMD', 'WL_SDIO_D0', 'WL_SDIO_D1', 'WL_SDIO_D2', 'WL_SDIO_D3', 'WL_WAKE_HOST']:
    R(fl, '47k', 'VCC_WIFI', n)
R(fl, '100k', 'WL_PMU_EN', 'GND')
CAPS(fl, 'VCC_WIFI', [('1uF', None, 2), ('100nF', None, 3)])
fl.section('RF MATCHING + ANTENNA CONNECTOR')
C(fl, '10pF', 'WL_RF', 'WL_RF_A')
C(fl, 'DNP (tune)', 'WL_RF_A', 'GND', dnp=True)
L(fl, '0R (tune)', 'WL_RF_A', 'WL_RF_B', 'Inductor_SMD:L_0402_1005Metric')
C(fl, 'DNP (tune)', 'WL_RF_B', 'GND', dnp=True)
fl.add(COAX_, cx.ref('J'), 'u.FL', {'In': 'WL_RF_B', 'Ext': 'GND'}, footprint='Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical')
fl.section('MOUNTING  (4 x M2.5, CM4 pattern 48 x 33 mm, 3.5 mm from the edges, pads on GND)')
for i in range(4):
    fl.add(LB.MHP, 'H%d' % (i + 1), 'M2.5', {'1': 'GND'}, footprint='MountingHole:MountingHole_2.7mm_M2.5_Pad_Via')

PRJ.root_texts = [
    ('CN1  -  Allwinner H3 compute module, Raspberry Pi CM4 form factor 55 x 40 mm, 8-layer HDI', 25, 185, 2.5),
    ('H3 quad A7 1.2 GHz | 512 MB DDR3 (1 x 4 Gbit x16) | RTL8189FTV WiFi + u.FL | 10/100 EPHY | 4 x USB 2.0 | HDMI 1.4 | SDC0 | 28 GPIO\n'
     'Power: 5 V in (CM4 pins 77-87) -> TPS563201 3.3 V (GLOBAL_EN) -> TPS563201 VDD_CPUX 1.1/1.3 V | TPS562201 VDD_SYS 1.2 V | TPS562201 VCC_DRAM 1.5 V\n'
     '       TLV75518 1.8 V out.  Pinout follows BIGTREETECH CB1 on the CM4 connector.', 25, 195, 1.8),
    ('Generated by h3-two-board/gen/build_cn1.py - custom symbols in klipper_h3.kicad_sym, custom footprints in klipper_h3.pretty', 25, 212, 1.8),
]
cx.write(OUT, 'CN1 - H3 CM4-format module', CU)
# custom footprints: H3 BGA (existing generator) + renumbered DF40
import subprocess
subprocess.run([sys.executable, '/home/claude/klipper-h3-host/gen/gen_fp.py', os.path.join(OUT, 'klipper_h3.pretty')], check=True)
cm4.write_footprints(os.path.join(OUT, 'klipper_h3.pretty'))
print('CN1 sheets:', len(PRJ.sheets), 'global nets:', len(PRJ.global_nets))
