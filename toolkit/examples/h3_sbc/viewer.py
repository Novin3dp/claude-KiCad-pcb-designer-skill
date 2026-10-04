#!/usr/bin/env python3
"""Build the two-board HTML viewer (CN1 + Mizban): per-stage board JSON (export_geom), overlays, Persian notes."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, '/home/claude/klipper-h3-host/pcb')
import pcbnew
import export_geom as EG

OUT = os.path.join(HERE, 'out')
CN1_LAYERS = [dict(k='F.Cu', role='L1 · Signal + قطعات', c='#e5483f'), dict(k='In1.Cu', role='L2 · GND', c='#58c46c'),
              dict(k='In2.Cu', role='L3 · Signal (DDR / HDMI)', c='#eda23a'), dict(k='In3.Cu', role='L4 · پلین تغذیه (تقسیم‌شده)', c='#d65c9b'),
              dict(k='In4.Cu', role='L5 · GND', c='#3fc4cf'), dict(k='B.Cu', role='L6 · کانکتورها + دکاپلینگ', c='#4f82e6')]
MZ_LAYERS = [dict(k='F.Cu', role='L1 · Signal + قطعات', c='#e5483f'), dict(k='In1.Cu', role='L2 · GND', c='#58c46c'),
             dict(k='In2.Cu', role='L3 · 5V / 3V3 planes', c='#d65c9b'), dict(k='B.Cu', role='L4 · Signal + microSD', c='#4f82e6')]
IDS = {'F.Cu': pcbnew.F_Cu, 'In1.Cu': pcbnew.In1_Cu, 'In2.Cu': pcbnew.In2_Cu, 'In3.Cu': pcbnew.In3_Cu, 'In4.Cu': pcbnew.In4_Cu,
       'In5.Cu': pcbnew.In5_Cu, 'In6.Cu': pcbnew.In6_Cu, 'B.Cu': pcbnew.B_Cu}


def export(pcb, layers, name):
    EG.LAYERS = [(l['k'], IDS[l['k']]) for l in layers]
    EG.LID = {lid: i for i, (_, lid) in enumerate(EG.LAYERS)}
    d = EG.export(os.path.join(OUT, pcb))
    d['layers'] = layers
    d['boardName'] = name
    return d


def fp_bbox(d, refs, side=None):
    x0 = y0 = 1e12; x1 = y1 = -1e12
    for f in d['fps']:
        if f['r'] in refs and (side is None or f['s'] == side):
            q = f['cy']
            for i in range(0, len(q), 2):
                x0 = min(x0, q[i]); x1 = max(x1, q[i]); y0 = min(y0, q[i + 1]); y1 = max(y1, q[i + 1])
    return x0, y0, x1, y1


def centroid(d, ref, rx):
    fi = {f['r']: i for i, f in enumerate(d['fps'])}
    pts = [(p['x'], p['y']) for p in d['pads'] if p['f'] == fi.get(ref) and re.search(rx, d['nets'][p['n']])]
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def blocks_and_flows(d, blocks, flows):
    ov, legend = [], []
    for name, col, refs, side in blocks:
        x0, y0, x1, y1 = fp_bbox(d, refs, side)
        if x1 < x0:
            continue
        m = 350
        ov.append(dict(t='rect', x0=x0 - m, y0=y0 - m, x1=x1 + m, y1=y1 + m, c=col, fa=0.06, dash=True, label=name, fs=11))
        legend.append(dict(c=col, l=name))
    for name, col, rx, src, dst in flows:
        a = centroid(d, src, rx)
        bs = [c for c in (centroid(d, r, rx) for r in dst) if c]
        if not a or not bs:
            continue
        bx = sum(b[0] for b in bs) / len(bs); by = sum(b[1] for b in bs) / len(bs)
        ov.append(dict(t='arrow', p=[int(a[0]), int(a[1]), int(bx), int(by)], c=col, lw=2.2, dash=True,
                       label=name, lp=[int((a[0] + bx) / 2) + 250, int((a[1] + by) / 2) - 250], fs=10))
    return ov, legend


CN1_BLOCKS = [
    ('H3 + fan-out ring', '#e3a857', ['U1'], 'T'),
    ('DDR3 4Gb x16', '#b18cff', ['U8'], 'T'),
    ('VDD_CPUX buck', '#ff9b54', ['U3', 'L2', 'C15', 'C16', 'C17'], 'T'),
    ('VCC_3V3 buck', '#8fd16a', ['U2', 'L1', 'C8', 'C9'], 'T'),
    ('VDD_SYS buck', '#f3d34a', ['U4', 'L3', 'C22', 'C23'], 'T'),
    ('VCC_DRAM buck', '#c79bff', ['U5', 'L4', 'C28', 'C29'], 'T'),
    ('WiFi RTL8189 + u.FL', '#ff9fc7', ['U9', 'J3', 'Y3'], 'T'),
    ('J1 · CM4 1-100 (bottom)', '#4f82e6', ['J1'], 'B'),
    ('J2 · CM4 101-200 (bottom)', '#4f82e6', ['J2'], 'B'),
]
CN1_FLOWS = [
    ('HDMI', '#c79bff', r'^HDMI_(D\d|CK)_[PN]$', 'U1', ['J2']),
    ('USB0-3', '#7fb4ff', r'^USB\d_D[PM]$', 'U1', ['J2']),
    ('EPHY', '#6fd3c1', r'^EPHY_(TX|RX)[PN]$', 'U1', ['J1']),
    ('GPIO / SPI / UART', '#90a4ae', r'^(GPIO|ID_S)', 'U1', ['J1']),
    ('SD', '#4dd0e1', r'^SD_(CMD|D\d)$', 'U1', ['J1']),
    ('SDIO', '#ff9fc7', r'^WL_SDIO_', 'U1', ['U9']),
    ('DDR lanes', '#ffb74d', r'^DDR_(DQ\d+|DQS\d_[PN]|DM\d)$', 'U1', ['U8']),
    ('ADDR/CMD', '#b39ddb', r'^DDR_(A\d+|BA\d|RAS_N|CAS_N|WE_N)$', 'U1', ['U8']),
]
MZ_BLOCKS = [
    ('CN1 module outline (keep-out top)', '#e3a857', ['J1', 'J2', 'H5', 'H6', 'H7', 'H8'], None),
    ('40-pin header', '#90a4ae', ['J12'], 'T'),
    ('USB-A x4 + switches + ESD', '#7fb4ff', ['J6', 'J7', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7', 'U8', 'U9'], 'T'),
    ('RJ45 10/100', '#6fd3c1', ['J10'], 'T'),
    ('HDMI-A + ESD', '#c79bff', ['J9', 'D6', 'D7'], 'T'),
    ('12-24 V in + 5 V / 5 A buck', '#e8574d', ['J3', 'F1', 'Q1', 'C7', 'U1', 'D3', 'L1', 'C14', 'C15', 'C16'], 'T'),
    ('USB-C device (FEL) + mux', '#ffd166', ['J8', 'U11', 'U10', 'SW1'], 'T'),
    ('microSD (bottom)', '#4dd0e1', ['J11', 'U12'], 'B'),
    ('Keys', '#a5d6a7', ['SW2', 'SW3', 'SW4'], 'T'),
]
MZ_FLOWS = [
    ('HDMI', '#c79bff', r'^HDMI_(D\d|CK)_[PN]$', 'J2', ['J9']),
    ('USB1/2/3 -> A1-A3', '#7fb4ff', r'^USB[123]_D[PM]$', 'J2', ['J6', 'J7']),
    ('USB0 -> mux', '#ffd166', r'^USB0_D[PM]$', 'J2', ['U10']),
    ('EPHY', '#6fd3c1', r'^EPHY_(TX|RX)[PN]$', 'J1', ['J10']),
    ('GPIO', '#90a4ae', r'^(GPIO|ID_S)', 'J1', ['J12']),
    ('SD', '#4dd0e1', r'^SD_(CMD|D\d|CLK)$', 'J1', ['J11']),
    ('5 V', '#e8574d', r'^VCC_5V$', 'L1', ['J1']),
]


def n_cn1(d):
    return """
