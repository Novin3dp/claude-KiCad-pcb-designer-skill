"""Minimal KiCad 8/9 schematic generator.

Every symbol pin is connected by a short wire stub + a net label (local label if the
net only lives on one sheet, global label otherwise) or marked no-connect.
Library symbols are copied (and flattened) from the stock KiCad libraries; custom
symbols are generated from pin lists.
"""
import re, uuid, math, os, hashlib

KLIB = '/usr/share/kicad/symbols'
PROJECT = 'klipper_h3_host'
GRID = 2.54


def uid(seed=None):
    if seed is None:
        return str(uuid.uuid4())
    h = hashlib.md5(seed.encode()).hexdigest()
    return str(uuid.UUID(h))


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def snap(v):
    return round(round(v / 1.27) * 1.27, 4)

# ----------------------------------------------------------------------------
# s-expression helpers (only what we need to lift symbols out of .kicad_sym)

def find_block(text, start):
    d = 0
    instr = False
    i = start
    while i < len(text):
        c = text[i]
        if instr:
            if c == '\\':
                i += 2
                continue
            if c == '"':
                instr = False
        else:
            if c == '"':
                instr = True
            elif c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    return text[start:i + 1]
        i += 1
    raise ValueError('unbalanced')


class Pin:
    def __init__(self, num, name, x, y, ang, etype, length=2.54, unit=1, hidden=False):
        self.num, self.name, self.x, self.y, self.ang = num, name, x, y, ang
        self.etype, self.length, self.unit, self.hidden = etype, length, unit, hidden


class SymDef:
    """A symbol definition ready to be embedded into lib_symbols."""

    def __init__(self, lib_id, text, pins, units=1, bbox=None, power=False):
        self.lib_id = lib_id
        self.text = text          # full '(symbol "lib_id" ...)' text
        self.pins = pins          # list[Pin]
        self.units = units
        self.bbox = bbox          # per unit: {unit: (xmin,ymin,xmax,ymax)} lib coords
        self.power = power

    def unit_pins(self, unit):
        return [p for p in self.pins if p.unit in (0, unit)]


_libcache = {}


def _libtext(lib):
    if lib not in _libcache:
        _libcache[lib] = open(os.path.join(KLIB, lib + '.kicad_sym')).read()
    return _libcache[lib]


def _raw_symbol(lib, name):
    t = _libtext(lib)
    m = re.search(r'\n\t\(symbol ' + re.escape(q(name)), t)
    if not m:
        raise KeyError(lib + ':' + name)
    return find_block(t, m.start() + 2)


