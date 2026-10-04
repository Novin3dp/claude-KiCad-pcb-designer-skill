#!/bin/bash
# Build the v5 release package: merged KiCad project, fab outputs, docs, tools, zip.
#   usage: release_v2.sh BOARD.kicad_pcb
set -e
B=$(readlink -f "$1")
cd /home/claude/h3-two-board
R=release/${REL:-H3_Klipper_SBC_v5}; K=$R/kicad; F=$R/fab
rm -rf $R; mkdir -p $K $F/gerber $R/docs $R/tools
cp sbc/kicad/*.kicad_sch sbc/kicad/klipper_h3.kicad_sym sbc/kicad/sym-lib-table sbc/kicad/fp-lib-table $K/
cp -r sbc/kicad/klipper_h3.pretty $K/
cp "$B" $K/klipper_h3_sbc.kicad_pcb
cp sbc/kicad/sbc.kicad_dru $K/klipper_h3_sbc.kicad_dru
python3 - <<'EOF'
import json
S = json.load(open('sbc/kicad/sbc.kicad_pro'))
Kp = json.load(open('sbc/kicad/klipper_h3_sbc.kicad_pro'))
S['erc'] = Kp['erc']
S.setdefault('schematic', {}).update(Kp.get('schematic', {}))
S['schematic']['top_level_sheets'] = [{'filename': 'klipper_h3_sbc.kicad_sch', 'name': 'klipper_h3_sbc', 'uuid': '00000000-0000-0000-0000-000000000000'}]
S['sheets'] = Kp.get('sheets', S.get('sheets'))
S['meta'] = {'filename': 'klipper_h3_sbc.kicad_pro', 'version': 3}
json.dump(S, open(''+__import__("os").environ.get("RELDIR","release/H3_Klipper_SBC_v5")+'/kicad/klipper_h3_sbc.kicad_pro', 'w'), indent=2)
EOF
cd $K
kicad-cli sch erc --severity-all -o ../fab/erc.rpt klipper_h3_sbc.kicad_sch | tail -1
kicad-cli pcb drc --schematic-parity --severity-all --format json -o ../fab/drc.json klipper_h3_sbc.kicad_pcb | tail -2
kicad-cli pcb export gerbers -l "F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,Edge.Cuts" \
  --subtract-soldermask -o ../fab/gerber/ klipper_h3_sbc.kicad_pcb | tail -1
kicad-cli pcb export drill --format excellon --excellon-separate-th --generate-map --map-format gerberx2 -o ../fab/gerber/ klipper_h3_sbc.kicad_pcb | tail -1
kicad-cli pcb export pos --format csv --units mm --side both --exclude-dnp -o ../fab/positions_all.csv klipper_h3_sbc.kicad_pcb | tail -1
kicad-cli sch export bom --fields 'Reference,Value,Footprint,MPN,LCSC,Note,${QUANTITY}' --labels 'Designator,Comment,Footprint,MPN,LCSC,Note,Qty' \
  --group-by 'Value,Footprint,LCSC' --ref-range-delimiter '-' --exclude-dnp -o ../fab/bom.csv klipper_h3_sbc.kicad_sch | tail -1
kicad-cli sch export bom --fields 'Value,Reference,Footprint,LCSC' --labels 'Comment,Designator,Footprint,LCSC Part #' \
  --group-by 'Value,Footprint,LCSC' --ref-range-delimiter '' --exclude-dnp -o ../fab/bom_jlcpcb_raw.csv klipper_h3_sbc.kicad_sch | tail -1
python3 - <<'PY'
import csv
rows = list(csv.DictReader(open('../fab/bom_jlcpcb_raw.csv')))
with open('../fab/bom_jlcpcb.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
    n = 0
    for r in rows:
        if r['Designator'].startswith('U9') or not r['LCSC Part #']:
            continue
        w.writerow([r['Comment'], r['Designator'], r['Footprint'].split(':')[-1], r['LCSC Part #']]); n += 1
print('JLC BOM lines', n)
PY
rm -f ../fab/bom_jlcpcb_raw.csv
kicad-cli sch export pdf -o ../fab/schematic.pdf klipper_h3_sbc.kicad_sch | tail -1
kicad-cli pcb render --side top --width 1600 --height 1060 --quality high -o ../docs/render_top.png klipper_h3_sbc.kicad_pcb >/dev/null 2>&1 || echo "render top failed"
kicad-cli pcb render --side bottom --width 1600 --height 1060 --quality high -o ../docs/render_bottom.png klipper_h3_sbc.kicad_pcb >/dev/null 2>&1 || echo "render bottom failed"
cd ../fab
python3 - <<'EOF'
import csv
rows = list(csv.DictReader(open('positions_all.csv')))
with open('cpl_jlcpcb.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    for r in rows:
        w.writerow([r['Ref'], r['PosX'] + 'mm', r['PosY'] + 'mm', 'Top' if r['Side'] == 'top' else 'Bottom', r['Rot']])
print('CPL rows', len(rows), ' U9 in CPL:', any(r['Ref'] == 'U9' for r in rows))
EOF
# ---- independent layout review (kicad_skills / eda_toolkit, Apache-2.0, vendored in tools/kicad_skills)
cd ../kicad
mkdir -p ../fab/review
PYTHONPATH=/home/claude/h3-two-board/tools/kicad_skills/src timeout 1200 python3 -m eda_toolkit.cli pcb review klipper_h3_sbc.kicad_pcb \
  --no-cli --collapse 6 -o ../fab/review/pcb_review.json --map ../fab/review/pcb_review_map.png >/dev/null 2>&1 || true
PYTHONPATH=/home/claude/h3-two-board/tools/kicad_skills/src timeout 1200 python3 -m eda_toolkit.cli pcb review klipper_h3_sbc.kicad_pcb \
  --no-cli --collapse 6 --text > ../fab/review/pcb_review.txt 2>/dev/null || true
PYTHONPATH=/home/claude/h3-two-board/tools/kicad_skills/src timeout 900 python3 -m eda_toolkit.cli sch review klipper_h3_sbc.kicad_sch \
  --text > ../fab/review/sch_review.txt 2>/dev/null || true
grep -m1 '^## summary' ../fab/review/pcb_review.txt | sed 's/^/pcb review: /'
grep -m1 '^## summary' ../fab/review/sch_review.txt | sed 's/^/sch review: /'
