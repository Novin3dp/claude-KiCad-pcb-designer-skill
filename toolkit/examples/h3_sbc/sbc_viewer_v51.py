#!/usr/bin/env python3
"""Interactive HTML viewer for the H3 Klipper SBC v2 (85 x 56 mm, 6 layers): v2 placement + rip, HDMI Type A bus,
DDR3, v2 final, and the v1 final board for comparison; per-layer show / hide, Persian notes.  Ratsnest comes from the KiCad DRC
'unconnected items' (exact), not from the old pad-cluster approximation."""
import json, os, re, sys, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, '/home/claude/klipper-h3-host/pcb')
import pcbnew
import export_geom as EG
import viewer as V

OUT = os.path.join(HERE, 'out', 'sbc2')
PRO = os.path.join(HERE, '..', 'sbc', 'kicad', 'sbc.kicad_pro')
DRU = os.path.join(HERE, '..', 'sbc', 'kicad', 'sbc.kicad_dru')
LAYERS = [dict(k='F.Cu', role='L1 · Signal + قطعات + GND pour', c='#e5483f'), dict(k='In1.Cu', role='L2 · GND', c='#58c46c'),
          dict(k='In2.Cu', role='L3 · Signal (stripline)', c='#eda23a'), dict(k='In3.Cu', role='L4 · پلین تغذیه (تقسیم‌شده)', c='#d65c9b'),
          dict(k='In4.Cu', role='L5 · GND', c='#3fc4cf'), dict(k='B.Cu', role='L6 · Signal + دکاپلینگ + GND pour', c='#4f82e6')]
V.GROUPS_DDR = [
    ('Lane 0  DQ0-7 · DQS0 · DM0', '#ffb74d', r'DDR_(DQ[0-7]|DQS0_[PN]|DM0)$'),
    ('Lane 1  DQ8-15 · DQS1 · DM1', '#4fc3f7', r'DDR_(DQ([89]|1[0-5])|DQS1_[PN]|DM1)$'),
    ('CK / CK#', '#ffffff', r'DDR_CK_[PN]$'),
    ('ADDR / CMD', '#b39ddb', r'DDR_(A\d+|BA\d|RAS_N|CAS_N|WE_N|CS_N|CKE|ODT|RESET_N)$'),
]
EG.ratsnest = lambda b: ([], 0)          # replaced by the DRC unconnected list below


def export(pcb):
    path = os.path.join(OUT, pcb)
    base = path[:-len('.kicad_pcb')]
    v1 = pcb.startswith('r/')
    pro, dru = (PRO.replace('sbc.kicad_pro', 'sbc_v1.kicad_pro'), DRU.replace('sbc.kicad_dru', 'sbc_v1.kicad_dru')) if v1 else (PRO, DRU)
    for src, ext in ((pro, '.kicad_pro'), (dru, '.kicad_dru')):
        shutil.copy(src, base + ext)      # DRC with the project rules
    d = V.export(os.path.join('sbc2', pcb), LAYERS, 'H3 Klipper SBC')
    rats, n, _ = EG.drc_rats(path, d['nets'])
    d['rats'], d['unrouted'] = rats, n
    return d