def load_lib(lib, name):
    """Return a flattened SymDef for lib:name."""
    raw = _raw_symbol(lib, name)
    ext = re.search(r'\(extends "([^"]+)"\)', raw)
    if ext:
        parent = _raw_symbol(lib, ext.group(1))
        # child's properties replace parent's
        child_props = re.findall(r'\(property "([^"]+)"', raw)
        body = parent
        # rename top symbol + sub units
        pn = ext.group(1)
        body = body.replace('(symbol ' + q(pn), '(symbol ' + q(name), 1)
        body = re.sub(r'\(symbol "' + re.escape(pn) + r'_(\d+)_(\d+)"', lambda m: '(symbol "%s_%s_%s"' % (name, m.group(1), m.group(2)), body)
        # swap property blocks
        for pr in child_props:
            cm = re.search(r'\(property "' + re.escape(pr) + '"', raw)
            cblk = find_block(raw, cm.start())
            pm = re.search(r'\(property "' + re.escape(pr) + '"', body)
            if pm:
                pblk = find_block(body, pm.start())
                body = body[:pm.start()] + cblk + body[pm.start() + len(pblk):]
            else:
                # insert after first line
                k = body.find('(property')
                body = body[:k] + cblk + '\n\t\t' + body[k:]
        raw = body
    lib_id = lib + ':' + name
    text = raw.replace('(symbol ' + q(name), '(symbol ' + q(lib_id), 1)
    pins = []
    # units: sub symbols named name_U_S
    for sm in re.finditer(r'\(symbol "' + re.escape(name) + r'_(\d+)_(\d+)"', raw):
        unit = int(sm.group(1))
        blk = find_block(raw, sm.start())
        for pm in re.finditer(r'\(pin (\w+) (\w+)', blk):
            pb = find_block(blk, pm.start())
            at = re.search(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', pb)
            ln = re.search(r'\(length ([-\d.]+)\)', pb)
            nm = re.search(r'\(name "([^"]*)"', pb)
            nu = re.search(r'\(number "([^"]*)"', pb)
            hidden = bool(re.search(r'\(hide yes\)|\bhide\b', pb.split('(name')[0]))
            pins.append(Pin(nu.group(1), nm.group(1), float(at.group(1)), float(at.group(2)),
                            int(float(at.group(3) or 0)), pm.group(1), float(ln.group(1)), unit, hidden))
    units = max([p.unit for p in pins] + [1])
    power = '(power)' in raw
    # bbox from graphics (rectangles/polylines) + pins
    bb = {}
    for u in range(0, units + 1):
        bb[u] = None
    return SymDef(lib_id, text, pins, units, None, power)

# ----------------------------------------------------------------------------
# custom symbol builder


def make_ic(lib_id, units, ref='U', value='', footprint='', datasheet='', desc='', pin_len=2.54, min_w=15.24):
    """units: list of dict(name=str, left=[(num,name,etype)|None...], right=[...], top=[...], bottom=[...])
    None entries leave a gap. Returns SymDef."""
    pins = []
    parts = []
    bboxes = {}
    for ui, u in enumerate(units, start=1):
        L, R, T, B = u.get('left', []), u.get('right', []), u.get('top', []), u.get('bottom', [])
        maxlen_l = max([len(p[1]) for p in L if p] + [0])
        maxlen_r = max([len(p[1]) for p in R if p] + [0])
        w = max(min_w, (maxlen_l + maxlen_r) * 1.05 + 5.08, (max(len(T), len(B)) + 1) * GRID)
        w = math.ceil(w / (2 * GRID)) * 2 * GRID
        rows = max(len(L), len(R), 1)
        h = (rows + 2) * GRID
        if T:
            h += max(len(p[1]) for p in T if p) * 1.05 + 2.54
        if B:
            h += max(len(p[1]) for p in B if p) * 1.05 + 2.54
        h = math.ceil(h / (2 * GRID)) * 2 * GRID
        x0, x1 = -w / 2, w / 2
        y1 = h / 2
        y0 = -h / 2
        # left/right pins start from top margin
        top_off = (max(len(p[1]) for p in T if p) * 1.05 + 2.54) if T else 0
        top_off = math.ceil(top_off / GRID) * GRID
        for i, p in enumerate(L):
            if p:
                pins.append(Pin(p[0], p[1], x0 - pin_len, y1 - top_off - GRID * (i + 1), 0, p[2], pin_len, ui))
        for i, p in enumerate(R):
            if p:
                pins.append(Pin(p[0], p[1], x1 + pin_len, y1 - top_off - GRID * (i + 1), 180, p[2], pin_len, ui))
        n = len(T)
        for i, p in enumerate(T):
            if p:
                xx = (i - (n - 1) / 2) * GRID
                pins.append(Pin(p[0], p[1], snap(xx), y1 + pin_len, 270, p[2], pin_len, ui))
        n = len(B)
        for i, p in enumerate(B):
            if p:
                xx = (i - (n - 1) / 2) * GRID
                pins.append(Pin(p[0], p[1], snap(xx), y0 - pin_len, 90, p[2], pin_len, ui))
        bboxes[ui] = (x0, y0, x1, y1)
        ptxt = []
        for p in [pp for pp in pins if pp.unit == ui]:
            ptxt.append('(pin %s line (at %.4g %.4g %d) (length %.4g) (name %s (effects (font (size 1.016 1.016)))) (number %s (effects (font (size 1.016 1.016)))))'
                        % (p.etype, p.x, p.y, p.ang, p.length, q(p.name), q(p.num)))
        title = u.get('name', '')
        body = '(rectangle (start %.4g %.4g) (end %.4g %.4g) (stroke (width 0.254) (type default)) (fill (type background)))' % (x0, y1, x1, y0)
        if title:
            body += ' (text %s (at 0 %.4g 0) (effects (font (size 1.27 1.27) bold)))' % (q(title), y0 + 1.905 + (B and (max(len(p[1]) for p in B if p) * 1.05 + 2.54) or 0))
        short = lib_id.split(':')[1]
        parts.append('(symbol %s %s %s)' % (q('%s_%d_1' % (short, ui)), body, ' '.join(ptxt)))
    props = ('(property "Reference" %s (at 0 0 0) (effects (font (size 1.27 1.27))))'
             '(property "Value" %s (at 0 0 0) (effects (font (size 1.27 1.27))))'
             '(property "Footprint" %s (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))'
             '(property "Datasheet" %s (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))'
             '(property "Description" %s (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))') % (
        q(ref), q(value or lib_id.split(':')[1]), q(footprint), q(datasheet), q(desc))
    text = '(symbol %s (pin_names (offset 0.762)) (exclude_from_sim no) (in_bom yes) (on_board yes) %s %s)' % (
        q(lib_id), props, ' '.join(parts))
    return SymDef(lib_id, text, pins, len(units), bboxes)

# ----------------------------------------------------------------------------
# placement / geometry


def rot_vec(dx, dy_screen, rot):
    """rotate a screen-space vector by rot degrees CCW (screen, y down)."""
    t = math.radians(rot)
    c, s = round(math.cos(t)), round(math.sin(t))
    return dx * c + dy_screen * s, -dx * s + dy_screen * c


class Placed:
    pass


class Sheet:
    def __init__(self, name, fname, title, paper='A3'):
        self.name, self.fname, self.title, self.paper = name, fname, title, paper
        self.uuid = uid('sheet:' + fname)
        self.items = []   # placed symbols
        self.labels = []  # (net, x, y, angle)
        self.wires = []
        self.ncs = []
        self.texts = []
        self.junctions = []
        self.symdefs = {}
        self.nets_here = set()

    # -- symbols
    def place(self, sd, ref, value, x, y, conns, unit=1, rot=0, footprint=None, fields=None, stub=2.54,
              ref_pos=None, val_pos=None, dnp=False, in_bom=True):
        x, y = snap(x), snap(y)
        self.symdefs[sd.lib_id] = sd
        P = Placed()
        P.sd, P.ref, P.value, P.x, P.y, P.unit, P.rot = sd, ref, value, x, y, unit, rot
        P.footprint = footprint
        P.fields = fields or {}
        P.dnp, P.in_bom = dnp, in_bom
        pins = sd.unit_pins(unit)
        conns = dict(conns)
        used = set()
        # group pins by location (stacked hidden pins share a label)
        seen_loc = {}
        xs, ys = [], []
        for p in pins:
            dx, dy = rot_vec(p.x, -p.y, rot)
            px, py = snap(x + dx), snap(y + dy)
            xs.append(px); ys.append(py)
            key = p.num
            net = conns.get(key, conns.get(p.name))
            if key in conns:
                used.add(key)
            elif p.name in conns:
                used.add(p.name)
            if (px, py) in seen_loc:
                if net is not None and seen_loc[(px, py)] != net:
                    raise ValueError('%s: stacked pin %s conflicts' % (ref, key))
                continue
            if net is None:
                if p.hidden:
                    continue
                raise ValueError('%s (%s) pin %s/%s unconnected - specify net or NC' % (ref, sd.lib_id, p.num, p.name))
            seen_loc[(px, py)] = net
            # outward direction in lib coords = opposite of pin angle
            a = math.radians(p.ang)
            odx, ody = -round(math.cos(a)), -round(math.sin(a))  # lib (y up)
            sdx, sdy = rot_vec(odx, -ody, rot)
            if net == 'NC':
                self.ncs.append((px, py))
                continue
            ex, ey = snap(px + sdx * stub), snap(py + sdy * stub)
            if stub:
                self.wires.append((px, py, ex, ey))
            ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(int(sdx), int(sdy))]
            self.labels.append((net, ex, ey, ang))
            self.nets_here.add(net)
        extra = set(conns) - used
        if extra:
            raise ValueError('%s: unknown pins %s' % (ref, extra))
        P.bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (x, y, x, y)
        # reference / value positions
        horiz = (P.bbox[2] - P.bbox[0]) >= (P.bbox[3] - P.bbox[1])
        if ref_pos is None:
            ref_pos = (x, y - 3.556) if (horiz and len(pins) <= 3) else ((x, P.bbox[1] - 3.81) if rot in (0, 180) else (x, P.bbox[1] - 2.54))
        if val_pos is None:
            val_pos = (x, y + 3.556) if (horiz and len(pins) <= 3) else ((x, P.bbox[3] + 3.81) if rot in (0, 180) else (x, P.bbox[3] + 2.54))
        P.ref_pos, P.val_pos = ref_pos, val_pos
        self.items.append(P)
        return P

    def text(self, s, x, y, size=1.27, bold=False):
        self.texts.append((s, snap(x), snap(y), size, bold))

    def label(self, net, x, y, ang=0):
        self.labels.append((net, snap(x), snap(y), ang))
        self.nets_here.add(net)

    def content_extent(self):
        xs, ys = [0], [0]
        for P in self.items:
            xs += [P.bbox[0], P.bbox[2], P.ref_pos[0], P.val_pos[0]]
            ys += [P.bbox[1], P.bbox[3], P.ref_pos[1], P.val_pos[1]]
        for (net, x, y, ang) in self.labels:
            L = label_len(net)
            dx = {0: L, 180: -L, 90: 0, 270: 0}[ang]
            dy = {0: 0, 180: 0, 90: -L, 270: L}[ang]
            xs += [x, x + dx]; ys += [y, y + dy]
        for (s, x, y, size, bold) in self.texts:
            w = max(len(l) for l in s.split('\n')) * size * 0.62
            xs += [x, x + w]; ys += [y, y + size * 1.6 * (s.count('\n') + 1)]
        return max(xs), max(ys)

    def auto_paper(self):
        mx, my = self.content_extent()
        for name, w, h in (('A4', 297, 210), ('A3', 420, 297), ('A2', 594, 420), ('A1', 841, 594), ('A0', 1189, 841)):
            if mx <= w - 12 and (my <= h - 45 or (mx <= w - 125 and my <= h - 12)):
                return name
        return 'A0'

    # -- serialisation
    def render(self, global_nets, root_uuid, page, project=PROJECT):
        out = []
        out.append('(kicad_sch (version 20231120) (generator "klipper_h3_gen") (generator_version "9.0")')
        out.append('  (uuid %s)' % q(self.uuid))
        self.paper = self.auto_paper()
        if isinstance(self.paper, tuple):
            out.append('  (paper "User" %.2f %.2f)' % self.paper)
        else:
            out.append('  (paper %s)' % q(self.paper))
        out.append('  (title_block (title %s) (date "2026-09-22") (rev "A") (company "Klipper H3 Host") (comment 1 %s))' % (
            q(self.title), q('Sheet: ' + self.name)))
        out.append('  (lib_symbols')
        for sd in self.symdefs.values():
            out.append('    ' + sd.text)
        out.append('  )')
        for (x1, y1, x2, y2) in self.wires:
            out.append('  (wire (pts (xy %.4f %.4f) (xy %.4f %.4f)) (stroke (width 0) (type default)) (uuid %s))' % (x1, y1, x2, y2, q(uid())))
        for (x, y) in self.ncs:
            out.append('  (no_connect (at %.4f %.4f) (uuid %s))' % (x, y, q(uid())))
        for (x, y) in self.junctions:
            out.append('  (junction (at %.4f %.4f) (diameter 0) (color 0 0 0 0) (uuid %s))' % (x, y, q(uid())))
        for (net, x, y, ang) in self.labels:
            just = {0: 'left', 90: 'left', 180: 'right', 270: 'right'}[ang]
            if net in global_nets:
                out.append('  (global_label %s (shape bidirectional) (at %.4f %.4f %d) (fields_autoplaced yes) (effects (font (size 1.016 1.016)) (justify %s)) (uuid %s)'
                           ' (property "Intersheetrefs" "${INTERSHEET_REFS}" (at %.4f %.4f 0) (effects (font (size 1.016 1.016)) (hide yes))))' % (q(net), x, y, ang, just, q(uid()), x, y))
            else:
                out.append('  (label %s (at %.4f %.4f %d) (fields_autoplaced yes) (effects (font (size 1.016 1.016)) (justify %s bottom)) (uuid %s))' % (q(net), x, y, ang, just, q(uid())))
        for (s, x, y, size, bold) in self.texts:
            out.append('  (text %s (exclude_from_sim no) (at %.4f %.4f 0) (effects (font (size %.3f %.3f)%s) (justify left top)) (uuid %s))' % (
                q(s), x, y, size, size, ' bold' if bold else '', q(uid())))
        for P in self.items:
            sd = P.sd
            fp = P.footprint if P.footprint is not None else ''
            su = uid('sym:%s:%s:%d' % (self.fname, P.ref, P.unit))
            props = []
            fa = P.rot % 180
            props.append('(property "Reference" %s (at %.4f %.4f %d) (effects (font (size 1.27 1.27))%s))' % (
                q(P.ref), P.ref_pos[0], P.ref_pos[1], fa, ' (hide yes)' if sd.power else ''))
            props.append('(property "Value" %s (at %.4f %.4f %d) (effects (font (size 1.27 1.27))))' % (q(P.value), P.val_pos[0], P.val_pos[1], fa))
            props.append('(property "Footprint" %s (at %.4f %.4f 0) (effects (font (size 1.27 1.27)) (hide yes)))' % (q(fp), P.x, P.y))
            props.append('(property "Datasheet" "" (at %.4f %.4f 0) (effects (font (size 1.27 1.27)) (hide yes)))' % (P.x, P.y))
            for k, v in P.fields.items():
                props.append('(property %s %s (at %.4f %.4f 0) (effects (font (size 1.27 1.27)) (hide yes)))' % (q(k), q(v), P.x, P.y))
            pins = ' '.join('(pin %s (uuid %s))' % (q(p.num), q(uid())) for p in sd.unit_pins(P.unit))
            out.append('  (symbol (lib_id %s) (at %.4f %.4f %d) (unit %d) (exclude_from_sim no) (in_bom %s) (on_board yes) (dnp %s) (uuid %s) %s %s'
                       ' (instances (project %s (path %s (reference %s) (unit %d)))))' % (
                           q(sd.lib_id), P.x, P.y, P.rot, P.unit, 'yes' if P.in_bom else 'no', 'yes' if P.dnp else 'no', q(su), ' '.join(props), pins,
                           q(project), q('/' + root_uuid + '/' + self.uuid), q(P.ref), P.unit))
        out.append(')')
        return '\n'.join(out)