<h2>CN1 · مرحله‌ی ۱: ابعاد، استک‌آپ و جای‌گذاری</h2>
<p class="lead">ماژول H3 در قالب CM4: ابعاد 55 × 40 mm، <b>شش لایه</b> با قوانین HDI (track و clearance برابر 0.10، سوراخ 0.10)، و دو کانکتور DF40C-100DP زیر برد. ۱۷۸ قطعه جای‌گذاری شده‌اند.</p>
<div class="callout"><b>موقعیت کانکتورها</b> (دید از بالا، مبدأ گوشه‌ی بالا-چپ): پین k هر کانکتور در <span class="mono">X = 19.82 + 0.4·⌊(k−1)/2⌋</span> است، پس مرکز هر دو کانکتور در <span class="mono">X = 29.62</span> قرار دارد.
J1 (پین‌های 1 تا 100): ردیف فرد در <span class="mono">Y 38.315</span> و ردیف زوج در <span class="mono">Y 35.625</span>. J2 (پین‌های 101 تا 200): ردیف فرد در <span class="mono">Y 4.375</span> و ردیف زوج در <span class="mono">Y 1.665</span>.
این عددها از نقشه‌ی مونتاژ CB1 V2.1 با دقت حدود ±0.05 mm استخراج شده‌اند. <b>قبل از سفارش، آن‌ها را با فایل STEP ماژول CM4 یا فایل KiCad برد CM4IO تطبیق دهید.</b></div>
<h4>چیدمان (نسخه‌ی ۳)</h4>
<ul>
<li><b>H3</b> با چرخش 180° در <span class="mono">(30.5, 19.2)</span> قرار دارد. byte lane های DRAM روی لبه‌ی چپ آن‌اند، آدرس در گوشه‌ی بالا-چپ، GPIO/SD/EPHY رو به J1 در پایین، و HDMI/USB/SDIO روی لبه‌ی راست. سمت راست H3 یک نوار ۳ میلی‌متری برای فن‌اوت سیگنال‌ها آزاد مانده است.</li>
<li><b>DDR3</b> (K4B4G1646E، ‏512MB) <b>خوابیده</b> با چرخش 270° در <span class="mono">(8.6, 19.2)</span> است. ردیف‌های دیتا (A..H) رو به H3 هستند و ردیف‌های آدرس (J..T) در سمت دور. کانال بین DDR و H3 حدود 6.8 mm پهنا دارد.</li>
<li><b>مبدل‌ها:</b> VDD_CPUX و 3V3 در ستون راست‌اند، VCC_DRAM در نوار بالا (بالای DDR)، و VDD_SYS زیر DDR.</li>
<li><b>WiFi</b> در گوشه‌ی بالا-راست است و u.FL روی لبه‌ی بالا قرار دارد.</li>
<li><b>Bottom:</b> کانکتورها و خازن‌های 0402/0603 زیر BGA ها، و کریستال 24MHz. محدوده‌ی ویاهای فن‌اوت کانکتورها (نوار ۵.۶ میلی‌متری کنار هر کانکتور) روی هر دو طرف از قطعه خالی است.</li>
</ul>
"""


def n_cn1_2(d):
    nv = len(d['vias'])
    return """