BLOCKS = [
    ('H3 (TFBGA-347)', '#e3a857', ['U1'], 'T'),
    ('DDR3 4Gb x16', '#b18cff', ['U7'], 'T'),
    ('12-24 V XH in + protection', '#e8574d', ['J2', 'F1', 'Q2', 'D3', 'C100', 'C101'], None),
    ('MP1584 module (bottom) + OR diode', '#ff7a6b', ['U9', 'D4'], None),
    ('USB-C 5 V in + P-FET', '#ffd166', ['J7', 'Q3', 'D6'], None),
    ('VDD_CPUX buck', '#ff9b54', ['U3', 'L2'], 'T'),
    ('VCC_3V3 buck', '#8fd16a', ['U2', 'L1'], 'T'),
    ('VDD_SYS buck', '#f3d34a', ['U4', 'L3'], 'T'),
    ('VCC_DRAM buck', '#c79bff', ['U5', 'L4'], 'T'),
    ('WiFi RTL8189 + u.FL', '#ff9fc7', ['U8', 'Y3', 'J1', 'L5'], 'T'),
    ('HDMI Type A + ESD', '#c79bff', ['J8', 'D7', 'D8'], 'T'),
    ('USB-A x4 + power switches', '#7fb4ff', ['J5', 'J6'], 'T'),
    ('RJ45 10/100', '#6fd3c1', ['J9'], 'T'),
    ('40-pin GPIO', '#90a4ae', ['J11'], 'T'),
    ('Debug UART pads', '#ffffff', ['TP1', 'TP2', 'TP3'], 'T'),
    ('microSD (bottom)', '#4dd0e1', ['J10'], 'B'),
    ('Keys', '#a5d6a7', ['SW2', 'SW3', 'SW4'], 'T'),
]
FLOWS = [
    ('HDMI', '#c79bff', r'^HDMI_(D\d|CK)_[PN]$', 'U1', ['J8']),
    ('USB0-3', '#7fb4ff', r'^USB[0123]_D[PM]$', 'U1', ['J5', 'J6']),
    ('EPHY', '#6fd3c1', r'^EPHY_(TX|RX)[PN]$', 'U1', ['J9']),
    ('GPIO', '#90a4ae', r'^(GPIO|ID_S)', 'U1', ['J11']),
    ('SD', '#4dd0e1', r'^SD_(CMD|D\d|CLK)$', 'U1', ['J10']),
    ('SDIO', '#ff9fc7', r'^WL_SDIO_', 'U1', ['U8']),
    ('DDR', '#ffb74d', r'^DDR_(DQ\d+|DQS\d_[PN]|DM\d)$', 'U1', ['U7']),
]


def n1(d):
    return """
<h2>v2 · مرحله‌ی ۱: تغییرات چیدمان</h2>
<p class="lead">برد v1 با ECO به v2 تبدیل شد، یعنی از اول ساخته نشد: %d قطعه، رفرنس‌ها ثابت مانده‌اند و DDR3، H3 و بیشتر مسیرها دست نخورده‌اند. خطوط نازک ratsnest نت‌هایی را نشان می‌دهند که بعد از جابه‌جایی‌ها پاره شدند (%d اتصال) و در مرحله‌ی بعد دوباره سیم‌کشی شدند.</p>
<ul>
<li><b>ورودی 12–24 V</b> با کانکتور JST XH (J2) به‌جای ترمینال، روی لبه‌ی پایین سمت راست. فیوز 3A، P-FET حفاظت معکوس و TVS SMAJ26CA.</li>
<li><b>5 V از ماژول MP1584</b> (U9) که SMD و صاف پشت برد لحیم می‌شود. IN در سمت راست و OUT در سمت چپ است. خروجی از دیود B560C (D4) به VCC_5V می‌رود.</li>
<li><b>USB-C فقط برای ورود 5 V</b> (J7) کنار ورودی XH. P-FET AO3401A (Q3) وقتی ماژول برق داشته باشد USB-C را قطع می‌کند، پس اولویت با ماژول است.</li>
<li>J4 (FAN2) و J12 (دیباگ) حذف شدند. دیباگ حالا ۳ پد تست (TP1 GND، TP2 RX، TP3 TX) کنار هدر ۴۰ پین است.</li>
<li><b>HDMI Type A</b> (Molex 208658-1001) به‌جای micro-HDMI، وسط لبه‌ی پایین.</li>
<li>سوراخ‌ها با الگوی BTT Pi / Raspberry Pi با فاصله‌ی 58 × 49 mm: (23.5, 3.5) (81.5, 3.5) (23.5, 52.5) (81.5, 52.5).</li>
</ul>
""" % (len(d['fps']), d['unrouted'])