class Project:
    def __init__(self, name=PROJECT):
        self.name = name
        self.sheets = []
        self.root_uuid = uid('root')
        self.refcount = {}

    def ref(self, prefix):
        self.refcount[prefix] = self.refcount.get(prefix, 0) + 1
        return '%s%d' % (prefix, self.refcount[prefix])

    def add_sheet(self, sh):
        self.sheets.append(sh)
        return sh

    def write(self, outdir, root_title='Klipper H3 Host - Root'):
        os.makedirs(outdir, exist_ok=True)
        count = {}
        for sh in self.sheets:
            for n in sh.nets_here:
                count[n] = count.get(n, 0) + 1
        global_nets = {n for n, c in count.items() if c > 1}
        self.global_nets = global_nets
        for i, sh in enumerate(self.sheets, start=2):
            open(os.path.join(outdir, sh.fname), 'w').write(sh.render(global_nets, self.root_uuid, i, self.name))
        # root sheet
        out = ['(kicad_sch (version 20231120) (generator "klipper_h3_gen") (generator_version "9.0")',
               '  (uuid %s)' % q(self.root_uuid), '  (paper "A3")',
               '  (title_block (title %s) (date "2026-09-22") (rev "A") (company "Klipper H3 Host"))' % q(root_title),
               '  (lib_symbols)']
        cols = 4
        for i, sh in enumerate(self.sheets):
            cx, cy = 30 + (i % cols) * 90, 45 + (i // cols) * 45
            out.append('  (sheet (at %.2f %.2f) (size 70 25) (fields_autoplaced yes) (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid %s)'
                       ' (property "Sheetname" %s (at %.2f %.2f 0) (effects (font (size 1.524 1.524)) (justify left bottom)))'
                       ' (property "Sheetfile" %s (at %.2f %.2f 0) (effects (font (size 1.27 1.27)) (justify left top)))'
                       ' (instances (project %s (path %s (page %s)))))' % (
                           cx, cy, q(sh.uuid), q(sh.name), cx, cy - 0.7, q(sh.fname), cx, cy + 25.6,
                           q(self.name), q('/' + self.root_uuid), q(str(i + 2))))
        self._root_texts(out)
        out.append('  (sheet_instances (path "/" (page "1")))')
        out.append(')')
        open(os.path.join(outdir, self.name + '.kicad_sch'), 'w').write('\n'.join(out))
        # project file
        open(os.path.join(outdir, self.name + '.kicad_pro'), 'w').write(PRO_TEMPLATE % {'name': self.name})

    def _root_texts(self, out):
        for (s, x, y, size) in getattr(self, 'root_texts', []):
            out.append('  (text %s (exclude_from_sim no) (at %.2f %.2f 0) (effects (font (size %.2f %.2f)) (justify left top)) (uuid %s))' % (
                q(s), x, y, size, size, q(uid())))


PRO_TEMPLATE = '''{
  "meta": { "filename": "%(name)s.kicad_pro", "version": 1 },
  "schematic": { "legacy_lib_dir": "", "legacy_lib_list": [] },
  "sheets": [],
  "boards": [],
  "libraries": { "pinned_footprint_libs": [], "pinned_symbol_libs": [] },
  "erc": {
    "erc_exclusions": [],
    "meta": { "version": 0 },
    "pin_map": [],
    "rule_severities": {
      "bus_definition_conflict": "error",
      "bus_entry_needed": "error",
      "bus_to_bus_conflict": "error",
      "bus_to_net_conflict": "error",
      "different_unit_footprint": "error",
      "different_unit_net": "error",
      "duplicate_reference": "error",
      "duplicate_sheet_names": "error",
      "extra_units": "error",
      "global_label_dangling": "warning",
      "hier_label_mismatch": "error",
      "label_dangling": "error",
      "lib_symbol_issues": "warning",
      "lib_symbol_mismatch": "warning",
      "missing_bidi_pin": "warning",
      "missing_input_pin": "warning",
      "missing_power_pin": "error",
      "missing_unit": "warning",
      "multiple_net_names": "warning",
      "net_not_bus_member": "warning",
      "no_connect_connected": "warning",
      "no_connect_dangling": "warning",
      "pin_not_connected": "error",
      "pin_not_driven": "error",
      "pin_to_pin": "warning",
      "power_pin_not_driven": "error",
      "similar_labels": "warning",
      "simulation_model_issue": "ignore",
      "single_global_label": "warning",
      "unannotated": "error",
      "unit_value_mismatch": "error",
      "unresolved_variable": "error",
      "wire_dangling": "error",
      "footprint_link_issues": "ignore",
      "footprint_filter": "ignore"
    }
  }
}
'''


# ----------------------------------------------------------------------------
# automatic flow layout

def label_len(net):
    return 2.54 + len(net) * 0.95 + 3.2


def extent(sd, unit, rot, conns, stub=2.54):
    """bbox (relative to symbol origin, screen coords) including labels & ref/value text."""
    xs, ys = [], []
    for p in sd.unit_pins(unit):
        dx, dy = rot_vec(p.x, -p.y, rot)
        a = math.radians(p.ang)
        odx, ody = -round(math.cos(a)), -round(math.sin(a))
        sdx, sdy = rot_vec(odx, -ody, rot)
        # body side: pin extends inward by length
        bx, by = dx - sdx * p.length, dy - sdy * p.length
        xs += [dx, bx]; ys += [dy, by]
        net = conns.get(p.num, conns.get(p.name))
        if net and net != 'NC' and not p.hidden:
            L = stub + label_len(net)
            xs.append(dx + sdx * L); ys.append(dy + sdy * L)
            # label text height
            if sdx:
                ys += [dy - 1.5, dy + 1.5]
            else:
                xs += [dx - 1.5, dx + 1.5]
    if not xs:
        xs, ys = [-2.54, 2.54], [-2.54, 2.54]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return (x0 - 1.27, y0 - 5.5, x1 + 1.27, y1 + 5.5)


class Flow:
    def __init__(self, sheet, x0, y0, width, gap=3.81):
        self.sh, self.x0, self.y0, self.w, self.gap = sheet, x0, y0, width, gap
        self.cx, self.cy, self.rowh = x0, y0, 0

    def newrow(self, extra=0):
        if self.rowh or self.cx > self.x0:
            self.cy += self.rowh + self.gap + extra
        self.cx, self.rowh = self.x0, 0

    def section(self, title, note=None):
        self.newrow(2.54)
        self.sh.text(title, self.x0, self.cy, size=2.0, bold=True)
        self.cy += 4.5
        if note:
            for ln in note.split('\n'):
                self.sh.text(ln, self.x0, self.cy, size=1.27)
                self.cy += 2.54
            self.cy += 1.0

    def add(self, sd, ref, value, conns, unit=1, rot=0, **kw):
        e = extent(sd, unit, rot, conns)
        w, h = e[2] - e[0], e[3] - e[1]
        if self.cx + w > self.x0 + self.w and self.cx > self.x0:
            self.newrow()
        x = self.cx - e[0]
        y = self.cy - e[1]
        P = self.sh.place(sd, ref, value, x, y, conns, unit=unit, rot=rot, **kw)
        self.cx += w + self.gap
        self.rowh = max(self.rowh, h)
        return P

    def bottom(self):
        return self.cy + self.rowh