<h2>CN1 · مرحله‌ی ۲: فن‌اوت BGA، پلین‌ها و دکاپلینگ</h2>
<p class="lead">در این مرحله هر توپ داخلی H3 و DDR3 یک dog-bone با ویای 0.30/0.15 گرفت، پلین‌ها کشیده شدند و خازن‌های Bottom با آگاهی از موقعیت ویاها دوباره چیده شدند. تعداد کل ویاها %d است.</p>
<h4>استک‌آپ ۶ لایه</h4>
<ul>
<li><b>L1</b> سیگنال (فن‌اوت دو حلقه‌ی بیرونی BGA و lane 1 حافظه) · <b>L2</b> GND · <b>L3</b> سیگنال (lane 0، آدرس و HDMI) · <b>L4</b> پلین تقسیم‌شده‌ی تغذیه · <b>L5</b> GND · <b>L6</b> سیگنال، کانکتورها و دکاپلینگ.</li>
<li>L3 بین L2 (زمین) و L4 (تغذیه) است و مرجع اصلی‌اش L2 است. L6 روی L5 (زمین) قرار دارد.</li>
</ul>
<h4>تقسیم پلین L4 (در لایه‌ی L4 ببینید)</h4>
<ul>
<li><b>VCC_DRAM</b> (بنفش): کل DDR، توپ‌های DRAM در H3 (سمت چپ خط مرز x ≈ 30.8) و نوار مبدل DRAM در بالا.</li>
<li><b>VDD_SYS</b> (زرد): خوشه‌ی توپ‌های SYS، <b>دو گردنه</b> که بین ستون‌های توپ به پایین می‌روند (هیچ ویای دیگری داخل گردنه‌ها مجاز نیست)، سپس یک نوار زیر H3 و DDR تا مبدل SYS.</li>
<li><b>VDD_CPUX</b> (نارنجی): خوشه‌ی CPUX و یک نوار به سمت راست تا خروجی مبدل CPUX.</li>
<li><b>VCC_5V</b> (قرمز): ستون راست (ورودی مبدل‌ها) و نوار پایین کنار پین‌های 77 تا 87 کانکتور.</li>
<li><b>VCC_3V3</b> (سبز روشن): بقیه‌ی سطح.</li>
</ul>
<h4>دکاپلینگ</h4>
<p>هر خازن 0402 در Bottom نزدیک توپ یا ویای ریل خودش قرار گرفته است. اگر پد روی ویای هم‌نت بیفتد (via-in-pad پرشده) از همان استفاده می‌شود، و در غیر این صورت یک ویای 0.40/0.20 کنار پد به پلین می‌رود. پدهای تغذیه‌ی قطعات دیگر هم ویای پلین گرفته‌اند.</p>
""" % nv


def ddr_table():
    import cn1_ddr, pcbnew as _p
    rows, summ = cn1_ddr.summary(_p.LoadBoard(os.path.join(OUT, 'cn1_ddr_tuned.kicad_pcb')))
    tr = ''
    for g in summ:
        tr += '<tr><td>%s</td><td>%s</td><td>%s – %s</td><td>%s</td></tr>' % (
            g['group'], '%.2f' % g['ref'] if g['ref'] else '-', g['min'] if g['min'] is not None else '-', g['max'] if g['max'] is not None else '-',
            '%.3f' % g['pair_skew'] if g['pair_skew'] is not None else '-')
    det = ''
    for r in sorted(rows, key=lambda r: (r['group'], r['net'])):
        det += '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (r['group'], r['net'], r['len'], r['vias'])
    return tr, det


def n_cn1_3(d):
    tr, det = ddr_table()
    return """