def n2(d):
    return """
<h2>v2 · مرحله‌ی ۲: باس HDMI Type A</h2>
<p class="lead">هشت خط TMDS به‌صورت دستی و کاملاً روی L1 کشیده شدند، بدون هیچ ویا: H3 → ESD (TPD4E05U06، flow-through) → J8. بقیه‌ی نت‌ها در این مرحله هنوز پاره‌اند (%d اتصال) و بعداً دور این باس سیم‌کشی شدند.</p>
<ul>
<li>خروج از دو ردیف بیرونی ball ها از جاهای خالی ردیف y = 40.0 استفاده می‌کند. خطوط به شکل L تودرتو هستند، پس مسیرها از هم عبور نمی‌کنند.</li>
<li>عرض 0.10 mm با فاصله‌ی 0.20 mm داخل هر جفت (Zdiff ≈ 100 Ω) و 0.40 mm بین جفت‌ها.</li>
<li>پایه‌های GND هر ESD به هم وصل‌اند و یک ویای GND دارند. هر پایه‌ی GND کانکتور هم یک استاب و ویا پشت ردیف پدها دارد.</li>
</ul>
""" % d['unrouted']


def n3(d):
    rows = json.load(open(os.path.join(OUT, 'v2', 'q1_ddrlen.json')))
    L = {r['net']: r['len'] for r in rows if r['len']}

    def rng(rx):
        v = [l for n, l in L.items() if re.match(rx, n)]
        return '%.1f – %.1f' % (min(v), max(v)) if v else '-'
    return """
<h2>DDR3 (بدون تغییر نسبت به v1)</h2>
<p class="lead">مسیرهای DDR3 در v2 و v3 دست نخورده‌اند و طول‌ها عیناً همان v1 است.</p>
<div class="tblwrap"><table><thead><tr><th>گروه</th><th>طول (mm)</th><th>skew زوج</th></tr></thead><tbody>
<tr><td>Lane 0 · DQ0-7, DM0</td><td>%s</td><td>DQS0: %.2f</td></tr>
<tr><td>Lane 1 · DQ8-15, DM1</td><td>%s</td><td>DQS1: %.2f</td></tr>
<tr><td>CK / CK#</td><td>%.1f / %.1f</td><td>%.2f</td></tr>
<tr><td>ADDR / CMD</td><td>%s</td><td>—</td></tr></tbody></table></div>
<div class="callout"><b>مثل v1:</b> اختلاف طول داخل هر lane تا حدود 9 mm (≈ 60 ps) است. کلاک DRAM را اول روی <b>480 تا 528 MHz</b> بگذارید و با memtester تست کنید.</div>
""" % (rng(r'DDR_(DQ[0-7]|DM0)$'), abs(L['DDR_DQS0_P'] - L['DDR_DQS0_N']),
       rng(r'DDR_(DQ([89]|1[0-5])|DM1)$'), abs(L['DDR_DQS1_P'] - L['DDR_DQS1_N']),
       L['DDR_CK_P'], L['DDR_CK_N'], abs(L['DDR_CK_P'] - L['DDR_CK_N']), rng(r'DDR_(A\d+|BA\d|RAS_N|CAS_N|WE_N|CS_N|CKE|ODT|RESET_N)$'))


