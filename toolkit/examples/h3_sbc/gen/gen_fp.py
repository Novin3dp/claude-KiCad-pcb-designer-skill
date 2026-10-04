"""Generate the Allwinner H3 TFBGA-347 footprint (14 x 14 mm, 0.65 mm pitch, 21 x 21 grid)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'kicad', 'klipper_h3.pretty')
balls = json.load(open(os.path.join(HERE, 'h3_pins.json')))
ROWS = 'A B C D E F G H J K L M N P R T U V W Y AA'.split()
P = 0.65
pad = 0.30
L = []
L.append('(footprint "Allwinner_H3_TFBGA-347_14x14mm_P0.65mm" (version 20240108) (generator "klipper_h3_gen") (layer "F.Cu")')
L.append('  (descr "Allwinner H3 TFBGA-347, 14x14 mm body, 0.65 mm pitch, 21x21 grid (347 balls). NSMD 0.30 mm pads - verify against the H3 package drawing / your fab capability")')
L.append('  (tags "BGA 347 Allwinner H3")')
L.append('  (attr smd)')
L.append('  (property "Reference" "REF**" (at 0 -8.2 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))')
L.append('  (property "Value" "Allwinner_H3" (at 0 8.2 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))')
h = 7.0
for lay, w, e in (('F.Fab', 0.1, h), ('F.CrtSd', 0.05, h + 0.5)):
    lay = 'F.CrtYd' if lay == 'F.CrtSd' else lay
    L.append('  (fp_rect (start %.3f %.3f) (end %.3f %.3f) (stroke (width %.2f) (type solid)) (fill none) (layer "%s"))' % (-e, -e, e, e, w, lay))
# silk corners + pin 1 mark
s = h + 0.11
for (x, y, dx, dy) in ((-s, -s, 1, 1), (s, -s, -1, 1), (-s, s, 1, -1), (s, s, -1, -1)):
    L.append('  (fp_line (start %.3f %.3f) (end %.3f %.3f) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))' % (x, y, x + dx * 1.5, y))
    L.append('  (fp_line (start %.3f %.3f) (end %.3f %.3f) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))' % (x, y, x, y + dy * 1.5))
L.append('  (fp_circle (center %.3f %.3f) (end %.3f %.3f) (stroke (width 0.25) (type solid)) (fill solid) (layer "F.SilkS"))' % (-s - 0.6, -s - 0.6, -s - 0.45, -s - 0.6))
L.append('  (fp_text user "${REFERENCE}" (at 0 0 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))')
n = 0
for r, row in enumerate(ROWS):
    for c in range(1, 22):
        b = '%s%d' % (row, c)
        if b not in balls:
            continue
        x = (c - 11) * P
        y = (r - 10) * P
        L.append('  (pad "%s" smd circle (at %.3f %.3f) (size %.2f %.2f) (layers "F.Cu" "F.Paste" "F.Mask"))' % (b, x, y, pad, pad))
        n += 1
L.append(')')
assert n == 347, n
os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, 'Allwinner_H3_TFBGA-347_14x14mm_P0.65mm.kicad_mod'), 'w').write('\n'.join(L) + '\n')
print('pads', n)