<h2>CN1 · مرحله‌ی ۳: مسیریابی DDR3</h2>
<p class="lead">هر ۵۲ نت DDR (دو byte lane، آدرس/کامند، CK، و VREF/ZQ) با مسیریاب negotiated-congestion (روش PathFinder روی شبکه‌ی 0.05 mm) کشیده شده‌اند و هیچ تداخلی با هم ندارند. بعد طول‌ها تنظیم شدند و مسیرهای کوتاه با meander (آکاردئونی) بلند شدند.</p>
<h4>تصمیم‌ها</h4>
<ul>
<li><b>ترتیب بیت‌ها</b> داخل هر lane (DQ1 تا DQ7) طوری عوض شد که خطوط مستقیم کمترین اختلاف طول و تقاطع را داشته باشند. DQ0، DQS و DM سر جایشان مانده‌اند. این تغییر در شماتیک (<span class="mono">DQ_SWAP</span> در فایل <span class="mono">build_cn1.py</span>) هم اعمال شده است.</li>
<li><b>هر lane روی یک لایه:</b> lane 0 روی L3 (ردیف‌های E..H حافظه که دورترند و از طریق ویاهای dog-bone در دسترس‌اند) و lane 1 روی L1 (ردیف‌های A..D). آدرس روی L3 و L6 از بالای DDR عبور می‌کند.</li>
<li>زوج‌های DQS و CK در یک کریدور جفت‌شده کشیده شده‌اند و اختلاف طول P/N پس از تنظیم تقریباً صفر است. مقاومت 100Ω خاتمه‌ی CK کنار DDR است.</li>
<li><b>بودجه‌ی طول:</b> DQ/DM نسبت به DQS همان lane ±1.27 mm (50 mil)، زوج‌ها ±0.13 mm و آدرس/کامند نسبت به CK ±5 mm در نظر گرفته شده است (H3 در حدود 672 MHz). اختلاف فعلی lane ها هنوز بزرگ‌تر از هدف است و در مرحله‌ی بهینه‌سازی نهایی با meander دستی روی چند نت کوتاه جبران می‌شود.</li>
</ul>
<h4>خلاصه‌ی طول‌ها (mm، شامل طول بشکه‌ی ویا)</h4>
<div class="tblwrap"><table><thead><tr><th>Group</th><th>Ref (DQS/CK)</th><th>Range</th><th>P/N skew</th></tr></thead><tbody>%s</tbody></table></div>
<details><summary>جزئیات همه‌ی نت‌ها</summary><div class="tblwrap"><table><thead><tr><th>Group</th><th>Net</th><th>Length mm</th><th>Vias</th></tr></thead><tbody>%s</tbody></table></div></details>
""" % (tr, det)


def n_cn1_4(d):
    drc = d.get('drc', [])
    return """