def n4(d):
    errs = [v for v in d['drc'] if v['s'] == 'error']
    warn = [v for v in d['drc'] if v['s'] != 'error']
    return """
<h2>v3 · برد قبلی (DDR3 قبل از تطبیق دوباره)</h2>
<p class="lead">%d ترک و %d ویا. خطاهای DRC: <b>%d</b>، اتصال‌های باز: <b>%d</b>، هشدارها: %d. همه‌ی هشدارها همپوشانی courtyard هستند: 44 تا خازن 0402 زیر BGA (مثل v1)، و ۲ تا سوراخ H3/H4 با هدر ۴۰ پین و RJ45 که بدنه‌هایشان برخورد ندارند. ERC صفر و parity شماتیک صفر است.</p>
<ul>
<li><b>مسیر 5 V (تا 3 A):</b>
<ul>
<li>OUT+ ماژول با ۳ ویای 0.6/0.3 (via-in-pad) به آند D4 می‌رسد.</li>
<li>کاتد D4 با ۴ ویای 0.6/0.3 به پلین VCC_5V روی L4 وصل است.</li>
<li>IN+ ماژول با نوار 1.0 mm روی L6 و ۳ ویا به drain ترانزیستور Q2 می‌رسد.</li>
</ul></li>
<li><b>HDMI Type A:</b> skew داخل هر جفت حداکثر 0.88 mm (≈ 6 ps) و طول‌ها 15.8 تا 18.8 mm، بدون ویا.</li>
<li><b>USB:</b> USB0 (پورت A4) skew برابر 1.4 mm، USB1-3 بین 0.33 و 0.97 mm. EPHY برابر 0.33 mm.</li>
<li><b>GND pour</b> روی L1 و L6، با 61 ویای stitching.</li>
<li>U9 (ماژول) در فایل‌های pos/CPL نیست، چون دستی لحیم می‌شود. قبل از نصب، خروجی ماژول را روی <b>5.30 V</b> تنظیم کنید و پتانسیومتر را با چسب ثابت کنید.</li>
</ul>
""" % (len(d['tracks']), len(d['vias']), len(errs), d['unrouted'], len(warn))


def n5(d):
    errs = [v for v in d['drc'] if v['s'] == 'error']
    warn = [v for v in d['drc'] if v['s'] != 'error']
    return """
<h2>v4 · برد نهایی (0603 از v3 + DDR3 جدید)</h2>
<p class="lead">%d ترک و %d ویا. خطای DRC: <b>%d</b>، اتصال باز: <b>%d</b>، هشدار: %d (همه همپوشانی courtyard، بیشترشان خازن‌های 0402 زیر BGA). ERC صفر و parity شماتیک صفر است.</p>
<ul>
<li><b>56 قطعه از 0402 به 0603</b> تبدیل شدند. از 122 قطعه‌ی 0402، حالا 66 تا مانده است:
<ul>
<li>44 تا زیر H3 و DDR (بین ball ها جای 0603 نیست).</li>
<li>4 تا شبکه‌ی تطبیق آنتن (C97، C98، C99، L5).</li>
<li>18 تا در شلوغ‌ترین نقاط کنار مبدل‌ها و H3: C1، C8، C16، C24، C27، C34، C40، C58، C89، D1، R2، R11، R12، R13، R16، R19، R22 و R28.</li>
</ul></li>
<li>49 قطعه جابه‌جا شدند، بیشترشان کمتر از 3 mm:
<ul>
<li>pull-up های SD (R34، R37، R38، R18) تا 6 mm.</li>
<li>C36، R18، R17 و R34 به پشت برد رفتند.</li>
<li>خازن‌های ورودی مبدل‌ها و کریستال‌ها حداکثر 1.4 mm.</li>
</ul></li>
<li>حدود 50 نت سیگنال دوباره سیم‌کشی شدند (SD، SDIO وای‌فای، FB مبدل‌ها، کریستال‌ها، چند GPIO). هر جا مسیر v2 هنوز جا داشت، همان مسیر حفظ شد.</li>
<li>DDR3، HDMI، USB و Ethernet دست نخورده‌اند و طول‌ها عیناً همان v2 است.</li>
</ul>
""" % (len(d['tracks']), len(d['vias']), len(errs), d['unrouted'], len(warn))


