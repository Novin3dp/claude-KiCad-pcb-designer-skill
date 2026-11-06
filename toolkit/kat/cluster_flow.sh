#!/bin/bash
# cluster_flow.sh IN.kicad_pcb TAG [cluster_place options...]
# cluster placement -> plane vias -> route only affected nets -> close -> refill + DRC.
set -e
IN="$1"; TAG="$2"; shift 2
K=$(dirname "$(readlink -f "$0")"); B="${IN%.kicad_pcb}"
ITER=${ITER:-14}; CR=${CLOSE_ROUNDS:-4}; CFG=${CFG:-cfg_v3.py}
ROUTER=${ROUTER:-../tools/ncroute_msla.py}; export KEEP=${KEEP:-'[AB]_*'}
side() { for e in kicad_pro kicad_dru net_areas.json; do [ -f "$B.$e" ] && cp "$B.$e" "$1.$e"; done; true; }
echo "== 1. cluster placement"
python3 "$K/cluster_place.py" "$IN" "${TAG}1.kicad_pcb" "$@" 2>&1 | grep -v "assert\\|swig"
side "${TAG}1"
RAILS=$(cat "${TAG}1.kicad_pcb.rails")
if [ -n "$RAILS" ]; then
  python3 "$K/plane_via.py" "${TAG}1.kicad_pcb" "${TAG}1v.kicad_pcb" "$RAILS" 1.6
  mv "${TAG}1v.kicad_pcb" "${TAG}1.kicad_pcb"
fi
RX=$(cat "${TAG}1.kicad_pcb.netrx")
[ "$RX" = '^()$' ] && { echo "nothing moved"; exit 0; }
echo "== 2. route affected nets: $RX"
NA_BOARD="${TAG}1.kicad_pcb" NETRX="$RX" RIPALL_AFTER=999 SHOVE_FROM=${SHOVE_FROM:-3} SHOVE_EVERY=${SHOVE_EVERY:-3} STAG=${STAG:-4} \
  python3 "$ROUTER" "$CFG" "${TAG}1.kicad_pcb" "${TAG}2.kicad_pcb" "$ITER" > "${TAG}2.log" 2>&1 || true
side "${TAG}2"; grep -a "^it\\|dropped\\|failed\\|written" "${TAG}2.log" | tail -5
echo "== 3. close"
bash "$K/close.sh" "${TAG}2.kicad_pcb" "${TAG}3.kicad_pcb" "$CR" 2>&1 | grep -E '^DRC|^open' || true
side "${TAG}3"
if [ -n "$RAILS" ]; then
  python3 "$K/plane_via.py" "${TAG}3.kicad_pcb" "${TAG}3v.kicad_pcb" "$RAILS" 2.0
  mv "${TAG}3v.kicad_pcb" "${TAG}3.kicad_pcb"
fi
echo "== 4. DRC"
kicad-cli pcb drc --refill-zones --format json -o "${TAG}3.drc.json" "${TAG}3.kicad_pcb" >/dev/null 2>&1
python3 -c "import json,collections;d=json.load(open('${TAG}3.drc.json'));print('${TAG}3',dict(collections.Counter(v['type'] for v in d['violations'] if v['severity']=='error')),'unconnected',len(d['unconnected_items']))"