<h2>CN1 · مرحله‌ی ۴: بقیه‌ی سیگنال‌ها</h2>
<p class="lead">HDMI (۴ زوج 100Ω)، USB0 تا USB3 (زوج‌های 90Ω)، EPHY، SD، SDIO، GPIO های هدر، سیگنال‌های سیستمی و تغذیه‌های کوچک (AVCC، EPHY، WiFi، 1.8V) با همان مسیریاب کشیده شده‌اند. زوج‌های تفاضلی کریدور جفت‌شده دارند. اتصال‌های باز در این نسخه: <b>%d</b>.</p>
<ul>
<li>HDMI و USB از لبه‌ی راست H3 به J2 (بالای برد) می‌روند و GPIO/SD/EPHY از لبه‌ی پایین H3 به J1.</li>
<li>برای خروج از پدهای 0.4 mm کانکتور DF40، ویاها در نوار کنار هر کانکتور قرار گرفته‌اند (Bottom = L6).</li>
<li>مسیرهای SW مبدل‌ها کوتاه و پهن (0.6 mm) روی L1 کشیده شده‌اند. خروجی مبدل‌ها از طریق پلین L4 پخش می‌شود.</li>
</ul>
""" % d.get('unrouted', 0)


def n_mz(d):
    return '''
<h2>میزبان · مرحله‌ی ۲: ابعاد، استک‌آپ و جای‌گذاری</h2>
<p class="lead">برد میزبان 96 × 72 mm است (زیر 10 × 10 سانتی‌متر)، چهار لایه با قوانین عادی سازنده: track و space برابر 0.127، ویا 0.45/0.20 و annular ring حداقل 0.1016. ۱۲۶ قطعه جای‌گذاری شده‌اند: ۱۰۳ روی Top و ۲۳ روی Bottom.</p>
<div class="callout">CN1 در ربع بالا-چپ نشسته و نسبت به نقشه‌ی CN1 به اندازه‌ی 180° چرخیده است (<span class="mono">x = 58.5 − xm</span> و <span class="mono">y = 48 − ym</span>). در این حالت J1 ماژول (GPIO، اترنت، SD و 5V) رو به هدر ۴۰ پین بالاست و J2 (USB و HDMI) رو به لبه‌ی پایین. موقعیت همه‌ی ۲۰۰ پد سوکت با پدهای CN1 به‌صورت خودکار چک شد و هیچ خطایی نداشت.</div>
<h4>چیدمان</h4>
<ul>
<li><b>لبه‌ی بالا:</b> هدر ۴۰ پین با ترتیب Raspberry Pi (پین 1 در <span class="mono">(9.0, 5.04)</span>، ردیف زوج کنار لبه)، دو هدر فن و UART دیباگ.</li>
<li><b>لبه‌ی راست:</b> دو USB-A دوطبقه (پورت‌های A1 تا A4) و RJ45 از نوع HR911105A. در ستون کنار آن‌ها، هر پورت یک SY6280 و یک USBLC6 دارد که درست روبه‌روی پین‌های همان پورت قرار گرفته‌اند.</li>
<li><b>لبه‌ی پایین:</b> USB-C برای حالت device و FEL، HDMI-A، مبدل 5V/5A (TPS54560 و سلف 12 × 12)، و ترمینال ورودی 12 تا 24 ولت زیر RJ45. مسیر توان کوتاه و خطی است: J3 → F1 → Q1 → C7 → U1 → L1 → خازن‌های خروجی → پلین 5V در L3.</li>
<li><b>Bottom:</b> سوکت microSD روی لبه‌ی چپ (شیار رو به بیرون، مثل Raspberry Pi) به‌همراه سوئیچ توان کارت و چند مقاومت و خازن. خازن‌های 5V و 3V3 ماژول پشت پین‌های 77 تا 87 قرار دارند.</li>
<li><b>زیر ماژول هیچ قطعه‌ای روی Top نیست.</b> نوار پشت پدهای سوکت در Bottom هم برای ویاهای فن‌اوت خالی نگه داشته شده است.</li>
<li>USB0 از طریق FSUSB42 بین پورت A4 (Host) و USB-C (Device) سوئیچ می‌شود. کلید SW1 هم‌زمان سیگنال USB0_ID را تنظیم می‌کند.</li>
</ul>
<h4>مرحله‌ی بعد</h4>
<p>مسیریابی زوج‌های HDMI (100Ω)، USB (90Ω) و اترنت، سپس SD و GPIO و در آخر پلین‌ها. روی ۴ لایه، L2 زمین یکپارچه است و L3 پلین 5V و 3V3.</p>
'''


def n_mz_2(d):
    return """