def n6(d):
    errs = [v for v in d['drc'] if v['s'] == 'error']
    rows = json.load(open(os.path.join(OUT, 'v4', 'f2_ddrlen.json')))
    L = {r['net']: r['len'] for r in rows if r['len']}
    def lane(i):
        r = (L['DDR_DQS%d_P' % i] + L['DDR_DQS%d_N' % i]) / 2
        mem = ['DDR_DQ%d' % k for k in range(8 * i, 8 * i + 8)] + ['DDR_DM%d' % i]
        return r, ' · '.join('%s %+.1f' % (m.replace('DDR_', ''), L[m] - r) for m in mem)
    r0, t0 = lane(0); r1, t1 = lane(1)
    return """
<h2>v4 · تطبیق دوباره‌ی طول DDR3</h2>
<p class="lead">DRC بدون خطا (%d) و بدون اتصال باز (%d). meander های قدیمی صاف شدند و هر lane حالا با طول DQS خودش تطبیق داده شده است، نه با بلندترین DQ.</p>
<div class="tblwrap"><table><thead><tr><th>گروه</th><th>v3</th><th>v4</th></tr></thead><tbody>
<tr><td>Lane 0: میانگین |ΔL| تا DQS0</td><td>5.7 mm</td><td>1.3 mm (7 از 9 در ±1 mm)</td></tr>
<tr><td>Lane 1: میانگین |ΔL| تا DQS1</td><td>3.9 mm</td><td>2.0 mm (5 از 9 در ±1 mm)</td></tr>
<tr><td>اختلاف P/N در DQS1 و CK</td><td>2.1 / 0.7 mm</td><td>0.02 / 0.00 mm</td></tr>
<tr><td>آدرس/فرمان در ±1 mm از CK</td><td>4 از 26</td><td>15 از 26</td></tr></tbody></table></div>
<p class="mono" style="font-size:12px">Lane 0 (DQS0 %.2f mm): %s<br>Lane 1 (DQS1 %.2f mm): %s</p>
<div class="callout"><b>هنوز بیرون از محدوده:</b>
<ul>
<li>DQ2 (+7.5) و DM0 (+2.4) در lane 0.</li>
<li>DQ14 (−7.3)، DQ13 (−4.0)، DQ12 (−2.6) و DQ8 (+2.7) در lane 1.</li>
<li>A11، A15 و CS_N در آدرس.</li>
</ul>
در فضای ۶ میلی‌متری بین H3 و DDR راه کوتاه‌تری برای خطوط بلند پیدا نشد، و خطوط کوتاه جای meander ندارند. کلاک DRAM را اول روی 528 MHz تست کنید.</div>
""" % (len(errs), d['unrouted'], r0, t0, r1, t1)