<h2>میزبان · مرحله‌ی ۲: مسیریابی</h2>
<p class="lead">همه‌ی نت‌های سیگنال و تغذیه‌های کوچک روی L1 و L4 کشیده شده‌اند. L3 (پلین 5V) فقط در صورت لزوم و با هزینه‌ی بالا برای عبورهای کوتاه استفاده شده است. L2 زمین یکپارچه است. اتصال‌های باز در این نسخه: <b>%d</b>.</p>
<ul>
<li><b>HDMI:</b> چهار زوج TMDS مستقیم از J2 ماژول به ESD های TPD4E05U06 و بعد به کانکتور HDMI-A در لبه‌ی پایین می‌روند (0.13/0.20 برای 100Ω).</li>
<li><b>USB:</b> USB1/2/3 به پورت‌های A1 تا A3 وصل‌اند و USB0 از FSUSB42 به A4 یا USB-C می‌رود. همه زوج 0.15/0.17 برای 90Ω هستند و ESD کنار کانکتورها قرار دارد.</li>
<li><b>اترنت:</b> TX/RX از J1 ماژول به HR911105A می‌روند و LED ها با 330Ω از 3.3V تغذیه می‌شوند.</li>
<li><b>تغذیه‌ی ورودی:</b> VIN (0.8 mm) و SW مبدل (1.0 mm) کوتاه روی L1 هستند، و 5V خروجی از طریق پلین L3 به همه جا می‌رسد.</li>
<li><b>3.3V</b> از پین‌های 84/86 ماژول با ترک 0.2 mm تغذیه می‌شود. مصرف روی میزبان کم است: کارت SD، LED ها و pull-up ها.</li>
</ul>
""" % d.get('unrouted', 0)


def stack_html():
    def rows(L):
        out = []
        for ln, name, role, c, t in L:
            if c:
                out.append('<div class="st cu"><span><b>%s</b> %s</span><span style="display:flex;gap:10px;align-items:center"><span class="bar" style="background:%s;width:120px"></span><span style="direction:rtl">%s</span></span><span class="mono" style="color:var(--muted)">%s</span></div>' % (ln, name, c, role, t))
            else:
                out.append('<div class="st di"><span></span><span>%s</span><span></span></div>' % role)
        return ''.join(out)
    cn1 = [('L1', 'F.Cu', 'Signal + قطعات', '#e5483f', '0.035'), ('', '', 'PP 1080 · 0.076 · εr 4.1', None, ''),
           ('L2', 'In1.Cu', 'GND', '#58c46c', '0.018'), ('', '', 'Core · 0.20 · εr 4.3', None, ''),
           ('L3', 'In2.Cu', 'Signal · stripline (DDR، HDMI)', '#eda23a', '0.018'), ('', '', 'PP · 0.50', None, ''),
           ('L4', 'In3.Cu', 'Power planes (تقسیم‌شده)', '#d65c9b', '0.018'), ('', '', 'Core · 0.20', None, ''),
           ('L5', 'In4.Cu', 'GND', '#3fc4cf', '0.018'), ('', '', 'PP 1080 · 0.076', None, ''),
           ('L6', 'B.Cu', 'Signal + کانکتورها + دکاپلینگ', '#4f82e6', '0.035')]
    mz = [('L1', 'F.Cu', 'Signal + قطعات', '#e5483f', '0.035'), ('', '', 'PP 3313 · 0.0994 · εr 4.1', None, ''),
          ('L2', 'In1.Cu', 'GND یکپارچه', '#58c46c', '0.0152'), ('', '', 'Core · 1.265', None, ''),
          ('L3', 'In2.Cu', '5V / 3V3 planes', '#d65c9b', '0.0152'), ('', '', 'PP 3313 · 0.0994', None, ''),
          ('L4', 'B.Cu', 'Signal + microSD', '#4f82e6', '0.035')]
    imp = [('CN1', '50 Ω', 'L1 / L6', '0.10', '—'), ('CN1', '90 Ω diff', 'L1 / L6', '0.10', '0.11'),
           ('CN1', '100 Ω diff', 'L1 / L6', '0.10', '0.25'), ('CN1', '50 Ω', 'L3', '0.10', '—'),
           ('CN1', '100 Ω diff', 'L3', '0.10', '0.21'),
           ('میزبان', '50 Ω', 'L1 / L4', '0.15', '—'), ('میزبان', '90 Ω diff (USB)', 'L1 / L4', '0.15', '0.17'),
           ('میزبان', '100 Ω diff (HDMI, ETH)', 'L1 / L4', '0.13', '0.20')]
    trs = ''.join('<tr><td style="font-family:var(--sans)">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % r for r in imp)
    return '''
<h2>استک‌آپ و قوانین هر دو برد</h2>
<h4>CN1 · شش لایه، حدود 1.2 mm، سطح پیشرفته (HDI)</h4>
<p class="lead">هر لایه‌ی سیگنال یک GND نزدیک دارد: L1 روی L2، L3 زیر L2 (فاصله‌ی 0.20 در برابر 0.50 تا L4) و L6 روی L5. پلین تقسیم‌شده‌ی تغذیه (L4) از L3 دور نگه داشته شده تا مسیرهای L3 مرجعشان را از L2 بگیرند.</p>
<div class="stack">%s</div>
<h4>میزبان · چهار لایه، 1.6 mm، قوانین عادی</h4>
<div class="stack">%s</div>
<h4>امپدانس‌ها (تخمین با فرمول‌های IPC-2141)</h4>
<div class="tblwrap"><table><thead><tr><th>Board</th><th>Target</th><th>Layer</th><th>W mm</th><th>Gap mm</th></tr></thead><tbody>%s</tbody></table></div>
<p style="color:var(--muted);font-size:12.5px">این عددها تقریبی‌اند. قبل از سفارش، آن‌ها را با ماشین‌حساب امپدانس سازنده و برای همان استک‌آپ دقیق کنید و گزینه‌ی Impedance Control را فعال کنید.</p>
<h4>قوانین ساخت</h4>
<ul>
<li><b>CN1:</b> track و clearance حداقل 0.10، ویای BGA و سیگنال 0.30/0.15، ویای تغذیه 0.40/0.20، و via-in-pad پرشده فقط برای خازن‌های زیر BGA. همه‌ی ویاها through هستند و blind/buried لازم نشد.</li>
<li><b>میزبان:</b> track و clearance حداقل 0.127 (سیگنال‌ها 0.15)، ویا 0.50/0.25، annular ring حداقل 0.1016، فاصله‌ی مس تا لبه 0.3، و حداقل ارتفاع متن 6 mil. زیر ماژول قطعه‌ای روی Top نیست.</li>
</ul>
''' % (rows(cn1), rows(mz), trs)


STAGES = [
    dict(id='c1', title='CN1 · ابعاد و جای‌گذاری', sub='55×40 · 6L HDI · floorplan v3', state='done'),
    dict(id='c2', title='CN1 · فن‌اوت BGA و پلین‌ها', sub='Dog-bone · L4 split · decaps', state='done'),
    dict(id='c3', title='CN1 · مسیریابی DDR3', sub='2 byte lanes · addr/cmd · meanders', state='done'),
    dict(id='c4', title='CN1 · بقیه‌ی سیگنال‌ها', sub='HDMI · USB · EPHY · SD · GPIO', state='done'),
    dict(id='m1', title='میزبان · ابعاد و جای‌گذاری', sub='96×72 · 4L · floorplan', state='done'),
    dict(id='m2', title='میزبان · مسیریابی', sub='HDMI · USB · ETH · power', state='done'),
    dict(id='x1', title='بهینه‌سازی، DRC و خروجی ساخت', sub='Length polish · pours · Gerber', state='planned'),
]


GROUPS_DDR = [
    ('Lane 0  DQ0-7 · DQS0 · DM0 (L3)', '#ffb74d', r'DDR_(DQ[0-7]|DQS0_[PN]|DM0)$'),
    ('Lane 1  DQ8-15 · DQS1 · DM1 (L1)', '#4fc3f7', r'DDR_(DQ([89]|1[0-5])|DQS1_[PN]|DM1)$'),
    ('CK / CK#', '#ffffff', r'DDR_CK_[PN]$'),
    ('ADDR / CMD', '#b39ddb', r'DDR_(A\d+|BA\d|RAS_N|CAS_N|WE_N|CS_N|CKE|ODT|RESET_N)$'),
]
GROUPS_PAIRS = [
    ('HDMI TMDS (100 Ω)', '#c79bff', r'^HDMI_(D\d|CK)_[PN]$'),
    ('Ethernet TX/RX (100 Ω)', '#6fd3c1', r'^EPHY_(TX|RX)[PN]$'),
    ('USB D± (90 Ω)', '#7fb4ff', r'^USB\w*_D[PM]$'),
]


def groups(d, which):
    spec = GROUPS_DDR + (GROUPS_PAIRS if which == 'all' else [])
    out = []
    for name, col, rx in spec:
        codes = [i for i, n in enumerate(d['nets']) if n and re.search(rx, n.split('/')[-1])]
        if codes:
            out.append(dict(name=name, c=col, nets=codes))
    return out


def main():
    tpl = open(os.path.join(HERE, 'viewer_template.html')).read()
    blocks, meta = [], []
    data = {'c1': ('cn1_stage1.kicad_pcb', CN1_LAYERS, 'CN1 · H3 module', CN1_BLOCKS, CN1_FLOWS, n_cn1, None),
            'c2': ('cn1_stage2.kicad_pcb', CN1_LAYERS, 'CN1 · H3 module', [], [], n_cn1_2, None),
            'c3': ('cn1_ddr_tuned.kicad_pcb', CN1_LAYERS, 'CN1 · H3 module', [], [], n_cn1_3, 'ddr'),
            'c4': ('cn1_all.kicad_pcb', CN1_LAYERS, 'CN1 · H3 module', [], [], n_cn1_4, 'all'),
            'm1': ('mizban_stage1.kicad_pcb', MZ_LAYERS, 'Mizban · carrier', MZ_BLOCKS, MZ_FLOWS, n_mz, None),
            'm2': ('mizban_r1.kicad_pcb', MZ_LAYERS, 'Mizban · carrier', [], [], n_mz_2, 'all')}
    for st in STAGES:
        meta.append(dict(id=st['id'], title=st['title'], sub=st['sub'], state=st['state']))
        if st['id'] in data:
            pcb, layers, name, bl, fl, nf, grp = data[st['id']]
            if not os.path.exists(os.path.join(OUT, pcb)) or st['id'] in os.environ.get('VIEW_SKIP', '').split(','):
                meta[-1]['state'] = 'planned'
                blocks.append('<template id="notes-%s"><h2>این مرحله هنوز انجام نشده</h2></template>' % st['id'])
                continue
            d = export(pcb, layers, name)
            d['ov'], d['legend'] = blocks_and_flows(d, bl, fl)
            if grp:
                d['groups'] = groups(d, grp)
                d['legend'] = d['legend'] + [dict(c=g['c'], l=g['name']) for g in d['groups']]
            blocks.append('<script type="application/json" id="stage-%s">%s</script>' % (st['id'], json.dumps(d, separators=(',', ':')).replace('</', '<\\/')))
            blocks.append('<template id="notes-%s">%s</template>' % (st['id'], nf(d)))
        else:
            blocks.append('<template id="notes-%s"><h2>این مرحله هنوز انجام نشده</h2></template>' % st['id'])
    blocks.insert(0, '<script type="application/json" id="stages-meta">%s</script>' % json.dumps(meta))
    blocks.append('<template id="stack-html">%s</template>' % stack_html())
    out = tpl.replace('<!--DATA-->', '\n'.join(blocks))
    dst = os.path.join(OUT, 'h3_cn1_mizban.html')
    open(dst, 'w').write(out)
    print('wrote', dst, os.path.getsize(dst) // 1024, 'KB')


if __name__ == '__main__':
    main()