def n7(d):
    errs = [v for v in d['drc'] if v['s'] == 'error']
    return """
<h2>v5.1 · بازبینی کامل از صفر تا صد</h2>
<p class="lead">چهار بازبینی مستقل انجام شد: تغذیه، SoC و DDR، تجهیزات جانبی، و فیزیک PCB و ساخت. هر یافته جداگانه با شماتیک‌های مرجع Orange Pi PC / One / PC Plus و خود برد چک شد. نتیجه: DRC بدون خطا (%d)، اتصال باز %d، ERC صفر و parity صفر.</p>
<div class="tblwrap"><table><thead><tr><th>بخش</th><th>ایراد در v4</th><th>اصلاح در v5</th></tr></thead><tbody>
<tr><td>microSD (J10)</td><td>دهانه‌ی سوکت رو به داخل برد بود و کارت جا نمی‌رفت</td><td>سوکت ۱۸۰° چرخید، دهانه رو به لبه‌ی راست است، خطوط SD دوباره روت شدند</td></tr>
<tr><td>تشخیص کارت</td><td>پد ۱۰ سوییچ DM3AT به جایی وصل نبود و تشخیص کارت هرگز کار نمی‌کرد</td><td>نماد Det2، پد ۱۰ به GND (پد ۹ = SD_DET، پایین یعنی کارت داخل است)</td></tr>
<tr><td>H3 · H11 VDD_EFUSEBP</td><td>به 3.3V وصل بود</td><td>طبق مرجع فقط ۴.۷µF به GND (خازن جدید C132)</td></tr>
<tr><td>H3 · J7/J8 VDD_CPUS</td><td>از VDD_SYS تغذیه می‌شد (با PWR_STB قطع می‌شد)</td><td>به RTC_VIO وصل شد، C56 = 4.7µF</td></tr>
<tr><td>فیدبک CPUX (R8)</td><td>DNP بود: اگر توپ T10 لحیم نشود، ولتاژ هسته بالا می‌رود</td><td>10Ω نصب می‌شود (پشتیبان محلی)</td></tr>
<tr><td>3.3V</td><td>3.32V، در بدترین حالت بالای حد AVCC</td><td>R1 = 32.4k، یعنی 3.26V</td></tr>
<tr><td>CEC (D10)</td><td>دیود برعکس بود و pull-up خط CEC را قطع می‌کرد</td><td>آند روی 3V3، کاتد سمت 27k</td></tr>
<tr><td>HDMI 5V (D9)</td><td>با 1N5819 ولتاژ پورت حدود 4.55V می‌شد</td><td>PMEG2010AEJ (افت حدود 0.2V)</td></tr>
<tr><td>USB-A</td><td>محدودیت ۴×۱A بیشتر از ظرفیت ۳A ماژول بود</td><td>RSET = 10k یعنی حدود 0.68A برای هر پورت</td></tr>
<tr><td>ورودی 12-24V</td><td>فیوز 1812 بدون رده‌ی ولتاژ کافی، TVS دوطرفه</td><td>فیوز 1206 مدل 0468003.NRHF با 32V، و TVS یک‌طرفه SMAJ26A</td></tr>
<tr><td>مبدل DRAM (U5)</td><td>خازن ورودی ۸ میلی‌متر دور بود، SW حدود ۱۴ میلی‌متر از پشت با ۴ ویا می‌رفت</td><td>U5 چرخید تا SW رو به L4 باشد، C23 کنار VIN، و SW با مسیر کوتاه روی لایه‌ی بالا</td></tr>
<tr><td>زمین مبدل‌ها</td><td>یک ویای 0.2 برای GND</td><td>ویاهای 0.4 کنار GND تراشه‌ها و خازن‌های ورودی</td></tr>
<tr><td>RTL8189 (U8)</td><td>پد زمین زیر تراشه ویا نداشت</td><td>آرایه‌ی ویا در پد (پرشده و درپوش‌دار)، و stitching زمین کنار خط آنتن</td></tr>
<tr><td>مسیر 5V داخلی</td><td>نوار L4 به عرض 1.6 میلی‌متر برای چهار پورت USB</td><td>عرض نوار 3.2 میلی‌متر و نوار عمودی 2.2 میلی‌متر</td></tr>
<tr><td>ماژول MP1584</td><td>روی پدها خمیر قلع چاپ می‌شد</td><td>پدها بدون paste، و ویاهای بیشتر بین OUT+ و D4</td></tr>
<tr><td>ورودی USB-C (v5.1)</td><td>مسیر VBUS به Q3 فقط 0.3 mm</td><td>پور مسی روی لایه‌ی بالا به عرض حدود 1.3 mm با اتصال کامل به پدها</td></tr>
<tr><td>مونتاژ</td><td>بدون fiducial، BOM بدون شماره‌ی LCSC، سیلک روی پدها</td><td>۶ fiducial، شماره‌ی LCSC و MPN برای همه‌ی ردیف‌ها، refها جابه‌جا یا روی سیلک مخفی</td></tr>
</tbody></table></div>
<div class="callout"><b>بررسی شد و ایراد نبود:</b>
<ul>
<li>pull-up های DDC به 5V (مثل Orange Pi PC).</li>
<li>پایه‌ی WAKE وای‌فای (مثل PC Plus).</li>
<li>دکمه‌ی RESET روی خروجی open-drain.</li>
<li>پایه‌ی ۸ سوکت RJ45.</li>
<li>جهت ترانزیستورها، دیودها، LEDها و کریستال‌ها.</li>
</ul></div>
""" % (len(errs), d['unrouted'])


def n0(d):
    return """
<h2>v1 · برد نهایی (برای مقایسه)</h2>
<p class="lead">نسخه‌ی قبلی: ورودی ترمینال، مبدل TPS54560 روی برد، USB-C برای USB0 همراه با mux، و micro-HDMI. %d ترک و %d ویا.</p>
""" % (len(d['tracks']), len(d['vias']))


def stack_html():
    def rows(L):
        out = []
        for ln, name, role, c, t in L:
            if c:
                out.append('<div class="st cu"><span><b>%s</b> %s</span><span style="display:flex;gap:10px;align-items:center"><span class="bar" style="background:%s;width:120px"></span><span style="direction:rtl">%s</span></span><span class="mono" style="color:var(--muted)">%s</span></div>' % (ln, name, c, role, t))
            else:
                out.append('<div class="st di"><span></span><span>%s</span><span></span></div>' % role)
        return ''.join(out)
    st = [('L1', 'F.Cu', 'Signal + قطعات + GND pour', '#e5483f', '0.035'), ('', '', 'PP 1080 · 0.0764 · εr 3.91', None, ''),
          ('L2', 'In1.Cu', 'GND', '#58c46c', '0.0152'), ('', '', 'Core · 0.10 · εr 4.6', None, ''),
          ('L3', 'In2.Cu', 'Signal · stripline', '#eda23a', '0.0152'), ('', '', 'PP 7628 + Core 0.70 + PP 7628 · 1.12', None, ''),
          ('L4', 'In3.Cu', 'پلین تغذیه (تقسیم‌شده)', '#d65c9b', '0.0152'), ('', '', 'Core · 0.10 · εr 4.6', None, ''),
          ('L5', 'In4.Cu', 'GND', '#3fc4cf', '0.0152'), ('', '', 'PP 1080 · 0.0764', None, ''),
          ('L6', 'B.Cu', 'Signal + دکاپلینگ + GND pour', '#4f82e6', '0.035')]
    imp = [('SE 50 Ω (RF 0.12)', 'L1', '0.12', '—', '50.7'), ('SE (سیگنال‌ها)', 'L1 / L6', '0.10', '—', '55'),
           ('SE', 'L3', '0.10', '—', '54'), ('USB 90 Ω diff', 'L1 / L6', '0.10', '0.11', '89'), ('USB 90 Ω diff', 'L3', '0.10', '0.11', '86'),
           ('HDMI 100 Ω diff', 'L1', '0.10', '0.20', '≈100'), ('HDMI 100 Ω diff', 'L3', '0.10', '0.21', '97')]
    trs = ''.join('<tr><td style="font-family:var(--sans)">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % r for r in imp)
    return '''
<h2>استک‌آپ و قوانین</h2>
<h4>شش لایه، 1.6 mm، JLCPCB JLC06161H-1080B</h4>
<p class="lead">هر لایه‌ی سیگنال یک GND در فاصله‌ی 0.08 تا 0.10 mm دارد: L1 روی L2، L3 زیر L2، و L6 روی L5. پلین تقسیم‌شده‌ی L4 حدود 1.12 mm از L3 فاصله دارد، پس مسیرهای L3 مرجعشان را از L2 می‌گیرند.</p>
<div class="stack">%s</div>
<h4>امپدانس هندسه‌ی مسیریابی‌شده (حل‌گر میدان دوبعدی zsolve)</h4>
<div class="tblwrap"><table><thead><tr><th>Target</th><th>Layer</th><th>W mm</th><th>Gap mm</th><th>Z Ω</th></tr></thead><tbody>%s</tbody></table></div>
<p style="color:var(--muted);font-size:12.5px">در سفارش گزینه‌ی Impedance Control با همین استک‌آپ را انتخاب کنید. سازنده عرض نهایی را با جدول خودش تنظیم می‌کند.</p>
<h4>قوانین ساخت</h4>
<ul>
<li>track و clearance حداقل 0.10 mm. ویای سیگنال 0.31/0.15، ویای تغذیه / stitching برابر 0.40/0.20، و ویای جریان بالای مسیر 5 V / VIN برابر 0.60/0.30. همه‌ی ویاها through هستند (blind/buried ندارد).</li>
<li>زیر H3 قانون BGA escape برقرار است: clearance برابر 0.10 و hole-clearance برابر 0.12. ردیف پایه‌های HDMI Type A (J8) هم clearance برابر 0.10 دارد.</li>
<li><b>via-in-pad</b> (پرشده با اپوکسی و درپوش‌دار، IPC-4761 VII) برای چند پد BGA، و پدهای ماژول MP1584 و دیود D4 (ویاهای جریان). در سفارش JLC گزینه‌ی «Via Covering: Epoxy Filled & Capped» را بزنید.</li>
<li>فاصله‌ی مس تا لبه 0.3 mm و پوشش سطح ENIG (برای BGA با گام 0.65 و USON با گام 0.5).</li>
</ul>
''' % (rows(st), trs)


STAGES = [
    dict(id='s7', title='v5.1 · بازبینی کامل', sub='J10 · تغذیه H3 · U5 · BOM', state='done'),
    dict(id='s6', title='v4 · DDR3 دوباره تطبیق', sub='lanes ↔ DQS · pairs 0.0', state='done'),
]
DATA = {'s7': ('v51/fin.kicad_pcb', BLOCKS, FLOWS, n7, 'all'), 's6': ('v4/f2.kicad_pcb', [], [], n6, 'ddr')}


def main():
    tpl = open(os.path.join(HERE, 'viewer_template.html')).read()
    tpl = tpl.replace('<title>H3 CN1 and Mizban</title>', '<title>H3 Klipper SBC</title>')
    tpl = tpl.replace('<b>CN1 + میزبان — طراحی دو برد</b>', '<b>H3 Klipper SBC v5.1 — برد تکی شش لایه</b>')
    blocks, meta = [], []
    for st in STAGES:
        meta.append(dict(id=st['id'], title=st['title'], sub=st['sub'], state=st['state']))
        pcb, bl, fl, nf, grp = DATA[st['id']]
        d = export(pcb)
        d['ov'], d['legend'] = V.blocks_and_flows(d, bl, fl)
        if grp:
            d['groups'] = V.groups(d, grp)
            d['legend'] = d['legend'] + [dict(c=g['c'], l=g['name']) for g in d['groups']]
        blocks.append('<script type="application/json" id="stage-%s">%s</script>' % (st['id'], json.dumps(d, separators=(',', ':')).replace('</', '<\\/')))
        blocks.append('<template id="notes-%s">%s</template>' % (st['id'], nf(d)))
        print(st['id'], 'tracks', len(d['tracks']), 'vias', len(d['vias']), 'rats', d['unrouted'], 'drc', len(d['drc']), flush=True)
    blocks.insert(0, '<script type="application/json" id="stages-meta">%s</script>' % json.dumps(meta))
    blocks.append('<template id="stack-html">%s</template>' % stack_html())
    out = tpl.replace('<!--DATA-->', '\n'.join(blocks))
    dst = os.path.join(HERE, 'out', 'h3_klipper_sbc.html')
    open(dst, 'w').write(out)
    print('wrote', dst, os.path.getsize(dst) // 1024, 'KB')


if __name__ == '__main__':
    main()
